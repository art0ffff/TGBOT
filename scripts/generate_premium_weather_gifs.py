from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "weather"
WIDTH = 384
HEIGHT = 216
SCALE = 2
FRAMES = 24
DURATION = 70
PERIODS = ("day", "night")
THEMES = ("sun", "cloud", "rain", "snow", "storm", "fog", "wind", "heat")


def s(value: float) -> int:
    return round(value * SCALE)


def box(values: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(s(value) for value in values)


def color(rgb: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return (*rgb, alpha)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float, alpha: int = 255) -> tuple[int, int, int, int]:
    return (round(lerp(a[0], b[0], t)), round(lerp(a[1], b[1], t)), round(lerp(a[2], b[2], t)), alpha)


def gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (WIDTH * SCALE, HEIGHT * SCALE))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT * SCALE):
        draw.line((0, y, WIDTH * SCALE, y), fill=mix(top, bottom, y / max(1, HEIGHT * SCALE - 1)))
    return image


def blur_layer(base: Image.Image, radius: float) -> Image.Image:
    return base.filter(ImageFilter.GaussianBlur(s(radius)))


def glow(image: Image.Image, x: float, y: float, radius: float, rgba: tuple[int, int, int, int]) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for step in range(7, 0, -1):
        scale = step / 7
        r = radius * (1.0 + 2.0 * scale)
        alpha = round(rgba[3] * scale * 0.18)
        draw.ellipse(box((x - r, y - r, x + r, y + r)), fill=(rgba[0], rgba[1], rgba[2], alpha))
    image.alpha_composite(blur_layer(layer, 2.0))


def draw_sun(image: Image.Image, frame: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    x, y = 90, 56
    phase = frame / FRAMES * math.tau
    glow(image, x, y, 30 + math.sin(phase) * 2, color((255, 221, 118), 240))
    for index in range(16):
        angle = phase * 0.6 + index * math.tau / 16
        inner = 35
        outer = 51 + math.sin(phase + index) * 3
        draw.line(
            (s(x + math.cos(angle) * inner), s(y + math.sin(angle) * inner), s(x + math.cos(angle) * outer), s(y + math.sin(angle) * outer)),
            fill=color((255, 218, 88), 245),
            width=s(3.2),
        )
    pulse = 1 + math.sin(phase) * 0.035
    r = 25 * pulse
    draw.ellipse(box((x - r, y - r, x + r, y + r)), fill=color((255, 240, 151)), outline=color((255, 250, 205)), width=s(2))


def draw_moon(image: Image.Image, sky: tuple[int, int, int], frame: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    x, y, r = 296, 52, 24
    phase = frame / FRAMES * math.tau
    glow(image, x, y, r * 1.1, color((210, 230, 255), 190))
    draw.ellipse(box((x - r, y - r, x + r, y + r)), fill=color((248, 245, 226)), outline=color((255, 253, 238)), width=s(1.5))
    offset = 10 + math.sin(phase) * 1.5
    draw.ellipse(box((x - r + offset, y - r, x + r + offset, y + r)), fill=color(sky))


def draw_stars(image: Image.Image, frame: int, tint: tuple[int, int, int] = (255, 246, 218)) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for index in range(36):
        x = 14 + (index * 41) % (WIDTH - 28)
        y = 10 + (index * 29) % 90
        alpha = 70 + round(150 * (0.5 + 0.5 * math.sin(frame * 0.65 + index * 1.37)))
        r = 1.2 + (index % 10 == 0)
        draw.ellipse(box((x - r, y - r, x + r, y + r)), fill=(*tint, alpha))


def draw_land(image: Image.Image, hill: tuple[int, int, int], ground: tuple[int, int, int], frame: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    wobble = math.sin(frame / FRAMES * math.tau) * 2
    draw.polygon(
        [(s(0), s(HEIGHT)), (s(0), s(164)), (s(68), s(132 + wobble)), (s(154), s(148 - wobble)), (s(260), s(126 + wobble)), (s(WIDTH), s(158)), (s(WIDTH), s(HEIGHT))],
        fill=color(hill),
    )
    draw.rectangle(box((0, 178, WIDTH, HEIGHT)), fill=color(ground))
    for x in range(18, WIDTH, 58):
        shade = tuple(max(0, c - 26) for c in ground)
        draw.line((s(x), s(183), s(x + 34), s(174)), fill=color(shade, 90), width=s(1.2))


def draw_cloud(image: Image.Image, x: float, y: float, scale: float, fill: tuple[int, int, int], alpha: int = 235) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    rgba = (*fill, alpha)
    for dx, dy, r in ((0, 15, 23), (31, 0, 29), (65, 12, 31), (99, 20, 24)):
        rr = r * scale
        cx = x + dx * scale
        cy = y + dy * scale
        draw.ellipse(box((cx - rr, cy - rr, cx + rr, cy + rr)), fill=rgba)
    draw.rounded_rectangle(box((x - 18 * scale, y + 17 * scale, x + 122 * scale, y + 58 * scale)), radius=s(20 * scale), fill=rgba)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow, "RGBA")
    shadow_draw.rounded_rectangle(box((x - 16 * scale, y + 39 * scale, x + 118 * scale, y + 58 * scale)), radius=s(13 * scale), fill=(0, 0, 0, 28))
    image.alpha_composite(blur_layer(shadow, 1.3))
    image.alpha_composite(layer)


def draw_rain(image: Image.Image, frame: int, count: int, rgba: tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for index in range(count):
        x = (index * 21 + frame * 10) % (WIDTH + 40) - 35
        y = (index * 17 + frame * 14) % HEIGHT
        length = 18 + (index % 4) * 4
        draw.line((s(x), s(y), s(x - 8), s(y + length)), fill=rgba, width=s(2.3))
    for index in range(6):
        x = 34 + index * 62 + math.sin(frame * 0.35 + index) * 4
        y = 166 + (index % 2) * 7
        draw.ellipse(box((x - 17, y - 4, x + 17, y + 4)), outline=(185, 228, 255, 130), width=s(1.3))


def draw_snow(image: Image.Image, frame: int) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for index in range(44):
        x = (index * 17 + frame * 3.2) % WIDTH
        y = (index * 13 + frame * 7.8) % HEIGHT
        drift = math.sin(frame * 0.45 + index * 0.72) * 7
        r = 1.8 + (index % 3) * 0.55
        draw.ellipse(box((x + drift - r, y - r, x + drift + r, y + r)), fill=(255, 255, 255, 238))
    for index in range(8):
        x = 18 + ((index * 43 + frame * 4) % (WIDTH - 36))
        y = 154 + (index * 11) % 23
        draw.line((s(x - 2), s(y), s(x + 2), s(y)), fill=(255, 255, 255, 135), width=s(1))
        draw.line((s(x), s(y - 2), s(x), s(y + 2)), fill=(255, 255, 255, 135), width=s(1))


def draw_wind(image: Image.Image, frame: int, rgba: tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for band in range(7):
        start_x = (frame * 18 + band * 54) % (WIDTH + 120) - 120
        y = 50 + band * 18
        points = [(s(start_x + step * 26), s(y + math.sin((frame + step + band) * 0.62) * 4)) for step in range(9)]
        draw.line(points, fill=rgba, width=s(3))
    for index in range(9):
        x = (frame * 17 + index * 49) % (WIDTH + 40) - 20
        y = 113 + math.sin((frame + index) * 0.55) * 24
        draw.ellipse(box((x - 5, y - 2.2, x + 5, y + 2.2)), fill=(223, 181, 74, 170))


def draw_fog(image: Image.Image, frame: int) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for band in range(6):
        x = (frame * 8 + band * 72) % (WIDTH + 170) - 170
        y = 58 + band * 20
        draw.rounded_rectangle(box((x, y, x + 248, y + 17)), radius=s(9), fill=(238, 244, 246, 86))
    image.alpha_composite(blur_layer(layer, 1.2))


def draw_heat(image: Image.Image, frame: int, rgba: tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for band in range(6):
        y = 88 + band * 14
        points = [(s(20 + step * 27), s(y + math.sin((frame + step + band) * 0.62) * 5)) for step in range(12)]
        draw.line(points, fill=rgba, width=s(2.4))


def palette(theme: str, period: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    if period == "night":
        values = {
            "sun": ((23, 34, 72), (74, 96, 143), (45, 75, 91), (29, 55, 73), (154, 169, 190)),
            "cloud": ((27, 38, 68), (77, 93, 124), (47, 67, 80), (36, 54, 64), (138, 151, 170)),
            "rain": ((20, 26, 48), (66, 82, 120), (42, 55, 75), (27, 38, 52), (70, 80, 102)),
            "snow": ((29, 44, 86), (99, 123, 166), (172, 190, 212), (225, 235, 245), (166, 183, 205)),
            "storm": ((13, 15, 30), (47, 54, 82), (28, 35, 54), (20, 25, 39), (38, 44, 61)),
            "fog": ((43, 55, 72), (102, 116, 135), (76, 90, 105), (60, 73, 86), (163, 176, 188)),
            "wind": ((23, 47, 86), (78, 115, 168), (58, 95, 88), (43, 76, 71), (174, 197, 219)),
            "heat": ((73, 34, 48), (161, 82, 63), (103, 58, 49), (86, 42, 36), (214, 146, 111)),
        }
    else:
        values = {
            "sun": ((78, 178, 238), (235, 242, 190), (104, 176, 113), (73, 148, 90), (247, 249, 252)),
            "cloud": ((124, 155, 188), (217, 226, 234), (99, 128, 116), (85, 110, 96), (228, 234, 241)),
            "rain": ((76, 97, 126), (151, 170, 188), (80, 105, 103), (62, 82, 84), (105, 119, 138)),
            "snow": ((156, 181, 205), (232, 240, 247), (210, 224, 235), (238, 246, 250), (224, 234, 242)),
            "storm": ((51, 57, 85), (114, 115, 136), (59, 70, 88), (42, 52, 66), (61, 68, 87)),
            "fog": ((163, 176, 180), (217, 225, 227), (140, 152, 154), (116, 130, 131), (207, 216, 219)),
            "wind": ((90, 160, 215), (210, 236, 255), (116, 170, 126), (87, 148, 100), (238, 246, 252)),
            "heat": ((255, 184, 91), (255, 232, 166), (198, 149, 82), (176, 118, 55), (255, 228, 151)),
        }
    return values[theme]


def frame(theme: str, period: str, frame_index: int) -> Image.Image:
    sky_top, sky_bottom, hill, ground, cloud = palette(theme, period)
    image = gradient(sky_top, sky_bottom)
    phase = frame_index / FRAMES * math.tau
    if period == "night":
        draw_stars(image, frame_index)
        draw_moon(image, sky_top, frame_index)
    else:
        if theme in {"sun", "cloud", "wind", "heat"}:
            draw_sun(image, frame_index)
    draw_land(image, hill, ground, frame_index)
    if theme in {"sun", "cloud", "rain", "snow", "storm", "fog", "wind"}:
        draw_cloud(image, 34 + math.sin(phase) * 9, 45, 1.02, cloud)
        draw_cloud(image, 171 + math.cos(phase * 0.8) * 13, 40, 0.88, cloud, 224)
        if theme == "cloud":
            draw_cloud(image, 238 + math.sin(phase * 0.9 + 2) * 10, 66, 0.82, cloud, 188)
    if theme == "rain":
        draw_rain(image, frame_index, 30, (125, 207, 255, 220))
    elif theme == "snow":
        draw_snow(image, frame_index)
    elif theme == "storm":
        draw_rain(image, frame_index, 22, (156, 212, 255, 195))
        if frame_index in {4, 5, 13, 14, 15}:
            draw = ImageDraw.Draw(image, "RGBA")
            draw.polygon([(s(212), s(62)), (s(186), s(104)), (s(208), s(104)), (s(174), s(156)), (s(247), s(89)), (s(218), s(92))], fill=(255, 235, 109, 255))
            draw.rectangle((0, 0, WIDTH * SCALE, HEIGHT * SCALE), fill=(255, 255, 255, 48 if period == "day" else 70))
    elif theme == "fog":
        draw_fog(image, frame_index)
    elif theme == "wind":
        draw_wind(image, frame_index, (232, 247, 255, 185 if period == "day" else 150))
    elif theme == "heat":
        draw_heat(image, frame_index, (255, 255, 255, 150 if period == "day" else 112))
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def save_gif(theme: str, period: str) -> Path:
    frames = [frame(theme, period, index) for index in range(FRAMES)]
    prepared = [image.convert("P", palette=Image.Palette.ADAPTIVE, colors=128) for image in frames]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{theme}_{period}.gif"
    prepared[0].save(path, save_all=True, append_images=prepared[1:], duration=DURATION, loop=0, disposal=2, optimize=False)
    return path


def main() -> None:
    for theme in THEMES:
        for period in PERIODS:
            print(save_gif(theme, period))


if __name__ == "__main__":
    main()
