"""Draw the dirt pistol, its dirt clod and the splat as sprite sheets.

    python tools/make_dirt_gun_art.py

assets/dirt_gun_sheet.png    GUN_FRAME cells, facing right. Row 0: idle (the
                             dirt in the glass canister churns), row 1: fire
                             (muzzle burst of dirt, recoil, canister refills).
assets/dirt_clod_sheet.png   CLOD_FRAME cells, one row: a tumbling clod.
assets/dirt_splat_sheet.png  SPLAT_FRAME cells, one row: the clod bursting.

Frame counts and rates live in dirt_gun.py. Pixel maps below are drawn by
hand, one character per pixel. Needs Pillow and numpy (only this tool).
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dirt_gun import (GUN_FRAME, CLOD_FRAME, SPLAT_FRAME, IDLE_FRAMES, FIRE_FRAMES,  # noqa: E402
                      CLOD_FRAMES, SPLAT_FRAMES, MUZZLE)

COLORS = {
    'o': (24, 18, 16), 'b': (122, 78, 34), 'B': (186, 128, 50), 'H': (238, 194, 108),
    'w': (92, 52, 28), 'W': (142, 88, 46), 'g': (150, 196, 206), 'G': (210, 236, 240),
    'd': (80, 50, 28), 'D': (128, 84, 48), 'l': (172, 124, 76), 'm': (84, 86, 96),
    'M': (150, 152, 164), 'e': (40, 34, 36),
}

GUN = [
    "......oooooo",
    ".....oG*****go",
    ".....og*****go",
    ".....og*****go",
    "...ooooMMMMMooooooooooo",
    "..obBBHHHHHHHHHHHHHHmMMo",
    "..obBBBBBBBBBBBBBBBBmMeo",
    "..obbbbbbbbbbbbbbbbbmmmo",
    "...oobWWWobboooooooooo",
    ".....oWWWo.obo",
    ".....oWwWo.oo",
    "....oWWwWo",
    "....oWwWWo",
    "...oWWwWWo",
    "...oooooo",
]
DIRT_ROWS = 3          # canister rows marked '*'
CLOD = [
    "..oooo..",
    ".oDlDDo.",
    "oDllDdDo",
    "oDlDDDdo",
    "oDDDdDdo",
    "oDdDDddo",
    ".odDddo.",
    "..oooo..",
]


def paint(rows, size, offset=(0, 0), fill=None):
    img = np.zeros((size[1], size[0], 4), np.uint8)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == '.':
                continue
            if ch == '*':
                ch = fill(x, y) if fill else 'D'
                if ch is None:
                    continue
            px, py = x + offset[0], y + offset[1]
            if 0 <= px < size[0] and 0 <= py < size[1]:
                img[py, px] = (*COLORS[ch], 255)
    return img


def canister(phase, level=1.0):
    """Dirt in the glass: a churning pattern, filled up to ``level``."""
    def fill(x, y):
        row = y - 1                                  # 0 top .. 2 bottom
        if row < round((1 - level) * DIRT_ROWS):
            return 'g' if (x + y) % 2 else None      # empty glass: a faint sheen
        return 'ldD'[(x * 2 + y * 3 + phase) % 3] if (x + phase) % 4 else 'd'
    return fill


def put(img, x, y, color, alpha=255):
    if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]:
        img[y, x] = (*color, alpha)


def burst(img, origin, size, seed):
    """A muzzle burst of dirt: a bright core, then brown puffs and specks."""
    rng = np.random.default_rng(seed)
    ox, oy = origin
    if size >= 3:
        for dx, dy in ((0, 0), (1, 0), (0, -1), (0, 1), (2, 0)):
            put(img, ox + dx, oy + dy, (255, 238, 170))
    for _ in range(size * 5):
        a = rng.uniform(-0.9, 0.9)
        d = rng.uniform(1, size * 2.2)
        x, y = int(ox + math.cos(a) * d + 1), int(oy + math.sin(a) * d * 0.8)
        put(img, x, y, COLORS['l'] if d < size else (COLORS['D'] if rng.random() < .6 else COLORS['d']))


def gun_sheet():
    w, h = GUN_FRAME
    rows = []
    idle = [paint(GUN, GUN_FRAME, (0, 0), canister(n)) for n in range(IDLE_FRAMES)]
    rows.append(idle)
    fire = []
    # recoil px, burst size, canister level
    beats = [(-2, 4, 0.34), (-2, 3, 0.34), (-1, 2, 0.67), (0, 1, 1.0), (0, 0, 1.0)]
    for n, (kick, size, level) in enumerate(beats[:FIRE_FRAMES]):
        frame = paint(GUN, GUN_FRAME, (kick, 0), canister(n, level))
        if size:
            burst(frame, (MUZZLE[0] + kick, MUZZLE[1]), size, seed=n + 3)
        fire.append(frame)
    rows.append(fire)
    cols = max(len(r) for r in rows)
    sheet = np.zeros((h * len(rows), w * cols, 4), np.uint8)
    for r, frames in enumerate(rows):
        for c, frame in enumerate(frames):
            sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = frame
    return sheet


def clod_sheet():
    w, h = CLOD_FRAME
    base = paint(CLOD, CLOD_FRAME, ((w - 8) // 2, (h - 8) // 2))
    frames = [np.rot90(base, -n).copy() for n in range(CLOD_FRAMES)]
    return np.concatenate(frames, axis=1)


def splat_sheet():
    """Chunks thrown up and out from the hit point, with a dust puff."""
    w, h = SPLAT_FRAME
    rng = np.random.default_rng(9)
    cx, cy = w / 2, h - 4
    chunks = [(rng.uniform(-1, 1) * 9, -rng.uniform(4, 11), rng.integers(1, 3)) for _ in range(12)]
    frames = []
    for t in range(SPLAT_FRAMES):
        p = (t + 1) / SPLAT_FRAMES
        img = np.zeros((h, w, 4), np.uint8)
        # dust puff, thinning out
        r = 2 + p * 7
        for y in range(h):
            for x in range(w):
                d = math.hypot((x - cx) / 1.3, y - cy)
                if r - 1.6 < d < r and (x + y + t) % (1 + int(p * 3)) == 0:
                    put(img, x, y, (150, 124, 94), round(200 * (1 - p)) + 40)
        if t < 2:     # the flat smack
            for x in range(int(cx - 5 + t * -2), int(cx + 6 + t * 2)):
                put(img, x, int(cy) + 1, COLORS['D'])
                put(img, x, int(cy), COLORS['l'] if x % 2 else COLORS['D'])
        for vx, vy, size in chunks:
            x = cx + vx * p * 1.3
            y = cy + vy * p * 1.4 + 9 * p * p * 1.4
            color = COLORS['l'] if size > 1 else COLORS['D']
            for dx in range(size):
                for dy in range(size):
                    put(img, int(x) + dx, int(y) + dy, color)
            put(img, int(x), int(y) + size, COLORS['d'])
        frames.append(img)
    return np.concatenate(frames, axis=1)


if __name__ == '__main__':
    assets = ROOT / 'assets'
    Image.fromarray(gun_sheet()).save(assets / 'dirt_gun_sheet.png')
    Image.fromarray(clod_sheet()).save(assets / 'dirt_clod_sheet.png')
    Image.fromarray(splat_sheet()).save(assets / 'dirt_splat_sheet.png')
    print('assets/dirt_gun_sheet.png, dirt_clod_sheet.png, dirt_splat_sheet.png')
