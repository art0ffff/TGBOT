# Telegram Weather Bot

Telegram-бот погоды для Railway. Прогноз берется из бесплатного Open-Meteo, ключ погоды не нужен.

## Что умеет

- Показывает погоду по городу: можно написать `Москва` без команды.
- Показывает погоду по геопозиции из Telegram.
- Переключает карточку кнопками: Сейчас, Сегодня, Завтра, 5 дней, Обновить.
- Пишет дружескую фразу про одежду одним предложением, без сухих рубрик.
- Склоняет город в карточке: `В Москве`, `В Санкт-Петербурге`, `В Нижнем Новгороде`.
- Работает локально через polling и на Railway через webhook.

## Переменные

```text
TELEGRAM_BOT_TOKEN=...
WEATHER_PROVIDER=openmeteo
USE_WEBHOOK=1
```

Для Railway добавь `TELEGRAM_BOT_TOKEN`, `WEATHER_PROVIDER=openmeteo`, `USE_WEBHOOK=1`.
Если Railway сам даст домен, бот возьмет его из `RAILWAY_PUBLIC_DOMAIN`.

Open-Meteo не требует `OPENWEATHER_API_KEY`.

## Запуск локально

```powershell
cd D:\tgbot
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python app.py
```

Если PowerShell блокирует активацию:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Railway

1. Подключи этот GitHub-репозиторий к Railway.
2. Добавь переменные `TELEGRAM_BOT_TOKEN`, `WEATHER_PROVIDER=openmeteo`, `USE_WEBHOOK=1`.
3. Проверь, что Start Command пустой или равен `python app.py`.
4. Убедись, что у сервиса есть публичный домен Railway, и запусти redeploy.

`railway.json` уже содержит нужный start command.

## GitHub

Не добавляй в Git `.env`, `.venv/`, `data/`, `bot*.log`, `__pycache__/`, `*.pyc`, `app_loader.py` и `runtime_parts/`: они закрыты в `.gitignore`.
