from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path


def ensure_runtime_bundle() -> None:
    root = Path(__file__).resolve().parent
    bundle_path = root / "runtime_bundle.b64"
    data = base64.b64decode(bundle_path.read_text(encoding="ascii"))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        archive.extractall(root)


ensure_runtime_bundle()

from weather_bot.bot import main


if __name__ == "__main__":
    main()
