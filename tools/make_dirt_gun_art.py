"""Draw the dirt pistol, its dirt clod and the splat as sprite sheets.

    python tools/make_dirt_gun_art.py

assets/dirt_gun_sheet.png    GUN_FRAME cells, facing right, from the team's
                             revolver art (assets/dirt_gun_source.png, white
                             background removed): shrunk to GUN_WIDTH px,
                             reduced to a small palette and outlined. Row 0:
                             idle (the glow in the bell pulses), row 1: fire
                             (dirt bursts from the bell, recoil, settle).
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
from dirt_gun import (GUN_FRAME, GUN_WIDTH, CLOD_FRAME, SPLAT_FRAME, IDLE_FRAMES, FIRE_FRAMES,  # noqa: E402
                      CLOD_FRAMES, SPLAT_FRAMES, MUZZLE)

COLORS = {
    'o': (24, 18, 16), 'b': (122, 78, 34), 'B': (186, 128, 50), 'H': (238, 194, 108),
    'w': (92, 52, 28), 'W': (142, 88, 46), 'g': (150, 196, 206), 'G': (210, 236, 240),
    'd': (80, 50, 28), 'D': (128, 84, 48), 'l': (172, 124, 76), 'm': (84, 86, 96),
    'M': (150, 152, 164), 'e': (40, 34, 36),
}

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


def gun_sprite():
    """The revolver at game size: shrunk, crisp palette, dark outline."""
    src = Image.open(ROOT / 'assets' / 'dirt_gun_source.png').convert('RGBA')
    h = round(src.height * GUN_WIDTH / src.width)
    from PIL import ImageEnhance
    shrunk = src.resize((GUN_WIDTH, h), Image.BOX)
    small = np.array(shrunk)
    solid = small[..., 3] >= 120
    # Shrinking averages the brass toward brown: give back colour and contrast.
    rgb = Image.fromarray(small[..., :3])
    rgb = ImageEnhance.Contrast(ImageEnhance.Color(rgb).enhance(1.15)).enhance(1.2)
    rgb = rgb.quantize(18, method=Image.Quantize.MEDIANCUT)
    small[..., :3] = np.array(rgb.convert('RGB'))
    small[..., 3] = np.where(solid, 255, 0)
    # The bell's hot orange lining: the column just inside its mouth.
    right = GUN_WIDTH - 1
    for y in range(h):
        xs = np.where(solid[y])[0]
        if len(xs) and xs.max() >= right - 1 and 1 <= y <= h * 0.55:
            small[y, xs.max() - 1, :3] = (236, 112, 40)
            small[y, xs.max(), :3] = (150, 70, 30)
    out = np.zeros((h + 2, GUN_WIDTH + 2, 4), np.uint8)
    out[1:-1, 1:-1] = small
    solid = out[..., 3] > 0
    near = (np.roll(solid, 1, 0) | np.roll(solid, -1, 0) | np.roll(solid, 1, 1) | np.roll(solid, -1, 1))
    out[near & ~solid] = (*COLORS['o'], 255)
    return out


def gun_sheet():
    w, h = GUN_FRAME
    art = gun_sprite()
    ah, aw = art.shape[:2]
    top = (h - ah) // 2

    def frame(kick=0, glow=0):
        img = np.zeros((h, w, 4), np.uint8)
        piece = art.copy()
        if glow:
            # The hot orange lining of the bell brightens.
            r, g, b = (piece[..., i].astype(int) for i in range(3))
            hot = (piece[..., 3] > 0) & (((r == 236) & (g == 112)) | ((r == 150) & (g == 70) & (b == 30)))
            piece[hot, 0] = np.clip(r[hot] + glow, 0, 255)
            piece[hot, 1] = np.clip(g[hot] + glow, 0, 255)
        x0 = 1 + kick
        img[top:top + ah, max(0, x0):x0 + aw] = piece[:, max(0, -x0):]
        return img

    rows = [[frame(glow=g) for g in (0, 30, 60, 30)[:IDLE_FRAMES]]]
    fire = []
    beats = [(-2, 4, 90), (-2, 3, 60), (-1, 2, 30), (0, 1, 0), (0, 0, 0)]
    for n, (kick, size, glow) in enumerate(beats[:FIRE_FRAMES]):
        img = frame(kick, glow)
        if size:
            burst(img, (MUZZLE[0] + kick, MUZZLE[1]), size, seed=n + 3)
        fire.append(img)
    rows.append(fire)
    cols = max(len(r) for r in rows)
    sheet = np.zeros((h * len(rows), w * cols, 4), np.uint8)
    for r, frames in enumerate(rows):
        for c, img in enumerate(frames):
            sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = img
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
