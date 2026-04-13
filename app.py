from __future__ import annotations

import asyncio, hashlib, html, json, logging, math, os, zlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

try:
    import pymorphy3
except ImportError:
    pymorphy3 = None

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = ImageDraw = None

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PLACES = DATA / "user_places.json"
GIFS = ROOT / "assets" / "weather"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
BTN_GEO = "Отправить геопозицию"
V_NOW, V_TODAY, V_TOMORROW, V_5, V_REFRESH = "now", "today", "tomorrow", "five", "refresh"
VIEWS = {V_NOW, V_TODAY, V_TOMORROW, V_5}
MORPH = pymorphy3.MorphAnalyzer() if pymorphy3 else None

CODES = {
    0: "ясно", 1: "преимущественно ясно", 2: "переменная облачность", 3: "пасмурно",
    45: "туман", 48: "изморозь и туман", 51: "слабая морось", 53: "морось", 55: "сильная морось",
    61: "слабый дождь", 63: "дождь", 65: "сильный дождь", 71: "слабый снег", 73: "снег",
    75: "сильный снег", 80: "слабый ливень", 81: "ливень", 82: "сильный ливень",
    85: "слабый снегопад", 86: "снегопад", 95: "гроза", 96: "гроза с градом", 99: "гроза с градом",
}
CITY = {
    "москва": "Москве", "санкт-петербург": "Санкт-Петербурге", "нижний новгород": "Нижнем Новгороде",
    "ростов-на-дону": "Ростове-на-Дону", "казань": "Казани", "сочи": "Сочи",
    "екатеринбург": "Екатеринбурге", "новосибирск": "Новосибирске",
}


def truthy(v: str | None) -> bool:
    return bool(v and v.strip().lower() in {"1", "true", "yes", "on"})


def num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def fmt(v: Any, d: int = 1) -> str:
    n = num(v)
    if n is None:
        return "—"
    r = round(n, d)
    return str(int(r)) if float(r).is_integer() else f"{r:.{d}f}".rstrip("0").rstrip(".")


def desc(code: Any) -> str:
    n = num(code)
    return CODES.get(int(n), "без описания") if n is not None else "без описания"


def emoji(text: str) -> str:
    t = text.lower()
    if "гроз" in t or "град" in t: return "⚡️"
    if "снег" in t: return "🧊"
    if any(x in t for x in ("дожд", "лив", "морось")): return "🫧"
    if "туман" in t: return "🪞"
    if "ясно" in t: return "🌞"
    if "облач" in t or "пасмур" in t: return "🪶"
    return "🛰️"


def theme(text: str, temp: float | None = None, wind: float | None = None) -> str:
    t = text.lower()
    if "гроз" in t or "град" in t: return "storm"
    if "снег" in t: return "snow"
    if any(x in t for x in ("дожд", "лив", "морось")): return "rain"
    if "туман" in t: return "fog"
    if wind is not None and wind >= 9: return "wind"
    if temp is not None and temp >= 26: return "heat"
    if "облач" in t or "пасмур" in t: return "cloud"
    return "sun"


def city_in(name: str) -> str:
    clean = " ".join(name.strip().split())
    if clean.lower() in CITY:
        return CITY[clean.lower()]
    if MORPH is None:
        return clean

    def one(w: str) -> str:
        if not any("а" <= c.lower() <= "я" or c.lower() == "ё" for c in w):
            return w
        inf = MORPH.parse(w)[0].inflect({"loct"})
        out = inf.word if inf else w
        return out.capitalize() if w[:1].isupper() else out

    return "-".join(" ".join(one(w) for w in p.split()) for p in clean.split("-"))


def read_places() -> dict[str, Any]:
    try:
        return json.loads(PLACES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_place(chat_id: int, q: dict[str, Any]) -> None:
    DATA.mkdir(exist_ok=True)
    data = read_places()
    data[str(chat_id)] = q
    PLACES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def saved_place(chat_id: int) -> dict[str, Any] | None:
    q = read_places().get(str(chat_id))
    return q if isinstance(q, dict) and "lat" in q and "lon" in q else None


def get_json(url: str, **params: Any) -> dict[str, Any]:
    r = requests.get(url, params=params, timeout=12)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError("BAD_RESPONSE")
    return data


def geocode(city: str) -> dict[str, Any]:
    data = get_json(GEOCODE, name=city, count=1, language="ru", format="json")
    items = data.get("results") or []
    if not items:
        raise ValueError("CITY_NOT_FOUND")
    x = items[0]
    return {"lat": float(x["latitude"]), "lon": float(x["longitude"]), "label": str(x.get("name") or city)}


def parse_time(raw: Any, offset: int) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone(timedelta(seconds=offset))) if dt.tzinfo is None else dt


def weather(q: dict[str, Any]) -> dict[str, Any]:
    data = get_json(
        FORECAST,
        latitude=q["lat"], longitude=q["lon"], timezone="auto", forecast_days=5,
        temperature_unit="celsius", wind_speed_unit="ms", precipitation_unit="mm",
        current="temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,pressure_msl,wind_speed_10m,visibility",
        hourly="temperature_2m,apparent_temperature,relative_humidity_2m,precipitation_probability,precipitation,weather_code,pressure_msl,wind_speed_10m,visibility",
    )
    off = int(data.get("utc_offset_seconds", 0) or 0)
    now = parse_time((data.get("current") or {}).get("time"), off) or datetime.now(timezone(timedelta(seconds=off)))
    h = data.get("hourly") or {}
    rows = []
    for i, raw in enumerate(h.get("time") or []):
        dt = parse_time(raw, off)
        if dt:
            rows.append({
                "dt": dt, "temp": num((h.get("temperature_2m") or [None])[i]), "feel": num((h.get("apparent_temperature") or [None])[i]),
                "pop": (num((h.get("precipitation_probability") or [0])[i]) or 0) / 100,
                "rain": num((h.get("precipitation") or [0])[i]) or 0, "wind": num((h.get("wind_speed_10m") or [0])[i]) or 0,
                "code": (h.get("weather_code") or [0])[i],
            })
    return {"q": q, "now": now, "current": data.get("current") or {}, "hours": rows}


def stats(rows: list[dict[str, Any]], current_temp: float | None = None) -> dict[str, Any]:
    temps = [r["temp"] for r in rows if r.get("temp") is not None]
    if current_temp is not None:
        temps.append(current_temp)
    return {
        "min": min(temps) if temps else None, "max": max(temps) if temps else None,
        "pop": max((r["pop"] for r in rows), default=0), "rain": sum(r["rain"] for r in rows),
        "wind": max((r["wind"] for r in rows), default=0),
    }


def groups(bundle: dict[str, Any]) -> dict[date, list[dict[str, Any]]]:
    out: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for r in bundle["hours"]:
        if r["dt"].date() >= bundle["now"].date():
            out[r["dt"].date()].append(r)
    return out


def advice(text: str, feel: float | None, st: dict[str, Any]) -> str:
    base = feel if feel is not None else ((st["min"] + st["max"]) / 2 if st["min"] is not None and st["max"] is not None else 12)
    if base <= -10: clothes = ["пуховик, шапка и обувь, которая не сдаётся на холоде", "самый тёплый слой, шарф и перчатки без геройства"]
    elif base <= 0: clothes = ["куртка, свитер и закрытая обувь, чтобы не ловить холод спиной", "пальто или куртка плюс плотный слой под низ"]
    elif base <= 8: clothes = ["лёгкая куртка, худи или ветровка поверх базы", "кофта, которую удобно расстегнуть по пути"]
    elif base <= 17: clothes = ["обычный городской комплект и лёгкий верх на вечер", "футболка с кофтой или тонкой курткой на всякий случай"]
    elif base <= 25: clothes = ["футболка и лёгкие брюки без лишнего утепления", "лёгкая одежда, в которой не станет душно после пары кварталов"]
    else: clothes = ["самая лёгкая одежда из дышащих тканей и вода рядом", "футболка, шорты или свободные брюки, плюс вода"]
    picked = clothes[zlib.adler32(f"{text}{base}{st['pop']}".encode()) % len(clothes)]
    extra = []
    if st["pop"] >= .65 or st["rain"] >= 1: extra.append("зонт или непромокаемый верх")
    elif st["pop"] >= .35: extra.append("компактный зонт")
    if "снег" in text.lower() or st["rain"] >= 1: extra.append("обувь поплотнее")
    if st["wind"] >= 8: extra.append("капюшон или шарф от ветра")
    if st["max"] and st["max"] >= 25: extra.append("воду")
    return f"🧵 Я бы оделся слоями: {picked}; ещё прихвати {', '.join(dict.fromkeys(extra))}." if extra else f"🧵 Я бы оделся слоями: {picked}, без лишнего груза."


def make_gif(kind: str) -> Path | None:
    if Image is None or ImageDraw is None:
        return None
    GIFS.mkdir(parents=True, exist_ok=True)
    path = GIFS / f"{kind}.gif"
    if path.is_file() and path.stat().st_size > 8000:
        return path
    top, bottom = {
        "sun": ((78, 179, 231), (230, 243, 213)), "cloud": ((112, 165, 196), (214, 228, 218)),
        "rain": ((72, 88, 118), (148, 171, 192)), "snow": ((150, 177, 204), (232, 242, 249)),
        "storm": ((45, 49, 78), (111, 112, 137)), "fog": ((158, 172, 177), (220, 226, 227)),
        "wind": ((96, 161, 195), (218, 235, 221)), "heat": ((252, 173, 83), (255, 232, 155)),
    }.get(kind, ((78, 179, 231), (230, 243, 213)))
    frames = []
    for f in range(14):
        img = Image.new("RGBA", (384, 216), top)
        d = ImageDraw.Draw(img, "RGBA")
        for y in range(216):
            k = y / 215
            c = tuple(round(top[i] * (1 - k) + bottom[i] * k) for i in range(3))
            d.line((0, y, 384, y), fill=c)
        phase = f / 14 * math.tau
        if kind in {"sun", "heat", "wind"}:
            x, y = 84 + math.sin(phase) * 4, 64 + math.cos(phase) * 3
            d.ellipse((x - 42, y - 42, x + 42, y + 42), fill=(255, 220, 86, 70))
            d.ellipse((x - 24, y - 24, x + 24, y + 24), fill=(255, 214, 62, 255))
        if kind in {"cloud", "rain", "snow", "storm", "fog", "wind"}:
            fill = (238, 243, 244, 225) if kind not in {"rain", "storm"} else (92, 108, 132, 235)
            for cx, cy, r in ((78, 88, 28), (112, 72, 34), (150, 88, 36), (206, 78, 27), (238, 94, 34)):
                d.ellipse((cx-r+math.sin(phase)*7, cy-r, cx+r+math.sin(phase)*7, cy+r), fill=fill)
            d.rounded_rectangle((48, 96, 280, 132), radius=18, fill=fill)
        d.polygon([(0,216),(0,166),(82,136),(168,154),(264,130),(384,158),(384,216)], fill=(59,121,88,255))
        if kind == "rain":
            for i in range(36):
                x = (i * 27 + f * 13) % 420 - 30; y = (i * 17 + f * 15) % 216
                d.line((x, y, x - 8, y + 22), fill=(126,209,255,220), width=3)
        if kind == "snow":
            for i in range(42):
                x = (i * 23 + f * 5) % 384; y = (i * 13 + f * 9) % 216; r = 2 + (i % 4 == 0)
                d.ellipse((x-r, y-r, x+r, y+r), fill=(255,255,255,235))
        if kind == "storm" and f % 7 in {3, 4}:
            d.rectangle((0,0,384,216), fill=(255,255,255,38))
            d.polygon([(226,62),(198,112),(222,110),(184,170),(266,92),(236,96)], fill=(255,236,108,255))
        if kind == "fog":
            for b in range(6):
                x = (f * 12 + b * 74) % 560 - 180
                d.rounded_rectangle((x, 64 + b * 22, x + 270, 80 + b * 22), radius=8, fill=(240,246,246,96))
        if kind == "wind":
            for b in range(7):
                x = (f * 20 + b * 60) % 500 - 100; y = 58 + b * 19
                pts = [(x + s * 30, y + math.sin((f + s + b) / 1.7) * 4) for s in range(9)]
                d.line(pts, fill=(236,247,255,185), width=4)
        if kind == "heat":
            for b in range(5):
                pts = [(24 + s * 32, 96 + b * 16 + math.sin((f + s + b) / 1.4) * 5) for s in range(12)]
                d.line(pts, fill=(255,255,255,145), width=3)
        frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=96))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=82, loop=0, disposal=2, optimize=False)
    return path


def report(bundle: dict[str, Any], view: str) -> tuple[str, Path | None]:
    cur, q, by_day = bundle["current"], bundle["q"], groups(bundle)
    city = html.escape(city_in(q["label"]))
    if view in {V_TODAY, V_TOMORROW}:
        days = sorted(by_day)
        rows = by_day[days[min(0 if view == V_TODAY else 1, len(days)-1)]] if days else []
        text = desc(max((r["code"] for r in rows), key=lambda c: sum(1 for x in rows if x["code"] == c), default=cur.get("weather_code")))
        st = stats(rows); title = "Сегодня" if view == V_TODAY else "Завтра"
        lines = [f"{emoji(text)} <b>В {city}</b>", f"🗓️ {title}", "", f"{emoji(text)} {html.escape(text.capitalize())}", f"🪜 Диапазон: {fmt(st['min'])}..{fmt(st['max'])}°C", f"🫧 Осадки: {round(st['pop']*100)}% / {fmt(st['rain'])} мм", f"🪁 Ветер: до {fmt(st['wind'])} м/с", "", advice(text, None, st)]
        return "\n".join(lines), make_gif(theme(text, st["max"], st["wind"]))
    if view == V_5:
        lines = [f"🪶 <b>В {city}</b>", "🗓️ Ближайшие 5 дней", ""]
        for i, day in enumerate(sorted(by_day)[:5]):
            rows = by_day[day]; st = stats(rows); text = desc(rows[0]["code"] if rows else cur.get("weather_code"))
            label = "Сегодня" if i == 0 else "Завтра" if i == 1 else day.strftime("%d.%m")
            lines.append(f"{label}: {fmt(st['min'])}..{fmt(st['max'])}°C {emoji(text)} {html.escape(text.capitalize())} · 🫧 {round(st['pop']*100)}%")
        lines += ["", "🧳 На неделе ориентируйся по дождю и ветру: они решают больше, чем сухие градусы."]
        return "\n".join(lines), make_gif("cloud")
    text = desc(cur.get("weather_code")); now_temp = num(cur.get("temperature_2m")); today = by_day.get(bundle["now"].date(), [])
    st = stats(today, now_temp); press = num(cur.get("pressure_msl")); press = round(press * .750062) if press else "—"
    lines = [f"{emoji(text)} <b>В {city}</b>", f"{emoji(text)} {html.escape(text.capitalize())}", "", f"🧊 Сейчас: {fmt(now_temp)}°C", f"🧭 Ощущается: {fmt(cur.get('apparent_temperature'))}°C", f"🪜 Сегодня: {fmt(st['min'])}..{fmt(st['max'])}°C", f"🍃 Ветер: {fmt(cur.get('wind_speed_10m'))} м/с", f"🪼 Влажность: {fmt(cur.get('relative_humidity_2m'),0)}%", f"🪨 Давление: {press} мм", f"🫧 Осадки: {round(st['pop']*100)}%", "", advice(text, num(cur.get('apparent_temperature')), st)]
    return "\n".join(lines), make_gif(theme(text, now_temp, num(cur.get("wind_speed_10m"))))


def keyboard(view: str) -> InlineKeyboardMarkup:
    mark = lambda text, v: f"• {text}" if v == view else text
    return InlineKeyboardMarkup([[InlineKeyboardButton(mark("Сейчас", V_NOW), callback_data=f"v:{V_NOW}"), InlineKeyboardButton(mark("Сегодня", V_TODAY), callback_data=f"v:{V_TODAY}"), InlineKeyboardButton(mark("Завтра", V_TOMORROW), callback_data=f"v:{V_TOMORROW}")], [InlineKeyboardButton(mark("5 дней", V_5), callback_data=f"v:{V_5}"), InlineKeyboardButton("Обновить", callback_data=f"v:{V_REFRESH}")]])


async def show(m: Message, q: dict[str, Any], view: str = V_NOW, edit: bool = False) -> None:
    b = await asyncio.to_thread(weather, q); save_place(m.chat_id, q)
    text, gif = await asyncio.to_thread(report, b, view)
    if edit:
        try:
            if m.caption is not None: await m.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard(view))
            else: await m.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=keyboard(view))
            return
        except BadRequest as e:
            if "message is not modified" not in str(e).lower(): log.warning("edit failed: %s", e)
    if gif:
        with gif.open("rb") as f:
            await m.reply_animation(animation=f, caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard(view))
    else:
        await m.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard(view))


def geo_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(BTN_GEO, request_location=True)]], resize_keyboard=True)


async def fail(m: Message, e: Exception) -> None:
    if isinstance(e, ValueError):
        await m.reply_text("🔎 Не нашёл такой город. Попробуй написать чуть точнее.", reply_markup=geo_keyboard())
    else:
        log.exception("weather failed")
        await m.reply_text("🌐 Не получается связаться с погодой. Попробуй чуть позже.", reply_markup=geo_keyboard())


async def start(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
    if u.effective_message:
        await u.effective_message.reply_text("👋 Привет! Напиши город, например Москва, и я пришлю погоду с GIF и живой подсказкой по одежде.", reply_markup=geo_keyboard())


async def help_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
    if u.effective_message:
        await u.effective_message.reply_text("Напиши город обычным сообщением или /weather Москва. Кнопки переключают прогноз.", reply_markup=geo_keyboard())


async def weather_cmd(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
    m = u.effective_message
    if not m: return
    try:
        q = await asyncio.to_thread(geocode, " ".join(c.args).strip()) if c.args else saved_place(m.chat_id)
        if not q:
            await m.reply_text("Напиши /weather Москва или просто Москва.", reply_markup=geo_keyboard()); return
        await show(m, q)
    except Exception as e:
        await fail(m, e)


async def text_city(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
    m = u.effective_message
    if not m or not m.text: return
    if m.text.strip() == BTN_GEO:
        await m.reply_text("📍 Нажми кнопку и отправь геопозицию, я покажу погоду рядом.", reply_markup=geo_keyboard()); return
    try:
        await show(m, await asyncio.to_thread(geocode, m.text.strip()))
    except Exception as e:
        await fail(m, e)


async def location(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
    m = u.effective_message
    if not m or not m.location: return
    await show(m, {"lat": m.location.latitude, "lon": m.location.longitude, "label": "вашем районе"})


async def cb(u: Update, c: ContextTypes.DEFAULT_TYPE) -> None:
    q = u.callback_query
    if not q or not q.message: return
    view = (q.data or "").removeprefix("v:")
    view = V_NOW if view == V_REFRESH else view
    if view not in VIEWS:
        await q.answer("Не понял эту кнопку.", show_alert=True); return
    place = saved_place(q.message.chat_id)
    if not place:
        await q.answer("Сначала напиши город.", show_alert=True); return
    await show(q.message, place, view, edit=True)
    await q.answer("Готово")


def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token.startswith("your_"):
        raise RuntimeError("MISSING_TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start)); app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("weather", weather_cmd)); app.add_handler(CommandHandler("location", help_cmd))
    app.add_handler(CallbackQueryHandler(cb)); app.add_handler(MessageHandler(filters.LOCATION, location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_city))
    base = os.getenv("WEBHOOK_URL", "").strip() or (f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN','').strip()}" if os.getenv("RAILWAY_PUBLIC_DOMAIN") else "")
    if truthy(os.getenv("USE_WEBHOOK")) and base:
        path = os.getenv("WEBHOOK_PATH", "").strip("/") or hashlib.sha256(token.encode()).hexdigest()[:24]
        app.run_webhook(listen="0.0.0.0", port=int(os.getenv("PORT", "8080")), url_path=path, webhook_url=f"{base.rstrip('/')}/{path}", drop_pending_updates=True)
    else:
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
