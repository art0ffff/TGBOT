from __future__ import annotations

import math
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as error:
    raise SystemExit(
        "Pillow is required. Run `pip install -r requirements.txt` first."
    ) from error


Color = tuple[int, int, int, int]

WIDTH = 320
HEIGHT = 192
FRAME_COUNT = 14
DURATION_MS = 90
ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "assets" / "weather"
PERIODS = ("day", "night")


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def blend_color(start: Color, end: Color, t: float) -> Color:
    return tuple(int(lerp(left, right, t)) for left, right in zip(start, end))


def make_gradient(top: Color, bottom: Color) -> Image.Image:
    image = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    last_row = max(HEIGHT - 1, 1)
    for y in range(HEIGHT):
        color = blend_color(top, bottom, y / last_row)
        draw.line((0, y, WIDTH, y), fill=color)
    return image


def add_ground(image: Image.Image, color: Color, height: int = 34) -> None:
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, HEIGHT - height, WIDTH, HEIGHT), fill=color)


def draw_hill(
    image: Image.Image,
    color: Color,
    crest: int,
    depth: int,
    wobble: int = 0,
) -> None:
    draw = ImageDraw.Draw(image)
    points = [
        (0, HEIGHT),
        (0, HEIGHT - depth),
        (WIDTH * 0.18, crest + wobble),
        (WIDTH * 0.46, crest + 12 - wobble),
        (WIDTH * 0.74, crest - 8 + wobble),
        (WIDTH, HEIGHT - depth + 6),
        (WIDTH, HEIGHT),
    ]
    draw.polygon(points, fill=color)


def draw_glow(image: Image.Image, x: float, y: float, radius: float, color: Color) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for step in range(5, 0, -1):
        scale = step / 5
        current_radius = radius * (1 + scale * 1.8)
        alpha = int(color[3] * scale * 0.22)
        current_color = (color[0], color[1], color[2], alpha)
        draw.ellipse(
            (
                x - current_radius,
                y - current_radius,
                x + current_radius,
                y + current_radius,
            ),
            fill=current_color,
        )
    image.alpha_composite(overlay)


def draw_sun(image: Image.Image, x: float, y: float, radius: float, phase: float) -> None:
    draw = ImageDraw.Draw(image)
    ray_color = (255, 212, 92, 255)
    glow_color = (255, 238, 170, 255)
    pulse = 1 + math.sin(phase) * 0.05
    outer_radius = radius * pulse
    draw_glow(image, x, y, radius * 1.3, (255, 226, 136, 200))
    for index in range(12):
        angle = phase / 3 + (index * math.tau / 12)
        inner = outer_radius + 12
        outer = inner + 14 + math.sin(phase + index) * 3
        x1 = x + math.cos(angle) * inner
        y1 = y + math.sin(angle) * inner
        x2 = x + math.cos(angle) * outer
        y2 = y + math.sin(angle) * outer
        draw.line((x1, y1, x2, y2), fill=ray_color, width=4)
    draw.ellipse(
        (x - outer_radius, y - outer_radius, x + outer_radius, y + outer_radius),
        fill=glow_color,
        outline=(255, 245, 200, 255),
        width=3,
    )


def draw_moon(
    image: Image.Image,
    x: float,
    y: float,
    radius: float,
    phase: float,
    sky_mask_color: Color,
) -> None:
    draw = ImageDraw.Draw(image)
    draw_glow(image, x, y, radius * 1.5, (214, 231, 255, 190))
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill=(247, 244, 228, 255),
        outline=(255, 252, 238, 255),
        width=2,
    )
    offset = radius * 0.42 + math.sin(phase) * 2
    draw.ellipse(
        (x - radius + offset, y - radius, x + radius + offset, y + radius),
        fill=sky_mask_color,
    )


def draw_stars(
    image: Image.Image,
    frame_index: int,
    count: int,
    tint: Color,
    max_y: int = 96,
) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for index in range(count):
        x = 10 + ((index * 37) % (WIDTH - 20))
        y = 10 + ((index * 23) % max_y)
        twinkle = 0.45 + 0.55 * math.sin(frame_index * 0.8 + index * 1.7)
        alpha = int(tint[3] * max(twinkle, 0.18))
        radius = 1 + (index % 3 == 0)
        color = (tint[0], tint[1], tint[2], alpha)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    image.alpha_composite(overlay)


def draw_cloud(
    image: Image.Image,
    x: float,
    y: float,
    scale: float,
    fill: Color,
    outline: Color | None = None,
) -> None:
    draw = ImageDraw.Draw(image)
    puffs = [
        (x, y + 14 * scale, 28 * scale),
        (x + 32 * scale, y, 24 * scale),
        (x + 62 * scale, y + 16 * scale, 30 * scale),
        (x + 96 * scale, y + 20 * scale, 22 * scale),
    ]
    for px, py, radius in puffs:
        draw.ellipse(
            (px - radius, py - radius, px + radius, py + radius),
            fill=fill,
            outline=outline,
        )
    base_top = y + 16 * scale
    draw.rounded_rectangle(
        (x - 16 * scale, base_top, x + 116 * scale, base_top + 34 * scale),
        radius=18 * scale,
        fill=fill,
        outline=outline,
    )


def draw_rain(image: Image.Image, frame_index: int, count: int, color: Color) -> None:
    draw = ImageDraw.Draw(image)
    for index in range(count):
        base_x = (index * 23 + frame_index * 9) % (WIDTH + 20) - 20
        base_y = (index * 17 + frame_index * 13) % HEIGHT
        length = 18 + (index % 3) * 4
        draw.line((base_x, base_y, base_x - 8, base_y + length), fill=color, width=3)


def draw_puddle_ripples(image: Image.Image, frame_index: int, color: Color) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for index in range(4):
        x = 48 + index * 68 + math.sin(frame_index / 2 + index) * 4
        y = 150 + (index % 2) * 8
        radius_x = 14 + ((frame_index + index * 2) % 5)
        radius_y = 4 + ((frame_index + index) % 3)
        draw.ellipse(
            (x - radius_x, y - radius_y, x + radius_x, y + radius_y),
            outline=color,
            width=2,
        )
    image.alpha_composite(overlay)


def draw_snow(image: Image.Image, frame_index: int, count: int, color: Color) -> None:
    draw = ImageDraw.Draw(image)
    for index in range(count):
        base_x = (index * 19 + frame_index * 4) % WIDTH
        drift = math.sin(frame_index / 2 + index * 0.7) * 6
        base_y = (index * 13 + frame_index * 11) % HEIGHT
        radius = 2 + (index % 2)
        draw.ellipse(
            (
                base_x + drift - radius,
                base_y - radius,
                base_x + drift + radius,
                base_y + radius,
            ),
            fill=color,
        )


def draw_snow_sparkles(image: Image.Image, frame_index: int, color: Color) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for index in range(8):
        x = 20 + ((index * 39 + frame_index * 5) % (WIDTH - 40))
        y = 132 + ((index * 11) % 18)
        alpha = 70 + int(60 * (0.5 + 0.5 * math.sin(frame_index + index)))
        sparkle = (color[0], color[1], color[2], alpha)
        draw.line((x - 2, y, x + 2, y), fill=sparkle, width=1)
        draw.line((x, y - 2, x, y + 2), fill=sparkle, width=1)
    image.alpha_composite(overlay)


def draw_wind_lines(image: Image.Image, frame_index: int, color: Color) -> None:
    draw = ImageDraw.Draw(image)
    for band in range(6):
        start_x = ((frame_index * 22) + band * 48) % (WIDTH + 80) - 80
        start_y = 48 + band * 18
        points: list[tuple[float, float]] = []
        for step in range(7):
            x = start_x + step * 24
            y = start_y + math.sin((frame_index + step + band) / 2) * 4
            points.append((x, y))
        draw.line(points, fill=color, width=4)


def draw_leaves(image: Image.Image, frame_index: int, color: Color) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for index in range(6):
        x = ((frame_index * 20) + index * 54) % (WIDTH + 40) - 20
        y = 112 + math.sin((frame_index + index) / 1.8) * 22
        draw.ellipse((x - 4, y - 2, x + 4, y + 2), fill=color)
    image.alpha_composite(overlay)


def draw_fog_bands(image: Image.Image, frame_index: int, color: Color) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for band in range(4):
        offset = ((frame_index * 14) + band * 62) % (WIDTH + 120) - 120
        top = 58 + band * 24
        draw.rounded_rectangle(
            (offset, top, offset + 220, top + 18),
            radius=10,
            fill=color,
        )
    image.alpha_composite(overlay)


def draw_heat_waves(image: Image.Image, frame_index: int, color: Color) -> None:
    draw = ImageDraw.Draw(image)
    for band in range(5):
        start_y = 88 + band * 16
        points: list[tuple[float, float]] = []
        for step in range(11):
            x = 18 + step * 28
            wave = math.sin((frame_index + step + band) / 1.7) * 5
            points.append((x, start_y + wave))
        draw.line(points, fill=color, width=3)


def draw_horizon_glow(image: Image.Image, color: Color) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.ellipse((-20, HEIGHT - 80, WIDTH + 20, HEIGHT + 10), fill=color)
    image.alpha_composite(overlay)


def add_flash(image: Image.Image, alpha: int) -> None:
    overlay = Image.new("RGBA", image.size, (255, 255, 255, alpha))
    image.alpha_composite(overlay)


def save_gif(name: str, frames: list[Image.Image]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prepared_frames = [
        frame.convert("P", palette=Image.ADAPTIVE, colors=96)
        for frame in frames
    ]
    output_path = OUTPUT_DIR / f"{name}.gif"
    prepared_frames[0].save(
        output_path,
        save_all=True,
        append_images=prepared_frames[1:],
        duration=DURATION_MS,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return output_path


def decorate_clear_sky(
    image: Image.Image,
    period: str,
    frame_index: int,
    phase: float,
    sky_top: Color,
) -> None:
    if period == "day":
        draw_sun(image, 84, 58, 28, phase)
    else:
        draw_stars(image, frame_index, count=26, tint=(255, 248, 216, 220))
        draw_moon(image, 244, 52, 24, phase, sky_top)


def sun_frames(period: str) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for frame_index in range(FRAME_COUNT):
        phase = frame_index / FRAME_COUNT * math.tau
        if period == "day":
            sky_top = (92, 190, 255, 255)
            sky_bottom = (243, 247, 185, 255)
            hill = (109, 182, 112, 255)
            ground = (82, 156, 94, 255)
            cloud_fill = (255, 255, 255, 235)
        else:
            sky_top = (24, 39, 83, 255)
            sky_bottom = (78, 99, 155, 255)
            hill = (43, 75, 95, 255)
            ground = (32, 56, 78, 255)
            cloud_fill = (174, 192, 214, 210)

        image = make_gradient(sky_top, sky_bottom)
        decorate_clear_sky(image, period, frame_index, phase, sky_top)
        draw_hill(image, hill, crest=124, depth=40, wobble=2)
        add_ground(image, ground)
        cloud_offset = math.sin(phase) * 8
        draw_cloud(image, 180 + cloud_offset, 42, 0.75, cloud_fill)
        frames.append(image)
    return frames


def cloud_frames(period: str) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for frame_index in range(FRAME_COUNT):
        if period == "day":
            sky_top = (125, 153, 186, 255)
            sky_bottom = (215, 224, 234, 255)
            hill = (102, 129, 116, 255)
            ground = (87, 111, 96, 255)
            fills = (
                (241, 244, 248, 235),
                (222, 228, 236, 245),
                (247, 248, 250, 230),
            )
        else:
            sky_top = (28, 39, 69, 255)
            sky_bottom = (73, 89, 122, 255)
            hill = (50, 67, 79, 255)
            ground = (38, 54, 63, 255)
            fills = (
                (142, 153, 170, 225),
                (119, 130, 149, 236),
                (161, 171, 186, 215),
            )

        image = make_gradient(sky_top, sky_bottom)
        if period == "night":
            draw_stars(image, frame_index, count=18, tint=(240, 236, 216, 145))
            draw_moon(image, 70, 48, 18, frame_index / 3, sky_top)
        draw_hill(image, hill, crest=134, depth=36)
        add_ground(image, ground)
        drift = frame_index * 3
        draw_cloud(image, 30 + drift % 22, 44, 0.95, fills[0])
        draw_cloud(image, 118 + (drift // 2) % 28, 66, 1.05, fills[1])
        draw_cloud(image, 224 + drift % 18, 38, 0.78, fills[2])
        frames.append(image)
    return frames


def rain_frames(period: str) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for frame_index in range(FRAME_COUNT):
        if period == "day":
            sky_top = (78, 98, 126, 255)
            sky_bottom = (151, 169, 187, 255)
            hill = (81, 106, 102, 255)
            ground = (63, 82, 84, 255)
            clouds = ((110, 122, 138, 255), (96, 108, 124, 255))
            rain_color = (126, 208, 255, 230)
            ripple_color = (178, 225, 255, 150)
        else:
            sky_top = (26, 30, 51, 255)
            sky_bottom = (71, 85, 121, 255)
            hill = (48, 61, 76, 255)
            ground = (28, 38, 52, 255)
            clouds = ((72, 81, 100, 255), (60, 69, 89, 255))
            rain_color = (140, 202, 255, 220)
            ripple_color = (119, 186, 247, 150)

        image = make_gradient(sky_top, sky_bottom)
        if period == "night":
            draw_stars(image, frame_index, count=12, tint=(235, 236, 222, 95), max_y=70)
            draw_moon(image, 260, 42, 16, frame_index / 2.5, sky_top)
        draw_hill(image, hill, crest=138, depth=38)
        add_ground(image, ground)
        draw_cloud(image, 24, 34, 1.15, clouds[0])
        draw_cloud(image, 154, 30, 1.05, clouds[1])
        draw_rain(image, frame_index, count=18, color=rain_color)
        draw_puddle_ripples(image, frame_index, ripple_color)
        frames.append(image)
    return frames


def snow_frames(period: str) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for frame_index in range(FRAME_COUNT):
        if period == "day":
            sky_top = (156, 180, 204, 255)
            sky_bottom = (231, 239, 246, 255)
            hill = (214, 225, 233, 255)
            ground = (240, 246, 250, 255)
            cloud_a = (222, 231, 239, 255)
            cloud_b = (230, 238, 244, 245)
        else:
            sky_top = (29, 44, 86, 255)
            sky_bottom = (99, 123, 166, 255)
            hill = (172, 190, 212, 255)
            ground = (225, 235, 245, 255)
            cloud_a = (166, 183, 205, 235)
            cloud_b = (182, 198, 220, 228)

        image = make_gradient(sky_top, sky_bottom)
        if period == "night":
            draw_stars(image, frame_index, count=20, tint=(245, 248, 255, 160))
            draw_moon(image, 242, 42, 18, frame_index / 2.2, sky_top)
        draw_hill(image, hill, crest=132, depth=36)
        add_ground(image, ground)
        draw_cloud(image, 36, 34, 1.05, cloud_a)
        draw_cloud(image, 166, 42, 0.92, cloud_b)
        draw_snow(image, frame_index, count=28, color=(255, 255, 255, 245))
        draw_snow_sparkles(image, frame_index, (255, 255, 255, 180))
        frames.append(image)
    return frames


def storm_frames(period: str) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for frame_index in range(FRAME_COUNT):
        if period == "day":
            sky_top = (53, 58, 86, 255)
            sky_bottom = (117, 117, 136, 255)
            hill = (60, 71, 88, 255)
            ground = (44, 52, 66, 255)
            clouds = ((66, 72, 91, 255), (57, 64, 81, 255))
        else:
            sky_top = (14, 16, 31, 255)
            sky_bottom = (49, 56, 84, 255)
            hill = (28, 35, 54, 255)
            ground = (20, 25, 39, 255)
            clouds = ((39, 45, 62, 255), (31, 37, 52, 255))

        image = make_gradient(sky_top, sky_bottom)
        if period == "night":
            draw_stars(image, frame_index, count=10, tint=(241, 244, 252, 80), max_y=60)
        draw_hill(image, hill, crest=138, depth=36)
        add_ground(image, ground)
        draw_cloud(image, 22, 28, 1.22, clouds[0])
        draw_cloud(image, 172, 40, 0.95, clouds[1])
        draw_rain(image, frame_index, count=16, color=(159, 212, 255, 200))

        if frame_index in {3, 4, 10}:
            draw = ImageDraw.Draw(image)
            lightning = [
                (184, 58),
                (164, 96),
                (182, 96),
                (156, 142),
                (218, 88),
                (192, 88),
            ]
            draw.polygon(lightning, fill=(255, 236, 124, 255))
            add_flash(image, 90 if period == "night" else 70)
        elif period == "night" and frame_index == 11:
            add_flash(image, 30)

        draw_puddle_ripples(image, frame_index, (138, 196, 243, 120))
        frames.append(image)
    return frames


def fog_frames(period: str) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for frame_index in range(FRAME_COUNT):
        if period == "day":
            sky_top = (163, 175, 179, 255)
            sky_bottom = (217, 224, 226, 255)
            hill = (140, 151, 152, 255)
            ground = (118, 129, 130, 255)
            cloud_a = (205, 211, 213, 185)
            cloud_b = (214, 220, 221, 175)
            fog_color = (234, 240, 242, 92)
        else:
            sky_top = (44, 55, 72, 255)
            sky_bottom = (103, 116, 135, 255)
            hill = (79, 90, 105, 255)
            ground = (62, 74, 88, 255)
            cloud_a = (154, 167, 180, 155)
            cloud_b = (173, 184, 194, 145)
            fog_color = (221, 231, 237, 74)

        image = make_gradient(sky_top, sky_bottom)
        if period == "night":
            draw_stars(image, frame_index, count=10, tint=(235, 236, 229, 82), max_y=55)
            draw_moon(image, 82, 46, 18, frame_index / 2.8, sky_top)
        draw_hill(image, hill, crest=136, depth=32)
        add_ground(image, ground)
        draw_cloud(image, 34, 48, 0.92, cloud_a)
        draw_cloud(image, 194, 42, 0.84, cloud_b)
        draw_fog_bands(image, frame_index, fog_color)
        frames.append(image)
    return frames


def wind_frames(period: str) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for frame_index in range(FRAME_COUNT):
        if period == "day":
            sky_top = (92, 160, 214, 255)
            sky_bottom = (210, 236, 255, 255)
            hill = (117, 170, 126, 255)
            ground = (88, 148, 100, 255)
            cloud_a = (243, 248, 252, 235)
            cloud_b = (235, 241, 247, 240)
            wind_color = (232, 247, 255, 200)
            leaf_color = (245, 199, 95, 190)
        else:
            sky_top = (24, 47, 86, 255)
            sky_bottom = (78, 115, 168, 255)
            hill = (58, 95, 88, 255)
            ground = (45, 78, 72, 255)
            cloud_a = (184, 206, 224, 215)
            cloud_b = (171, 192, 214, 225)
            wind_color = (220, 239, 255, 150)
            leaf_color = (194, 218, 132, 160)

        image = make_gradient(sky_top, sky_bottom)
        if period == "night":
            draw_stars(image, frame_index, count=18, tint=(239, 244, 251, 115))
            draw_moon(image, 248, 44, 16, frame_index / 2.5, sky_top)
        draw_hill(image, hill, crest=132, depth=38, wobble=2)
        add_ground(image, ground)
        shift = (frame_index * 10) % 120
        draw_cloud(image, -18 + shift, 50, 0.78, cloud_a)
        draw_cloud(image, 132 + shift // 2, 38, 0.92, cloud_b)
        draw_wind_lines(image, frame_index, wind_color)
        draw_leaves(image, frame_index, leaf_color)
        frames.append(image)
    return frames


def heat_frames(period: str) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for frame_index in range(FRAME_COUNT):
        phase = frame_index / FRAME_COUNT * math.tau
        if period == "day":
            sky_top = (255, 186, 93, 255)
            sky_bottom = (255, 234, 168, 255)
            hill = (202, 155, 86, 255)
            ground = (181, 123, 57, 255)
            wave_color = (255, 255, 255, 170)
        else:
            sky_top = (74, 34, 48, 255)
            sky_bottom = (161, 82, 63, 255)
            hill = (103, 58, 49, 255)
            ground = (86, 42, 36, 255)
            wave_color = (255, 216, 176, 145)

        image = make_gradient(sky_top, sky_bottom)
        if period == "day":
            draw_sun(image, 82, 56, 30, phase)
        else:
            draw_horizon_glow(image, (255, 171, 108, 80))
            draw_stars(image, frame_index, count=12, tint=(255, 227, 198, 85), max_y=65)
            draw_moon(image, 250, 40, 15, phase, sky_top)
        draw_hill(image, hill, crest=144, depth=30)
        add_ground(image, ground)
        draw_heat_waves(image, frame_index, wave_color)
        frames.append(image)
    return frames


def main() -> None:
    generators = {
        "sun": sun_frames,
        "cloud": cloud_frames,
        "rain": rain_frames,
        "snow": snow_frames,
        "storm": storm_frames,
        "fog": fog_frames,
        "wind": wind_frames,
        "heat": heat_frames,
    }
    for theme, factory in generators.items():
        for period in PERIODS:
            output_path = save_gif(f"{theme}_{period}", factory(period))
            print(output_path)


if __name__ == "__main__":
    main()
