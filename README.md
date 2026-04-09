# Telegram Weather Bot

Компактный Telegram-бот погоды для Railway.

## Что умеет

- Показывает погоду по городу: можно написать `Москва` без `/weather`.
- Показывает погоду по геопозиции из Telegram.
- Коротко советует, что лучше надеть сегодня.
- Использует эмодзи и дружелюбный короткий стиль.
- Склоняет частые названия городов: `в Москве`, `в Санкт-Петербурге`.
- Работает локально через polling и на Railway через webhook.

## Переменные

```text
TELEGRAM_BOT_TOKEN=...
OPENWEATHER_API_KEY=...
USE_WEBHOOK=1
```

Для Railway обычно достаточно добавить `TELEGRAM_BOT_TOKEN`, `OPENWEATHER_API_KEY`, `USE_WEBHOOK=1`.
Если Railway сам даст домен, бот возьмет его из `RAILWAY_PUBLIC_DOMAIN`.

## Запуск локально

```powershell
cd D:\tgbot
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
py app.py
```

Если PowerShell блокирует активацию:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Railway

1. Подключи этот GitHub-репозиторий к Railway.
2. Добавь переменные `TELEGRAM_BOT_TOKEN`, `OPENWEATHER_API_KEY`, `USE_WEBHOOK=1`.
3. Проверь, что Start Command пустой или равен `python app.py`.
4. Запусти новый deploy.

`railway.json` уже содержит нужный start command.
