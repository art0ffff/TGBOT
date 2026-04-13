# Telegram Weather Bot

Telegram-бот погоды для Railway. Прогноз берется из бесплатного Open-Meteo, ключ погоды не нужен.

## Что умеет

- Показывает погоду по городу: можно написать `Москва` без команды.
- Показывает погоду по геопозиции из Telegram.
- Отправляет GIF под погоду: солнце, облака, дождь, снег, гроза, туман, ветер или жара.
- Если GIF-файлов нет в репозитории, бот сам создаст их через Pillow при первом запросе.
- Переключает карточку кнопками: Сейчас, Сегодня, Завтра, 5 дней, Обновить.
- Пишет дружескую фразу про одежду одним предложением, без сухих рубрик.
- Склоняет город в карточке: `В Москве`, `В Санкт-Петербурге`, `В Нижнем Новгороде`.
- Работает на Railway через polling, поэтому публичный домен не обязателен.

## Переменные

```text
TELEGRAM_BOT_TOKEN=...
WEATHER_PROVIDER=openmeteo
USE_WEBHOOK=0
```

Для Railway добавь `TELEGRAM_BOT_TOKEN`, `WEATHER_PROVIDER=openmeteo`, `USE_WEBHOOK=0`.
Open-Meteo не требует `OPENWEATHER_API_KEY`.

## Railway

1. Подключи этот GitHub-репозиторий к Railway.
2. В `Variables` добавь `TELEGRAM_BOT_TOKEN`, `WEATHER_PROVIDER=openmeteo`, `USE_WEBHOOK=0`.
3. Проверь, что Start Command пустой или равен `env USE_WEBHOOK=0 python app.py`.
4. Нажми `Redeploy`.

`railway.json` уже содержит нужный start command. Он принудительно запускает polling, даже если в Variables случайно осталось `USE_WEBHOOK=1`.

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

## GitHub

Не добавляй в Git `.env`, `.venv/`, `data/`, `bot*.log`, `__pycache__/`, `*.pyc`, `app_loader.py` и `runtime_parts/`: они закрыты в `.gitignore`.
