from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path


def ensure_runtime_bundle() -> None:
    root = Path(__file__).resolve().parent
    parts_dir = root / "runtime_bundle"
    part_files = sorted(parts_dir.glob("part*.b64"))
    if not part_files:
        raise RuntimeError("RUNTIME_BUNDLE_PARTS_MISSING")

    encoded = "".join(path.read_text(encoding="ascii").strip() for path in part_files)
    data = base64.b64decode(encoded, validate=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        archive.extractall(root)


ensure_runtime_bundle()

from weather_bot.bot import main


if __name__ == "__main__":
    main()
