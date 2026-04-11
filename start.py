from __future__ import annotations

import runpy
from pathlib import Path

from app import main as run_bot


def main() -> None:
    root = Path(__file__).resolve().parent
    runpy.run_path(str(root / "scripts" / "generate_premium_weather_gifs.py"), run_name="__main__")
    run_bot()


if __name__ == "__main__":
    main()
