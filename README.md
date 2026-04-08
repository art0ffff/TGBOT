# TGBOT

Telegram weather bot with animated weather GIFs, compact forecast cards, clothing advice, inline controls, subscriptions, and weather alerts.

## Features
- current weather, today, tomorrow, and 5-day forecast
- one Telegram message with GIF and caption
- day and night GIF variants
- clothing advice and scenario-based hints
- daily subscriptions and alert notifications
- polling or webhook mode for Railway

## Environment
- `TELEGRAM_BOT_TOKEN`
- `OPENWEATHER_API_KEY`
- `WEATHER_CACHE_TTL_SECONDS`
- `USE_WEBHOOK`
- `WEBHOOK_URL`
- `WEBHOOK_PATH`
- `WEBHOOK_SECRET_TOKEN`
- `WEBHOOK_LISTEN`

## Run
```bash
python app.py
```

`app.py` unpacks the bundled runtime sources on startup and launches the modular bot from `weather_bot.bot`.
