# TGBOT

Telegram weather bot with GIF weather cards, subscriptions, alerts, and inline controls.

## Features
- current weather, today, tomorrow, and 5-day forecast
- one Telegram message with GIF and caption
- clothing advice by activity mode
- daily subscriptions and smart alerts
- polling or webhook mode for Railway

## Run
```bash
python app.py
```

`app.py` reconstructs the modular runtime from `runtime_bundle/part*.b64` on startup and then launches `weather_bot.bot`.
