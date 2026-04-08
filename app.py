import html
import logging
import os
import re
import zlib
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
try:
    import pymorphy3
except ImportError:
    pymorphy3 = None
from telegram import KeyboardButton, Message, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("pymorphy3").setLevel(logging.WARNING)

CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
GEOCODING_URL = "https://api.openweathermap.org/geo/1.0/direct"
LOCATION_BUTTON_TEXT = "Отправить геопозицию"
BASE_DIR = Path(__file__).resolve().parent
WEATHER_THEMES = ("storm", "snow", "rain", "heat", "fog", "wind", "sun", "cloud")
WEATHER_GIF_DIR = BASE_DIR / "assets" / "weather"
WEATHER_GIF_VARIANTS = tuple(
    WEATHER_GIF_DIR / f"{theme}_{period}.gif"
    for theme in WEATHER_THEMES
    for period in ("day", "night")
)
REQUEST_TIMEOUT = 10
SERVICE_PARTS = {"на", "де", "ла", "ле", "ди", "ду"}
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

OUTFIT_PHRASES = {
    "freezing": [
        "Сегодня нужен зимний набор: пуховик, шапка и теплая обувь.",
        "Одевайся очень тепло: пуховик, шарф и перчатки будут кстати.",
        "Без теплой куртки и зимней обуви сегодня будет неуютно.",
    ],
    "very_cold": [
        "Лучше выйти в теплой куртке, шапке и закрытой обуви.",
        "Хорошо зайдут пальто или теплая куртка и плотный слой под низ.",
        "На улице зябко, так что бери теплую верхнюю одежду.",
    ],
    "cold": [
        "Подойдут куртка, свитер и закрытая обувь.",
        "Лучше выбрать демисезонную куртку и что-то теплое под нее.",
        "Сегодня комфортнее в куртке или худи и закрытой обуви.",
    ],
    "cool": [
        "Хватит легкой куртки, худи или плотной рубашки.",
        "Возьми что-то накинуть сверху: ветровку или кофту.",
        "На улице свежо, так что легкий верхний слой будет кстати.",
    ],
    "mild": [
        "Можно спокойно идти в футболке с кофтой на всякий случай.",
        "Подойдет легкий верх без тяжелой куртки.",
        "День мягкий, так что хватит обычной повседневной одежды.",
    ],
    "warm": [
        "Хватит футболки и легких брюк или джинсов.",
        "Одевайся легко, без лишних слоев.",
        "Сегодня комфортно в простой легкой одежде.",
    ],
    "hot": [
        "Лучше выбрать легкую одежду и взять воду.",
        "Футболка, шорты или свободные брюки будут в самый раз.",
        "Чем легче одежда, тем приятнее будет на улице.",
    ],
}

LAYER_PHRASES = [
    "Лучше одеться слоями, чтобы можно было легко подстроиться.",
    "Если будешь долго на улице, удобнее выбрать несколько слоев.",
    "Возьми вещь сверху, чтобы по пути можно было подстроиться под погоду.",
]

RAIN_PHRASES = [
    "Зонт или дождевик сегодня точно пригодятся.",
    "Лучше взять с собой зонт, на всякий случай.",
    "Если не хочется промокнуть, захвати дождевик.",
]

SNOW_PHRASES = [
    "Лучше выбрать непромокаемую обувь и теплые носки.",
    "На снег удобнее выйти в теплой обуви, которая не промокает.",
    "Если пойдет снег, теплая обувь очень выручит.",
]

WIND_PHRASES = [
    "Из-за ветра пригодится непродуваемый верх.",
    "На ветру комфортнее в куртке или жилете.",
    "Если будешь долго идти пешком, защита от ветра не помешает.",
]

HEAT_PHRASES = [
    "Вода и головной убор сегодня будут очень кстати.",
    "На солнце быстро станет жарче, так что кепка и вода пригодятся.",
    "Если будешь много ходить, лучше взять воду.",
]

COMFORT_PHRASES = [
    "В целом погода спокойная, так что подойдет обычная удобная одежда.",
    "Без сюрпризов: можно одеться просто и комфортно.",
    "Погода ровная, так что хватит привычного удобного набора.",
]

MORPH_ANALYZER = None

CYRILLIC_TO_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

load_dotenv()


def build_location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(LOCATION_BUTTON_TEXT, request_location=True)]],
        resize_keyboard=True,
    )


def get_morph_analyzer():
    global MORPH_ANALYZER
    if MORPH_ANALYZER is None and pymorphy3 is not None:
        MORPH_ANALYZER = pymorphy3.MorphAnalyzer()
    return MORPH_ANALYZER


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("your_"):
        raise RuntimeError(f"MISSING_{name}")
    return value


def get_openweather_api_key() -> str:
    return get_required_env("OPENWEATHER_API_KEY")


def get_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def format_value(value: Any, digits: int = 0) -> str:
    number = get_number(value)
    if number is None:
        return "—"
    if digits == 0:
        return str(round(number))
    return f"{number:.{digits}f}"


def format_compact_value(value: Any, digits: int = 1) -> str:
    number = get_number(value)
    if number is None:
        return "—"
    rounded = round(number, digits)
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def format_pressure_mmhg(value: Any) -> str:
    pressure_hpa = get_number(value)
    if pressure_hpa is None:
        return "—"
    return str(round(pressure_hpa * 0.750062))


def format_visibility_km(value: Any) -> str:
    visibility_meters = get_number(value)
    if visibility_meters is None:
        return "—"
    return format_compact_value(visibility_meters / 1000, digits=1)


def choose_phrase(options: list[str], *seed_parts: Any) -> str:
    if not options:
        return ""
    seed = "|".join(str(part) for part in seed_parts if part is not None)
    index = zlib.adler32(seed.encode("utf-8")) % len(options)
    return options[index]


def preserve_word_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement.capitalize()
    return replacement


def inflect_word_to_prepositional(word: str) -> str:
    if not word or not CYRILLIC_RE.search(word):
        return word

    morph = get_morph_analyzer()
    if morph is None:
        return word

    for parse in morph.parse(word):
        inflected = parse.inflect({"loct"})
        if inflected is not None:
            return preserve_word_case(word, inflected.word)

    return word


def inflect_hyphenated_part(part: str) -> str:
    pieces = part.split("-")
    lexical_indexes = [
        index
        for index, piece in enumerate(pieces)
        if piece and piece.lower() not in SERVICE_PARTS
    ]
    if not lexical_indexes:
        return part

    if len(pieces) >= 3 and "на" in [piece.lower() for piece in pieces]:
        target_index = lexical_indexes[0]
    else:
        target_index = lexical_indexes[-1]

    pieces[target_index] = inflect_word_to_prepositional(pieces[target_index])
    return "-".join(pieces)


def inflect_city_name_to_prepositional(city_name: str) -> str:
    if not city_name or not CYRILLIC_RE.search(city_name):
        return city_name

    inflected_parts: list[str] = []
    for part in city_name.split():
        if "-" in part:
            inflected_parts.append(inflect_hyphenated_part(part))
        else:
            inflected_parts.append(inflect_word_to_prepositional(part))

    return " ".join(inflected_parts)


def transliterate_city_name(city: str) -> str:
    transliterated: list[str] = []
    for char in city:
        lower_char = char.lower()
        latin = CYRILLIC_TO_LATIN.get(lower_char)
        if latin is None:
            transliterated.append(char)
            continue
        if char.isupper():
            transliterated.append(latin.capitalize())
        else:
            transliterated.append(latin)
    return "".join(transliterated)


def request_openweather(endpoint: str, api_key: str, **params: Any) -> dict[str, Any]:
    response = requests.get(
        endpoint,
        params={
            **params,
            "appid": api_key,
            "units": "metric",
            "lang": "ru",
        },
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 404:
        raise ValueError("CITY_NOT_FOUND")

    response.raise_for_status()
    return response.json()


def geocode_city(city: str, api_key: str) -> dict[str, Any]:
    candidates = [city.strip()]
    transliterated = transliterate_city_name(city).strip()
    if transliterated and transliterated not in candidates:
        candidates.append(transliterated)

    for candidate in candidates:
        response = requests.get(
            GEOCODING_URL,
            params={"q": candidate, "limit": 1, "appid": api_key},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        locations = response.json()
        if locations:
            return locations[0]

    raise ValueError("CITY_NOT_FOUND")


def fetch_weather_bundle_by_city(city: str, api_key: str) -> dict[str, Any]:
    location = geocode_city(city, api_key)
    current_data = request_openweather(
        CURRENT_WEATHER_URL,
        api_key,
        lat=location.get("lat"),
        lon=location.get("lon"),
    )
    forecast_data = request_openweather(
        FORECAST_URL,
        api_key,
        lat=location.get("lat"),
        lon=location.get("lon"),
    )
    return {
        "current": current_data,
        "forecast": forecast_data,
        "resolved_name": location.get("local_names", {}).get("ru") or location.get("name") or city,
    }


def fetch_weather_bundle_by_coordinates(
    latitude: float,
    longitude: float,
    api_key: str,
) -> dict[str, Any]:
    current_data = request_openweather(
        CURRENT_WEATHER_URL,
        api_key,
        lat=latitude,
        lon=longitude,
    )
    forecast_data = request_openweather(
        FORECAST_URL,
        api_key,
        lat=latitude,
        lon=longitude,
    )
    return {"current": current_data, "forecast": forecast_data}


def get_local_datetime(timestamp: Any, timezone_shift: int) -> datetime | None:
    unix_time = get_number(timestamp)
    if unix_time is None:
        return None
    local_timezone = timezone(timedelta(seconds=timezone_shift))
    return datetime.fromtimestamp(unix_time, tz=local_timezone)


def get_weather_description(data: dict[str, Any]) -> str:
    return str(data.get("weather", [{}])[0].get("description", "")).strip().lower()


def get_precipitation_volume(entry: dict[str, Any]) -> float:
    precipitation = 0.0
    for key in ("rain", "snow"):
        block = entry.get(key, {})
        if isinstance(block, dict):
            for value in block.values():
                number = get_number(value)
                if number is not None:
                    precipitation += number
    return precipitation


def summarize_forecast(
    current_data: dict[str, Any],
    forecast_data: dict[str, Any],
) -> dict[str, Any]:
    timezone_shift = int(
        current_data.get("timezone", forecast_data.get("city", {}).get("timezone", 0)) or 0
    )
    current_timestamp = get_number(current_data.get("dt"))
    current_local_dt = get_local_datetime(current_timestamp, timezone_shift)
    current_local_date = current_local_dt.date() if current_local_dt else None

    entries = forecast_data.get("list", [])
    upcoming_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and get_number(entry.get("dt")) is not None
        and (current_timestamp is None or get_number(entry.get("dt")) >= current_timestamp)
    ]
    near_entries = upcoming_entries[:4] or entries[:4]

    today_entries: list[dict[str, Any]] = []
    if current_local_date is not None:
        for entry in entries:
            local_dt = get_local_datetime(entry.get("dt"), timezone_shift)
            if local_dt is not None and local_dt.date() == current_local_date:
                today_entries.append(entry)
    if not today_entries:
        today_entries = near_entries

    current_temp = get_number(current_data.get("main", {}).get("temp"))
    current_wind = get_number(current_data.get("wind", {}).get("speed"))

    today_temperatures = [current_temp] if current_temp is not None else []
    today_temperatures.extend(
        temperature
        for temperature in (
            get_number(entry.get("main", {}).get("temp")) for entry in today_entries
        )
        if temperature is not None
    )

    day_winds = [current_wind] if current_wind is not None else []
    day_winds.extend(
        wind_speed
        for wind_speed in (
            get_number(entry.get("wind", {}).get("speed")) for entry in today_entries
        )
        if wind_speed is not None
    )

    descriptions = [
        description
        for description in (get_weather_description(entry) for entry in near_entries)
        if description
    ]
    dominant_description = (
        Counter(descriptions).most_common(1)[0][0]
        if descriptions
        else get_weather_description(current_data)
    )

    trend_entry = near_entries[min(2, len(near_entries) - 1)] if near_entries else None
    trend_temp = get_number(trend_entry.get("main", {}).get("temp")) if trend_entry else None
    trend_delta = (
        trend_temp - current_temp
        if trend_temp is not None and current_temp is not None
        else None
    )
    trend_time = None
    if trend_entry is not None:
        trend_dt = get_local_datetime(trend_entry.get("dt"), timezone_shift)
        if trend_dt is not None:
            trend_time = trend_dt.strftime("%H:%M")

    precipitation_chance = max(
        (get_number(entry.get("pop")) or 0.0 for entry in near_entries),
        default=0.0,
    )
    precipitation_volume = sum(get_precipitation_volume(entry) for entry in near_entries)

    return {
        "current_local_time": current_local_dt.strftime("%H:%M") if current_local_dt else None,
        "day_min": min(today_temperatures) if today_temperatures else None,
        "day_max": max(today_temperatures) if today_temperatures else None,
        "day_range": (
            max(today_temperatures) - min(today_temperatures)
            if len(today_temperatures) >= 2
            else 0.0
        ),
        "max_wind": max(day_winds) if day_winds else None,
        "trend_temp": trend_temp,
        "trend_delta": trend_delta,
        "trend_time": trend_time,
        "precipitation_chance": precipitation_chance,
        "precipitation_volume": precipitation_volume,
        "dominant_description": dominant_description,
    }


def detect_precipitation_kind(description: str) -> str:
    lowered = description.lower()
    if "снег" in lowered:
        return "снег"
    if any(word in lowered for word in ("дожд", "лив", "морось", "гроза")):
        return "дождь"
    return "осадки"


def build_short_term_outlook(summary: dict[str, Any]) -> str:
    parts: list[str] = []

    day_min = summary.get("day_min")
    day_max = summary.get("day_max")
    if isinstance(day_min, (int, float)) and isinstance(day_max, (int, float)):
        parts.append(
            f"Сегодня примерно от {format_value(day_min, 1)} до {format_value(day_max, 1)}°C."
        )

    trend_temp = summary.get("trend_temp")
    trend_delta = summary.get("trend_delta")
    trend_time = summary.get("trend_time")
    if (
        isinstance(trend_temp, (int, float))
        and isinstance(trend_delta, (int, float))
        and trend_time
    ):
        if trend_delta >= 2:
            parts.append(
                f"К {trend_time} потеплеет до {format_value(trend_temp, 1)}°C."
            )
        elif trend_delta <= -2:
            parts.append(
                f"К {trend_time} похолодает до {format_value(trend_temp, 1)}°C."
            )
        else:
            parts.append(
                f"В ближайшие часы будет около {format_value(trend_temp, 1)}°C."
            )

    precipitation_chance = summary.get("precipitation_chance", 0.0)
    precipitation_volume = summary.get("precipitation_volume", 0.0)
    precipitation_kind = detect_precipitation_kind(summary.get("dominant_description", ""))
    if precipitation_chance >= 0.7:
        parts.append(
            f"{precipitation_kind.capitalize()} вероятен: до {round(precipitation_chance * 100)}%."
        )
    elif precipitation_chance >= 0.35:
        parts.append(
            f"Осадки возможны: до {round(precipitation_chance * 100)}%."
        )

    if isinstance(precipitation_volume, (int, float)) and precipitation_volume >= 1:
        parts.append(
            f"По объему это около {format_value(precipitation_volume, 1)} мм."
        )

    if not parts:
        return "Пока все спокойно, без резких сюрпризов."

    return " ".join(parts[:3])


def get_temperature_bucket(temperature: float | None) -> str:
    if temperature is None:
        return "mild"
    if temperature <= -15:
        return "freezing"
    if temperature <= -5:
        return "very_cold"
    if temperature <= 5:
        return "cold"
    if temperature <= 12:
        return "cool"
    if temperature <= 20:
        return "mild"
    if temperature <= 27:
        return "warm"
    return "hot"


def get_condition_emoji(description: str) -> str:
    lowered = description.lower()
    if "гроза" in lowered:
        return "⛈️"
    if "снег" in lowered:
        return "❄️"
    if any(word in lowered for word in ("дожд", "лив", "морось")):
        return "🌧️"
    if any(word in lowered for word in ("туман", "дымка", "мгла")):
        return "🌫️"
    if any(word in lowered for word in ("ясно", "солнечно")):
        return "☀️"
    if any(word in lowered for word in ("облачно", "пасмурно")):
        return "☁️"
    return "🌤️"


def get_weather_theme(
    current_description: str,
    forecast_summary: dict[str, Any],
    day_max: float | None,
) -> str:
    combined = f"{current_description} {forecast_summary.get('dominant_description', '')}".lower()
    precipitation_chance = get_number(forecast_summary.get("precipitation_chance")) or 0.0
    max_wind = get_number(forecast_summary.get("max_wind")) or 0.0

    if "гроза" in combined:
        return "storm"
    if "снег" in combined:
        return "snow"
    if precipitation_chance >= 0.35 or any(
        word in combined for word in ("дожд", "лив", "морось")
    ):
        return "rain"
    if day_max is not None and day_max >= 28:
        return "heat"
    if any(word in combined for word in ("туман", "дымка", "мгла")):
        return "fog"
    if max_wind >= 11:
        return "wind"
    if any(word in combined for word in ("ясно", "солнечно")):
        return "sun"
    return "cloud"


def resolve_weather_theme_from_bundle(weather_bundle: dict[str, Any]) -> str:
    current_data = weather_bundle["current"]
    forecast_data = weather_bundle["forecast"]
    forecast_summary = summarize_forecast(current_data, forecast_data)
    raw_description = str(current_data.get("weather", [{}])[0].get("description", ""))
    current_temp = get_number(current_data.get("main", {}).get("temp"))
    day_max = get_number(forecast_summary.get("day_max")) or current_temp
    return get_weather_theme(raw_description, forecast_summary, day_max)


def resolve_weather_period_from_bundle(weather_bundle: dict[str, Any]) -> str:
    current_data = weather_bundle["current"]
    forecast_data = weather_bundle["forecast"]
    weather = current_data.get("weather", [{}])[0]
    icon_code = str(weather.get("icon", "")).strip().lower()
    if icon_code.endswith("d"):
        return "day"
    if icon_code.endswith("n"):
        return "night"

    current_timestamp = get_number(current_data.get("dt"))
    sys_info = current_data.get("sys", {})
    sunrise = get_number(sys_info.get("sunrise"))
    sunset = get_number(sys_info.get("sunset"))
    if (
        current_timestamp is not None
        and sunrise is not None
        and sunset is not None
        and sunrise < sunset
    ):
        if sunrise <= current_timestamp < sunset:
            return "day"
        return "night"

    timezone_shift = int(
        current_data.get("timezone", forecast_data.get("city", {}).get("timezone", 0)) or 0
    )
    local_dt = get_local_datetime(current_timestamp, timezone_shift)
    if local_dt is not None and 6 <= local_dt.hour < 21:
        return "day"
    return "night"


def ensure_weather_gif_assets() -> None:
    if all(path.is_file() for path in WEATHER_GIF_VARIANTS):
        return

    try:
        from scripts.generate_weather_gif_variants import main as generate_weather_gif_variants
    except Exception:
        logger.exception("Не удалось импортировать генератор погодных GIF")
        return

    try:
        generate_weather_gif_variants()
    except Exception:
        logger.exception("Не удалось сгенерировать погодные GIF")


def get_weather_animation_path(weather_bundle: dict[str, Any]) -> Path | None:
    ensure_weather_gif_assets()
    theme = resolve_weather_theme_from_bundle(weather_bundle)
    period = resolve_weather_period_from_bundle(weather_bundle)
    candidates = [
        WEATHER_GIF_DIR / f"{theme}_{period}.gif",
        WEATHER_GIF_DIR / f"{theme}.gif",
    ]
    for animation_path in candidates:
        if animation_path.is_file():
            return animation_path
    return None


def get_report_emoji(theme: str) -> str:
    return {
        "storm": "⛈️",
        "snow": "❄️",
        "rain": "🌧️",
        "heat": "🔥",
        "fog": "🌫️",
        "wind": "🌬️",
        "sun": "☀️",
        "cloud": "☁️",
    }.get(theme, "🌤️")


def get_forecast_emoji(theme: str) -> str:
    return {
        "storm": "⛈️",
        "snow": "🌨️",
        "rain": "☔",
        "heat": "🌡️",
        "fog": "🌫️",
        "wind": "🌬️",
        "sun": "🌤️",
        "cloud": "🕒",
    }.get(theme, "🕒")


def get_temperature_emoji(temperature: float | None) -> str:
    bucket = get_temperature_bucket(temperature)
    return {
        "freezing": "🥶",
        "very_cold": "🥶",
        "cold": "🧥",
        "cool": "🍃",
        "mild": "🌤️",
        "warm": "😎",
        "hot": "🔥",
    }.get(bucket, "🌡️")


def get_feels_like_emoji(
    temperature: float | None,
    feels_like: float | None,
) -> str:
    if temperature is None or feels_like is None:
        return "🤔"
    if feels_like <= temperature - 3:
        return "🥶"
    if feels_like >= temperature + 3:
        return "🥵"
    return "🙂"


def get_outfit_emoji(bucket: str) -> str:
    emoji_map = {
        "freezing": "🧣",
        "very_cold": "🧥",
        "cold": "🧥",
        "cool": "🧶",
        "mild": "👕",
        "warm": "😎",
        "hot": "🩳",
    }
    return emoji_map.get(bucket, "👕")


def get_outfit_heading_emoji(theme: str, bucket: str) -> str:
    theme_emojis = {
        "storm": "☔",
        "snow": "🧣",
        "rain": "☔",
        "heat": "🧢",
        "fog": "🧥",
        "wind": "🧥",
        "sun": "😎",
        "cloud": get_outfit_emoji(bucket),
    }
    return theme_emojis.get(theme, get_outfit_emoji(bucket))


def get_clothing_advice(
    current_data: dict[str, Any],
    forecast_summary: dict[str, Any],
) -> str:
    main = current_data.get("main", {})
    wind = current_data.get("wind", {})

    temperature = get_number(main.get("temp"))
    feels_like = get_number(main.get("feels_like"))
    wind_speed = get_number(wind.get("speed")) or 0.0
    description = get_weather_description(current_data)

    base_temperature = feels_like if feels_like is not None else temperature
    bucket = get_temperature_bucket(base_temperature)
    city_name = current_data.get("name", "city")
    current_day_key = (
        forecast_summary.get("current_local_time") or str(round(base_temperature or 0))
    )
    seed = f"{city_name}|{description}|{current_day_key}|{bucket}"

    advice_parts = [choose_phrase(OUTFIT_PHRASES[bucket], seed, "base")]

    day_range = get_number(forecast_summary.get("day_range")) or 0.0
    trend_delta = get_number(forecast_summary.get("trend_delta")) or 0.0
    if day_range >= 7 or abs(trend_delta) >= 4:
        advice_parts.append(choose_phrase(LAYER_PHRASES, seed, "layers"))

    precipitation_chance = get_number(forecast_summary.get("precipitation_chance")) or 0.0
    precipitation_description = (
        f"{description} {forecast_summary.get('dominant_description', '')}".lower()
    )
    if "снег" in precipitation_description:
        advice_parts.append(choose_phrase(SNOW_PHRASES, seed, "snow"))
    elif precipitation_chance >= 0.35 or any(
        word in precipitation_description for word in ("дожд", "лив", "морось", "гроза")
    ):
        advice_parts.append(choose_phrase(RAIN_PHRASES, seed, "rain"))

    max_wind = get_number(forecast_summary.get("max_wind")) or wind_speed
    if max_wind >= 8:
        advice_parts.append(choose_phrase(WIND_PHRASES, seed, "wind"))

    day_max = get_number(forecast_summary.get("day_max")) or temperature
    if day_max is not None and day_max >= 25 and precipitation_chance < 0.35:
        advice_parts.append(choose_phrase(HEAT_PHRASES, seed, "heat"))

    if len(advice_parts) == 1:
        advice_parts.append(choose_phrase(COMFORT_PHRASES, seed, "comfort"))

    return " ".join(advice_parts[:2])


def build_weather_report(weather_bundle: dict[str, Any]) -> str:
    current_data = weather_bundle["current"]
    forecast_data = weather_bundle["forecast"]
    forecast_summary = summarize_forecast(current_data, forecast_data)

    city_label = weather_bundle.get("resolved_name") or current_data.get("name", "Неизвестный город")
    city_name = html.escape(str(city_label))
    weather = current_data.get("weather", [{}])[0]
    main = current_data.get("main", {})
    wind = current_data.get("wind", {})

    raw_description = str(weather.get("description", "без описания"))
    description = html.escape(raw_description.capitalize())
    condition_emoji = get_condition_emoji(raw_description)
    current_temp_number = get_number(main.get("temp"))
    feels_like_number = get_number(main.get("feels_like"))
    bucket = get_temperature_bucket(feels_like_number or current_temp_number)
    day_max_number = get_number(forecast_summary.get("day_max")) or current_temp_number
    theme = get_weather_theme(raw_description, forecast_summary, day_max_number)
    report_emoji = get_report_emoji(theme)
    feels_like_emoji = get_feels_like_emoji(current_temp_number, feels_like_number)
    outfit_emoji = get_outfit_heading_emoji(theme, bucket)
    advice = html.escape(get_clothing_advice(current_data, forecast_summary))
    temperature = format_compact_value(main.get("temp"), digits=1)
    feels_like = format_compact_value(main.get("feels_like"), digits=1)
    pressure = format_pressure_mmhg(main.get("pressure"))
    visibility = format_visibility_km(current_data.get("visibility"))
    humidity = format_value(main.get("humidity"))
    wind_speed = format_compact_value(wind.get("speed"), digits=1)
    day_min = format_compact_value(forecast_summary.get("day_min"), digits=1)
    day_max = format_compact_value(forecast_summary.get("day_max"), digits=1)
    trend_temp = format_compact_value(forecast_summary.get("trend_temp"), digits=1)
    trend_time = html.escape(str(forecast_summary.get("trend_time") or "—"))
    precipitation_chance = round(
        (get_number(forecast_summary.get("precipitation_chance")) or 0.0) * 100
    )
    wind_emoji = "🌬️" if (get_number(wind.get("speed")) or 0.0) >= 8 else "💨"

    lines = [
        f"{report_emoji} <b>{city_name}</b>",
        f"{condition_emoji} {description}",
        "",
        f"🌡️ Сейчас: {temperature}°C",
        f"{feels_like_emoji} Ощущается: {feels_like}°C",
        f"📉 Сегодня: {day_min}..{day_max}°C",
        f"{wind_emoji} Ветер: {wind_speed} м/с",
        f"💧 Влажность: {humidity}%",
        f"📊 Давление: {pressure} мм",
        f"👁️ Видимость: {visibility} км",
        f"🌧️ Осадки: {precipitation_chance}%",
    ]

    if trend_time != "—" and trend_temp != "—":
        lines.append(f"🕒 К {trend_time}: {trend_temp}°C")

    lines.extend(
        [
            "",
            f"<b>{outfit_emoji} Что надеть</b>",
            advice,
        ]
    )

    return "\n".join(lines)


async def reply_with_weather(message: Message, weather_bundle: dict[str, Any]) -> None:
    report = build_weather_report(weather_bundle)
    animation_path = get_weather_animation_path(weather_bundle)
    if animation_path is not None:
        try:
            with animation_path.open("rb") as animation_file:
                await message.reply_animation(
                    animation=animation_file,
                    caption=report,
                    parse_mode=ParseMode.HTML,
                    reply_markup=build_location_keyboard(),
                )
                return
        except Exception:
            logger.exception("Не удалось отправить GIF-анимацию погоды: %s", animation_path)

    await message.reply_text(
        report,
        parse_mode=ParseMode.HTML,
        reply_markup=build_location_keyboard(),
    )


async def handle_city_weather_request(message: Message, city: str) -> None:
    try:
        weather_bundle = fetch_weather_bundle_by_city(city, get_openweather_api_key())
        await reply_with_weather(message, weather_bundle)
    except RuntimeError:
        await message.reply_text(
            "⚠️ Не вижу OPENWEATHER_API_KEY. Добавь его в переменные окружения."
        )
    except ValueError as error:
        if str(error) == "CITY_NOT_FOUND":
            await message.reply_text("🔎 Не нашел такой город. Попробуй еще раз.")
            return
        logger.exception("Ошибка валидации при обработке погоды")
        await message.reply_text("⚠️ Что-то не сложилось. Давай еще раз.")
    except requests.HTTPError:
        logger.exception("OpenWeather вернул ошибку")
        await message.reply_text("🛠️ Сервис погоды сейчас занят. Попробуй чуть позже.")
    except requests.RequestException:
        logger.exception("Сетевая ошибка при запросе к OpenWeather")
        await message.reply_text("🌐 Не могу подключиться к сервису погоды. Попробуй позже.")
    except Exception:
        logger.exception("Непредвиденная ошибка")
        await message.reply_text("⚠️ Что-то пошло не так. Попробуй еще раз.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "👋 Привет! Напиши город, например Москва, и я коротко подскажу погоду и что надеть.\n"
        "📍 Или просто отправь геопозицию кнопкой ниже.",
        reply_markup=build_location_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "📚 Можно так:\n"
        "/weather <город>\n"
        "/location\n\n"
        "Или просто напиши название города. Я пойму 🙂",
        reply_markup=build_location_keyboard(),
    )


async def location_prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "📍 Нажми кнопку ниже, и я покажу погоду рядом с тобой.",
        reply_markup=build_location_keyboard(),
    )


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    if not context.args:
        await message.reply_text(
            "🏙️ Напиши /weather Москва, просто Москва или отправь геопозицию.",
            reply_markup=build_location_keyboard(),
        )
        return

    city = " ".join(context.args).strip()
    await handle_city_weather_request(message, city)

 
async def text_city_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return

    city = message.text.strip()
    if not city:
        return

    if city == LOCATION_BUTTON_TEXT:
        await message.reply_text(
            "📍 Нажми кнопку и отправь геопозицию, я все покажу.",
            reply_markup=build_location_keyboard(),
        )
        return

    await handle_city_weather_request(message, city)


async def location_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.location is None:
        return

    try:
        weather_bundle = fetch_weather_bundle_by_coordinates(
            message.location.latitude,
            message.location.longitude,
            get_openweather_api_key(),
        )
        await reply_with_weather(message, weather_bundle)
    except RuntimeError:
        await message.reply_text(
            "⚠️ Не вижу OPENWEATHER_API_KEY. Добавь его в переменные окружения."
        )
    except requests.HTTPError:
        logger.exception("OpenWeather вернул ошибку при запросе по координатам")
        await message.reply_text("📍 Не получилось взять погоду по геопозиции. Попробуй чуть позже.")
    except requests.RequestException:
        logger.exception("Сетевая ошибка при запросе погоды по координатам")
        await message.reply_text("🌐 Не могу подключиться к сервису погоды. Попробуй позже.")
    except Exception:
        logger.exception("Непредвиденная ошибка при обработке геопозиции")
        await message.reply_text("⚠️ Что-то пошло не так. Попробуй еще раз.")


def main() -> None:
    try:
        telegram_token = get_required_env("TELEGRAM_BOT_TOKEN")
    except RuntimeError:
        raise RuntimeError(
            "Не найден TELEGRAM_BOT_TOKEN. "
            "Заполни реальный токен в файле .env или в переменных окружения."
        ) from None

    ensure_weather_gif_assets()
    application = Application.builder().token(telegram_token).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("location", location_prompt_command))
    application.add_handler(CommandHandler("weather", weather_command))
    application.add_handler(MessageHandler(filters.LOCATION, location_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_city_message))

    logger.info("Weather bot started")
    application.run_polling()


if __name__ == "__main__":
    main()
