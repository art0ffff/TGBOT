from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

try:
    import pymorphy3
except ImportError:
    pymorphy3 = None

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 12
LOCATION_BUTTON_TEXT = "Отправить геопозицию"

VIEW_NOW = "now"
VIEW_TODAY = "today"
VIEW_TOMORROW = "tomorrow"
VIEW_FIVE_DAYS = "five_days"
VIEW_REFRESH = "refresh"
VALID_VIEWS = {VIEW_NOW, VIEW_TODAY, VIEW_TOMORROW, VIEW_FIVE_DAYS}

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
USER_PLACES_PATH = DATA_DIR / "user_places.json"
MORPH = pymorphy3.MorphAnalyzer() if pymorphy3 else None

WEATHER_CODES = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозь и туман",
    51: "слабая морось",
    53: "морось",
    55: "сильная морось",
    56: "ледяная морось",
    57: "ледяная морось",
    61: "слабый дождь",
    63: "дождь",
    65: "сильный дождь",
    66: "ледяной дождь",
    67: "ледяной дождь",
    71: "слабый снег",
    73: "снег",
    75: "сильный снег",
    77: "снежные зерна",
    80: "слабый ливень",
    81: "ливень",
    82: "сильный ливень",
    85: "слабый снегопад",
    86: "снегопад",
    95: "гроза",
    96: "гроза с градом",
    99: "сильная гроза с градом",
}
CITY_EXCEPTIONS = {
    "москва": "Москве",
    "санкт-петербург": "Санкт-Петербурге",
    "нижний новгород": "Нижнем Новгороде",
    "ростов-на-дону": "Ростове-на-Дону",
    "казань": "Казани",
    "сочи": "Сочи",
    "екатеринбург": "Екатеринбурге",
    "новосибирск": "Новосибирске",
}


@dataclass(frozen=True)
class WeatherQuery:
    latitude: float
    longitude: float
    label: str


@dataclass(frozen=True)
class HourEntry:
    dt: datetime
    temp: float | None
    feels_like: float | None
    humidity: float | None
    pressure: float | None
    wind: float | None
    visibility: float | None
    pop: float
    precipitation: float
    code: int | None


@dataclass(frozen=True)
class WeatherBundle:
    query: WeatherQuery
    current_time: datetime
    current: dict[str, Any]
    hours: list[HourEntry]


def is_truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("your_"):
        raise RuntimeError(f"MISSING_{name}")
    return value


def get_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def compact(value: Any, digits: int = 1) -> str:
    number = get_number(value)
    if number is None:
        return "—"
    rounded = round(number, digits)
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def condition_description(code: Any) -> str:
    number = get_number(code)
    if number is None:
        return "без описания"
    return WEATHER_CODES.get(int(number), "без описания")


def condition_emoji(description: str) -> str:
    text = description.lower()
    if any(word in text for word in ("гроза", "град")):
        return "⚡️"
    if "снег" in text:
        return "🧊"
    if any(word in text for word in ("дожд", "лив", "морось")):
        return "🫧"
    if "туман" in text:
        return "🪞"
    if "ясно" in text:
        return "🌞"
    if any(word in text for word in ("облач", "пасмур")):
        return "🪶"
    return "🛰️"


def has_cyrillic(value: str) -> bool:
    return any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in value)


def inflect_word(word: str) -> str:
    if MORPH is None or not has_cyrillic(word):
        return word
    parsed = MORPH.parse(word)[0]
    inflected = parsed.inflect({"loct"})
    if inflected is None:
        return word
    result = inflected.word
    if word.isupper():
        return result.upper()
    if word[:1].isupper():
        return result.capitalize()
    return result


def city_in(city: str) -> str:
    clean = " ".join(city.strip().split())
    exception = CITY_EXCEPTIONS.get(clean.lower())
    if exception:
        return exception
    return "-".join(" ".join(inflect_word(word) for word in part.split()) for part in clean.split("-"))


def request_json(url: str, **params: Any) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        raise ValueError("CITY_NOT_FOUND")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("BAD_WEATHER_RESPONSE")
    return data


def load_places() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(USER_PLACES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        logger.exception("Could not read saved places")
        return {}


def save_place(chat_id: int, query: WeatherQuery) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    places = load_places()
    places[str(chat_id)] = {"lat": query.latitude, "lon": query.longitude, "label": query.label}
    USER_PLACES_PATH.write_text(json.dumps(places, ensure_ascii=False, indent=2), encoding="utf-8")


def get_place(chat_id: int) -> WeatherQuery | None:
    place = load_places().get(str(chat_id))
    if not isinstance(place, dict):
        return None
    lat = get_number(place.get("lat"))
    lon = get_number(place.get("lon"))
    if lat is None or lon is None:
        return None
    return WeatherQuery(lat, lon, str(place.get("label") or "Мой город"))


def geocode_city(city: str) -> WeatherQuery:
    data = request_json(GEOCODE_URL, name=city, count=1, language="ru", format="json")
    results = data.get("results") or []
    if not results:
        raise ValueError("CITY_NOT_FOUND")
    item = results[0]
    return WeatherQuery(float(item["latitude"]), float(item["longitude"]), str(item.get("name") or city))


def parse_time(value: Any, offset_seconds: int) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(seconds=offset_seconds)))
    return parsed


def list_value(values: Any, index: int) -> Any:
    if isinstance(values, list) and index < len(values):
        return values[index]
    return None


def fetch_weather(query: WeatherQuery) -> WeatherBundle:
    data = request_json(
        FORECAST_URL,
        latitude=query.latitude,
        longitude=query.longitude,
        current=",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "pressure_msl",
            "wind_speed_10m",
            "wind_direction_10m",
            "visibility",
        ]),
        hourly=",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation_probability",
            "precipitation",
            "weather_code",
            "pressure_msl",
            "wind_speed_10m",
            "visibility",
        ]),
        forecast_days=5,
        temperature_unit="celsius",
        wind_speed_unit="ms",
        precipitation_unit="mm",
        timezone="auto",
    )
    offset = int(data.get("utc_offset_seconds", 0) or 0)
    current = data.get("current") or {}
    hourly = data.get("hourly") or {}
    current_time = parse_time(current.get("time"), offset) or datetime.now(timezone(timedelta(seconds=offset)))
    hours: list[HourEntry] = []
    times = hourly.get("time") or []
    for index, raw_time in enumerate(times if isinstance(times, list) else []):
        dt = parse_time(raw_time, offset)
        if dt is None:
            continue
        hours.append(
            HourEntry(
                dt=dt,
                temp=get_number(list_value(hourly.get("temperature_2m"), index)),
                feels_like=get_number(list_value(hourly.get("apparent_temperature"), index)),
                humidity=get_number(list_value(hourly.get("relative_humidity_2m"), index)),
                pressure=get_number(list_value(hourly.get("pressure_msl"), index)),
                wind=get_number(list_value(hourly.get("wind_speed_10m"), index)),
                visibility=get_number(list_value(hourly.get("visibility"), index)),
                pop=(get_number(list_value(hourly.get("precipitation_probability"), index)) or 0.0) / 100.0,
                precipitation=get_number(list_value(hourly.get("precipitation"), index)) or 0.0,
                code=int(get_number(list_value(hourly.get("weather_code"), index)) or 0),
            )
        )
    return WeatherBundle(query=query, current_time=current_time, current=current, hours=hours)


def location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(LOCATION_BUTTON_TEXT, request_location=True)]], resize_keyboard=True)


def weather_keyboard(view: str = VIEW_NOW) -> InlineKeyboardMarkup:
    def label(text: str, target: str) -> str:
        return f"• {text}" if target == view else text

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(label("Сейчас", VIEW_NOW), callback_data=f"v:{VIEW_NOW}"),
                InlineKeyboardButton(label("Сегодня", VIEW_TODAY), callback_data=f"v:{VIEW_TODAY}"),
                InlineKeyboardButton(label("Завтра", VIEW_TOMORROW), callback_data=f"v:{VIEW_TOMORROW}"),
            ],
            [
                InlineKeyboardButton(label("5 дней", VIEW_FIVE_DAYS), callback_data=f"v:{VIEW_FIVE_DAYS}"),
                InlineKeyboardButton("Обновить", callback_data=f"v:{VIEW_REFRESH}"),
            ],
        ]
    )


def day_groups(bundle: WeatherBundle) -> dict[date, list[HourEntry]]:
    groups: dict[date, list[HourEntry]] = defaultdict(list)
    for entry in bundle.hours:
        if entry.dt.date() >= bundle.current_time.date():
            groups[entry.dt.date()].append(entry)
    return groups


def dominant_description(entries: list[HourEntry], fallback: str) -> str:
    descriptions = [condition_description(entry.code) for entry in entries]
    return Counter(descriptions).most_common(1)[0][0] if descriptions else fallback


def day_stats(entries: list[HourEntry], current_temp: float | None = None) -> dict[str, Any]:
    temps = [entry.temp for entry in entries if entry.temp is not None]
    if current_temp is not None:
        temps.append(current_temp)
    return {
        "min": min(temps) if temps else None,
        "max": max(temps) if temps else None,
        "pop": max((entry.pop for entry in entries), default=0.0),
        "precipitation": sum(entry.precipitation for entry in entries),
        "wind": max((entry.wind or 0.0 for entry in entries), default=0.0),
    }


def temperature_bucket(value: float | None) -> str:
    if value is None:
        return "mild"
    if value <= -10:
        return "freezing"
    if value <= 0:
        return "cold"
    if value <= 8:
        return "cool"
    if value <= 17:
        return "mild"
    if value <= 25:
        return "warm"
    return "hot"


def friendly_advice(description: str, feels_like: float | None, min_temp: float | None, max_temp: float | None, pop: float, precipitation: float, wind: float | None) -> str:
    base_temp = feels_like
    if base_temp is None and min_temp is not None and max_temp is not None:
        base_temp = (min_temp + max_temp) / 2
    bucket = temperature_bucket(base_temp)
    variants = {
        "freezing": "пуховик, шапка и обувь, которая не сдаётся на холоде",
        "cold": "куртка, свитер и закрытая обувь, чтобы не ловить холод спиной",
        "cool": "лёгкая куртка, худи или ветровка поверх базы",
        "mild": "обычный городской комплект и лёгкий верх на вечер",
        "warm": "футболка и лёгкие брюки без лишнего утепления",
        "hot": "самая лёгкая одежда из дышащих тканей и вода рядом",
    }
    extras: list[str] = []
    lowered = description.lower()
    if pop >= 0.65 or precipitation >= 1.0:
        extras.append("зонт или непромокаемый верх")
    elif pop >= 0.35:
        extras.append("компактный зонт на всякий случай")
    if "снег" in lowered or precipitation >= 1.0:
        extras.append("обувь поплотнее")
    if (wind or 0.0) >= 8:
        extras.append("капюшон или шарф от ветра")
    if (max_temp or 0.0) >= 25:
        extras.append("воду")
    if extras:
        return f"🧵 Я бы оделся слоями: {variants[bucket]}; ещё прихвати {', '.join(dict.fromkeys(extras))}."
    return f"🧵 Я бы оделся слоями: {variants[bucket]}, без лишнего груза."


def current_report(bundle: WeatherBundle) -> str:
    current = bundle.current
    city = html.escape(city_in(bundle.query.label))
    description = condition_description(current.get("weather_code"))
    current_temp = get_number(current.get("temperature_2m"))
    feels = get_number(current.get("apparent_temperature"))
    today_entries = day_groups(bundle).get(bundle.current_time.date(), [])
    stats = day_stats(today_entries, current_temp)
    later = next((entry for entry in today_entries if entry.dt >= bundle.current_time + timedelta(hours=2)), None)
    advice = friendly_advice(description, feels, stats["min"], stats["max"], stats["pop"], stats["precipitation"], stats["wind"])
    pressure = get_number(current.get("pressure_msl"))
    pressure_mmhg = round(pressure * 0.750062) if pressure is not None else "—"
    lines = [
        f"{condition_emoji(description)} <b>В {city}</b>",
        f"{condition_emoji(description)} {html.escape(description.capitalize())}",
        "",
        f"🧊 Сейчас: {compact(current_temp)}°C",
        f"🧭 Ощущается: {compact(feels)}°C",
        f"🪜 Сегодня: {compact(stats['min'])}..{compact(stats['max'])}°C",
        f"🍃 Ветер: {compact(current.get('wind_speed_10m'))} м/с",
        f"🪼 Влажность: {compact(current.get('relative_humidity_2m'), 0)}%",
        f"🪨 Давление: {pressure_mmhg} мм",
        f"🪟 Видимость: {compact((get_number(current.get('visibility')) or 0) / 1000)} км",
        f"🫧 Осадки: {round(stats['pop'] * 100)}%",
    ]
    if later is not None and later.temp is not None:
        lines.append(f"🕯️ К {later.dt.strftime('%H:%M')}: {compact(later.temp)}°C")
    lines.extend(["", advice])
    return "\n".join(lines)


def day_report(bundle: WeatherBundle, offset: int) -> str:
    groups = day_groups(bundle)
    days = sorted(groups)
    if not days:
        return current_report(bundle)
    target = days[min(offset, len(days) - 1)]
    entries = groups[target]
    description = dominant_description(entries, condition_description(bundle.current.get("weather_code")))
    stats = day_stats(entries)
    city = html.escape(city_in(bundle.query.label))
    title = "Сегодня" if offset == 0 else "Завтра"
    timeline = " · ".join(f"{entry.dt.strftime('%H:%M')} {compact(entry.temp)}°C" for entry in entries[:4])
    advice = friendly_advice(description, None, stats["min"], stats["max"], stats["pop"], stats["precipitation"], stats["wind"])
    lines = [
        f"{condition_emoji(description)} <b>В {city}</b>",
        f"🗓️ {title}",
        "",
        f"{condition_emoji(description)} {html.escape(description.capitalize())}",
        f"🪜 Диапазон: {compact(stats['min'])}..{compact(stats['max'])}°C",
        f"🫧 Осадки: {round(stats['pop'] * 100)}% / {compact(stats['precipitation'])} мм",
        f"🪁 Ветер: до {compact(stats['wind'])} м/с",
    ]
    if timeline:
        lines.append(f"🕯️ По часам: {html.escape(timeline)}")
    lines.extend(["", advice])
    return "\n".join(lines)


def five_day_report(bundle: WeatherBundle) -> str:
    groups = day_groups(bundle)
    days = sorted(groups)[:5]
    city = html.escape(city_in(bundle.query.label))
    lines = [f"🪶 <b>В {city}</b>", "🗓️ Ближайшие 5 дней", ""]
    rainy = 0
    windy = 0
    for index, day in enumerate(days):
        entries = groups[day]
        description = dominant_description(entries, "без описания")
        stats = day_stats(entries)
        label = "Сегодня" if index == 0 else "Завтра" if index == 1 else day.strftime("%a %d.%m")
        if stats["pop"] >= 0.45:
            rainy += 1
        if stats["wind"] >= 8:
            windy += 1
        lines.append(f"{label}: {compact(stats['min'])}..{compact(stats['max'])}°C {condition_emoji(description)} {html.escape(description.capitalize())} · 🫧 {round(stats['pop'] * 100)}%")
    useful = []
    if rainy:
        useful.append("зонт")
    if windy:
        useful.append("ветровка")
    lines.extend(["", f"🧳 На неделе чаще выручат: {', '.join(useful)}." if useful else "🧳 Неделя выглядит спокойной: без тяжёлого арсенала."])
    return "\n".join(lines)


def build_report(bundle: WeatherBundle, view: str) -> str:
    if view == VIEW_TODAY:
        return day_report(bundle, 0)
    if view == VIEW_TOMORROW:
        return day_report(bundle, 1)
    if view == VIEW_FIVE_DAYS:
        return five_day_report(bundle)
    return current_report(bundle)


async def show_weather(message: Message, query: WeatherQuery, view: str = VIEW_NOW, edit: bool = False) -> None:
    bundle = await asyncio.to_thread(fetch_weather, query)
    save_place(message.chat_id, query)
    text = build_report(bundle, view)
    markup = weather_keyboard(view)
    if edit:
        try:
            if message.caption is not None:
                await message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
            else:
                await message.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)
            return
        except BadRequest as error:
            if "message is not modified" not in str(error).lower():
                logger.warning("Could not edit weather message: %s", error)
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def reply_weather_error(message: Message, error: Exception) -> None:
    if isinstance(error, ValueError) and str(error) == "CITY_NOT_FOUND":
        await message.reply_text("🔎 Не нашёл такой город. Попробуй написать чуть точнее.", reply_markup=location_keyboard())
        return
    if isinstance(error, requests.RequestException):
        logger.exception("Weather request failed")
        await message.reply_text("🌐 Не получается связаться с погодой. Попробуй чуть позже.", reply_markup=location_keyboard())
        return
    logger.exception("Unexpected weather error")
    await message.reply_text("⚠️ Что-то пошло не так. Попробуй ещё раз.", reply_markup=location_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "👋 Привет! Напиши город, например Москва, и я пришлю живую карточку погоды: что надеть, что захватить и прогноз по кнопкам.",
        reply_markup=location_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "Напиши город обычным сообщением или используй /weather Москва.\n"
        "Кнопки переключают Сейчас, Сегодня, Завтра, 5 дней и Обновить.\n"
        "/location попросит геопозицию.",
        reply_markup=location_keyboard(),
    )


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    try:
        if context.args:
            query = await asyncio.to_thread(geocode_city, " ".join(context.args).strip())
        else:
            query = get_place(message.chat_id)
            if query is None:
                await message.reply_text("Напиши /weather Москва или просто Москва.", reply_markup=location_keyboard())
                return
        await show_weather(message, query)
    except Exception as error:
        await reply_weather_error(message, error)


async def text_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return
    city = message.text.strip()
    if city == LOCATION_BUTTON_TEXT:
        await message.reply_text("📍 Нажми кнопку и отправь геопозицию, я покажу погоду рядом.", reply_markup=location_keyboard())
        return
    try:
        query = await asyncio.to_thread(geocode_city, city)
        await show_weather(message, query)
    except Exception as error:
        await reply_weather_error(message, error)


async def location_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.location is None:
        return
    query = WeatherQuery(message.location.latitude, message.location.longitude, "вашем районе")
    try:
        await show_weather(message, query)
    except Exception as error:
        await reply_weather_error(message, error)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return
    view = (query.data or "").removeprefix("v:")
    edit = True
    if view == VIEW_REFRESH:
        saved_view = VIEW_NOW
    elif view in VALID_VIEWS:
        saved_view = view
    else:
        await query.answer("Не понял эту кнопку.", show_alert=True)
        return
    place = get_place(query.message.chat_id)
    if place is None:
        await query.answer("Сначала напиши город или отправь геопозицию.", show_alert=True)
        return
    try:
        await show_weather(query.message, place, view=saved_view, edit=edit)
    except Exception as error:
        logger.exception("Callback update failed")
        await query.answer("Не удалось обновить прогноз.", show_alert=True)
        return
    await query.answer("Готово")


def main() -> None:
    load_dotenv()
    token = get_required_env("TELEGRAM_BOT_TOKEN")
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_command))
    application.add_handler(CommandHandler("location", help_command))
    application.add_handler(CallbackQueryHandler(callback))
    application.add_handler(MessageHandler(filters.LOCATION, location_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_city))

    webhook_base_url = os.getenv("WEBHOOK_URL", "").strip()
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if not webhook_base_url and railway_domain:
        webhook_base_url = f"https://{railway_domain}"
    use_webhook = is_truthy(os.getenv("USE_WEBHOOK")) or bool(webhook_base_url)
    if use_webhook:
        if not webhook_base_url:
            raise RuntimeError("Для webhook нужен WEBHOOK_URL или RAILWAY_PUBLIC_DOMAIN")
        path = os.getenv("WEBHOOK_PATH", "").strip("/") or hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
        application.run_webhook(
            listen=os.getenv("WEBHOOK_LISTEN", "0.0.0.0"),
            port=int(os.getenv("PORT", "8080")),
            url_path=path,
            webhook_url=f"{webhook_base_url.rstrip('/')}/{path}",
            secret_token=os.getenv("WEBHOOK_SECRET_TOKEN") or None,
            drop_pending_updates=True,
        )
        return
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
