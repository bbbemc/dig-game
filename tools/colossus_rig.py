"""The Abyssal Volcanic Colossus (from the Dig Game Book), cut into a rig.

Source: assets/enemies/source/colossus_front.png, the book's boss image with
its white background removed (324 x 325, front view, the sword arm on the
left). It is cut into three pieces in source pixels:

- the sword (pommel, grip, guard and the cleaver blade across the legs),
- the sword arm (forearm and gauntlet) below the pauldron, turning about
  the shoulder,
- the body (everything else); where the sword covered the legs and loin
  cloth they are rebuilt from the armour just above, so lifting the sword
  leaves no hole.

Each frame is posed at source resolution (smooth rotations), effects are
drawn there too, then the frame is shrunk to game size with a hard alpha
edge so it stays crisp. The sword is held at the fist in every pose: the
arm turns about the shoulder and the sword turns about the fist (a wrist).

Used by tools/make_enemy_animations.py. Needs Pillow and numpy.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets' / 'enemies' / 'source' / 'colossus_front.png'
GAME_H = 96                                   # the still sprite's height in game px

# The coordinates below are in the source image as published (sword arm on
# the left, blade pointing right); the rig mirrors the image and them so the
# blade points forward (left, toward the player) and the swing crosses the
# body from the far shoulder.
SWORD = [(0, 186), (40, 188), (100, 198), (106, 196), (128, 198), (132, 220), (150, 224),
         (200, 229), (250, 233), (290, 230), (312, 222), (324, 232), (324, 300), (314, 323),
         (298, 320), (270, 308), (220, 296), (170, 284), (140, 274), (118, 254), (102, 228),
         (40, 226), (0, 228)]
ARM = [(22, 118), (60, 112), (108, 116), (116, 150), (110, 196), (102, 232), (70, 236),
       (30, 232), (22, 190)]
SHOULDER = (70, 95)
FIST = (70, 210)
TIP = (318, 270)
# Where the legs and loin cloth stand behind the blade (rebuilt when it lifts).
LEGS = [[(84, 228), (142, 230), (152, 325), (78, 325)],
        [(140, 224), (188, 224), (182, 292), (148, 286)],
        [(184, 246), (268, 240), (278, 325), (188, 325)]]
FEET_L = [(70, 296), (156, 296), (156, 325), (70, 325)]
FEET_R = [(182, 296), (284, 296), (284, 325), (182, 325)]

OUT = (14, 8, 16, 255)
_SWORD, _ARM, _LEGS, _FEET_L, _FEET_R = SWORD, ARM, LEGS, FEET_L, FEET_R
_SHOULDER, _FIST, _TIP = SHOULDER, FIST, TIP


def _mask(size, polys):
    m = Image.new('L', size, 0)
    d = ImageDraw.Draw(m)
    for p in polys:
        d.polygon(p, fill=255)
    return np.array(m) > 0


def _outline(a):
    solid = a[..., 3] > 0
    ring = (np.roll(solid, 1, 0) | np.roll(solid, -1, 0) | np.roll(solid, 1, 1)
            | np.roll(solid, -1, 1)) & ~solid
    a[ring] = OUT
    return a


def _mirror_points(points, w):
    return [(w - 1 - x, y) for x, y in points]


class Colossus:
    def __init__(self):
        src = np.array(Image.open(SOURCE).convert('RGBA'))[:, ::-1].copy()
        self.src = src
        h, w = src.shape[:2]
        m = lambda pts: _mirror_points(pts, w)
        global SWORD, ARM, LEGS, FEET_L, FEET_R, SHOULDER, FIST, TIP
        SWORD, ARM = m(_SWORD), m(_ARM)
        LEGS = [m(p) for p in _LEGS]
        FEET_L, FEET_R = m(_FEET_R), m(_FEET_L)
        SHOULDER, FIST, TIP = m([_SHOULDER])[0], m([_FIST])[0], m([_TIP])[0]
        self.size = (w, h)
        solid = src[..., 3] > 0
        sword = _mask((w, h), [SWORD]) & solid
        arm = _mask((w, h), [ARM]) & solid & ~sword
        legs = _mask((w, h), LEGS)
        self.sword = np.where(sword[..., None], src, 0).astype(np.uint8)
        self.arm = np.where(arm[..., None], src, 0).astype(np.uint8)
        body = np.where((sword | arm)[..., None], 0, src).astype(np.uint8)
        # Rebuild legs and loin cloth behind the blade from the plates above.
        hole = sword & legs
        for y, x in zip(*np.where(hole)):
            for dy in (70, 90, 110, 50):
                sy = y - dy
                if sy >= 0 and body[sy, x, 3] > 0 and not sword[sy, x] and not arm[sy, x]:
                    px = src[sy, x].astype(float)
                    px[:3] *= 0.7
                    body[y, x] = px.astype(np.uint8)
                    break
        self.body = _outline(body)
        r, g, b = (src[..., i].astype(int) for i in range(3))
        self.lava = solid & (((r > 150) & (r > g + 50)) | ((b > 150) & (r > 100) & (b > g + 40)))
        self.feet_l = _mask((w, h), [FEET_L]) & (self.body[..., 3] > 0)
        self.feet_r = _mask((w, h), [FEET_R]) & (self.body[..., 3] > 0)
        self.scale = GAME_H / h
        self.game_w = round(w * self.scale)

    # ---- one pose ---------------------------------------------------------
    def pose(self, pad, arm=90, sword=0, body=(0, 0), feet=((0, 0), (0, 0)), glow=0.0,
             aura=0.0, ghosts=(), tint=None, trail=None, impact=0, embers=False):
        """One frame at game size.

        ``arm`` is the shoulder-to-fist direction and ``sword`` the extra
        turn of the sword about the fist, both in screen degrees (rest: arm
        straight down = 90, sword 0). ``body`` shifts the upper body; ``feet``
        shift the left and right feet. ``pad`` is the game frame's (x, top)
        margin. Returns (frame, fist and tip in game frame px).
        """
        s = self.scale
        w, h = self.size
        px, pt = round(pad[0] / s), round(pad[1] / s)
        W, H = w + 2 * px, h + pt
        canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        ox, oy = px + body[0], pt + body[1]
        shoulder = np.array([ox + SHOULDER[0], oy + SHOULDER[1]], float)
        turn = arm - 90                                   # rotation of the arm piece
        rad = math.radians(turn)
        fist_rest = np.array([FIST[0] - SHOULDER[0], FIST[1] - SHOULDER[1]], float)
        rot = np.array([[math.cos(rad), -math.sin(rad)], [math.sin(rad), math.cos(rad)]])
        fist = shoulder + rot @ fist_rest
        sword_turn = turn + sword
        tip_rest = np.array([TIP[0] - FIST[0], TIP[1] - FIST[1]], float)
        sr = math.radians(sword_turn)
        srot = np.array([[math.cos(sr), -math.sin(sr)], [math.sin(sr), math.cos(sr)]])
        tip = fist + srot @ tip_rest

        def piece(arr, at, pivot, degrees, alpha=1.0, glow_amt=0.0):
            img = arr
            if glow_amt:
                img = self._glow(arr, glow_amt)
            layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            p = Image.fromarray(img)
            if alpha < 1:
                a = np.array(p)
                a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
                p = Image.fromarray(a)
            layer.alpha_composite(p, (round(at[0]), round(at[1])))
            if degrees:
                layer = layer.rotate(-degrees, resample=Image.BICUBIC,
                                     center=(float(pivot[0]), float(pivot[1])))
            return layer

        def sword_layer(turn_deg, alpha=1.0):
            # The sword's own frame: place so its fist point sits at the
            # current fist, then turn about it.
            at = (fist[0] - FIST[0], fist[1] - FIST[1])
            layer = piece(self.sword, at, fist, turn_deg, alpha, glow)
            if aura:
                layer = self._aura(layer, aura)
            return layer

        if trail:
            canvas.alpha_composite(self._trail((W, H), fist, trail))
        # feet step separately; the body rides on them
        body_img = self._glow(self.body, glow) if glow else self.body
        legs = np.zeros_like(body_img)
        upper = body_img.copy()
        for mask, (dx, dy) in ((self.feet_l, feet[0]), (self.feet_r, feet[1])):
            foot = np.where(mask[..., None], body_img, 0).astype(np.uint8)
            canvas.alpha_composite(Image.fromarray(foot), (px + dx, pt + dy))
            upper[mask] = 0
        for g_turn, g_alpha in ghosts:
            canvas.alpha_composite(sword_layer(turn + g_turn, g_alpha))
        canvas.alpha_composite(Image.fromarray(upper), (ox, oy))
        canvas.alpha_composite(sword_layer(sword_turn))
        canvas.alpha_composite(piece(self.arm, (ox, oy), shoulder, turn, 1.0, glow))
        draw = ImageDraw.Draw(canvas)
        if embers:
            for k in range(14):
                t = 0.25 + k * 0.05
                ex, ey = fist + (tip - fist) * t
                draw.ellipse((ex - 3 + (k % 3 - 1) * 14, ey - 20 - k * 6,
                              ex + 3 + (k % 3 - 1) * 14, ey - 14 - k * 6),
                             fill=(255, 200, 90, 255) if k % 2 else (255, 120, 40, 255))
        if impact:
            self._impact(draw, tip, H - 3, impact)
        if tint:
            a = np.array(canvas).astype(np.int16)
            a[..., :3] = np.clip(a[..., :3] + np.array(tint), 0, 255)
            canvas = Image.fromarray(a.astype(np.uint8))
        game = self._shrink(canvas, pad)
        return game, fist * s, tip * s

    # ---- effects (drawn at source resolution) ------------------------------
    def _glow(self, arr, amount):
        out = arr.copy()
        lava = self.lava & (arr[..., 3] > 0) if arr.shape[:2] == self.lava.shape else None
        if lava is None:
            return arr
        rgb = out[..., :3].astype(np.int16)
        rgb[lava] = np.clip(rgb[lava] + round(90 * amount), 0, 255)
        out[..., :3] = rgb.astype(np.uint8)
        return out

    @staticmethod
    def _aura(layer, amount):
        a = np.array(layer)
        solid = a[..., 3] > 40
        ring = solid.copy()
        for _ in range(5):
            ring = ring | np.roll(ring, 1, 0) | np.roll(ring, -1, 0) | np.roll(ring, 1, 1) | np.roll(ring, -1, 1)
        outer = ring.copy()
        for _ in range(5):
            outer = outer | np.roll(outer, 1, 0) | np.roll(outer, -1, 0) | np.roll(outer, 1, 1) | np.roll(outer, -1, 1)
        a[outer & ~ring & ~solid] = (176, 100, 255, round(130 * amount))
        a[ring & ~solid] = (255, 130, 40, round(210 * amount))
        return Image.fromarray(a)

    @staticmethod
    def _trail(size, center, spec):
        """The slash trail: the tip's path, a hot edge, orange, a violet tail."""
        start, end, radius, alpha = spec
        W, H = size
        ys, xs = np.mgrid[0:H, 0:W]
        d = np.hypot(xs - center[0], ys - center[1])
        ang = np.degrees(np.arctan2(ys - center[1], xs - center[0])) % 360
        lo, hi = start % 360, end % 360
        inside = (ang >= lo) & (ang <= hi) if lo <= hi else (ang >= lo) | (ang <= hi)
        span = (hi - lo) % 360 or 360
        fade = np.clip(1 - ((ang - lo) % 360) / span, 0.2, 1)
        a = np.zeros((H, W, 4), np.uint8)
        for r0, r1, color, k in ((radius - 10, radius + 4, (255, 240, 190), 1.0),
                                 (radius - 40, radius - 10, (255, 128, 40), 0.75),
                                 (radius - 80, radius - 40, (176, 100, 255), 0.35)):
            band = inside & (d >= r0) & (d < r1)
            a[band, :3] = color
            a[band, 3] = (alpha * k * fade[band]).astype(np.uint8)
        return Image.fromarray(a)

    @staticmethod
    def _impact(draw, tip, ground, stage):
        tx = float(tip[0])
        big = stage == 2
        rx, ry = (110, 26) if big else (60, 14)
        draw.ellipse((tx - rx, ground - ry, tx + rx, ground + ry), outline=(255, 236, 170, 230), width=6)
        draw.ellipse((tx - rx + 14, ground - ry + 6, tx + rx - 14, ground + ry - 4),
                     outline=(255, 120, 40, 210), width=5)
        for k in range(15):                                   # lava spray
            sx = tx + (k - 7) * (16 if big else 10)
            sy = ground - 10 - (7 - abs(k - 7)) * (12 if big else 7)
            color = (255, 210, 110, 255) if k % 2 else (255, 110, 40, 255)
            draw.ellipse((sx - 5, sy - 5, sx + 5, sy + 5), fill=color)
        for k in range(0, 200 if big else 120, 6):              # glowing cracks
            jx = tx + 30 - k
            draw.line([(jx, ground - 2 - (k * 7) % 9), (jx - 6, ground - (k * 5) % 7)],
                      fill=(255, 150, 50, 255), width=3)
        for k, x in enumerate((tx - 60, tx - 10, tx + 50)):     # dust
            r = (26 if big else 18) + k * 4
            draw.ellipse((x - r, ground - r, x + r, ground + 4), fill=(150, 130, 105, 140))

    def _shrink(self, canvas, pad):
        W = self.game_w + 2 * pad[0]
        H = GAME_H + pad[1]
        small = canvas.resize((W, H), Image.BOX)
        a = np.array(small)
        a[..., 3] = np.where(a[..., 3] >= 110, 255, 0)
        return Image.fromarray(a)

    def still(self):
        """The rest pose at game size, no padding: assets/enemies/enemy_boss.png."""
        return self.pose((0, 0))[0]
