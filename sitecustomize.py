from __future__ import annotations

import logging
import os
import runpy
import sys
from pathlib import Path


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)


def _premium_weather_gifs_ready(root: Path) -> bool:
    out = root / "assets" / "weather"
    marker = out / ".premium-gifs"
    themes = ("sun", "cloud", "rain", "snow", "storm", "fog", "wind", "heat")
    periods = ("day", "night")
    try:
        if marker.read_text(encoding="utf-8").strip() != "premium-v5":
            return False
        for theme in themes:
            for period in periods:
                path = out / f"{theme}_{period}.gif"
                if not path.is_file() or path.stat().st_size < 50_000:
                    return False
    except Exception:
        return False
    return True


def _generate_premium_weather_gifs() -> None:
    if os.getenv("SKIP_WEATHER_GIF_BOOTSTRAP") == "1":
        return
    root = Path(__file__).resolve().parent
    if _premium_weather_gifs_ready(root):
        return
    script = root / "scripts" / "generate_premium_weather_gifs.py"
    if not script.is_file():
        return
    try:
        runpy.run_path(str(script), run_name="__main__")
    except Exception:
        logging.getLogger(__name__).exception("Could not bootstrap premium weather GIFs")


_generate_premium_weather_gifs()
