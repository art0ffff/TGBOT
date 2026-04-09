from __future__ import annotations

import html
import logging
import math
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - handled at runtime with a text fallback.
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
GEOCODING_URL = "https://api.openweathermap.org/geo/1.0/direct"
LOCATION_BUTTON_TEXT = "Отправить геопозицию"
REQUEST_TIMEOUT = 12

BASE_DIR = Path(__file__).resolve().parent
WEATHER_GIF_DIR = BASE_DIR / "assets" / "weather"
WIDTH = 320
HEIGHT = 192
FRAME_COUNT = 12
DURATION_MS = 95


class MissingSettingsError(RuntimeError):
    pass


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("your_"):
        raise MissingSettingsError(name)
    return value


def location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(LOCATION_BUTTON_TEXT, request_location=True)]],
        resize_keyboard=True,
    )


def get_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def format_number(value: Any, digits: int = 0) -> str:
    number = get_number(value)
    if number is None:
        return "—"
    if digits == 0:
        return str(round(number))
    rounded = round(number, digits)
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def request_json(url: str, **params: Any) -> dict[str, Any] | list[dict[str, Any]]:
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        raise LookupError("CITY_NOT_FOUND")
    if response.status_code == 401:
        raise PermissionError("OPENWEATHER_API_KEY")
    response.raise_for_status()
    return response.json()


def fetch_weather_by_city(city: str) -> dict[str, Any]:
    api_key = get_required_env("OPENWEATHER_API_KEY")
    locations = request_json(
        GEOCODING_URL,
        q=city,
        limit=1,
        appid=api_key,
    )
    if not isinstance(locations, list) or not locations:
        raise LookupError("CITY_NOT_FOUND")

    location = locations[0]
    data = fetch_weather_by_coordinates(
        float(location["lat"]),
        float(location["lon"]),
    )
    local_names = location.get("local_names") or {}
    data["_place_name"] = local_names.get("ru") or location.get("name") or city
    return data


def fetch_weather_by_coordinates(latitude: float, longitude: float) -> dict[str, Any]:
    api_key = get_required_env("OPENWEATHER_API_KEY")
    data = request_json(
        CURRENT_WEATHER_URL,
        lat=latitude,
        lon=longitude,
        appid=api_key,
        units="metric",
        lang="ru",
    )
    if not isinstance(data, dict):
        raise LookupError("WEATHER_NOT_FOUND")
    return data


def weather_description(data: dict[str, Any]) -> str:
    weather = data.get("weather") or [{}]
    return str(weather[0].get("description") or "").strip().lower()


def classify_weather_theme(data: dict[str, Any]) -> str:
    weather = data.get("weather") or [{}]
    weather_id = int(weather[0].get("id") or 0)
    temp = get_number(data.get("main", {}).get("temp")) or 0
    wind_speed = get_number(data.get("wind", {}).get("speed")) or 0

    if 200 <= weather_id < 300:
        return "storm"
    if 300 <= weather_id < 600:
        return "rain"
    if 600 <= weather_id < 700:
        return "snow"
    if 700 <= weather_id < 800:
        return "fog"
    if temp >= 30:
        return "heat"
    if wind_speed >= 10:
        return "wind"
    if weather_id == 800:
        return "sun"
    return "cloud"


def classify_weather_period(data: dict[str, Any]) -> str:
    timestamp = int(data.get("dt") or 0)
    system = data.get("sys") or {}
    sunrise = int(system.get("sunrise") or 0)
    sunset = int(system.get("sunset") or 0)
    if sunrise and sunset and sunrise <= timestamp <= sunset:
        return "day"
    return "night"


def outfit_advice(data: dict[str, Any]) -> str:
    main = data.get("main") or {}
    temp = get_number(main.get("feels_like"))
    if temp is None:
        temp = get_number(main.get("temp")) or 0

    description = weather_description(data)
    wind_speed = get_number(data.get("wind", {}).get("speed")) or 0
    parts: list[str] = []

    if temp <= -10:
        parts.append("Нужны пуховик, шапка, шарф и теплая обувь.")
    elif temp <= 0:
        parts.append("Лучше выбрать теплую куртку, шапку и закрытую обувь.")
    elif temp <= 10:
        parts.append("Подойдут куртка, свитер или плотная кофта.")
    elif temp <= 18:
        parts.append("Возьми легкую куртку или худи.")
    elif temp <= 27:
        parts.append("Можно одеться легко, без лишних слоев.")
    else:
        parts.append("Выбирай легкую одежду, воду и головной убор.")

    if "дожд" in description or "лив" in description or "морось" in description:
        parts.append("Зонт или дождевик пригодятся.")
    if "снег" in description:
        parts.append("Лучше взять обувь, которая не промокает.")
    if wind_speed >= 8:
        parts.append("Из-за ветра комфортнее в непродуваемом верхе.")

    return " ".join(parts)


def build_caption(data: dict[str, Any]) -> str:
    main = data.get("main") or {}
    wind = data.get("wind") or {}
    system = data.get("sys") or {}
    city = data.get("_place_name") or data.get("name") or "это место"
    country = system.get("country")
    place = f"{city}, {country}" if country else str(city)

    pressure = get_number(main.get("pressure"))
    pressure_mmhg = round(pressure * 0.750062) if pressure is not None else "—"

    lines = [
        f"<b>Погода: {html.escape(place)}</b>",
        f"{html.escape(weather_description(data).capitalize() or 'Без описания')}",
        "",
        f"Температура: {format_number(main.get('temp'))} °C",
        f"Ощущается как: {format_number(main.get('feels_like'))} °C",
        f"Влажность: {format_number(main.get('humidity'))}%",
        f"Давление: {pressure_mmhg} мм рт. ст.",
        f"Ветер: {format_number(wind.get('speed'), 1)} м/с",
        "",
        html.escape(outfit_advice(data)),
    ]
    return "\n".join(lines)


def blend(start: tuple[int, int, int], end: tuple[int, int, int], t: float) -> tuple[int, int, int, int]:
    return tuple(round(a + (b - a) * t) for a, b in zip(start, end)) + (255,)


def make_gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]):
    image = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        draw.line((0, y, WIDTH, y), fill=blend(top, bottom, y / (HEIGHT - 1)))
    return image


def draw_sun(draw: Any, x: float, y: float, radius: float, phase: float) -> None:
    for index in range(12):
        angle = phase + index * math.tau / 12
        inner = radius + 8
        outer = radius + 22
        draw.line(
            (
                x + math.cos(angle) * inner,
                y + math.sin(angle) * inner,
                x + math.cos(angle) * outer,
                y + math.sin(angle) * outer,
            ),
            fill=(255, 220, 98, 255),
            width=4,
        )
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 239, 145, 255))


def draw_moon(draw: Any, x: float, y: float, radius: float, mask: tuple[int, int, int, int]) -> None:
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(247, 246, 231, 255))
    draw.ellipse((x - radius + 10, y - radius, x + radius + 10, y + radius), fill=mask)


def draw_cloud(draw: Any, x: float, y: float, scale: float, fill: tuple[int, int, int, int]) -> None:
    for dx, dy, radius in ((0, 16, 24), (30, 2, 28), (62, 12, 30), (96, 20, 22)):
        r = radius * scale
        cx = x + dx * scale
        cy = y + dy * scale
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)
    draw.rounded_rectangle((x - 18 * scale, y + 18 * scale, x + 118 * scale, y + 56 * scale), radius=20 * scale, fill=fill)


def draw_ground(draw: Any, hill: tuple[int, int, int, int], ground: tuple[int, int, int, int]) -> None:
    draw.polygon(
        [(0, HEIGHT), (0, 150), (75, 126), (160, 142), (240, 122), (WIDTH, 150), (WIDTH, HEIGHT)],
        fill=hill,
    )
    draw.rectangle((0, 162, WIDTH, HEIGHT), fill=ground)


def draw_stars(draw: Any, frame_index: int) -> None:
    for index in range(24):
        x = 12 + (index * 37) % (WIDTH - 24)
        y = 10 + (index * 23) % 74
        alpha = 120 + round(90 * (0.5 + 0.5 * math.sin(frame_index * 0.8 + index)))
        draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(255, 248, 218, alpha))


def draw_rain(draw: Any, frame_index: int, count: int = 22) -> None:
    for index in range(count):
        x = (index * 23 + frame_index * 10) % (WIDTH + 20) - 20
        y = (index * 17 + frame_index * 14) % HEIGHT
        draw.line((x, y, x - 8, y + 20), fill=(132, 207, 255, 220), width=3)


def draw_snow(draw: Any, frame_index: int, count: int = 30) -> None:
    for index in range(count):
        x = (index * 19 + frame_index * 4) % WIDTH
        y = (index * 13 + frame_index * 9) % HEIGHT
        drift = math.sin(frame_index * 0.5 + index) * 5
        draw.ellipse((x + drift - 2, y - 2, x + drift + 2, y + 2), fill=(255, 255, 255, 238))


def draw_wind(draw: Any, frame_index: int) -> None:
    for band in range(6):
        start_x = (frame_index * 24 + band * 52) % (WIDTH + 80) - 80
        start_y = 48 + band * 18
        points = [
            (start_x + step * 25, start_y + math.sin(frame_index + step + band) * 4)
            for step in range(7)
        ]
        draw.line(points, fill=(238, 249, 255, 190), width=4)


def draw_fog(draw: Any, frame_index: int) -> None:
    for band in range(5):
        x = (frame_index * 14 + band * 70) % (WIDTH + 140) - 140
        y = 58 + band * 22
        draw.rounded_rectangle((x, y, x + 220, y + 16), radius=8, fill=(235, 241, 243, 95))


def draw_heat(draw: Any, frame_index: int) -> None:
    for band in range(5):
        y = 88 + band * 16
        points = [(20 + step * 28, y + math.sin(frame_index + step + band) * 5) for step in range(11)]
        draw.line(points, fill=(255, 255, 255, 155), width=3)


def build_animation_frames(theme: str, period: str) -> list[Any]:
    frames: list[Any] = []
    for frame_index in range(FRAME_COUNT):
        phase = frame_index / FRAME_COUNT * math.tau
        if period == "day":
            top, bottom = (91, 177, 236), (224, 241, 220)
            hill, ground = (104, 171, 112, 255), (73, 146, 91, 255)
            cloud = (244, 247, 250, 235)
        else:
            top, bottom = (23, 34, 72), (72, 94, 141)
            hill, ground = (45, 75, 91, 255), (29, 55, 73, 255)
            cloud = (154, 169, 190, 225)

        if theme == "rain":
            top, bottom = ((78, 98, 126), (151, 169, 187)) if period == "day" else ((26, 30, 51), (71, 85, 121))
        elif theme == "snow":
            top, bottom = ((156, 180, 204), (231, 239, 246)) if period == "day" else ((29, 44, 86), (99, 123, 166))
            ground = (229, 238, 247, 255)
        elif theme == "storm":
            top, bottom = ((53, 58, 86), (117, 117, 136)) if period == "day" else ((14, 16, 31), (49, 56, 84))
        elif theme == "fog":
            top, bottom = ((163, 175, 179), (217, 224, 226)) if period == "day" else ((44, 55, 72), (103, 116, 135))
        elif theme == "heat":
            top, bottom = ((255, 186, 93), (255, 234, 168)) if period == "day" else ((74, 34, 48), (161, 82, 63))

        image = make_gradient(top, bottom)
        draw = ImageDraw.Draw(image, "RGBA")

        if period == "day":
            draw_sun(draw, 82, 56, 26 + math.sin(phase) * 2, phase)
        else:
            draw_stars(draw, frame_index)
            draw_moon(draw, 244, 48, 22, blend(top, top, 0))

        draw_ground(draw, hill, ground)

        if theme in {"cloud", "rain", "snow", "storm", "fog", "wind"}:
            draw_cloud(draw, 36 + math.sin(phase) * 8, 44, 1.02, cloud)
            draw_cloud(draw, 168 + math.cos(phase) * 9, 38, 0.88, cloud)
        if theme == "rain":
            draw_rain(draw, frame_index)
        elif theme == "snow":
            draw_snow(draw, frame_index)
        elif theme == "storm":
            draw_rain(draw, frame_index, count=18)
            if frame_index in {3, 4, 9}:
                draw.polygon([(180, 58), (158, 98), (178, 98), (152, 145), (218, 84), (190, 86)], fill=(255, 236, 124, 255))
        elif theme == "fog":
            draw_fog(draw, frame_index)
        elif theme == "wind":
            draw_wind(draw, frame_index)
        elif theme == "heat":
            draw_heat(draw, frame_index)

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
    prepared[0].save(
        path,
        save_all=True,
        append_images=prepared[1:],
        duration=DURATION_MS,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return path


def get_weather_animation_path(data: dict[str, Any]) -> Path | None:
    theme = classify_weather_theme(data)
    period = classify_weather_period(data)
    return ensure_weather_animation(theme, period)


async def reply_weather(update: Update, data: dict[str, Any]) -> None:
    message = update.effective_message
    if message is None:
        return

    caption = build_caption(data)
    animation_path = get_weather_animation_path(data)
    if animation_path is not None and animation_path.is_file():
        with animation_path.open("rb") as animation:
            await message.reply_animation(
                animation=animation,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=location_keyboard(),
            )
        return

    await message.reply_text(
        caption,
        parse_mode=ParseMode.HTML,
        reply_markup=location_keyboard(),
    )


async def handle_weather_error(update: Update, error: Exception) -> None:
    message = update.effective_message
    if message is None:
        return

    if isinstance(error, MissingSettingsError):
        text = f"В Railway не хватает переменной <code>{html.escape(str(error))}</code>."
    elif isinstance(error, PermissionError):
        text = "OpenWeather не принял ключ. Проверь переменную <code>OPENWEATHER_API_KEY</code>."
    elif isinstance(error, LookupError):
        text = "Не нашел такой город. Попробуй написать название точнее, например: <code>Москва</code>."
    else:
        logger.exception("Weather request failed")
        text = "Не получилось получить погоду. Попробуй еще раз через минуту."

    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=location_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "Привет. Напиши город, например Москва, или отправь геопозицию. Я пришлю погоду с GIF-анимацией и советом по одежде.",
        reply_markup=location_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "Команды:\n"
        "/weather Москва - погода по городу\n"
        "/location - кнопка для геопозиции\n\n"
        "Можно просто написать название города обычным сообщением.",
        reply_markup=location_keyboard(),
    )


async def location_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text("Нажми кнопку ниже и отправь геопозицию.", reply_markup=location_keyboard())


async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    city = " ".join(context.args).strip()
    message = update.effective_message
    if not city:
        if message is not None:
            await message.reply_text("Напиши город после команды, например: /weather Москва")
        return

    try:
        await reply_weather(update, fetch_weather_by_city(city))
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
        await reply_weather(update, fetch_weather_by_city(city))
    except Exception as error:
        await handle_weather_error(update, error)


async def location_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.location is None:
        return

    try:
        await reply_weather(
            update,
            fetch_weather_by_coordinates(message.location.latitude, message.location.longitude),
        )
    except Exception as error:
        await handle_weather_error(update, error)


def main() -> None:
    load_dotenv()
    token = get_required_env("TELEGRAM_BOT_TOKEN")
    get_required_env("OPENWEATHER_API_KEY")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("weather", weather_command))
    application.add_handler(CommandHandler("location", location_command))
    application.add_handler(MessageHandler(filters.LOCATION, location_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))

    logger.info("Weather bot started")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
