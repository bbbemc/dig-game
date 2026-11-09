"""Build the enemy animation sheets from the single-pose sprites.

    python tools/make_enemy_animations.py

Each enemy sprite (assets/enemies/enemy_<kind>.png) is cut into parts (legs,
body, weapon) and the parts are moved a pixel or two per frame, the way
cut-out animation works. The result is one sheet per enemy,
assets/enemies/enemy_<kind>_sheet.png: one row per animation (in the order
of enemy_sprites.ANIMATIONS), one column per frame. Every frame has the same
size, with the sprite's feet on the bottom edge and centred horizontally, so
the game anchors frames exactly like the single sprite.

Re-run this after editing a source sprite. Needs Pillow and numpy.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from enemy_sprites import ANIMATIONS, FOLDER, FILES, PAD_X, PAD_TOP, sheet_name  # noqa: E402


def load(kind):
    return np.array(Image.open(FOLDER / FILES[kind]).convert('RGBA'))


def masks_for(kind, art):
    """Which pixels belong to which part. Unlisted pixels are the body."""
    h, w = art.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    solid = art[..., 3] > 0
    if kind == 'walker':
        parts = {
            'leg_l': (ys >= 44) & (xs <= 34),
            'leg_r': (ys >= 44) & (xs >= 36),
            'blade': (xs <= 14) & (ys <= 33),
        }
    elif kind == 'gunner':
        parts = {
            'leg_l': (ys >= 30) & (xs <= 28),
            'leg_r': (ys >= 30) & (xs >= 29),
            'cannon': (ys >= 17) & (ys <= 29) & (xs <= 30),
        }
    else:  # boss
        parts = {
            'leg_l': (ys >= 84) & (xs >= 22) & (xs <= 49),
            'leg_r': (ys >= 84) & (xs >= 52),
        }
    taken = np.zeros_like(solid)
    out = {}
    for name, mask in parts.items():
        out[name] = mask & solid & ~taken
        taken |= out[name]
    out['body'] = solid & ~taken
    return out


def layer(art, mask):
    part = art.copy()
    part[~mask] = 0
    return Image.fromarray(part)


def compose(art, masks, pose, order):
    """One frame: each part pasted at its (dx, dy) offset, in drawing order."""
    h, w = art.shape[:2]
    frame = Image.new('RGBA', (w + 2 * PAD_X, h + PAD_TOP), (0, 0, 0, 0))
    for name in order:
        dx, dy = pose.get(name, (0, 0))
        frame.alpha_composite(layer(art, masks[name]), (PAD_X + dx, PAD_TOP + dy))
    return frame


def glow(frame, center, radius, colors):
    """A soft round flash (outer to inner colours) at a frame point."""
    draw = ImageDraw.Draw(frame)
    cx, cy = center
    for n, color in enumerate(colors):
        r = radius * (len(colors) - n) / len(colors)
        if r >= 0.5:
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)


def slash(frame, center, radius, start, end, color, width=2):
    draw = ImageDraw.Draw(frame)
    cx, cy = center
    draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), start, end, fill=color, width=width)


def brighten(art, mask, amount):
    out = art.copy()
    rgb = out[..., :3].astype(np.int16)
    rgb[mask] = np.clip(rgb[mask] + amount[mask, None], 0, 255)
    out[..., :3] = rgb.astype(np.uint8)
    return out


def walk_cycle(n, lift, swing, bob):
    """Leg offsets for an n-frame walk: one foot lifts while the other plants."""
    poses = []
    for i in range(n):
        p = 2 * math.pi * i / n
        s, c = math.sin(p), math.cos(p)
        poses.append({
            'leg_l': (round(-swing * c), -round(max(0.0, s) * lift)),
            'leg_r': (round(swing * c), -round(max(0.0, -s) * lift)),
            'body': (0, bob if abs(s) < 0.5 else 0),
        })
    return poses


# ---- per enemy ------------------------------------------------------------

def walker_frames(art, masks):
    order = ('leg_l', 'leg_r', 'body', 'blade')
    f = lambda pose: compose(art, masks, pose, order)
    anims = {}
    anims['idle'] = [f({'body': (0, b), 'blade': (0, b)}) for b in (0, 0, 0, 1, 1, 1, 1, 0)]
    walk = []
    for pose in walk_cycle(6, lift=3, swing=2, bob=1):
        pose['blade'] = pose['body']
        walk.append(f(pose))
    anims['walk'] = walk
    # Wind up, slash down toward the facing side (left), follow through, recover.
    attack = []
    for body, blade, arc in (((1, 0), (2, -3), None), ((-1, 0), (-3, 1), (200, 260)),
                             ((-2, 1), (-5, 4), (150, 250)), ((-1, 0), (-2, 1), None)):
        frame = f({'body': body, 'blade': blade})
        if arc:
            slash(frame, (PAD_X + 14, PAD_TOP + 26), 17, *arc, (255, 236, 200, 220))
        attack.append(frame)
    anims['attack'] = attack
    anims['stun'] = [f({'body': (sx, 2), 'blade': (sx + 1, 4)}) for sx in (-1, 1)]
    return anims


def gunner_frames(art, masks):
    order = ('leg_l', 'leg_r', 'body', 'cannon')
    f = lambda pose, src=art: compose(src, masks, pose, order)
    muzzle = (PAD_X + 1, PAD_TOP + 23)
    anims = {'idle': [f({'body': (0, b), 'cannon': (0, c)})
                      for b, c in ((0, 0), (0, 0), (0, 1), (1, 1), (1, 1), (1, 1), (1, 0), (0, 0))]}
    # Charging: the barrel's ember heats up and a glow gathers at the muzzle.
    h, w = art.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    hot = (xs <= 6) & (ys >= 19) & (ys <= 27) & (art[..., 0] > 150) & (art[..., 3] > 0)
    charge = []
    for n, radius in enumerate((2, 3, 4)):
        heated = brighten(art, hot, np.full(art.shape[:2], 30 + 30 * n, np.int16))
        frame = f({}, heated)
        glow(frame, muzzle, radius, [(255, 120, 40, 120), (255, 200, 90, 200), (255, 250, 220, 255)])
        charge.append(frame)
    anims['charge'] = charge
    # Firing: the cannon kicks back, the whole gunner rocks, a flash and smoke.
    fire = []
    for body, cannon, flash in (((1, 0), (3, 0), 6), ((1, 0), (2, 0), 4), ((0, 0), (1, 0), 0)):
        frame = f({'body': body, 'cannon': cannon})
        x, y = muzzle[0] + cannon[0], muzzle[1]
        if flash:
            glow(frame, (x - 2, y), flash, [(255, 110, 30, 150), (255, 210, 90, 230), (255, 255, 235, 255)])
        else:
            glow(frame, (x - 3, y - 1), 3, [(120, 110, 105, 140), (160, 150, 140, 160)])
        fire.append(frame)
    anims['fire'] = fire
    anims['stun'] = [f({'body': (sx, 2), 'cannon': (sx, 2)}) for sx in (-1, 1)]
    return anims


def boss_frames(art, masks):
    order = ('leg_l', 'leg_r', 'body')
    h, w = art.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    r, g, b = (art[..., i].astype(int) for i in range(3))
    crystal = (art[..., 3] > 0) & (b > 140) & (g > 140) & (r < 150)
    f = lambda pose, src=art: compose(src, masks, pose, order)
    idle = []
    for n, bob in enumerate((0, 0, 0, 1, 1, 1, 1, 0)):
        # A shimmer runs up through the crystals.
        wave = np.cos((ys + xs * 0.4) / 5.0 + n * math.pi / 4)
        lit = brighten(art, crystal, (np.maximum(wave, 0) * 70).astype(np.int16))
        idle.append(f({'body': (0, bob)}, lit))
    anims = {'idle': idle}
    walk = []
    for n, pose in enumerate(walk_cycle(6, lift=3, swing=2, bob=1)):
        bx, by = pose['body']
        pose['body'] = (round(math.sin(2 * math.pi * n / 6)), by)  # heavy side-to-side sway
        walk.append(f(pose))
    anims['walk'] = walk
    # A shoulder-first lunge toward the facing side (left).
    lunge = []
    for body, dust in (((2, 0), False), ((-3, 1), True), ((-4, 2), True), ((-1, 0), False)):
        frame = f({'body': body, 'leg_l': (min(0, body[0]), 0)})
        if dust:
            draw = ImageDraw.Draw(frame)
            base = frame.height - 1
            for x0 in (PAD_X + 6, PAD_X + 14, PAD_X + 64):
                draw.ellipse((x0 - 3, base - 3, x0 + 3, base + 1), fill=(150, 130, 105, 150))
        lunge.append(frame)
    anims['attack'] = lunge
    anims['stun'] = [f({'body': (sx, 4)}) for sx in (-2, 2)]
    return anims


BUILDERS = {'walker': walker_frames, 'gunner': gunner_frames, 'boss': boss_frames}


def build(kind):
    art = load(kind)
    frames = BUILDERS[kind](art, masks_for(kind, art))
    rows = ANIMATIONS[kind]
    fw, fh = frames['idle'][0].size
    columns = max(n for _, n in rows)
    sheet = Image.new('RGBA', (fw * columns, fh * len(rows)), (0, 0, 0, 0))
    for row, (name, count) in enumerate(rows):
        assert len(frames[name]) == count, (kind, name, len(frames[name]), count)
        for col, frame in enumerate(frames[name]):
            sheet.alpha_composite(frame, (col * fw, row * fh))
    path = FOLDER / sheet_name(kind)
    sheet.save(path)
    return path, (fw, fh)


if __name__ == '__main__':
    for kind in BUILDERS:
        path, size = build(kind)
        print(f'{path.relative_to(ROOT)}  frame {size[0]}x{size[1]}')
