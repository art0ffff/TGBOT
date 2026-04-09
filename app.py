from __future__ import annotations

import base64
import hashlib
from pathlib import Path

EXPECTED_SHA256 = "b04128b8235b3987f5659e6d065105a2eb5e4123e67030fa3b79034bf5da210f"
PART_COUNT = 7


def main() -> None:
    root = Path(__file__).resolve().parent
    encoded = "".join(
        (root / "runtime_parts" / f"part_{index:02d}.b64").read_text(encoding="ascii").strip()
        for index in range(PART_COUNT)
    )
    encoded += "=" * (-len(encoded) % 4)
    source = base64.b64decode(encoded)
    actual_sha256 = hashlib.sha256(source).hexdigest()
    if actual_sha256 != EXPECTED_SHA256:
        raise RuntimeError(f"Runtime bundle checksum mismatch: {actual_sha256}")

    globals_dict = {
        "__name__": "__main__",
        "__file__": str(root / "_runtime_weather_bot.py"),
        "__package__": None,
    }
    exec(compile(source.decode("utf-8"), globals_dict["__file__"], "exec"), globals_dict)


if __name__ == "__main__":
    main()
