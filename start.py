from __future__ import annotations

import logging
import runpy
from pathlib import Path

logger = logging.getLogger(__name__)


def patch_refresh_button(bot_app) -> None:
    original_weather_callback = bot_app.weather_callback

    async def weather_callback(update, context):
        query = update.callback_query
        if query is None or query.message is None:
            return
        view = (query.data or "").removeprefix("w:")
        if view != bot_app.VIEW_REFRESH:
            await original_weather_callback(update, context)
            return

        place = bot_app.get_user_place(query.message.chat_id)
        if place is None:
            await query.answer("Сначала напиши город или отправь геопозицию.", show_alert=True)
            return

        try:
            bundle = await bot_app.asyncio.to_thread(
                bot_app.fetch_bundle_by_coordinates,
                float(place["lat"]),
                float(place["lon"]),
                label=str(place.get("label") or "Мой город"),
            )
            await bot_app.update_weather_message(query.message, bundle, view=bot_app.VIEW_NOW, edit=False)
        except Exception:
            bot_app.logger.exception("Callback weather refresh failed")
            await query.answer("Не удалось обновить прогноз.", show_alert=True)
            return
        await query.answer("Готово")

    bot_app.weather_callback = weather_callback


def main() -> None:
    root = Path(__file__).resolve().parent
    try:
        runpy.run_path(str(root / "scripts" / "generate_premium_weather_gifs.py"), run_name="__main__")
    except Exception:
        logger.exception("Could not generate premium weather GIFs before startup")
    import app as bot_app

    patch_refresh_button(bot_app)
    bot_app.main()


if __name__ == "__main__":
    main()
