from __future__ import annotations

import asyncio
import html
import json
import logging
import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None
    ImageDraw = None


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
GEOCODING_URL = "https://api.openweathermap.org/geo/1.0/direct"
LOCATION_BUTTON_TEXT = "Отправить геопозицию"
REQUEST_TIMEOUT = 12

VIEW_NOW = "now"
VIEW_TODAY = "today"
VIEW_TOMORROW = "tomorrow"
VIEW_FIVE_DAYS = "five"
VIEW_REFRESH = "refresh"
VIEW_MY_CITY = "my"
VALID_VIEWS = {VIEW_NOW, VIEW_TODAY, VIEW_TOMORROW, VIEW_FIVE_DAYS}

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
USER_PLACES_PATH = DATA_DIR / "user_places.json"
WEATHER_GIF_DIR = BASE_DIR / "assets" / "weather"
WIDTH = 320
HEIGHT = 192
FRAME_COUNT = 16
DURATION_MS = 82

WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
USER_PLACES: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class DayBlock:
    day: date
    label: str
    entries: list[dict[str, Any]]
    min_temp: float | None
    max_temp: float | None
    description: str
    precipitation_chance: float
    precipitation_volume: float
    max_wind: float | None


class MissingSettingsError(RuntimeError):
    pass


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("your_"):
        raise MissingSettingsError(name)
    return value


def load_user_places() -> None:
    global USER_PLACES
    try:
        data = json.loads(USER_PLACES_PATH.read_text(encoding="utf-8"))
        USER_PLACES = data if isinstance(data, dict) else {}
    except FileNotFoundError:
        USER_PLACES = {}
    except Exception:
        logger.exception("Could not load saved user places")
        USER_PLACES = {}


def save_user_places() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        USER_PLACES_PATH.write_text(
            json.dumps(USER_PLACES, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        logger.exception("Could not save user places")


def get_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def store_user_place(chat_id: int, bundle: dict[str, Any]) -> None:
    USER_PLACES[str(chat_id)] = {
        "label": bundle.get("label") or "Мой город",
        "lat": bundle.get("lat"),
        "lon": bundle.get("lon"),
    }
    save_user_places()


def get_user_place(chat_id: int) -> dict[str, Any] | None:
    place = USER_PLACES.get(str(chat_id))
    if not isinstance(place, dict):
        return None
    if get_number(place.get("lat")) is None or get_number(place.get("lon")) is None:
        return None
    return place


def location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(LOCATION_BUTTON_TEXT, request_location=True)]],
        resize_keyboard=True,
    )


def weather_keyboard(active_view: str = VIEW_NOW) -> InlineKeyboardMarkup:
    def label(text: str, view: str) -> str:
        return f"* {text}" if active_view == view else text

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(label("Сейчас", VIEW_NOW), callback_data=f"w:{VIEW_NOW}"),
                InlineKeyboardButton(label("Сегодня", VIEW_TODAY), callback_data=f"w:{VIEW_TODAY}"),
                InlineKeyboardButton(label("Завтра", VIEW_TOMORROW), callback_data=f"w:{VIEW_TOMORROW}"),
            ],
            [
                InlineKeyboardButton(label("5 дней", VIEW_FIVE_DAYS), callback_data=f"w:{VIEW_FIVE_DAYS}"),
                InlineKeyboardButton("Обновить", callback_data=f"w:{VIEW_REFRESH}"),
            ],
            [InlineKeyboardButton("Мой город", callback_data=f"w:{VIEW_MY_CITY}")],
        ]
    )


def format_number(value: Any, digits: int = 0) -> str:
    number = get_number(value)
    if number is None:
        return "-"
    if digits == 0:
        return str(round(number))
    rounded = round(number, digits)
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def weather_description(data: dict[str, Any]) -> str:
    weather = data.get("weather") or [{}]
    return str(weather[0].get("description") or "без описания").strip().lower()


def condition_label(description: str) -> str:
    return description.capitalize() if description else "Без описания"


def request_json(url: str, **params: Any) -> dict[str, Any] | list[dict[str, Any]]:
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        raise LookupError("CITY_NOT_FOUND")
    if response.status_code == 401:
        raise PermissionError("OPENWEATHER_API_KEY")
    response.raise_for_status()
    return response.json()


def fetch_bundle_by_city(city: str) -> dict[str, Any]:
    api_key = get_required_env("OPENWEATHER_API_KEY")
    locations = request_json(GEOCODING_URL, q=city, limit=1, appid=api_key)
    if not isinstance(locations, list) or not locations:
        raise LookupError("CITY_NOT_FOUND")

    location = locations[0]
    local_names = location.get("local_names") or {}
    label = local_names.get("ru") or location.get("name") or city
    return fetch_bundle_by_coordinates(float(location["lat"]), float(location["lon"]), label=label)


def fetch_bundle_by_coordinates(latitude: float, longitude: float, *, label: str | None = None) -> dict[str, Any]:
    api_key = get_required_env("OPENWEATHER_API_KEY")
    current = request_json(
        CURRENT_WEATHER_URL,
        lat=latitude,
        lon=longitude,
        appid=api_key,
        units="metric",
        lang="ru",
    )
    forecast = request_json(
        FORECAST_URL,
        lat=latitude,
        lon=longitude,
        appid=api_key,
        units="metric",
        lang="ru",
    )
    if not isinstance(current, dict) or not isinstance(forecast, dict):
        raise LookupError("WEATHER_NOT_FOUND")

    forecast_city = forecast.get("city") or {}
    resolved_label = label or current.get("name") or forecast_city.get("name") or "Мой город"
    return {"current": current, "forecast": forecast, "label": resolved_label, "lat": latitude, "lon": longitude}


def get_timezone_shift(bundle: dict[str, Any]) -> int:
    current = bundle["current"]
    forecast = bundle["forecast"]
    return int(current.get("timezone", forecast.get("city", {}).get("timezone", 0)) or 0)


def local_datetime(timestamp: Any, bundle: dict[str, Any]) -> datetime | None:
    unix_time = get_number(timestamp)
    if unix_time is None:
        return None
    return datetime.fromtimestamp(unix_time, tz=timezone(timedelta(seconds=get_timezone_shift(bundle))))


def current_local_date(bundle: dict[str, Any]) -> date:
    current_dt = local_datetime(bundle["current"].get("dt"), bundle)
    if current_dt is not None:
        return current_dt.date()
    return datetime.now(tz=timezone(timedelta(seconds=get_timezone_shift(bundle)))).date()


def precipitation_volume(entry: dict[str, Any]) -> float:
    total = 0.0
    for key in ("rain", "snow"):
        block = entry.get(key) or {}
        if isinstance(block, dict):
            for value in block.values():
                number = get_number(value)
                if number is not None:
                    total += number
    return total


def dominant_description(entries: list[dict[str, Any]], fallback: str) -> str:
    descriptions = [weather_description(entry) for entry in entries if weather_description(entry)]
    if not descriptions:
        return fallback
    return Counter(descriptions).most_common(1)[0][0]


def build_daily_blocks(bundle: dict[str, Any], limit: int = 5) -> list[DayBlock]:
    forecast = bundle["forecast"]
    start_date = current_local_date(bundle)
    groups: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for entry in forecast.get("list", []):
        if not isinstance(entry, dict):
            continue
        entry_dt = local_datetime(entry.get("dt"), bundle)
        if entry_dt is None or entry_dt.date() < start_date:
            continue
        groups[entry_dt.date()].append(entry)

    blocks: list[DayBlock] = []
    for day in sorted(groups)[:limit]:
        entries = groups[day]
        temps = [
            number
            for number in (get_number(entry.get("main", {}).get("temp")) for entry in entries)
            if number is not None
        ]
        if day == start_date:
            current_temp = get_number(bundle["current"].get("main", {}).get("temp"))
            if current_temp is not None:
                temps.append(current_temp)

        winds = [
            number
            for number in (get_number(entry.get("wind", {}).get("speed")) for entry in entries)
            if number is not None
        ]
        pop = max((get_number(entry.get("pop")) or 0.0 for entry in entries), default=0.0)
        volume = sum(precipitation_volume(entry) for entry in entries)
        description = dominant_description(entries, weather_description(bundle["current"]))
        blocks.append(
            DayBlock(
                day=day,
                label=f"{WEEKDAYS[day.weekday()]} {day.strftime('%d.%m')}",
                entries=entries,
                min_temp=min(temps) if temps else None,
                max_temp=max(temps) if temps else None,
                description=description,
                precipitation_chance=pop,
                precipitation_volume=volume,
                max_wind=max(winds) if winds else None,
            )
        )
    return blocks


def entries_next_hours(bundle: dict[str, Any], hours: int = 12) -> list[dict[str, Any]]:
    current_dt = local_datetime(bundle["current"].get("dt"), bundle)
    if current_dt is None:
        return list(bundle["forecast"].get("list", [])[:4])
    end_dt = current_dt + timedelta(hours=hours)
    entries: list[dict[str, Any]] = []
    for entry in bundle["forecast"].get("list", []):
        entry_dt = local_datetime(entry.get("dt"), bundle)
        if entry_dt is not None and current_dt <= entry_dt <= end_dt:
            entries.append(entry)
    return entries


def short_condition(description: str) -> str:
    lowered = description.lower()
    if "гроза" in lowered:
        return "гроза"
    if "снег" in lowered:
        return "снег"
    if any(word in lowered for word in ("дожд", "лив", "морось")):
        return "дождь"
    if any(word in lowered for word in ("туман", "дым", "мгла")):
        return "туман"
    if "ясно" in lowered:
        return "ясно"
    if "обла" in lowered or "пасмур" in lowered:
        return "облачно"
    return lowered[:14]


def hourly_timeline(entries: list[dict[str, Any]], bundle: dict[str, Any], points: int = 4) -> str:
    if not entries:
        return ""
    items: list[str] = []
    for entry in entries[:points]:
        entry_dt = local_datetime(entry.get("dt"), bundle)
        time_label = entry_dt.strftime("%H:%M") if entry_dt is not None else "--:--"
        temp = format_number(entry.get("main", {}).get("temp"), 0)
        items.append(f"{time_label} {temp}C {short_condition(weather_description(entry))}")
    return " | ".join(items)


def classify_theme_from_weather(
    data: dict[str, Any],
    *,
    precipitation_chance: float = 0.0,
    max_wind: float = 0.0,
    max_temp: float | None = None,
) -> str:
    weather = data.get("weather") or [{}]
    weather_id = int(weather[0].get("id") or 0)
    temp = max_temp if max_temp is not None else (get_number(data.get("main", {}).get("temp")) or 0.0)
    description = weather_description(data)
    if 200 <= weather_id < 300 or "гроза" in description:
        return "storm"
    if 600 <= weather_id < 700 or "снег" in description:
        return "snow"
    if 300 <= weather_id < 600 or precipitation_chance >= 0.55:
        return "rain"
    if 700 <= weather_id < 800:
        return "fog"
    if temp >= 30:
        return "heat"
    if max_wind >= 10 or (get_number(data.get("wind", {}).get("speed")) or 0.0) >= 10:
        return "wind"
    if weather_id == 800:
        return "sun"
    return "cloud"


def classify_weather_period(bundle: dict[str, Any]) -> str:
    current = bundle["current"]
    timestamp = int(current.get("dt") or 0)
    system = current.get("sys") or {}
    sunrise = int(system.get("sunrise") or 0)
    sunset = int(system.get("sunset") or 0)
    if sunrise and sunset and sunrise <= timestamp <= sunset:
        return "day"
    return "night"


def temperature_bucket(temp: float | None) -> str:
    if temp is None:
        return "mild"
    if temp <= -15:
        return "freezing"
    if temp <= -5:
        return "very_cold"
    if temp <= 5:
        return "cold"
    if temp <= 14:
        return "cool"
    if temp <= 22:
        return "mild"
    if temp <= 29:
        return "warm"
    return "hot"


def outfit_advice(
    *,
    current: dict[str, Any] | None,
    description: str,
    feels_like: float | None,
    min_temp: float | None,
    max_temp: float | None,
    precipitation_chance: float,
    precipitation_volume: float,
    max_wind: float | None,
) -> list[str]:
    base_temp = feels_like
    if base_temp is None and min_temp is not None and max_temp is not None:
        base_temp = (min_temp + max_temp) / 2
    if base_temp is None and current is not None:
        base_temp = get_number(current.get("main", {}).get("temp"))

    bucket = temperature_bucket(base_temp)
    wind = max_wind or (get_number((current or {}).get("wind", {}).get("speed")) or 0.0)
    swing = (max_temp - min_temp) if max_temp is not None and min_temp is not None else 0.0
    lowered = description.lower()

    clothing_by_bucket = {
        "freezing": "пуховик, шапка, шарф, перчатки и теплая обувь",
        "very_cold": "теплая куртка, шапка и закрытая обувь",
        "cold": "куртка, свитер или плотная кофта",
        "cool": "легкая куртка, худи или ветровка",
        "mild": "обычная одежда и легкий верх на всякий случай",
        "warm": "футболка, легкие брюки или джинсы",
        "hot": "дышащая легкая одежда, вода и головной убор",
    }
    details = [f"Одежда: {clothing_by_bucket[bucket]}."]
    if swing >= 8:
        details.append("Лучше одеться слоями: день заметно меняется по температуре.")
    if precipitation_chance >= 0.65 or precipitation_volume >= 1.0:
        details.append("Зонт или дождевик лучше взять обязательно.")
    elif precipitation_chance >= 0.35 or any(word in lowered for word in ("дожд", "лив", "морось")):
        details.append("Зонт лучше держать под рукой.")
    if "снег" in lowered:
        details.append("Обувь лучше выбрать непромокаемую и с теплой подошвой.")
    if wind >= 10:
        details.append("Из-за ветра пригодится непродуваемый верх.")
    elif wind >= 7:
        details.append("На открытых местах может продувать.")
    if (max_temp or 0.0) >= 28:
        details.append("Возьми воду, очки или кепку.")
    return details[:4]


def build_now_report(bundle: dict[str, Any]) -> str:
    current = bundle["current"]
    main = current.get("main") or {}
    wind = current.get("wind") or {}
    blocks = build_daily_blocks(bundle, limit=2)
    today = blocks[0] if blocks else None
    next_entries = entries_next_hours(bundle, hours=12)
    next_pop = max((get_number(entry.get("pop")) or 0.0 for entry in next_entries), default=0.0)
    next_volume = sum(precipitation_volume(entry) for entry in next_entries)
    max_wind = max(
        (get_number(entry.get("wind", {}).get("speed")) or 0.0 for entry in next_entries),
        default=get_number(wind.get("speed")) or 0.0,
    )
    description = weather_description(current)
    advice = outfit_advice(
        current=current,
        description=description,
        feels_like=get_number(main.get("feels_like")),
        min_temp=today.min_temp if today else get_number(main.get("temp")),
        max_temp=today.max_temp if today else get_number(main.get("temp")),
        precipitation_chance=max(next_pop, today.precipitation_chance if today else 0.0),
        precipitation_volume=next_volume,
        max_wind=max_wind,
    )

    pressure = get_number(main.get("pressure"))
    pressure_mmhg = round(pressure * 0.750062) if pressure is not None else "-"
    place = html.escape(str(bundle.get("label") or current.get("name") or "Мой город"))
    timeline = hourly_timeline(next_entries, bundle, points=4)
    lines = [
        f"<b>{place}</b>",
        html.escape(condition_label(description)),
        "",
        f"Сейчас: {format_number(main.get('temp'), 1)} C",
        f"Ощущается: {format_number(main.get('feels_like'), 1)} C",
    ]
    if today is not None:
        lines.append(f"Сегодня: {format_number(today.min_temp, 1)}..{format_number(today.max_temp, 1)} C")
    lines.extend(
        [
            f"Ветер: {format_number(wind.get('speed'), 1)} м/с",
            f"Влажность: {format_number(main.get('humidity'))}%",
            f"Давление: {pressure_mmhg} мм",
            f"Осадки за 12ч: {round(max(next_pop, 0.0) * 100)}%",
        ]
    )
    if timeline:
        lines.append(f"Ближайшие часы: {html.escape(timeline)}")
    lines.extend(["", "<b>Совет</b>", *[html.escape(line) for line in advice]])
    return "\n".join(lines)


def build_day_report(bundle: dict[str, Any], index: int) -> str:
    blocks = build_daily_blocks(bundle, limit=5)
    if not blocks:
        return build_now_report(bundle)
    block = blocks[min(index, len(blocks) - 1)]
    title = "Сегодня" if index == 0 else "Завтра"
    place = html.escape(str(bundle.get("label") or "Мой город"))
    timeline = hourly_timeline(block.entries, bundle, points=5)
    advice = outfit_advice(
        current=None,
        description=block.description,
        feels_like=None,
        min_temp=block.min_temp,
        max_temp=block.max_temp,
        precipitation_chance=block.precipitation_chance,
        precipitation_volume=block.precipitation_volume,
        max_wind=block.max_wind,
    )
    lines = [
        f"<b>{place}</b>",
        f"{title}, {block.label}",
        "",
        html.escape(condition_label(block.description)),
        f"Температура: {format_number(block.min_temp, 1)}..{format_number(block.max_temp, 1)} C",
        f"Осадки: {round(block.precipitation_chance * 100)}%, {format_number(block.precipitation_volume, 1)} мм",
        f"Ветер: до {format_number(block.max_wind, 1)} м/с",
    ]
    if timeline:
        lines.append(f"По часам: {html.escape(timeline)}")
    lines.extend(["", "<b>Совет</b>", *[html.escape(line) for line in advice]])
    return "\n".join(lines)


def build_five_days_report(bundle: dict[str, Any]) -> str:
    blocks = build_daily_blocks(bundle, limit=5)
    if not blocks:
        return build_now_report(bundle)
    place = html.escape(str(bundle.get("label") or "Мой город"))
    lines = [f"<b>{place}</b>", "Прогноз на 5 дней", ""]
    rainy_days = 0
    windy_days = 0
    for block in blocks[:5]:
        if block.precipitation_chance >= 0.45:
            rainy_days += 1
        if (block.max_wind or 0.0) >= 10:
            windy_days += 1
        lines.append(
            f"{block.label}: {format_number(block.min_temp, 0)}..{format_number(block.max_temp, 0)} C, "
            f"{html.escape(short_condition(block.description))}, дождь {round(block.precipitation_chance * 100)}%"
        )
    summary: list[str] = []
    if rainy_days:
        summary.append("зонт")
    if windy_days:
        summary.append("ветровка")
    hottest = max((block.max_temp or -99.0 for block in blocks), default=-99.0)
    if hottest >= 28:
        summary.append("вода")
    if summary:
        lines.extend(["", f"На неделе пригодится: {', '.join(dict.fromkeys(summary))}."])
    else:
        lines.extend(["", "Неделя выглядит спокойной: специальных вещей не нужно."])
    return "\n".join(lines)


def build_report(bundle: dict[str, Any], view: str) -> str:
    if view == VIEW_TODAY:
        return build_day_report(bundle, 0)
    if view == VIEW_TOMORROW:
        return build_day_report(bundle, 1)
    if view == VIEW_FIVE_DAYS:
        return build_five_days_report(bundle)
    return build_now_report(bundle)


def blend_color(start: tuple[int, int, int], end: tuple[int, int, int], t: float, alpha: int = 255) -> tuple[int, int, int, int]:
    return tuple(round(a + (b - a) * t) for a, b in zip(start, end)) + (alpha,)


def make_gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]):
    image = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        draw.line((0, y, WIDTH, y), fill=blend_color(top, bottom, y / (HEIGHT - 1)))
    return image


def draw_glow(draw: Any, x: float, y: float, radius: float, color: tuple[int, int, int, int]) -> None:
    for step in range(5, 0, -1):
        scale = step / 5
        r = radius * (1 + scale * 1.8)
        alpha = round(color[3] * scale * 0.16)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(color[0], color[1], color[2], alpha))


def draw_sun(draw: Any, x: float, y: float, radius: float, phase: float) -> None:
    draw_glow(draw, x, y, radius, (255, 223, 130, 230))
    for index in range(14):
        angle = phase / 2 + index * math.tau / 14
        inner = radius + 8
        outer = radius + 20 + math.sin(phase + index) * 3
        draw.line(
            (x + math.cos(angle) * inner, y + math.sin(angle) * inner, x + math.cos(angle) * outer, y + math.sin(angle) * outer),
            fill=(255, 216, 86, 255),
            width=4,
        )
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 239, 142, 255))


def draw_moon(draw: Any, x: float, y: float, radius: float, sky: tuple[int, int, int]) -> None:
    draw_glow(draw, x, y, radius, (214, 231, 255, 210))
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(247, 244, 228, 255))
    draw.ellipse((x - radius + 9, y - radius, x + radius + 9, y + radius), fill=(*sky, 255))


def draw_stars(draw: Any, frame_index: int) -> None:
    for index in range(28):
        x = 10 + (index * 37) % (WIDTH - 20)
        y = 10 + (index * 23) % 88
        alpha = 90 + round(135 * (0.5 + 0.5 * math.sin(frame_index * 0.7 + index * 1.4)))
        radius = 1 + (index % 9 == 0)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 248, 218, alpha))


def draw_cloud(draw: Any, x: float, y: float, scale: float, fill: tuple[int, int, int, int]) -> None:
    for dx, dy, radius in ((0, 16, 24), (30, 2, 28), (62, 12, 30), (96, 20, 22)):
        r = radius * scale
        cx = x + dx * scale
        cy = y + dy * scale
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    draw.rounded_rectangle((x - 18 * scale, y + 18 * scale, x + 118 * scale, y + 56 * scale), radius=20 * scale, fill=fill)


def draw_land(draw: Any, hill: tuple[int, int, int, int], ground: tuple[int, int, int, int]) -> None:
    draw.polygon([(0, HEIGHT), (0, 150), (64, 126), (142, 140), (230, 120), (WIDTH, 148), (WIDTH, HEIGHT)], fill=hill)
    draw.rectangle((0, 162, WIDTH, HEIGHT), fill=ground)


def draw_rain(draw: Any, frame_index: int, count: int, color: tuple[int, int, int, int]) -> None:
    for index in range(count):
        x = (index * 23 + frame_index * 10) % (WIDTH + 24) - 24
        y = (index * 17 + frame_index * 13) % HEIGHT
        length = 18 + (index % 3) * 4
        draw.line((x, y, x - 8, y + length), fill=color, width=3)
    for index in range(4):
        x = 46 + index * 68 + math.sin(frame_index / 2 + index) * 4
        y = 151 + (index % 2) * 7
        draw.ellipse((x - 13, y - 4, x + 13, y + 4), outline=(180, 225, 255, 130), width=2)


def draw_snow(draw: Any, frame_index: int) -> None:
    for index in range(32):
        x = (index * 19 + frame_index * 4) % WIDTH
        y = (index * 13 + frame_index * 10) % HEIGHT
        drift = math.sin(frame_index / 2 + index * 0.7) * 6
        r = 2 + (index % 3 == 0)
        draw.ellipse((x + drift - r, y - r, x + drift + r, y + r), fill=(255, 255, 255, 240))


def draw_wind(draw: Any, frame_index: int, color: tuple[int, int, int, int]) -> None:
    for band in range(6):
        start_x = (frame_index * 22 + band * 52) % (WIDTH + 100) - 100
        y = 50 + band * 18
        points = [(start_x + step * 26, y + math.sin((frame_index + step + band) / 1.7) * 4) for step in range(8)]
        draw.line(points, fill=color, width=4)
    for index in range(6):
        x = (frame_index * 18 + index * 57) % (WIDTH + 40) - 20
        y = 112 + math.sin((frame_index + index) / 1.8) * 22
        draw.ellipse((x - 4, y - 2, x + 4, y + 2), fill=(231, 188, 84, 170))


def draw_fog(draw: Any, frame_index: int) -> None:
    for band in range(5):
        x = (frame_index * 12 + band * 70) % (WIDTH + 150) - 150
        y = 58 + band * 22
        draw.rounded_rectangle((x, y, x + 230, y + 17), radius=9, fill=(235, 241, 243, 92))


def draw_heat(draw: Any, frame_index: int, color: tuple[int, int, int, int]) -> None:
    for band in range(5):
        y = 88 + band * 16
        points = [(18 + step * 28, y + math.sin((frame_index + step + band) / 1.5) * 5) for step in range(11)]
        draw.line(points, fill=color, width=3)


def build_animation_frames(theme: str, period: str) -> list[Any]:
    frames: list[Any] = []
    for frame_index in range(FRAME_COUNT):
        phase = frame_index / FRAME_COUNT * math.tau
        if period == "day":
            top, bottom = (86, 176, 236), (225, 241, 220)
            hill, ground = (101, 171, 110, 255), (72, 145, 89, 255)
            cloud = (244, 247, 250, 235)
        else:
            top, bottom = (23, 34, 72), (72, 94, 141)
            hill, ground = (45, 75, 91, 255), (29, 55, 73, 255)
            cloud = (154, 169, 190, 225)
        if theme == "rain":
            top, bottom = ((76, 96, 125), (148, 168, 188)) if period == "day" else ((24, 29, 52), (70, 86, 122))
            cloud = (102, 116, 135, 245)
        elif theme == "snow":
            top, bottom = ((156, 180, 204), (231, 239, 246)) if period == "day" else ((29, 44, 86), (99, 123, 166))
            hill, ground = (205, 220, 234, 255), (232, 241, 249, 255)
        elif theme == "storm":
            top, bottom = ((52, 57, 86), (112, 113, 136)) if period == "day" else ((14, 16, 31), (49, 56, 84))
            cloud = (58, 65, 84, 255)
        elif theme == "fog":
            top, bottom = ((163, 175, 179), (217, 224, 226)) if period == "day" else ((44, 55, 72), (103, 116, 135))
            cloud = (210, 218, 221, 150)
        elif theme == "heat":
            top, bottom = ((255, 184, 92), (255, 233, 166)) if period == "day" else ((74, 34, 48), (161, 82, 63))
            hill, ground = (197, 148, 82, 255), (178, 119, 56, 255)
        image = make_gradient(top, bottom)
        draw = ImageDraw.Draw(image, "RGBA")
        if period == "day":
            draw_sun(draw, 82, 56, 26 + math.sin(phase) * 2, phase)
        else:
            draw_stars(draw, frame_index)
            draw_moon(draw, 244, 48, 22, top)
        draw_land(draw, hill, ground)
        if theme in {"cloud", "rain", "snow", "storm", "fog", "wind"}:
            draw_cloud(draw, 34 + math.sin(phase) * 8, 44, 1.02, cloud)
            draw_cloud(draw, 166 + math.cos(phase) * 9, 38, 0.88, cloud)
        if theme == "rain":
            draw_rain(draw, frame_index, 24, (126, 208, 255, 225))
        elif theme == "snow":
            draw_snow(draw, frame_index)
        elif theme == "storm":
            draw_rain(draw, frame_index, 18, (159, 212, 255, 200))
            if frame_index in {3, 4, 10, 11}:
                draw.polygon([(184, 58), (162, 96), (182, 96), (154, 143), (218, 86), (192, 88)], fill=(255, 236, 124, 255))
                draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(255, 255, 255, 45))
        elif theme == "fog":
            draw_fog(draw, frame_index)
        elif theme == "wind":
            draw_wind(draw, frame_index, (232, 247, 255, 185))
        elif theme == "heat":
            draw_heat(draw, frame_index, (255, 255, 255, 150))
        frames.append(image)
    return frames


def ensure_weather_animation(theme: str, period: str) -> Path | None:
    if Image is None or ImageDraw is None:
        return None
    WEATHER_GIF_DIR.mkdir(parents=True, exist_ok=True)
    path = WEATHER_GIF_DIR / f"{theme}_{period}.gif"
    if path.is_file():
        return path
    frames = build_animation_frames(theme, period)
    prepared = [frame.convert("P", palette=Image.ADAPTIVE, colors=96) for frame in frames]
    prepared[0].save(path, save_all=True, append_images=prepared[1:], duration=DURATION_MS, loop=0, disposal=2, optimize=False)
    return path


def get_weather_animation_path(bundle: dict[str, Any]) -> Path | None:
    blocks = build_daily_blocks(bundle, limit=1)
    today = blocks[0] if blocks else None
    theme = classify_theme_from_weather(
        bundle["current"],
        precipitation_chance=today.precipitation_chance if today else 0.0,
        max_wind=(today.max_wind or 0.0) if today else 0.0,
        max_temp=today.max_temp if today else None,
    )
    return ensure_weather_animation(theme, classify_weather_period(bundle))


async def send_weather_message(update: Update, bundle: dict[str, Any], *, view: str = VIEW_NOW) -> None:
    message = update.effective_message
    if message is None:
        return
    store_user_place(message.chat_id, bundle)
    await reply_with_weather(message, bundle, view=view)


async def reply_with_weather(message: Any, bundle: dict[str, Any], *, view: str = VIEW_NOW) -> None:
    report = build_report(bundle, view)
    animation_path = get_weather_animation_path(bundle)
    if animation_path is not None and animation_path.is_file():
        try:
            with animation_path.open("rb") as animation:
                await message.reply_animation(animation=animation, caption=report, parse_mode=ParseMode.HTML, reply_markup=weather_keyboard(view))
            return
        except Exception:
            logger.exception("Failed to send weather animation")
    await message.reply_text(report, parse_mode=ParseMode.HTML, reply_markup=weather_keyboard(view))


async def update_weather_message(message: Any, bundle: dict[str, Any], *, view: str = VIEW_NOW, edit: bool = False) -> None:
    store_user_place(message.chat_id, bundle)
    if not edit:
        await reply_with_weather(message, bundle, view=view)
        return
    report = build_report(bundle, view)
    reply_markup = weather_keyboard(view)
    try:
        if message.caption is not None or message.animation is not None:
            await message.edit_caption(caption=report, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await message.edit_text(text=report, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except BadRequest as error:
        if "message is not modified" not in str(error).lower():
            logger.warning("Could not edit weather message: %s", error)
            await reply_with_weather(message, bundle, view=view)


async def handle_weather_error(update: Update, error: Exception) -> None:
    message = update.effective_message
    if message is None:
        return
    if isinstance(error, MissingSettingsError):
        text = f"В Railway не хватает переменной <code>{html.escape(str(error))}</code>."
    elif isinstance(error, PermissionError):
        text = "OpenWeather не принял ключ. Проверь <code>OPENWEATHER_API_KEY</code>."
    elif isinstance(error, LookupError):
        text = "Не нашел такой город. Попробуй точнее, например: <code>Москва</code>."
    elif isinstance(error, requests.RequestException):
        logger.exception("Weather request failed")
        text = "Не могу подключиться к сервису погоды. Попробуй через минуту."
    else:
        logger.exception("Unexpected weather error")
        text = "Что-то пошло не так. Попробуй еще раз."
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=location_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "Привет. Напиши город или отправь геопозицию. После прогноза будут кнопки: Сейчас, Сегодня, Завтра, 5 дней, Обновить и Мой город.",
        reply_markup=location_keyboard(),
    )
    await message.reply_text("Быстрые кнопки появятся после первого города.", reply_markup=weather_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "Напиши город обычным сообщением или используй /weather Москва.\n"
        "После карточки можно переключать прогноз кнопками.\n"
        "/location попросит геопозицию.",
        reply_markup=location_keyboard(),
    )


async def location_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text("Нажми кнопку ниже и отправь геопозицию.", reply_markup=location_keyboard())


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    try:
        if context.args:
            bundle = await asyncio.to_thread(fetch_bundle_by_city, " ".join(context.args).strip())
        else:
            place = get_user_place(message.chat_id)
            if place is None:
                await message.reply_text("Напиши /weather Москва или просто Москва.", reply_markup=location_keyboard())
                return
            bundle = await asyncio.to_thread(
                fetch_bundle_by_coordinates,
                float(place["lat"]),
                float(place["lon"]),
                label=str(place.get("label") or "Мой город"),
            )
        await send_weather_message(update, bundle)
    except Exception as error:
        await handle_weather_error(update, error)


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return
    city = message.text.strip()
    if city == LOCATION_BUTTON_TEXT:
        await location_command(update, context)
        return
    try:
        bundle = await asyncio.to_thread(fetch_bundle_by_city, city)
        await send_weather_message(update, bundle)
    except Exception as error:
        await handle_weather_error(update, error)


async def location_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.location is None:
        return
    try:
        bundle = await asyncio.to_thread(fetch_bundle_by_coordinates, message.location.latitude, message.location.longitude)
        await send_weather_message(update, bundle)
    except Exception as error:
        await handle_weather_error(update, error)


async def weather_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return
    data = query.data or ""
    view = data.removeprefix("w:")
    if view == VIEW_REFRESH:
        view = VIEW_NOW
        use_edit = True
    elif view == VIEW_MY_CITY:
        view = VIEW_NOW
        use_edit = False
    elif view in VALID_VIEWS:
        use_edit = True
    else:
        await query.answer("Не понял эту кнопку.", show_alert=True)
        return

    place = get_user_place(query.message.chat_id)
    if place is None:
        await query.answer("Сначала напиши город или отправь геопозицию.", show_alert=True)
        return

    try:
        bundle = await asyncio.to_thread(
            fetch_bundle_by_coordinates,
            float(place["lat"]),
            float(place["lon"]),
            label=str(place.get("label") or "Мой город"),
        )
        await update_weather_message(query.message, bundle, view=view, edit=use_edit)
    except Exception:
        logger.exception("Callback weather update failed")
        await query.answer("Не удалось обновить прогноз.", show_alert=True)
        return
    await query.answer("Готово")


def main() -> None:
    load_dotenv()
    load_user_places()
    token = get_required_env("TELEGRAM_BOT_TOKEN")
    get_required_env("OPENWEATHER_API_KEY")
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_command))
    application.add_handler(CommandHandler("location", location_command))
    application.add_handler(CallbackQueryHandler(weather_callback))
    application.add_handler(MessageHandler(filters.LOCATION, location_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    logger.info("Weather bot started")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
