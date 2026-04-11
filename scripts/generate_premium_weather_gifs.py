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
SCALE = 2
FRAMES = 24
DURATION = 70
THEMES = ("sun", "cloud", "rain", "snow", "storm", "fog", "wind", "heat")
PERIODS = ("day", "night")


def s(value: float) -> int:
    return round(value * SCALE)


def box(values):
    return tuple(s(v) for v in values)


def mix(a, b, t, alpha=255):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (alpha,)


def gradient(top, bottom):
    image = Image.new("RGBA", (WIDTH * SCALE, HEIGHT * SCALE))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT * SCALE):
        draw.line((0, y, WIDTH * SCALE, y), fill=mix(top, bottom, y / max(1, HEIGHT * SCALE - 1)))
    return image


def blur(image, radius):
    return image.filter(ImageFilter.GaussianBlur(s(radius)))


def glow(image, x, y, radius, rgba):
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for step in range(7, 0, -1):
        r = radius * (1 + step / 2.4)
        draw.ellipse(box((x - r, y - r, x + r, y + r)), fill=(*rgba[:3], round(rgba[3] * step / 55)))
    image.alpha_composite(blur(layer, 2.0))


def sun(image, frame, x=90, y=56, radius=30):
    draw = ImageDraw.Draw(image, "RGBA")
    phase = frame / FRAMES * math.tau
    glow(image, x, y, radius, (255, 220, 100, 240))
    for index in range(16):
        a = phase * 0.6 + index * math.tau / 16
        draw.line((s(x + math.cos(a) * (radius + 5)), s(y + math.sin(a) * (radius + 5)), s(x + math.cos(a) * (radius + 22)), s(y + math.sin(a) * (radius + 22))), fill=(255, 220, 84, 230), width=s(3))
    r = (radius - 5) * (1 + math.sin(phase) * 0.035)
    draw.ellipse(box((x - r, y - r, x + r, y + r)), fill=(255, 241, 152, 255), outline=(255, 252, 205, 255), width=s(2))


def moon(image, sky, frame):
    draw = ImageDraw.Draw(image, "RGBA")
    x, y, r = 296, 52, 24
    glow(image, x, y, r, (210, 230, 255, 190))
    draw.ellipse(box((x - r, y - r, x + r, y + r)), fill=(248, 246, 227, 255), outline=(255, 254, 238, 255), width=s(1.5))
    draw.ellipse(box((x - r + 10, y - r, x + r + 10, y + r)), fill=(*sky, 255))


def stars(image, frame):
    draw = ImageDraw.Draw(image, "RGBA")
    for index in range(38):
        x = 14 + (index * 41) % (WIDTH - 28)
        y = 10 + (index * 29) % 92
        alpha = 95 + round(130 * (0.5 + 0.5 * math.sin(frame * 0.55 + index)))
        r = 1.2 + (index % 10 == 0)
        draw.ellipse(box((x - r, y - r, x + r, y + r)), fill=(255, 246, 218, alpha))


def land(image, hill, ground, frame):
    draw = ImageDraw.Draw(image, "RGBA")
    wobble = math.sin(frame / FRAMES * math.tau) * 2
    draw.polygon([(0, s(HEIGHT)), (0, s(164)), (s(68), s(132 + wobble)), (s(154), s(148 - wobble)), (s(260), s(126 + wobble)), (s(WIDTH), s(158)), (s(WIDTH), s(HEIGHT))], fill=(*hill, 255))
    draw.rectangle(box((0, 178, WIDTH, HEIGHT)), fill=(*ground, 255))
    shade = tuple(max(0, c - 28) for c in ground)
    for x in range(18, WIDTH, 58):
        draw.line((s(x), s(183), s(x + 34), s(174)), fill=(*shade, 90), width=s(1.2))


def cloud(image, x, y, scale, fill, alpha=235):
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for dx, dy, r in ((0, 15, 23), (31, 0, 29), (65, 12, 31), (99, 20, 24)):
        rr = r * scale
        cx = x + dx * scale
        cy = y + dy * scale
        draw.ellipse(box((cx - rr, cy - rr, cx + rr, cy + rr)), fill=(*fill, alpha))
    draw.rounded_rectangle(box((x - 18 * scale, y + 17 * scale, x + 122 * scale, y + 58 * scale)), radius=s(20 * scale), fill=(*fill, alpha))
    image.alpha_composite(blur(layer, 0.55))


def dense_clouds(image, frame, fill, night=False):
    phase = frame / FRAMES * math.tau
    back = tuple(max(0, c - (18 if night else 8)) for c in fill)
    front = tuple(min(255, c + (18 if night else 12)) for c in fill)
    shade = tuple(max(0, c - 34) for c in fill)
    drift = math.sin(phase * 0.65) * 5
    for x, y, sc, col, a in ((-34, 52, .94, shade, 184), (26, 42, 1.14, back, 238), (110, 39, 1.10, back, 245), (202, 44, 1.05, back, 238), (292, 54, .90, shade, 178), (42, 74, 1.0, front, 246), (134, 72, 1.05, front, 250), (232, 76, .96, front, 240)):
        cloud(image, x + drift, y, sc, col, a)


def sun_clouds(image, frame, fill):
    phase = frame / FRAMES * math.tau
    back = tuple(min(255, c + 8) for c in fill)
    front = tuple(min(255, c + 20) for c in fill)
    shade = tuple(max(0, c - 18) for c in fill)
    left = math.sin(phase * .8) * 4
    right = math.cos(phase * .8) * 4
    for x, y, sc, col, a in ((-30 + left, 104, .68, shade, 96), (28 + left, 96, .8, back, 205), (82 + left, 93, .72, back, 212), (111 + left, 113, .46, front, 220), (203 + right, 93, .72, back, 212), (260 + right, 96, .8, back, 205), (324 + right, 104, .68, shade, 96), (231 + right, 113, .46, front, 220)):
        cloud(image, x, y, sc, col, a)


def rain_clouds(image, frame, night=False):
    phase = frame / FRAMES * math.tau
    dark, mid, light = ((42, 48, 63), (62, 70, 88), (82, 92, 111)) if night else ((79, 88, 101), (105, 116, 130), (132, 144, 157))
    drift = math.sin(phase * .55) * 5
    for x, y, sc, col, a in ((-44, 38, .96, dark, 240), (20, 30, 1.18, mid, 250), (114, 26, 1.16, mid, 250), (216, 31, 1.08, dark, 244), (300, 43, .88, dark, 228), (58, 63, .94, light, 230), (154, 60, 1.0, light, 236), (254, 66, .84, light, 218)):
        cloud(image, x + drift, y, sc, col, a)


def rain(image, frame, night=False, storm=False):
    draw = ImageDraw.Draw(image, "RGBA")
    total = 76 if storm else 96
    for index in range(total):
        fall = (frame * (8.4 + index % 5 * 1.35) + index * 19) % 106
        sway = math.sin(frame * .38 + index) * 5 + ((index * 7) % 11 - 5) * .65
        x = 8 + (index * 37 + (index % 6) * 11) % (WIDTH - 16) + sway - (fall * .16 if storm else 0)
        y = 82 + fall + math.sin(index * 1.8) * 2
        size = .8 + (index % 5) * .15
        slant = 1.55 + (index % 4) * .24 + (.5 if storm else 0)
        drop = (63, 125, 161, 174) if night else (49, 103, 131, 168)
        top = (x + slant * .55, y - size * 2.2)
        left = (x - size * .95, y - size * .15)
        right = (x + size * .92, y - size * .35)
        bottom = (x - slant * .3, y + size * 1.15)
        draw.polygon([(s(top[0]), s(top[1])), (s(left[0]), s(left[1])), (s(bottom[0]), s(bottom[1])), (s(right[0]), s(right[1]))], fill=drop)
        draw.ellipse(box((x - size, y - size * .35, x + size * .92, y + size * 1.55)), fill=drop)
    for index in range(10):
        x = 22 + index * 38 + math.sin(frame * .32 + index) * 5
        y = 179 + (index % 3) * 8
        grow = ((frame + index * 2) % FRAMES) / FRAMES
        draw.ellipse(box((x - 11 - grow * 12, y - 3, x + 11 + grow * 12, y + 4)), fill=(60, 115, 145, 64), outline=(160, 210, 235, 110), width=s(1))


def snow_scene(image, frame, night=False):
    draw = ImageDraw.Draw(image, "RGBA")
    if night:
        draw.rectangle((0, s(150), WIDTH * SCALE, HEIGHT * SCALE), fill=(31, 53, 78, 150))
        pine = (20, 45, 45, 230)
    else:
        draw.rectangle((0, s(150), WIDTH * SCALE, HEIGHT * SCALE), fill=(202, 224, 239, 255))
        pine = (67, 117, 100, 230)
    for x in range(24, WIDTH, 58):
        h = 28 + (x % 5) * 4
        draw.polygon([(s(x), s(132)), (s(x - 18), s(168)), (s(x + 18), s(168))], fill=pine)
        draw.polygon([(s(x), s(145)), (s(x - 24), s(181)), (s(x + 24), s(181))], fill=pine)
        draw.line((s(x - 14), s(150), s(x + 12), s(148)), fill=(245, 250, 255, 215), width=s(2))
        draw.line((s(x - 19), s(164), s(x + 18), s(162)), fill=(245, 250, 255, 225), width=s(2))
    wave = math.sin(frame / FRAMES * math.tau) * 1.5
    for y, col in ((158 + wave, (226, 238, 246, 255)), (176 - wave, (238, 246, 250, 255)), (193, (248, 252, 255, 255))):
        draw.polygon([(0, s(y)), (s(70), s(y - 6)), (s(144), s(y - 1)), (s(230), s(y - 8)), (s(WIDTH), s(y - 3)), (s(WIDTH), s(HEIGHT)), (0, s(HEIGHT))], fill=col)
    sx, sy = 305, 182
    draw.ellipse(box((sx - 18, sy - 18, sx + 18, sy + 18)), fill=(250, 253, 255, 255), outline=(195, 210, 225, 160), width=s(1))
    draw.ellipse(box((sx - 13, sy - 40, sx + 13, sy - 14)), fill=(250, 253, 255, 255), outline=(195, 210, 225, 160), width=s(1))
    draw.ellipse(box((sx - 4, sy - 31, sx - 2, sy - 29)), fill=(18, 28, 38, 255))
    draw.ellipse(box((sx + 4, sy - 31, sx + 6, sy - 29)), fill=(18, 28, 38, 255))
    draw.polygon([(s(sx + 1), s(sy - 27)), (s(sx + 13), s(sy - 25)), (s(sx + 1), s(sy - 23))], fill=(231, 110, 48, 255))
    for index in range(58):
        x = (index * 23 + frame * (2.1 + index % 4)) % WIDTH
        y = (index * 17 + frame * (5 + index % 3)) % HEIGHT
        drift = math.sin(frame * .35 + index) * 7
        r = 1.1 + (index % 4) * .35
        draw.ellipse(box((x + drift - r, y - r, x + drift + r, y + r)), fill=(255, 255, 255, 220))
        if index % 7 == 0:
            draw.line((s(x + drift - 2), s(y), s(x + drift + 2), s(y)), fill=(255, 255, 255, 150), width=1)
            draw.line((s(x + drift), s(y - 2), s(x + drift), s(y + 2)), fill=(255, 255, 255, 150), width=1)


def lightning(image, frame, night=False):
    cycle = frame % 12
    if cycle > 7:
        return
    progress = min(1, (cycle + 1) / 6)
    fade = 1 if cycle <= 5 else max(0, 1 - (cycle - 5) / 2)
    points = [(206, 58), (189, 82), (204, 84), (178, 118), (196, 115), (166, 158)] if cycle < 4 else [(248, 56), (226, 82), (240, 84), (212, 120), (229, 117), (200, 158)]
    visible = [points[0]]
    for a, b in zip(points, points[1:]):
        if len(visible) / len(points) <= progress:
            visible.append(b)
    draw = ImageDraw.Draw(image, "RGBA")
    if len(visible) > 1:
        draw.line([(s(x), s(y)) for x, y in visible], fill=(255, 230, 95, round((230 if night else 210) * fade)), width=s(5))
        draw.line([(s(x), s(y)) for x, y in visible], fill=(255, 252, 190, round(245 * fade)), width=s(2))


def fog(image, frame):
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    for band in range(7):
        x = (frame * 8 + band * 72) % (WIDTH + 170) - 170
        y = 56 + band * 19
        draw.rounded_rectangle(box((x, y, x + 260, y + 18)), radius=s(9), fill=(238, 244, 246, 86))
    image.alpha_composite(blur(layer, 1.4))


def natural_wind(image, frame, night=False):
    draw = ImageDraw.Draw(image, "RGBA")
    phase = frame / FRAMES * math.tau
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gust = ImageDraw.Draw(layer, "RGBA")
    for cloud_index in range(10):
        cx = (frame * (10 + cloud_index % 4) + cloud_index * 50) % (WIDTH + 150) - 75
        cy = 70 + (cloud_index * 19) % 90
        for puff in range(6):
            px = cx - puff * 14 + math.sin(phase + puff) * 4
            py = cy + math.sin(phase * 1.3 + cloud_index + puff) * 3
            gust.ellipse(box((px - 20 - puff * 4, py - 4 - puff, px + 20 + puff * 4, py + 4 + puff)), fill=(210, 238, 246, 34 if not night else 26))
    image.alpha_composite(blur(layer, 1.6))
    grass = ((54, 119, 72, 220), (67, 139, 83, 210), (91, 154, 83, 185)) if not night else ((50, 84, 63, 220), (76, 111, 75, 205), (104, 126, 82, 180))
    for tuft in range(38):
        base_x = 2 + tuft * 10
        base_y = 190 + (tuft % 5) * 4
        for blade in range(4):
            length = 12 + ((tuft + blade) % 6) * 2
            push = 8 + math.sin(phase * 1.45 + tuft * .38 + blade) * 5
            draw.line((s(base_x + blade * 2), s(base_y), s(base_x + push * .45), s(base_y - length * .55), s(base_x + push), s(base_y - length)), fill=grass[(tuft + blade) % len(grass)], width=max(1, s(.75)))
    for index in range(28):
        x = (frame * (8 + index % 5) + index * 37) % (WIDTH + 70) - 35
        y = 68 + math.sin(phase * 1.25 + index) * 30 + (index % 5) * 17
        a = phase * 2 + index * .72
        length = 7 + (index % 4) * 1.4
        w = length * .45
        leaf = (187, 148, 48, 190) if index % 4 else (118, 152, 67, 190)
        cx, cy = x + math.cos(a) * 6, y + math.sin(a * .8) * 5
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy, ux
        draw.polygon([(s(cx + ux * length), s(cy + uy * length)), (s(cx + px * w), s(cy + py * w)), (s(cx - ux * length * .55), s(cy - uy * length * .55)), (s(cx - px * w), s(cy - py * w))], fill=leaf)


def tumbleweed(draw, x, y, r, angle, alpha):
    draw.ellipse(box((x - r, y + r * .55, x + r, y + r * .8)), fill=(58, 38, 20, 60))
    cols = ((104, 67, 33, alpha), (145, 91, 42, max(95, alpha - 35)), (190, 132, 63, max(80, alpha - 55)))
    for ring in (1, .72, .48):
        rr = r * ring
        for k in range(3):
            start = math.degrees(angle) + k * 118
            draw.arc(box((x - rr, y - rr, x + rr, y + rr)), start=start, end=start + 94, fill=cols[k], width=max(1, s(.7)))
    for branch in range(20):
        a = angle + branch * math.tau / 20
        draw.line((s(x + math.cos(a) * r * .12), s(y + math.sin(a) * r * .12), s(x + math.cos(a + math.sin(angle + branch) * .2) * r * .8), s(y + math.sin(a + math.sin(angle + branch) * .2) * r * .8)), fill=cols[branch % 3], width=1)


def heat(image, frame, night=False):
    draw = ImageDraw.Draw(image, "RGBA")
    phase = frame / FRAMES * math.tau
    if night:
        hill, ground, dust_col, grass_cols = (67, 35, 39, 116), (48, 28, 30, 136), (91, 51, 35), ((48, 30, 23, 210), (68, 42, 27, 185), (93, 59, 32, 150))
    else:
        hill, ground, dust_col, grass_cols = (176, 116, 55, 118), (156, 94, 43, 78), (139, 78, 31), ((116, 72, 28, 188), (150, 100, 38, 170), (191, 146, 64, 158))
    draw.polygon([(0, s(159)), (s(76), s(148)), (s(148), s(155)), (s(230), s(143)), (s(WIDTH), s(157)), (s(WIDTH), s(181)), (0, s(181))], fill=hill)
    draw.polygon([(0, s(180)), (s(80), s(171)), (s(154), s(176)), (s(244), s(166)), (s(WIDTH), s(175)), (s(WIDTH), s(HEIGHT)), (0, s(HEIGHT))], fill=ground)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    dust = ImageDraw.Draw(layer, "RGBA")
    for cloud_index in range(12):
        cx = (frame * (14 + cloud_index % 5) + cloud_index * 47) % (WIDTH + 160) - 80
        cy = 134 + (cloud_index * 11) % 55 + math.sin(phase * 1.15 + cloud_index) * 6
        for puff in range(8):
            px = cx - puff * (10 + cloud_index % 4 * 4) + math.sin(phase * 1.2 + puff) * 5
            py = cy + math.sin(phase * 1.35 + puff) * 4 + puff
            dust.ellipse(box((px - 15 - puff * 6, py - 5 - puff, px + 15 + puff * 6, py + 5 + puff)), fill=(*dust_col, max(11, 58 - puff * 6)))
    image.alpha_composite(blur(layer, 1.65))
    for tuft in range(62):
        bx = 1 + tuft * 6.35
        by = 191 + (tuft % 7) * 3.7
        pressure = .5 + .5 * math.sin((tuft - frame * 2.7) * .32)
        for blade in range(5):
            length = 11 + ((tuft + blade) % 7) * 2.4
            push = 10 + pressure * 10 + math.sin(phase * 1.65 + tuft * .43) * 3
            draw.line((s(bx + blade * 1.45), s(by), s(bx + push * .34), s(by - length * .52), s(bx + push), s(by - length)), fill=grass_cols[(tuft + blade) % len(grass_cols)], width=max(1, s(.66)))
    for x, y, r, speed, off in (((frame * 14.2) % (WIDTH + 136) - 68, 190 + math.sin(phase * 1.8) * 4.5, 20, 2.75, 0), ((frame * 10.8 + 92) % (WIDTH + 120) - 60, 185 + math.sin(phase * 1.4) * 3.5, 13.5, 2.15, 1.4), ((frame * 8.2 + 210) % (WIDTH + 126) - 63, 176 + math.sin(phase * 1.2) * 3, 11.5, 1.85, .7)):
        for dust_index in range(7):
            draw.ellipse(box((x - 40 - dust_index * 8, y + 5 - dust_index * .25, x - 5 - dust_index * 8, y + 10 + dust_index * .35)), fill=(*dust_col, max(16, 60 - dust_index * 6)))
        tumbleweed(draw, x, y, r, phase * speed + off, 220 if not night else 190)
    haze = Image.new("RGBA", image.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(haze, "RGBA")
    for band in range(7):
        y = 94 + band * 9
        for patch in range(5):
            x = -34 + patch * 95 + math.sin(phase * 1.15 + band) * 11
            hd.ellipse(box((x - 52, y - 7, x + 52, y + 7)), fill=(255, 241, 183, 16 if not night else 10))
    image.alpha_composite(blur(haze, 3.2))


def palette(theme, period):
    night = {
        "sun": ((23, 34, 72), (74, 96, 143), (45, 75, 91), (29, 55, 73), (154, 169, 190)),
        "cloud": ((27, 38, 68), (77, 93, 124), (47, 67, 80), (36, 54, 64), (138, 151, 170)),
        "rain": ((20, 26, 48), (66, 82, 120), (42, 55, 75), (27, 38, 52), (70, 80, 102)),
        "snow": ((29, 44, 86), (99, 123, 166), (172, 190, 212), (225, 235, 245), (166, 183, 205)),
        "storm": ((13, 15, 30), (47, 54, 82), (28, 35, 54), (20, 25, 39), (38, 44, 61)),
        "fog": ((43, 55, 72), (102, 116, 135), (76, 90, 105), (60, 73, 86), (163, 176, 188)),
        "wind": ((23, 47, 86), (78, 115, 168), (58, 95, 88), (43, 76, 71), (174, 197, 219)),
        "heat": ((73, 34, 48), (161, 82, 63), (103, 58, 49), (86, 42, 36), (214, 146, 111)),
    }
    day = {
        "sun": ((78, 178, 238), (235, 242, 190), (104, 176, 113), (73, 148, 90), (247, 249, 252)),
        "cloud": ((124, 155, 188), (217, 226, 234), (99, 128, 116), (85, 110, 96), (228, 234, 241)),
        "rain": ((76, 97, 126), (151, 170, 188), (80, 105, 103), (62, 82, 84), (105, 119, 138)),
        "snow": ((156, 181, 205), (232, 240, 247), (210, 224, 235), (238, 246, 250), (224, 234, 242)),
        "storm": ((51, 57, 85), (114, 115, 136), (59, 70, 88), (42, 52, 66), (61, 68, 87)),
        "fog": ((163, 176, 180), (217, 225, 227), (140, 152, 154), (116, 130, 131), (207, 216, 219)),
        "wind": ((90, 160, 215), (210, 236, 255), (116, 170, 126), (87, 148, 100), (238, 246, 252)),
        "heat": ((255, 184, 91), (255, 232, 166), (198, 149, 82), (176, 118, 55), (255, 228, 151)),
    }
    return (night if period == "night" else day)[theme]


def frame(theme, period, frame_index):
    sky_top, sky_bottom, hill, ground, cloud_col = palette(theme, period)
    image = gradient(sky_top, sky_bottom)
    phase = frame_index / FRAMES * math.tau
    night = period == "night"
    if night:
        stars(image, frame_index)
        moon(image, sky_top, frame_index)
    elif theme == "sun":
        sun(image, frame_index, WIDTH / 2, 74, 38)
    elif theme in {"cloud", "wind", "heat"}:
        sun(image, frame_index)
    if theme != "snow":
        land(image, hill, ground, frame_index)
    if theme == "sun" and period == "day":
        sun_clouds(image, frame_index, cloud_col)
    elif theme == "cloud":
        dense_clouds(image, frame_index, cloud_col, night)
    elif theme == "rain":
        rain_clouds(image, frame_index, night)
        rain(image, frame_index, night)
    elif theme == "snow":
        snow_scene(image, frame_index, night)
    elif theme == "storm":
        rain_clouds(image, frame_index, night)
        rain(image, frame_index, night, storm=True)
        natural_wind(image, frame_index, night)
        lightning(image, frame_index, night)
    elif theme == "fog":
        cloud(image, 34 + math.sin(phase) * 9, 45, 1.02, cloud_col)
        cloud(image, 171 + math.cos(phase * .8) * 13, 40, .88, cloud_col, 224)
        fog(image, frame_index)
    elif theme == "wind":
        cloud(image, 34 + math.sin(phase) * 9, 45, 1.02, cloud_col)
        cloud(image, 171 + math.cos(phase * .8) * 13, 40, .88, cloud_col, 224)
        natural_wind(image, frame_index, night)
    elif theme == "heat":
        heat(image, frame_index, night)
    else:
        cloud(image, 34 + math.sin(phase) * 9, 45, 1.02, cloud_col)
        cloud(image, 171 + math.cos(phase * .8) * 13, 40, .88, cloud_col, 224)
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def save_gif(theme, period):
    frames = [frame(theme, period, i) for i in range(FRAMES)]
    prepared = [im.convert("P", palette=Image.Palette.ADAPTIVE, colors=128) for im in frames]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{theme}_{period}.gif"
    prepared[0].save(path, save_all=True, append_images=prepared[1:], duration=DURATION, loop=0, disposal=2, optimize=False)
    return path


def assets_ready():
    try:
        if MARKER.read_text(encoding="utf-8").strip() != VERSION:
            return False
        for theme in THEMES:
            for period in PERIODS:
                path = OUT / f"{theme}_{period}.gif"
                if not path.is_file() or path.stat().st_size < 50_000:
                    return False
    except Exception:
        return False
    return True


def main():
    if assets_ready():
        print(MARKER)
        return
    for theme in THEMES:
        for period in PERIODS:
            print(save_gif(theme, period))
    MARKER.write_text(VERSION, encoding="utf-8")
    print(MARKER)


if __name__ == "__main__":
    main()
