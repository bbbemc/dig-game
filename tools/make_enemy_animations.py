"""Build the enemy animation sheets from the single-pose sprites.

    python tools/make_enemy_animations.py

Each enemy sprite (assets/enemies/enemy_<kind>.png) is cut into parts (legs,
body, head, weapon) and the parts are moved a pixel or a few per frame, the
way cut-out animation works. The head (helmet, crystal crown) follows the
body one frame late, which keeps the motion from looking stiff. Under the
moving parts sits the untouched body, so a part that shifts never leaves a
see-through hole behind it.

The result is one sheet per enemy, assets/enemies/enemy_<kind>_sheet.png: one
row per animation (in the order of enemy_sprites.ANIMATIONS), one column per
frame. Every frame has the same size, with the sprite's feet on the bottom
edge and centred horizontally, so the game anchors frames exactly like the
single sprite.

Re-run this after editing a source sprite. Needs Pillow and numpy. Frames
drawn by hand can replace any cell of a sheet directly instead.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from enemy_sprites import ANIMATIONS, FOLDER, FILES, PAD_X, PAD_TOP, sheet_name  # noqa: E402

BREATH = (0, 0, 0, 1, 1, 1, 1, 0)        # an 8-frame idle bob


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
            'weapon': (xs <= 14) & (ys <= 33),
            'head': (ys <= 18) & (xs >= 15),           # helmet and lamp
        }
    elif kind == 'gunner':
        parts = {
            'leg_l': (ys >= 30) & (xs <= 28),
            'leg_r': (ys >= 30) & (xs >= 29),
            'weapon': (ys >= 17) & (ys <= 29) & (xs <= 30),
            'head': (ys <= 15) & (xs >= 14) & (xs <= 27),  # spiked helmet
        }
    else:  # boss (Stage 6 Abyssal Volcanic Ruin Colossus)
        parts = {
            'head': (ys <= 28) & (xs >= 24) & (xs <= 56),  # horned obsidian helm
        }
    taken = np.zeros_like(solid)
    out = {}
    for name, mask in parts.items():
        out[name] = mask & solid & ~taken
        taken |= out[name]
    out['body'] = solid & ~taken
    out['core'] = solid if kind == 'boss' else (out['body'] | out.get('head', np.zeros_like(solid)))
    out['weapon'] = out.get('weapon', np.zeros_like(solid))
    return out


def layer(art, mask):
    part = art.copy()
    part[~mask] = 0
    return Image.fromarray(part)


def compose(art, masks, pose):
    """One frame. ``pose`` maps parts to (dx, dy); the head defaults to the body.

    Order: legs, the whole body+head at the body offset (fills any gap a
    moving part leaves), the head at its own offset, then the weapon.
    """
    h, w = art.shape[:2]
    frame = Image.new('RGBA', (w + 2 * PAD_X, h + PAD_TOP), (0, 0, 0, 0))
    body = pose.get('body', (0, 0))
    steps = (('leg_l', pose.get('leg_l', (0, 0))), ('leg_r', pose.get('leg_r', (0, 0))),
             ('core', body), ('head', pose.get('head', body)),
             ('weapon', pose.get('weapon', body)))
    for name, (dx, dy) in steps:
        if name in masks and masks[name].any():
            frame.alpha_composite(layer(art, masks[name]), (PAD_X + dx, PAD_TOP + dy))
    return frame


def tint(frame, add=(0, 0, 0), scale=1.0):
    a = np.array(frame).astype(np.int16)
    a[..., :3] = np.clip(a[..., :3] * scale + np.array(add), 0, 255)
    return Image.fromarray(a.astype(np.uint8))


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


def dust(frame, xs, size=3, color=(150, 130, 105, 150)):
    draw = ImageDraw.Draw(frame)
    base = frame.height - 1
    for x in xs:
        draw.ellipse((x - size, base - size, x + size, base + 1), fill=color)


def brighten(art, mask, amount):
    out = art.copy()
    rgb = out[..., :3].astype(np.int16)
    rgb[mask] = np.clip(rgb[mask] + amount[mask, None], 0, 255)
    out[..., :3] = rgb.astype(np.uint8)
    return out


def lagged(poses):
    """Give each pose a head that trails the body by one frame (looping)."""
    for n, pose in enumerate(poses):
        pose.setdefault('head', poses[n - 1].get('body', (0, 0)))
    return poses


def walk_cycle(n, lift, swing, bob):
    """Leg offsets for an n-frame walk: one foot lifts while the other plants."""
    poses = []
    for i in range(n):
        p = 2 * math.pi * i / n
        s, c = math.sin(p), math.cos(p)
        poses.append({
            'leg_l': (round(-swing * c), -round(max(0.0, s) * lift)),
            'leg_r': (round(swing * c), -round(max(0.0, -s) * lift)),
            'body': (0, bob if abs(s) < 0.4 else 0),
        })
    return poses


def crumble(frame, fraction, seed, sink=0):
    """Death: pixels drop out at random, the rest darkens and sinks."""
    a = np.array(frame)
    noise = np.random.default_rng(seed).random(a.shape[:2])
    # Upper pixels go first, like a body collapsing into dust.
    rows = np.linspace(0.25, -0.25, a.shape[0])[:, None]
    a[noise + rows < fraction, 3] = 0
    a[..., :3] = (a[..., :3] * (1 - 0.45 * fraction)).astype(np.uint8)
    out = Image.new('RGBA', frame.size, (0, 0, 0, 0))
    out.alpha_composite(Image.fromarray(a), (0, sink))
    return out


def death_row(still, collapse, seed, puffs, steps):
    """Flash white, slump through ``collapse`` poses, then crumble to dust."""
    frames = [tint(still, (170, 170, 170))]
    frames += collapse
    last = collapse[-1]
    for n in range(steps):
        f = (n + 1) / (steps + 1)
        frame = crumble(last, 0.15 + f * 0.95, seed + n, sink=n)
        dust(frame, puffs, size=2 + n, color=(140, 122, 100, max(40, 170 - 40 * n)))
        frames.append(frame)
    return frames


# ---- per enemy ------------------------------------------------------------

def walker_frames(art, masks):
    f = lambda pose: compose(art, masks, pose)
    anims = {}
    anims['idle'] = [f(p) for p in lagged([{'body': (0, b), 'weapon': (0, b)} for b in BREATH])]
    walk = walk_cycle(8, lift=3, swing=2, bob=1)
    for n, pose in enumerate(walk):
        c = math.cos(2 * math.pi * n / 8)
        pose['weapon'] = (round(c), pose['body'][1])      # the knife swings against the legs
    anims['walk'] = [f(p) for p in lagged(walk)]
    # Ready, wind up, slash down toward the facing side (left), follow through, recover.
    attack = []
    keys = (((1, 0), (2, -3), (1, 0), None),
            ((2, 0), (3, -5), (2, 0), None),
            ((-1, 0), (-3, 1), (0, 0), ((200, 268), 230)),
            ((-2, 1), (-5, 4), (-2, 1), ((150, 258), 170)),
            ((-1, 1), (-3, 2), (-2, 1), ((150, 200), 80)),
            ((0, 0), (-1, 1), (-1, 0), None))
    for body, weapon, head, arc in keys:
        frame = f({'body': body, 'weapon': weapon, 'head': head})
        if arc:
            (start, end), alpha = arc
            slash(frame, (PAD_X + 14, PAD_TOP + 26), 17, start, end, (255, 236, 200, alpha))
        attack.append(frame)
    anims['attack'] = attack
    hurt = [f({'body': (2, 0), 'head': (3, 0), 'weapon': (3, -1)}),
            f({'body': (1, 0), 'head': (2, 0), 'weapon': (2, 0)})]
    anims['hurt'] = [tint(hurt[0], (110, 110, 110)), hurt[1]]
    anims['stun'] = [f({'body': (sx, 2), 'head': (sx * 2, 3), 'weapon': (sx + 1, 4)})
                     for sx in (-1, 0, 1, 0)]
    collapse = [f({'body': (2, 1), 'head': (3, 1), 'weapon': (3, 2)}),
                f({'body': (2, 3), 'head': (4, 4), 'weapon': (4, 6)})]
    anims['death'] = death_row(f({}), collapse, 11, (PAD_X + 24, PAD_X + 40), 3)
    return anims


def gunner_frames(art, masks):
    f = lambda pose, src=art: compose(src, masks, pose)
    muzzle = (PAD_X + 1, PAD_TOP + 23)
    cannon = (0, 0, 1, 1, 1, 1, 0, 0)
    anims = {'idle': [f(p) for p in lagged([{'body': (0, b), 'weapon': (0, c)}
                                            for b, c in zip(BREATH, cannon)])]}
    # Charging: the barrel's ember heats up and a glow gathers at the muzzle.
    h, w = art.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    hot = (xs <= 6) & (ys >= 19) & (ys <= 27) & (art[..., 0] > 150) & (art[..., 3] > 0)
    charge = []
    for n, radius in enumerate((1.5, 2.5, 3.5, 4.5)):
        heated = brighten(art, hot, np.full(art.shape[:2], 25 + 25 * n, np.int16))
        frame = f({'body': (1, 0) if n >= 2 else (0, 0), 'head': (1, 0) if n == 3 else (0, 0)}, heated)
        glow(frame, muzzle, radius, [(255, 120, 40, 120), (255, 200, 90, 200), (255, 250, 220, 255)])
        charge.append(frame)
    anims['charge'] = charge
    # Firing: the cannon kicks back, the gunner rocks, a flash, then smoke.
    fire = []
    for body, weapon, head, flash in (((1, 0), (4, 0), (0, 0), 7), ((2, 0), (3, 0), (1, 0), 5),
                                      ((1, 0), (2, 0), (2, 0), 0), ((0, 0), (1, 0), (1, 0), -1)):
        frame = f({'body': body, 'weapon': weapon, 'head': head})
        x, y = muzzle[0] + weapon[0], muzzle[1]
        if flash > 0:
            glow(frame, (x - 2, y), flash, [(255, 110, 30, 150), (255, 210, 90, 230), (255, 255, 235, 255)])
        elif flash == 0:
            glow(frame, (x - 3, y - 1), 3, [(120, 110, 105, 150), (165, 155, 145, 170)])
        else:
            glow(frame, (x - 5, y - 3), 4, [(120, 110, 105, 80), (150, 140, 130, 90)])
        fire.append(frame)
    anims['fire'] = fire
    hurt = [f({'body': (2, 0), 'head': (3, 0), 'weapon': (3, 0)}),
            f({'body': (1, 0), 'head': (2, 0), 'weapon': (2, 0)})]
    anims['hurt'] = [tint(hurt[0], (110, 110, 110)), hurt[1]]
    anims['stun'] = [f({'body': (sx, 2), 'head': (sx * 2, 3), 'weapon': (sx, 2)})
                     for sx in (-1, 0, 1, 0)]
    collapse = [f({'body': (1, 1), 'head': (2, 1), 'weapon': (1, 3)}),
                f({'body': (1, 3), 'head': (2, 4), 'weapon': (1, 6)})]
    anims['death'] = death_row(f({}), collapse, 21, (PAD_X + 22, PAD_X + 34), 3)
    return anims


def _boss_directional_pose(grid, row, col, size, flip=True):
    """Extract and scale a left-facing pose from the 6-row Stage 6 boss grid."""
    w, h = size
    cell = grid[row * 160:(row + 1) * 160, col * 160:(col + 1) * 160].copy()
    if row == 1 or (row == 4 and col == 1):
        hook_xs = np.where(cell[146, :, 3] > 0)[0]
        if len(hook_xs):
            cell[145, hook_xs] = [14, 10, 18, 255]
        crop = cell[20:146, 17:142]
    elif row == 4:
        crop = cell[20:148, 17:142]
    elif row == 3 and col in (2, 3):
        crop = cell[20:148, 11:149]
    else:
        crop = cell[19:148, 12:148]
    if flip:
        crop = np.fliplr(crop)
    arr = np.array(Image.fromarray(crop).resize((w, h), Image.Resampling.NEAREST))
    if row == 1 and flip:
        arr[78:92, 22:44] = arr[76:90, 22:44]
    # Guarantee a foot pixel on the bottom edge (h - 2 or h - 1)
    if not (arr[h - 2:h, :, 3] > 0).any():
        ys = np.where(arr[:, :, 3] > 0)[0]
        if len(ys):
            shift = (h - 1) - ys.max()
            if shift > 0:
                shifted = np.zeros_like(arr)
                shifted[shift:] = arr[:-shift]
                arr = shifted
    return arr


def boss_frames(art, masks):
    h, w = art.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]

    def shimmer(src, n, count):
        r, g, b = (src[..., i].astype(int) for i in range(3))
        solid = src[..., 3] > 0
        # Molten orange-red lava veins, yellow eyes, and violet crystal runes
        lava_or_runes = solid & (((r > 115) & (r > b + 40)) | ((b > 90) & (b > g + 30) & (r > 70)))
        wave = np.cos((ys + xs * 0.4) / 5.0 + n * 2 * math.pi / count)
        return brighten(src, lava_or_runes, (np.maximum(wave, 0) * 65).astype(np.int16))

    grid_path = FOLDER / 'enemy_boss_directional.png'
    grid = np.array(Image.open(grid_path).convert('RGBA')) if grid_path.exists() else None

    def compose_src(src, pose):
        return compose(src, masks_for('boss', src), pose)

    if grid is not None:
        idle_srcs = [_boss_directional_pose(grid, 1, c, (w, h)) for c in range(3)]
        idle_order = (0, 0, 1, 1, 2, 2, 1, 0)
        idle_poses = lagged([{'body': (0, bob)} for bob in BREATH])
        anims = {
            'idle': [compose_src(shimmer(idle_srcs[idx], n, 8), pose)
                     for n, (idx, pose) in enumerate(zip(idle_order, idle_poses))]
        }
        run_srcs = [_boss_directional_pose(grid, 4, c, (w, h)) for c in range(4)]
        walk_frames = []
        for n in range(8):
            src = shimmer(run_srcs[n // 2], n, 8)
            step = n % 2
            pose = {'body': (0, step), 'head': (-step, step)}
            walk_frames.append(compose_src(src, pose))
        anims['walk'] = walk_frames

        swing_a = _boss_directional_pose(grid, 3, 3, (w, h), flip=True)
        swing_b = _boss_directional_pose(grid, 3, 2, (w, h), flip=False)
        attack_specs = (
            (idle_srcs[0], {'body': (1, 0), 'head': (1, 0)}, None, False),
            (idle_srcs[0], {'body': (3, 0), 'head': (2, 0)}, None, False),
            (swing_a, {'body': (-2, 0), 'head': (-1, 0)}, ((195, 270), 235), True),
            (swing_b, {'body': (-4, 0), 'head': (-2, 0)}, ((145, 255), 185), True),
            (idle_srcs[2], {'body': (-3, 1), 'head': (-4, 2)}, ((145, 205), 95), False),
            (idle_srcs[1], {'body': (-1, 0), 'head': (-2, 1)}, None, False),
        )
        attack = []
        for n, (src, pose, arc, puff) in enumerate(attack_specs):
            frame = compose_src(shimmer(src, n, 6), pose)
            if arc:
                (start, end), alpha = arc
                slash(frame, (PAD_X + 20, PAD_TOP + 54), 26, start, end, (255, 130, 45, alpha), width=3)
                slash(frame, (PAD_X + 20, PAD_TOP + 54), 23, start, end, (210, 110, 255, max(60, alpha - 50)), width=2)
            if puff:
                dust(frame, (PAD_X + 8, PAD_X + 20, PAD_X + 64))
            attack.append(frame)
        anims['attack'] = attack
    else:
        f_base = lambda pose, src=art: compose(src, masks, pose)
        idle = lagged([{'body': (0, bob)} for bob in BREATH])
        anims = {'idle': [f_base(p, shimmer(art, n, 8)) for n, p in enumerate(idle)]}
        walk = walk_cycle(8, lift=3, swing=2, bob=1)
        for n, pose in enumerate(walk):
            pose['body'] = (round(math.sin(2 * math.pi * n / 8)), pose['body'][1])
        anims['walk'] = [f_base(p, shimmer(art, n, 8)) for n, p in enumerate(lagged(walk))]
        lunge = []
        for body, head, puff in (((1, 0), (1, 0), False), ((3, 0), (2, 0), False),
                                 ((-3, 1), (0, 0), True), ((-5, 2), (-3, 2), True),
                                 ((-3, 1), (-4, 2), False), ((-1, 0), (-2, 1), False)):
            frame = f_base({'body': body, 'head': head, 'leg_l': (min(0, body[0]), 0)})
            if puff:
                dust(frame, (PAD_X + 6, PAD_X + 14, PAD_X + 64))
            lunge.append(frame)
        anims['attack'] = lunge

    f = lambda pose, src=art: compose(src, masks, pose)
    hurt = [f({'body': (2, 1), 'head': (3, 1)}),
            f({'body': (1, 0), 'head': (2, 1)})]
    anims['hurt'] = [tint(hurt[0], (120, 120, 120)), hurt[1]]
    anims['stun'] = [f({'body': (sx, 4), 'head': (sx * 2, 5)})
                     for sx in (-2, 0, 2, 0)]
    collapse = [f({'body': (0, 2), 'head': (1, 3)}),
                f({'body': (1, 4), 'head': (2, 6)}),
                f({'body': (1, 7), 'head': (3, 9)})]
    anims['death'] = death_row(f({}), collapse, 31, (PAD_X + 20, PAD_X + 44, PAD_X + 68), 4)
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
