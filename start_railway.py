from __future__ import annotations

import logging
import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WEATHER_GIF_DIR = ROOT / "assets" / "weather"
GENERATOR = ROOT / "scripts" / "generate_railway_weather_gifs.py"
BOOTSTRAP_MARKER = WEATHER_GIF_DIR / ".railway-gif-bootstrap"
BOOTSTRAP_VERSION = "premium-v6"


def refresh_weather_gifs() -> None:
    WEATHER_GIF_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if BOOTSTRAP_MARKER.read_text(encoding="utf-8").strip() == BOOTSTRAP_VERSION:
            return
    except FileNotFoundError:
        pass

    (WEATHER_GIF_DIR / ".premium-gifs").unlink(missing_ok=True)

    runpy.run_path(str(GENERATOR), run_name="__main__")
    BOOTSTRAP_MARKER.write_text(BOOTSTRAP_VERSION, encoding="utf-8")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    refresh_weather_gifs()

    from app import main as run_app

    run_app()


if __name__ == "__main__":
    main()
