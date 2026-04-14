from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "weather"
VERSION = "premium-v5"
MARKER = OUT / ".premium-gifs"
WIDTH = 384
HEIGHT = 216
FRAMES = 18
DURATION = 80
THEMES = ("sun", "cloud", "rain", "snow", "storm", "fog", "wind", "heat")
PERIODS = ("day", "night")


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float, alpha: int = 255) -> tuple[int, int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (alpha,)


def gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (WIDTH, HEIGHT))
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(HEIGHT):
        pixels.extend([mix(top, bottom, y / max(1, HEIGHT - 1))] * WIDTH)
    image.putdata(pixels)
    return image


def blur(image: Image.Image, radius: float) -> Image.Image:
    return image.filter(ImageFilter.GaussianBlur(radius))


def glow(image: Image.Image, x: float, y: float, rx: float, ry: float, rgba: tuple[int, int, int, int]) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for step in range(7, 0, -1):
        k = step / 7
        draw.ellipse((x - rx * (1 + k), y - ry * (1 + k), x + rx * (1 + k), y + ry * (1 + k)), fill=(*rgba[:3], round(rgba[3] * k * 0.18)))
    image.alpha_composite(blur(layer, 3.2))


def sun(image: Image.Image, frame: int, x: float = 88, y: float = 58, radius: float = 28) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    phase = frame / FRAMES * math.tau
    glow(image, x, y, radius * 2.3, radius * 1.8, (255, 210, 92, 210))
    halo = Image.new("RGBA", image.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo, "RGBA")
    for index in range(8):
        angle = phase * 0.18 + index * math.tau / 8
        hx = x + math.cos(angle) * radius * 0.36
        hy = y + math.sin(angle) * radius * 0.22
        hd.ellipse((hx - radius * 1.15, hy - radius * 0.76, hx + radius * 1.15, hy + radius * 0.76), fill=(255, 220, 104, 22))
    image.alpha_composite(blur(halo, 3.5))
    pulse = 1 + math.sin(phase) * 0.025
    r = radius * pulse
    for step in range(9, 0, -1):
        t = step / 9
        draw.ellipse((x - r * t, y - r * t, x + r * t, y + r * t), fill=mix((255, 156, 54), (255, 248, 184), 1 - t))


def moon(image: Image.Image, sky: tuple[int, int, int], frame: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    x, y, r = 292, 52, 24
    glow(image, x, y, 36, 30, (204, 224, 255, 170))
    draw.ellipse((x - r, y - r, x + r, y + r), fill=(247, 244, 228, 255))
    offset = 10 + math.sin(frame / FRAMES * math.tau) * 1.8
    draw.ellipse((x - r + offset, y - r, x + r + offset, y + r), fill=(*sky, 255))


def stars(image: Image.Image, frame: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for index in range(34):
        x = 16 + (index * 43) % (WIDTH - 32)
        y = 12 + (index * 29) % 92
        pulse = 0.35 + 0.65 * math.sin(frame * 0.55 + index * 1.3)
        r = 1.1 + (index % 8 == 0) * 0.9
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(244, 244, 225, round(45 + pulse * 120)))


def land(image: Image.Image, hill: tuple[int, int, int], ground: tuple[int, int, int], frame: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    wave = math.sin(frame / FRAMES * math.tau) * 1.6
    draw.polygon(((0, HEIGHT), (0, 166), (72, 138 + wave), (162, 154 - wave), (264, 132 + wave), (WIDTH, 160), (WIDTH, HEIGHT)), fill=(*hill, 255))
    draw.rectangle((0, 178, WIDTH, HEIGHT), fill=(*ground, 255))
    grass(image, ground, frame)


def grass(image: Image.Image, ground: tuple[int, int, int], frame: int, wind: bool = False) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    phase = frame / FRAMES * math.tau
    palette = (
        (max(20, ground[0] - 36), min(220, ground[1] + 32), max(20, ground[2] - 24), 190),
        (max(28, ground[0] - 14), min(235, ground[1] + 48), max(24, ground[2] - 10), 160),
        (min(190, ground[0] + 40), min(235, ground[1] + 62), min(170, ground[2] + 32), 120),
    )
    for index, x in enumerate(range(2, WIDTH, 5)):
        h = 9 + (index * 7) % 17
        base_y = HEIGHT - 4 - (index * 3) % 8
        push = ((index * 5) % 11) - 5
        if wind:
            push = 8 + math.sin(phase * 1.6 + index * 0.35) * 9
        draw.polygon(((x - 1.5, base_y), (x + push, max(176, base_y - h)), (x + 1.5, base_y)), fill=palette[index % len(palette)])
    image.alpha_composite(blur(layer, 0.25))


def cloud(image: Image.Image, x: float, y: float, scale: float, fill: tuple[int, int, int, int]) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    shadow = (max(0, fill[0] - 42), max(0, fill[1] - 42), max(0, fill[2] - 42), 26)
    for dx, dy, r in ((0, 15, 23), (31, 0, 29), (65, 12, 31), (99, 20, 24)):
        rr = r * scale
        cx = x + dx * scale
        cy = y + dy * scale
        draw.ellipse((cx - rr, cy - rr + 2, cx + rr, cy + rr + 2), fill=shadow)
        draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=fill)
        draw.ellipse((cx - rr * 0.35, cy - rr * 0.65, cx + rr * 0.15, cy - rr * 0.25), fill=(min(255, fill[0] + 22), min(255, fill[1] + 22), min(255, fill[2] + 22), min(92, fill[3])))
    base = y + 17 * scale
    draw.rounded_rectangle((x - 18 * scale, base, x + 122 * scale, base + 58 * scale), radius=20 * scale, fill=fill)
    image.alpha_composite(blur(layer, 0.35))


def rain_effect(image: Image.Image, frame: int, night: bool = False, storm: bool = False) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    total = 88 if not storm else 70
    color = (63, 125, 161, 180) if night else (49, 103, 131, 172)
    for index in range(total):
        y = (frame * (9 + index % 5) + index * 19) % 120 + 78
        x = 8 + (index * 37 + (index % 6) * 11) % (WIDTH - 16) + math.sin(frame * 0.38 + index) * 5
        if storm:
            x -= (y - 78) * 0.15
        rx = 1.4 + (index % 4) * 0.35
        ry = 4.8 + (index % 5) * 0.8
        draw.polygon(((x, y - ry * 1.2), (x - rx * 1.1, y - ry * 0.1), (x + rx * 0.9, y - ry * 0.25)), fill=color)
        draw.ellipse((x - rx, y - ry * 0.35, x + rx, y + ry), fill=color)
    for index in range(8):
        x = 28 + index * 44 + math.sin(frame * 0.32 + index) * 5
        y = 180 + (index % 3) * 7
        growth = ((frame + index * 2) % FRAMES) / FRAMES
        draw.ellipse((x - 9 - growth * 16, y - 2 - growth * 2, x + 9 + growth * 16, y + 3 + growth * 2), fill=(95, 150, 175, max(20, 70 - round(growth * 45))))
    image.alpha_composite(blur(layer, 0.25))


def snow_effect(image: Image.Image, frame: int, night: bool = False) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for index in range(70 if night else 54):
        x = (index * 23 + frame * (2.2 + index % 4)) % WIDTH
        y = (index * 17 + frame * (5.4 + index % 3)) % HEIGHT
        drift = math.sin(frame * 0.32 + index * 0.8) * 8
        r = 1.1 + (index % 4) * 0.45
        fill = (232, 244, 255, 210) if night else (255, 255, 255, 225)
        draw.ellipse((x + drift - r, y - r, x + drift + r, y + r), fill=fill)


def wind_effect(image: Image.Image, frame: int, night: bool = False) -> None:
    phase = frame / FRAMES * math.tau
    air = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(air, "RGBA")
    tint = (220, 239, 255, 26) if night else (236, 247, 255, 34)
    for pocket in range(30):
        x = (frame * (9 + pocket % 5) + pocket * 43) % (WIDTH + 70) - 35
        y = 36 + (pocket * 19) % 116 + math.sin(frame * 0.55 + pocket) * 7
        for puff in range(3):
            px = x - puff * (10 + pocket % 4)
            py = y + math.sin(frame * 0.4 + pocket + puff) * 3
            draw.ellipse((px - 10 - puff * 5, py - 3 - puff, px + 10 + puff * 5, py + 3 + puff), fill=tint)
    image.alpha_composite(blur(air, 2.4))
    leaf_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    leaf = ImageDraw.Draw(leaf_layer, "RGBA")
    colors = ((185, 144, 48, 185), (118, 152, 67, 178), (154, 102, 43, 165))
    for index in range(26):
        x = (frame * (10 + index % 5) + index * 37) % (WIDTH + 70) - 35
        y = 72 + math.sin(phase * 1.25 + index) * 30 + (index % 5) * 17
        a = phase * 2.0 + index * 0.72
        length = 6 + (index % 4) * 1.5
        w = length * 0.45
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        leaf.polygon(((x + ux * length, y + uy * length), (x + px * w, y + py * w), (x - ux * length * 0.5, y - uy * length * 0.5), (x - px * w, y - py * w)), fill=colors[index % len(colors)])
    image.alpha_composite(leaf_layer)


def fog_effect(image: Image.Image, frame: int) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for band in range(7):
        x = (frame * 7 + band * 72) % (WIDTH + 170) - 170
        y = 56 + band * 19
        draw.rounded_rectangle((x, y, x + 260, y + 18), radius=9, fill=(238, 244, 246, 86))
    image.alpha_composite(blur(layer, 1.4))


def heat_effect(image: Image.Image, frame: int, night: bool = False) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    phase = frame / FRAMES * math.tau
    if night:
        hill, ground, dust = (67, 35, 39, 116), (48, 28, 30, 136), (91, 51, 35)
    else:
        hill, ground, dust = (176, 116, 55, 118), (156, 94, 43, 78), (139, 78, 31)
    draw.polygon(((0, 159), (76, 148), (148, 155), (230, 143), (WIDTH, 157), (WIDTH, 181), (0, 181)), fill=hill)
    draw.polygon(((0, 180), (80, 171), (154, 176), (244, 166), (WIDTH, 175), (WIDTH, HEIGHT), (0, HEIGHT)), fill=ground)
    haze = Image.new("RGBA", image.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(haze, "RGBA")
    for band in range(7):
        y = 92 + band * 10
        drift = math.sin(phase * 1.15 + band) * 11
        for patch in range(5):
            x = -34 + patch * 95 + drift + math.sin(phase * 1.4 + patch + band) * 9
            hd.ellipse((x - 52, y - 7, x + 52, y + 7), fill=(255, 241, 183, 16 if not night else 10))
            hd.ellipse((x - 36, y - 3, x + 38, y + 3), fill=(*dust, 14 if not night else 10))
    image.alpha_composite(blur(haze, 3.5))
    for mote in range(80):
        x = (frame * (9 + mote % 6) + mote * 24) % (WIDTH + 100) - 50
        y = 124 + (mote * 17) % 76 + math.sin(phase * 1.45 + mote) * 5
        r = 0.8 + (mote % 5) * 0.3
        draw.ellipse((x - r * 1.5, y - r * 0.7, x + r * 1.5, y + r * 0.7), fill=(*dust, 50))
    grass(image, dust, frame, wind=True)


def palette(theme: str, period: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], tuple[int, int, int, int]]:
    day = {
        "sun": ((84, 184, 238), (228, 242, 196), (102, 176, 112), (73, 148, 90), (247, 249, 252, 235)),
        "cloud": ((124, 155, 188), (217, 226, 234), (99, 128, 116), (85, 110, 96), (228, 234, 241, 236)),
        "rain": ((76, 97, 126), (151, 170, 188), (80, 105, 103), (62, 82, 84), (105, 119, 138, 245)),
        "snow": ((156, 181, 205), (232, 240, 247), (210, 224, 235), (238, 246, 250), (224, 234, 242, 245)),
        "storm": ((51, 57, 85), (114, 115, 136), (59, 70, 88), (42, 52, 66), (61, 68, 87, 250)),
        "fog": ((163, 176, 180), (217, 225, 227), (140, 152, 154), (116, 130, 131), (207, 216, 219, 175)),
        "wind": ((90, 160, 215), (210, 236, 255), (116, 170, 126), (87, 148, 100), (238, 246, 252, 235)),
        "heat": ((255, 184, 91), (255, 232, 166), (198, 149, 82), (176, 118, 55), (255, 228, 151, 220)),
    }
    night = {
        "sun": ((23, 34, 72), (74, 96, 143), (45, 75, 91), (29, 55, 73), (154, 169, 190, 210)),
        "cloud": ((27, 38, 68), (77, 93, 124), (47, 67, 80), (36, 54, 64), (138, 151, 170, 225)),
        "rain": ((20, 26, 48), (66, 82, 120), (42, 55, 75), (27, 38, 52), (70, 80, 102, 245)),
        "snow": ((29, 44, 86), (99, 123, 166), (172, 190, 212), (225, 235, 245), (166, 183, 205, 235)),
        "storm": ((13, 15, 30), (47, 54, 82), (28, 35, 54), (20, 25, 39), (38, 44, 61, 250)),
        "fog": ((43, 55, 72), (102, 116, 135), (76, 90, 105), (60, 73, 86), (163, 176, 188, 160)),
        "wind": ((23, 47, 86), (78, 115, 168), (58, 95, 88), (43, 76, 71), (174, 197, 219, 220)),
        "heat": ((73, 34, 48), (161, 82, 63), (103, 58, 49), (86, 42, 36), (214, 146, 111, 185)),
    }
    return (night if period == "night" else day)[theme]


def frame(theme: str, period: str, frame_index: int) -> Image.Image:
    sky_top, sky_bottom, hill, ground, cloud_fill = palette(theme, period)
    night = period == "night"
    image = gradient(sky_top, sky_bottom)
    phase = frame_index / FRAMES * math.tau
    if night:
        stars(image, frame_index)
        moon(image, sky_top, frame_index)
    elif theme in {"sun", "cloud", "wind", "heat"}:
        sun(image, frame_index, WIDTH / 2 if theme == "sun" else 88, 74 if theme == "sun" else 58, 38 if theme == "sun" else 28)
    if theme != "snow":
        land(image, hill, ground, frame_index)
    if theme == "sun" and not night:
        cloud(image, 188 + math.sin(phase) * 7, 50, 0.74, cloud_fill)
    elif theme == "cloud":
        for x, y, sc in ((-18, 62, 0.9), (58, 48, 1.1), (146, 54, 1.05), (250, 48, 0.86)):
            cloud(image, x + math.sin(phase + sc) * 8, y, sc, cloud_fill)
    elif theme == "rain":
        for x, y, sc in ((18, 38, 1.18), (130, 34, 1.18), (238, 42, 0.92)):
            cloud(image, x + math.sin(phase) * 5, y, sc, cloud_fill)
        rain_effect(image, frame_index, night)
    elif theme == "snow":
        land(image, hill, ground, frame_index)
        cloud(image, 38, 42, 1.05, cloud_fill)
        cloud(image, 180, 50, 0.9, cloud_fill)
        snow_effect(image, frame_index, night)
    elif theme == "storm":
        for x, y, sc in ((12, 28, 1.22), (126, 24, 1.18), (238, 34, 0.98)):
            cloud(image, x + math.sin(phase) * 6, y, sc, cloud_fill)
        rain_effect(image, frame_index, night, storm=True)
        wind_effect(image, frame_index, night)
        if frame_index % 9 in {2, 3}:
            draw = ImageDraw.Draw(image, "RGBA")
            draw.polygon(((210, 58), (184, 112), (204, 106), (172, 164), (246, 88), (222, 92)), fill=(255, 237, 106, 210))
            image.alpha_composite(Image.new("RGBA", image.size, (255, 255, 255, 42 if night else 28)))
    elif theme == "fog":
        cloud(image, 40 + math.sin(phase) * 5, 56, 0.92, cloud_fill)
        cloud(image, 206 + math.cos(phase) * 5, 48, 0.84, cloud_fill)
        fog_effect(image, frame_index)
    elif theme == "wind":
        cloud(image, -40 + (frame_index * 16) % 160, 56, 0.82, cloud_fill)
        cloud(image, 118 + (frame_index * 9) % 150, 40, 0.96, cloud_fill)
        grass(image, ground, frame_index, wind=True)
        wind_effect(image, frame_index, night)
    elif theme == "heat":
        heat_effect(image, frame_index, night)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay, "RGBA")
    od.rectangle((0, HEIGHT - 34, WIDTH, HEIGHT), fill=(0, 0, 0, 14 if night else 7))
    image.alpha_composite(overlay)
    return image


def save_gif(name: str, frames: list[Image.Image]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    prepared = [image.convert("P", palette=Image.Palette.ADAPTIVE, colors=128) for image in frames]
    path = OUT / f"{name}.gif"
    prepared[0].save(path, save_all=True, append_images=prepared[1:], duration=DURATION, loop=0, disposal=2, optimize=False)
    return path


def assets_ready() -> bool:
    try:
        if MARKER.read_text(encoding="utf-8").strip() != VERSION:
            return False
        for theme in THEMES:
            if not (OUT / f"{theme}.gif").is_file():
                return False
            for period in PERIODS:
                path = OUT / f"{theme}_{period}.gif"
                if not path.is_file() or path.stat().st_size < 8_000:
                    return False
    except Exception:
        return False
    return True


def main() -> None:
    if assets_ready():
        print(MARKER)
        return
    generated: dict[tuple[str, str], list[Image.Image]] = {}
    for theme in THEMES:
        for period in PERIODS:
            frames = [frame(theme, period, index) for index in range(FRAMES)]
            generated[(theme, period)] = frames
            print(save_gif(f"{theme}_{period}", frames))
        print(save_gif(theme, generated[(theme, "day")]))
    MARKER.write_text(VERSION, encoding="utf-8")
    print(MARKER)


if __name__ == "__main__":
    main()
