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
from enemy_sprites import ANIMATIONS, FOLDER, FILES, PAD_X, PAD_TOP, pad as frame_pad, sheet_name  # noqa: E402

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


# ---- swings: a limb rotated about its joint ------------------------------

def inpaint(art, holes, rounds=24, shade=0.82):
    """Fill ``holes`` from their filled neighbours (a part was lifted off)."""
    out = art.astype(float)
    todo = holes.copy()
    out[todo] = 0
    for _ in range(rounds):
        if not todo.any():
            break
        filled = (out[..., 3] > 0) & ~todo
        acc = np.zeros(out.shape[:2] + (3,))
        cnt = np.zeros(out.shape[:2])
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            src = np.roll(np.roll(out, dy, 0), dx, 1)
            ok = np.roll(np.roll(filled, dy, 0), dx, 1)
            acc += src[..., :3] * ok[..., None]
            cnt += ok
        grow = todo & (cnt > 0)
        out[grow, :3] = acc[grow] / cnt[grow, None] * shade
        out[grow, 3] = 255
        todo &= ~grow
    return out.astype(np.uint8)


def rotated_layer(part, size, at, pivot, degrees):
    """``part`` placed at ``at`` on a ``size`` canvas, turned about ``pivot``
    (art coordinates) by ``degrees`` counter-clockwise, pixel-crisp."""
    canvas = Image.new('RGBA', size, (0, 0, 0, 0))
    canvas.alpha_composite(Image.fromarray(part), at)
    if degrees:
        canvas = canvas.rotate(degrees, resample=Image.NEAREST,
                               center=(at[0] + pivot[0], at[1] + pivot[1]))
    return canvas


def smear(frame, center, r0, r1, start, end, color, alpha):
    """A filled crescent: the motion blur of a swing (screen degrees, y down)."""
    a = np.array(frame)
    h, w = a.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    dx, dy = xs - center[0], ys - center[1]
    d = np.hypot(dx, dy)
    ang = np.degrees(np.arctan2(dy, dx)) % 360
    lo, hi = start % 360, end % 360
    inside = (ang >= lo) & (ang <= hi) if lo <= hi else (ang >= lo) | (ang <= hi)
    band = inside & (d >= r0) & (d <= r1) & (a[..., 3] == 0)
    edge = band & (d >= r1 - 1.5)
    inner = band & (d >= r1 - 4) & ~edge
    a[band] = (*color, alpha // 4)
    a[inner] = (*color, alpha // 2)
    a[edge] = (255, 255, 240, alpha)
    return Image.fromarray(a)


# ---- the boss's greatsword (drawn here; the art's own sword is cut off) ----

SWORD_LEN = 68                       # pommel to tip, px
SWORD_GRIP = (9, 13)                 # where the fists hold it, in the sprite


def greatsword(glow=0.0, fists=True):
    """The lava greatsword pointing right, with two armoured fists on the
    grip; ``glow`` (0..1) heats the lava core and adds an aura."""
    w, h = SWORD_LEN + 8, 27
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = SWORD_GRIP[1]
    tip = SWORD_LEN
    # blade: a long tapering wedge of obsidian
    # blade: a broad, jagged slab of obsidian
    top = [(17, cy - 6)]
    for x in range(22, tip - 12, 8):                                     # notched spine
        top += [(x, cy - 7), (x + 4, cy - 5)]
    blade = top + [(tip - 12, cy - 7), (tip, cy), (tip - 12, cy + 6), (17, cy + 6)]
    d.polygon(blade, fill=(58, 40, 70), outline=(16, 10, 20))
    d.line([(18, cy - 4), (tip - 13, cy - 4)], fill=(112, 88, 130))      # bevel catching light
    d.line([(18, cy + 5), (tip - 13, cy + 5)], fill=(34, 22, 42))        # under edge
    core = (255, round(110 + 110 * glow), round(30 + 80 * glow))
    d.line([(19, cy), (tip - 7, cy)], fill=core)                        # the lava core
    d.line([(19, cy + 1), (tip - 9, cy + 1)], fill=(220, 80, 30))
    for x in range(23, tip - 9, 6):                                      # cracks branching off
        d.line([(x, cy - 1), (x + 2, cy - 3)], fill=(255, 170, 70))
        d.line([(x + 3, cy + 2), (x + 5, cy + 4)], fill=(230, 110, 40))
    for x in (30, 46):                                                   # violet runes
        d.rectangle((x, cy - 3, x + 1, cy - 2), fill=(200, 126, 255))
    # cross-guard with a gem, grip, pommel
    d.rectangle((13, cy - 10, 17, cy + 10), fill=(46, 30, 56), outline=(14, 10, 18))
    d.point((15, cy), fill=(255, 150, 60))
    d.rectangle((3, cy - 1, 14, cy + 1), fill=(40, 26, 30))
    d.ellipse((0, cy - 3, 5, cy + 3), fill=(70, 50, 84), outline=(14, 10, 18))
    # two gauntleted fists
    for fx in ((5, 10) if fists else ()):
        d.rounded_rectangle((fx - 3, cy - 4, fx + 3, cy + 4), 2, fill=(64, 44, 78),
                            outline=(14, 10, 18))
        d.point((fx - 1, cy - 2), fill=(130, 100, 150))
    if glow:
        a = np.array(img)
        solid = a[..., 3] > 0
        blade_only = solid.copy()
        blade_only[:, :17] = False
        ring1 = blade_only
        for _ in range(2):
            ring1 = ring1 | np.roll(ring1, 1, 0) | np.roll(ring1, -1, 0) | np.roll(ring1, 1, 1) | np.roll(ring1, -1, 1)
        ring2 = ring1 | np.roll(ring1, 1, 0) | np.roll(ring1, -1, 0) | np.roll(ring1, 1, 1) | np.roll(ring1, -1, 1)
        a[ring2 & ~ring1 & ~solid] = (190, 100, 255, round(110 * glow))
        a[ring1 & ~solid] = (255, 130, 40, round(190 * glow))
        img = Image.fromarray(a)
    return img


def place_sword(frame, pivot, angle, glow=0.0, alpha=1.0, fists=True):
    """Draw the greatsword with its grip at ``pivot`` pointing at ``angle``
    (screen degrees: 0 right, 90 down, 180 left, 270 up)."""
    sword = greatsword(glow, fists)
    if alpha < 1:
        a = np.array(sword)
        a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
        sword = Image.fromarray(a)
    big = Image.new('RGBA', frame.size, (0, 0, 0, 0))
    big.alpha_composite(sword, (round(pivot[0]) - SWORD_GRIP[0], round(pivot[1]) - SWORD_GRIP[1]))
    big = big.rotate(-angle, resample=Image.NEAREST, center=pivot)
    frame.alpha_composite(big)
    return frame


def draw_arm(frame, shoulder, fist):
    """The boss's armoured sword arm from its shoulder to its fist."""
    d = ImageDraw.Draw(frame)
    d.line([shoulder, fist], fill=(14, 10, 18), width=11)
    d.line([shoulder, fist], fill=(62, 42, 76), width=8)
    dx, dy = fist[0] - shoulder[0], fist[1] - shoulder[1]
    n = max(1.0, math.hypot(dx, dy))
    ox, oy = -dy / n * 2, dx / n * 2                         # lit edge
    d.line([(shoulder[0] + ox, shoulder[1] + oy), (fist[0] + ox, fist[1] + oy)],
           fill=(112, 88, 132), width=2)
    for t in (0.35, 0.65):                                    # lava seams in the plates
        x, y = shoulder[0] + dx * t, shoulder[1] + dy * t
        d.line([(x - oy, y + ox), (x + oy, y - ox)], fill=(255, 130, 46), width=1)
    # pauldron over the shoulder, gauntlet at the fist
    d.ellipse((shoulder[0] - 7, shoulder[1] - 6, shoulder[0] + 7, shoulder[1] + 6),
              fill=(70, 48, 86), outline=(14, 10, 18))
    d.point((shoulder[0] - 2, shoulder[1] - 3), fill=(200, 126, 255))
    d.rounded_rectangle((fist[0] - 5, fist[1] - 5, fist[0] + 5, fist[1] + 5), 2,
                        fill=(66, 46, 80), outline=(14, 10, 18))
    d.point((fist[0] - 2, fist[1] - 2), fill=(130, 100, 150))
    return frame


def sword_tip(pivot, angle):
    r = math.radians(angle)
    length = SWORD_LEN - SWORD_GRIP[0]
    return pivot[0] + math.cos(r) * length, pivot[1] + math.sin(r) * length


def slash_band(frame, center, radius, start, end, alpha):
    """A stylised slash trail along the sword tip's path: a hot white edge,
    an orange band and a violet tail, transparent inside."""
    for r0, r1, color, a in ((radius - 2, radius + 1, (255, 240, 190), alpha),
                             (radius - 8, radius - 2, (255, 128, 40), alpha * 3 // 4),
                             (radius - 16, radius - 8, (190, 100, 255), alpha // 3)):
        a_img = np.array(frame)
        h, w = a_img.shape[:2]
        ys, xs = np.mgrid[0:h, 0:w]
        d = np.hypot(xs - center[0], ys - center[1])
        ang = np.degrees(np.arctan2(ys - center[1], xs - center[0])) % 360
        lo, hi = start % 360, end % 360
        inside = (ang >= lo) & (ang <= hi) if lo <= hi else (ang >= lo) | (ang <= hi)
        # fade toward the start of the swing: the trail is newest at the blade
        fade = np.clip(1 - np.abs(((ang - lo) % 360) / max(1, (hi - lo) % 360)), 0.25, 1)
        band = inside & (d >= r0) & (d < r1) & (a_img[..., 3] == 0)
        a_img[band, :3] = color
        a_img[band, 3] = (a * fade[band]).astype(np.uint8)
        frame = Image.fromarray(a_img)
    return frame


def boss_without_sword(src):
    """The side pose with its own sword lifted off; the hips it covered are
    re-armoured from the plates above, so the drawn greatsword can swing."""
    h, w = src.shape[:2]
    shape = Image.new('L', (w, h), 0)
    ImageDraw.Draw(shape).polygon([(0, 63), (30, 61), (60, 57), (85, 58), (85, 73),
                                   (62, 74), (44, 80), (22, 88), (0, 92)], fill=255)
    cut = np.array(shape) > 0
    ys, xs = np.mgrid[0:h, 0:w]
    solid = src[..., 3] > 0
    out = src.copy()
    out[cut] = 0
    hips = cut & solid & (xs >= 22) & (xs <= 72)
    for y, x in zip(*np.where(hips)):
        for dy in (20, 30, 40, 50):
            sy = y - dy
            if sy >= 0 and src[sy, x, 3] > 0 and not cut[sy, x]:
                px = src[sy, x].astype(float)
                px[:3] *= 0.72
                out[y, x] = px.astype(np.uint8)
                break
    # Its own front arm (hanging down the front of the body) comes off too:
    # the drawn sword arm replaces it, and the rear arm stays.
    arm = Image.new('L', (w, h), 0)
    ImageDraw.Draw(arm).polygon([(16, 26), (31, 25), (32, 66), (16, 68)], fill=255)
    arm_cut = (np.array(arm) > 0) & (out[..., 3] > 0)
    out[arm_cut] = 0
    cut |= arm_cut
    a = out[..., 3] > 0
    edge = a & ~(np.roll(a, 1, 0) & np.roll(a, -1, 0) & np.roll(a, 1, 1) & np.roll(a, -1, 1))
    out[edge & cut] = (14, 10, 18, 255)
    out[edge & (np.roll(cut, 1, 1) | np.roll(cut, -1, 1))] = (14, 10, 18, 255)
    return out


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
    # The swing: the arm and the machete are one piece turned about the
    # shoulder, so the arm follows the blade. The torso it covered is filled.
    h, w = art.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    solid = art[..., 3] > 0
    limb = solid & (((xs <= 14) & (ys <= 33)) | ((xs <= 20) & (ys >= 18) & (ys <= 38)))
    shoulder = (20, 23)
    body_art = inpaint(np.where(limb[..., None], 0, art).astype(np.uint8), limb & (xs >= 15))
    arm_art = np.where(limb[..., None], art, 0).astype(np.uint8)
    size = (w + 2 * PAD_X, h + PAD_TOP)
    # (body offset, arm angle, smear (from, to, alpha) in screen degrees)
    # The blade starts pointing up-left (about 208 deg); +angle swings it down.
    keys = (((1, 0), -15, None),                 # ready
            ((2, 0), -62, None),                 # wind up: blade raised back
            ((-2, 0), 55, (150, 272, 230)),      # strike: down across the front
            ((-3, 1), 92, (112, 210, 150)),      # follow through
            ((-2, 1), 40, None),                 # recover
            ((-1, 0), 10, None))                 # settle
    attack = []
    for (bx, by), angle, arc in keys:
        frame = Image.new('RGBA', size, (0, 0, 0, 0))
        legs = np.where((masks['leg_l'] | masks['leg_r'])[..., None], art, 0).astype(np.uint8)
        frame.alpha_composite(Image.fromarray(legs), (PAD_X, PAD_TOP))
        upper = np.where((masks['leg_l'] | masks['leg_r'])[..., None], 0, body_art).astype(np.uint8)
        frame.alpha_composite(Image.fromarray(upper), (PAD_X + bx, PAD_TOP + by))
        pivot = (PAD_X + bx + shoulder[0], PAD_TOP + by + shoulder[1])
        if arc:
            frame = smear(frame, pivot, 13, 25, arc[0], arc[1], (255, 244, 220), arc[2])
        frame.alpha_composite(rotated_layer(arm_art, size, (PAD_X + bx, PAD_TOP + by),
                                            shoulder, angle))
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
    """The Abyssal Volcanic Colossus (tools/colossus_rig.py): the book's
    boss cut into body, sword arm and sword, posed per frame, so the sword
    stays in its fist through every swing."""
    import colossus_rig
    rig = colossus_rig.Colossus()
    pad = frame_pad('boss')
    blade_rest = 166                                 # the sword's rest direction (forward-left), deg

    def blade(arm, want):
        """The wrist turn that points the blade at ``want`` with the arm at ``arm``."""
        return want - blade_rest - (arm - 90)

    counter = [0]

    def r(fire=0.7, **pose):
        """A pose with the blade burning (``fire`` 0..1); each frame flickers."""
        counter[0] += 1
        return rig.pose(pad, fire=fire, seed=counter[0], **pose)[0]

    anims = {}
    # idle: breathing, the lava in its cracks pulsing, the blade burning
    anims['idle'] = [r(body=(0, 3 * b), glow=0.25 + 0.45 * math.sin(n / 8 * math.pi) ** 2)
                     for n, b in enumerate(BREATH)]
    # walk: heavy steps, one foot lifting at a time, the body swaying
    walk = []
    for n in range(8):
        ph = 2 * math.pi * n / 8
        sn, cs = math.sin(ph), math.cos(ph)
        walk.append(r(body=(round(4 * cs), 4 if abs(sn) < 0.4 else 0),
                      feet=((round(-6 * cs), -round(max(0.0, sn) * 14)),
                            (round(6 * cs), -round(max(0.0, -sn) * 14))),
                      arm=90 + round(4 * cs), glow=0.35))
    anims['walk'] = walk
    # attack: the sword is hauled up over the far shoulder (warning: aura,
    # lava blazing, embers), then brought across and down in front with a
    # slash trail and after-images, into the ground, lava erupting, recover.
    # The arm turns at the shoulder, the sword at the fist; it always faces
    # the way it strikes (forward, left in the art).
    reach = 250
    anims['attack'] = [
        r(arm=-55, sword=blade(-55, 272), glow=0.6, fire=0.75, body=(4, 0)),   # raised beside the head
        r(arm=-80, sword=blade(-80, 318), glow=1.0, fire=1.0, embers=True, body=(8, 0)),
        r(arm=170, sword=blade(170, 184), glow=1.0, fire=1.0, body=(-12, 0),
          ghosts=((blade(170, 262), 0.45), (blade(170, 222), 0.3)), trail=(184, 318, reach, 240)),
        r(arm=132, sword=blade(132, 150), glow=0.8, fire=0.95, body=(-14, 8), impact=1,
          trail=(150, 262, reach, 170)),
        r(arm=126, sword=blade(126, 152), glow=0.5, fire=0.75, body=(-12, 8), impact=2),
        r(arm=100, sword=blade(100, 150), glow=0.25, fire=0.55),
    ]
    # hurt: rocked back, flashing white
    anims['hurt'] = [r(body=(14, 0), arm=80, sword=blade(80, 176), tint=(130, 130, 130)),
                     r(body=(7, 0), arm=86, sword=blade(86, 170))]
    # stun: slumped, the sword's point dropped to the ground, swaying
    anims['stun'] = [r(body=(sx, 14), arm=104, sword=blade(104, 128), glow=0.05, fire=0.15)
                     for sx in (-6, 0, 6, 0)]
    # death: flash, sag to its knees over the sword, crumble to ash
    sag = [r(body=(0, 16), arm=108, sword=blade(108, 132), glow=0.1, fire=0.25),
           r(body=(-2, 34), arm=114, sword=blade(114, 140), glow=0.05, fire=0.1),
           r(body=(-4, 52), arm=120, sword=blade(120, 148), fire=0.0)]
    anims['death'] = death_row(r(), sag, 31, (pad[0] + 30, pad[0] + 66, pad[0] + 104), 4)
    return anims


BUILDERS = {'walker': walker_frames, 'gunner': gunner_frames, 'boss': boss_frames}


def build(kind):
    if kind == 'boss':
        # The Colossus's rest pose is its still sprite (and sets its size).
        import colossus_rig
        colossus_rig.Colossus().still().save(FOLDER / FILES['boss'])
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
