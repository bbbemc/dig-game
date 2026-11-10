"""Draw the bomb and explosion sprite sheets.

    python tools/make_bomb_art.py

assets/bomb_sheet.png      24 x 24 frames. Row = fuse length (row 0 a full
                           fuse, row FUSE_ROWS - 1 a burnt-down stub);
                           column 0 unlit, columns 1-3 the burning spark.
assets/explosion_sheet.png EXPLOSION_SIZE square frames, one row: a white
                           flash, the fireball, rolling smoke, then wisps.

Pixel art is built from hard-edged shapes in a small palette, so it stays
crisp at 1:1. Needs Pillow and numpy (only this tool; the game just loads
the PNGs). Re-run after changing a shape or palette here.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bombs import BOMB_FRAME, FUSE_ROWS, EXPLOSION_FRAMES, EXPLOSION_SIZE  # noqa: E402

OUTLINE = (14, 12, 20)
BODY = [(30, 32, 46), (44, 48, 66), (62, 68, 92), (92, 100, 132), (150, 160, 196)]
CAP, CAP_DARK, CAP_LIGHT = (128, 120, 112), (70, 64, 60), (196, 186, 170)
ROPE, ROPE_DARK = (200, 162, 102), (132, 96, 56)
SPARK = [(255, 255, 236), (255, 226, 110), (255, 150, 46), (232, 84, 30)]
FIRE = [(255, 252, 230), (255, 230, 120), (255, 176, 58), (238, 104, 34), (168, 52, 30),
        (96, 34, 30)]
SMOKE = [(118, 106, 100), (86, 76, 74), (60, 52, 54), (40, 34, 38)]


def put(img, x, y, color, alpha=255):
    if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
        img[y, x] = (*color, alpha)


def bomb_body(size=BOMB_FRAME):
    """A shaded iron sphere with a riveted cap; lit from the upper left."""
    img = np.zeros((size, size, 4), np.uint8)
    cx, cy, r = 11.5, 14.0, 8.2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy)
            if d <= r:
                # Light direction (-0.6, -0.8): brighter toward the upper left.
                nx, ny = (x - cx) / r, (y - cy) / r
                nz = math.sqrt(max(0.0, 1 - nx * nx - ny * ny))
                light = max(0.0, -0.55 * nx - 0.7 * ny + 0.45 * nz)
                shade = min(len(BODY) - 2, int(light * 4.2))
                put(img, x, y, BODY[shade])
            elif d <= r + 1.0:
                put(img, x, y, OUTLINE)
    # Rim light on the lower right and a hard specular glint.
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy)
            if r - 1.2 < d <= r and (x - cx) + (y - cy) > 6:
                put(img, x, y, BODY[2])
    for x, y in ((8, 10), (9, 10), (8, 11), (10, 9)):
        put(img, x, y, BODY[4])
    put(img, 9, 9, (235, 240, 255))
    # Cap: a short metal collar on top.
    for y in range(4, 7):
        for x in range(9, 15):
            edge = x in (9, 14) or y == 4
            put(img, x, y, CAP_DARK if edge else (CAP_LIGHT if x == 10 else CAP))
    put(img, 12, 5, CAP_LIGHT)
    return img


FUSE_PATH = [(12, 3), (13, 2), (14, 1), (15, 1), (16, 0), (17, 0), (18, 1), (19, 1)]


def with_fuse(body, length):
    img = body.copy()
    for n, (x, y) in enumerate(FUSE_PATH[:length]):
        put(img, x, y, ROPE_DARK if n % 2 else ROPE)
        put(img, x, y + 1, OUTLINE) if img[y + 1, x, 3] == 0 else None
    return img


def spark(img, tip, phase):
    """A tiny star burst at the fuse tip, three shapes in turn."""
    x, y = tip
    shapes = {
        1: [(0, 0, 0), (-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 2), (2, -1, 2), (-2, -2, 3)],
        2: [(0, 0, 0), (1, -1, 1), (-1, 1, 1), (1, 1, 2), (-1, -1, 2), (2, -2, 3), (2, 1, 3)],
        3: [(0, 0, 1), (0, -1, 0), (-1, 0, 2), (1, 0, 2), (0, -2, 1), (-2, -1, 3), (1, -3, 3)],
    }
    for dx, dy, c in shapes[phase]:
        put(img, x + dx, y + dy, SPARK[c])


def bomb_sheet():
    body = bomb_body()
    sheet = np.zeros((BOMB_FRAME * FUSE_ROWS, BOMB_FRAME * 4, 4), np.uint8)
    for row in range(FUSE_ROWS):
        length = round(len(FUSE_PATH) * (1 - row / FUSE_ROWS))
        length = max(1, length)
        base = with_fuse(body, length)
        tip = FUSE_PATH[length - 1]
        tip = (tip[0], tip[1] + 1) if tip[1] == 0 else tip   # keep sparks in frame
        for col in range(4):
            frame = base.copy()
            if col:
                spark(frame, tip, col)
            sheet[row * BOMB_FRAME:(row + 1) * BOMB_FRAME, col * BOMB_FRAME:(col + 1) * BOMB_FRAME] = frame
    return sheet


# ---- explosion ---------------------------------------------------------

def explosion_frames(size=EXPLOSION_SIZE, count=EXPLOSION_FRAMES, seed=5):
    rng = np.random.default_rng(seed)
    c = size / 2
    ys, xs = np.mgrid[0:size, 0:size].astype(float)
    # Puffs around the centre; each frame they swell, rise and cool.
    n = 16
    angles = rng.uniform(0, 2 * math.pi, n)
    reach = rng.uniform(0.25, 0.9, n)
    sizes = rng.uniform(0.32, 0.5, n)
    def smooth(cells):
        """Value noise in [0, 1), soft at ``cells`` knots across the frame."""
        low = Image.fromarray((rng.random((cells, cells)) * 255).astype(np.uint8))
        return np.asarray(low.resize((size, size), Image.BICUBIC), float) / 255

    blocky = 0.65 * smooth(9) + 0.35 * smooth(18)
    # Break-up pattern in 3-pixel clumps, so smoke thins out in chunks.
    grain = np.kron(rng.random((size // 3 + 1, size // 3 + 1)), np.ones((3, 3)))[:size, :size]
    frames = []
    max_r = size * 0.43
    for t in range(count):
        p = t / (count - 1)
        img = np.zeros((size, size, 4), np.uint8)
        if t == 0:
            # A white flash and short rays.
            d = np.hypot(xs - c, ys - c)
            core = d < size * 0.14
            ring = (d < size * 0.2) & ~core
            img[core] = (*FIRE[0], 255)
            img[ring] = (*FIRE[1], 255)
            for k in range(8):
                a = k * math.pi / 4 + 0.2
                for s in range(int(size * 0.21), int(size * 0.3)):
                    put(img, int(c + math.cos(a) * s), int(c + math.sin(a) * s), FIRE[1 if s % 3 else 0])
            frames.append(img)
            continue
        grow = 1 - (1 - min(1.0, p / 0.45)) ** 2          # fast swell, then hold
        radius = max_r * (0.45 + 0.55 * grow)
        rise = p * size * 0.12
        density = np.full((size, size), -1.0)
        for a, r, s in zip(angles, reach, sizes):
            px = c + math.cos(a) * r * radius
            py = c + math.sin(a) * r * radius * 0.85 - rise * (0.5 + r)
            pr = s * radius * (1 + 0.35 * p)
            density = np.maximum(density, 1 - np.hypot(xs - px, ys - py) / pr)
        core_r = radius * 0.7 * (1 - p) ** 0.7
        dist = np.hypot(xs - c, ys - (c - rise * 0.6))
        density = np.maximum(density, 1 - dist / max(1.0, core_r))
        shape = density + (blocky - 0.5) * 0.3 > 0.04
        # Heat: hottest in the middle early on, cooling into smoke.
        cool = max(0.0, 1 - p * 1.35) ** 1.3
        heat = (1 - dist / radius) * 1.25 * cool + (blocky - 0.5) * 0.35 * cool
        heat += np.clip(density, 0, 1) * 0.3 * cool
        levels = (0.95, 0.78, 0.6, 0.42, 0.28, 0.17)
        color = np.zeros((size, size, 3), np.uint8)
        # Smoke is lit from above: lighter tops, darker undersides of each puff.
        smoke_shade = np.clip(((ys - c) / radius + 1) / 2 + (blocky - 0.5) * 0.6, 0, 0.999)
        smoke_index = (smoke_shade * len(SMOKE)).astype(int)
        for i, s in enumerate(SMOKE):
            color[smoke_index == i] = s
        for i in reversed(range(len(levels))):
            color[heat > levels[i]] = FIRE[i]
        alpha = np.where(shape, 255, 0)
        # Late frames break up from the outside in.
        if p > 0.45:
            fade = (p - 0.45) / 0.55
            thin = 1 - np.clip(density, 0, 1)
            gone = grain * 0.5 + blocky * 0.5 < fade * (0.7 + 0.6 * thin)
            alpha = np.where(gone, 0, alpha)
            alpha = np.where(alpha > 0, 235 - fade * 90, 0)
        # A 1-pixel dark rim around the cloud keeps it readable.
        solid = alpha > 0
        edge = solid & ~(np.roll(solid, 1, 0) & np.roll(solid, -1, 0) & np.roll(solid, 1, 1) & np.roll(solid, -1, 1))
        color[edge & (heat < levels[2])] = SMOKE[-1]
        img[..., :3] = color
        img[..., 3] = alpha.astype(np.uint8)
        # Shock ring on the early frames.
        if t in (1, 2, 3):
            ring_r = radius + 4 + t * 3
            ring = np.abs(np.hypot(xs - c, ys - c) - ring_r) < 0.8
            ring &= img[..., 3] == 0
            img[ring] = (255, 236, 200, 150 - t * 35)
        # Embers flung outward.
        if 2 <= t <= count - 2:
            for k in range(10):
                a = angles[k] + 0.4
                d = radius * (0.8 + 0.6 * p) + k % 3 * 3
                ex, ey = int(c + math.cos(a) * d), int(c + math.sin(a) * d * 0.8 + p * 10)
                put(img, ex, ey, FIRE[1] if (t + k) % 3 else FIRE[2])
        frames.append(img)
    return frames


def explosion_sheet():
    frames = explosion_frames()
    return np.concatenate(frames, axis=1)


if __name__ == '__main__':
    assets = ROOT / 'assets'
    Image.fromarray(bomb_sheet()).save(assets / 'bomb_sheet.png')
    Image.fromarray(explosion_sheet()).save(assets / 'explosion_sheet.png')
    print('assets/bomb_sheet.png, assets/explosion_sheet.png')
