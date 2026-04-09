# Telegram Weather Bot

Бот погоды для Telegram с запуском на Railway.

Что есть:
- погода по городу через `/weather Москва` или обычное сообщение `Москва`
- погода по геопозиции Telegram
- GIF-анимация погоды: солнце, облака, дождь, снег, гроза, туман, ветер, жара
- совет по одежде

## Переменные Railway

В Railway открой `Variables` и добавь:

```text
TELEGRAM_BOT_TOKEN=токен_бота_из_BotFather
OPENWEATHER_API_KEY=ключ_из_OpenWeather
```

`.env` в GitHub не загружай.

## Запуск

Railway берет команду из `railway.json`:

```bash
python app.py
```

При первом запросе бот сам создаст GIF-файлы в `assets/weather/` внутри контейнера. Архив `runtime_bundle.b64` больше не нужен и не используется.

## Проверка

После деплоя в логах Railway должна появиться строка:

```text
Weather bot started
```

Потом напиши боту `/start`, а затем город, например `Москва`.
