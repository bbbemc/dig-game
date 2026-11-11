"""Parallax depth behind the Stage 5.5 arena, and the air drifting through it.

Three painted layers lie behind the hall's open middle, where the renderer
fades its rear wall out (see WorldRenderer's backdrop mask):

- the abyss: violet gloom over a far lava sea whose glow climbs from below;
- distant colossal columns and broken arches, hazy with depth;
- nearer pillars and hanging chains in near-silhouette, rim-lit by the lava.

Each scrolls at a fraction of the camera, so the hall reads as one ledge of
a vast cavern. Layers are painted once at half resolution in the Deep
Descent palette and doubled with nearest scaling, which keeps their pixels as
chunky as the sprite sheet's. ``ArenaAir`` adds slow dust (lit like the
world) and rising embers (drawn after the light map, so they glow).
"""

import math
import random

import pygame

PIXEL = 2                  # painted at half resolution, doubled on build
HORIZON = 900              # px from a layer's top to its lava horizon
HORIZON_LIFT = 80          # the far lava sea's horizon sits this far above the floor
LAYER_HEIGHT = 1000

# (factor, tile width px): farther layers scroll less.
ABYSS, FAR, NEAR = (0.1, 640), (0.3, 880), (0.55, 1120)

VOID = ((14, 10, 24), (22, 15, 36), (32, 22, 50), (46, 29, 64))
GLOW = ((64, 28, 46), (100, 38, 40), (156, 56, 34), (214, 86, 36))
LAVA = ((224, 96, 34), (255, 150, 60), (255, 206, 120))
CRYSTAL = ((120, 190, 240), (178, 120, 247), (210, 170, 255))


def _gradient_rows(height, stops):
    """Row colours between (position 0..1, colour) stops, banded and dithered
    so the ramp keeps the pixel-art look instead of a smooth airbrush."""
    rows = []
    for y in range(height):
        t = y / max(1, height - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                break
        else:
            (t0, c0), (t1, c1), k = stops[-2], stops[-1], 1.0
        steps = 6
        band = k * steps
        low = math.floor(band)
        rows.append((c0, c1, low / steps, min(steps, low + 1) / steps, band - low))
    return rows


def _paint_gradient(surface, stops):
    width, height = surface.get_size()
    for y, (c0, c1, k0, k1, frac) in enumerate(_gradient_rows(height, stops)):
        a = tuple(round(c0[i] + (c1[i] - c0[i]) * k0) for i in range(3))
        b = tuple(round(c0[i] + (c1[i] - c0[i]) * k1) for i in range(3))
        surface.fill(a, (0, y, width, 1))
        if frac > 0.35:                    # 2x2 ordered dither toward the next band
            for x in range((y % 2) if frac < 0.7 else 0, width, 2 if frac < 0.7 else 1):
                if frac >= 0.7 and (x + y) % 2:
                    continue
                surface.set_at((x, y), b)


def _wrap_polygon(surface, color, points):
    """A polygon drawn again one tile left and right, so layers tile seamlessly."""
    width = surface.get_width()
    for shift in (-width, 0, width):
        pygame.draw.polygon(surface, color, [(x + shift, y) for x, y in points])


def _wrap_rect(surface, color, rect):
    width = surface.get_width()
    rect = pygame.Rect(rect)
    for shift in (-width, 0, width):
        surface.fill(color, rect.move(shift, 0))


def _stalactites(surface, rng, color, count, depth):
    width = surface.get_width()
    for _ in range(count):
        x, w = rng.uniform(0, width), rng.uniform(6, 18)
        length = rng.uniform(depth * 0.4, depth)
        _wrap_polygon(surface, color, [(x - w, 0), (x + w, 0), (x + w * 0.2, length),
                                       (x - w * 0.1, length * 0.8)])


def _column(surface, x, top, bottom, width, body, shade, light, glow):
    """A colossal column: plinth, banded shaft, capital, a lit edge and
    the lava's warm underglow climbing its foot."""
    _wrap_rect(surface, body, (x, top, width, bottom - top))
    _wrap_rect(surface, shade, (x + width * 0.62, top, width * 0.38, bottom - top))
    _wrap_rect(surface, light, (x + 2, top, 2, bottom - top))
    for y in range(top + 30, bottom - 20, 46):             # drum joints
        _wrap_rect(surface, shade, (x, y, width, 2))
    for y0, grow in ((bottom - 16, 8), (bottom - 8, 12)):   # plinth
        _wrap_rect(surface, body, (x - grow // 2, y0, width + grow, 8))
        _wrap_rect(surface, light, (x - grow // 2, y0, width + grow, 1))
    for k, color in enumerate(glow):                        # underglow
        _wrap_rect(surface, color, (x - 6, bottom - 34 + k * 9, width + 12, 3))


def _paint_abyss(width):
    w, h = width // PIXEL, LAYER_HEIGHT // PIXEL
    horizon = HORIZON // PIXEL
    surface = pygame.Surface((w, h), 0, 32)
    _paint_gradient(surface, ((0.0, VOID[0]), (0.45, VOID[2]), (0.72, VOID[3]),
                              (0.84, GLOW[0]), (0.93, GLOW[1]), (1.0, GLOW[3])))
    rng = random.Random(5501)
    _stalactites(surface, rng, VOID[1], 16, 110)
    # Far crags along the lava sea, rim-lit from below.
    for _ in range(9):
        x, rise, span = rng.uniform(0, w), rng.uniform(14, 48), rng.uniform(30, 80)
        crag = [(x - span, horizon), (x - span * 0.3, horizon - rise),
                (x + span * 0.1, horizon - rise * 0.7), (x + span, horizon)]
        _wrap_polygon(surface, (34, 16, 28), crag)
        _wrap_polygon(surface, GLOW[1], [(x - span * 0.3, horizon - rise),
                                         (x - span * 0.15, horizon - rise + 2),
                                         (x - span * 0.35, horizon - rise + 3)])
    # The lava sea itself: bright seams over a dark crust.
    surface.fill(GLOW[2], (0, horizon, w, h - horizon))
    for y in range(horizon + 1, h, 3):
        for _ in range(w // 18):
            x = rng.randrange(w)
            surface.fill(LAVA[rng.randrange(2)], (x, y, rng.randint(3, 12), 1))
    surface.fill(LAVA[2], (0, horizon, w, 1))
    for _ in range(70):                                     # crystal glints in the dark
        surface.set_at((rng.randrange(w), rng.randrange(horizon // 2)),
                       CRYSTAL[rng.randrange(3)])
    return surface


def _paint_far(width):
    w, h = width // PIXEL, LAYER_HEIGHT // PIXEL
    horizon = HORIZON // PIXEL
    surface = pygame.Surface((w, h), pygame.SRCALPHA)
    rng = random.Random(5502)
    body, shade, light = (54, 39, 78), (42, 29, 62), (92, 70, 126)
    glow = ((84, 38, 50), (116, 48, 44), (156, 62, 40))
    # Broken arches spanning between the columns.
    for left in (0, w // 2):
        cx, radius = left + w // 4, w // 4 - 10
        pygame.draw.circle(surface, body, (cx, horizon - 210), radius, 14,
                           draw_top_left=True, draw_top_right=True)
        pygame.draw.circle(surface, light, (cx, horizon - 210), radius, 1,
                           draw_top_left=True, draw_top_right=True)
    for x, wide in ((14, 34), (w // 2 + 10, 40)):
        _column(surface, x, 0, horizon, wide, body, shade, light, glow)
    broken = w // 4 + 18
    _column(surface, broken, horizon - 150, horizon, 30, body, shade, light, glow)
    _wrap_polygon(surface, body, [(broken - 2, horizon - 150), (broken + 12, horizon - 168),
                                  (broken + 24, horizon - 156), (broken + 32, horizon - 150)])
    _stalactites(surface, rng, (24, 16, 36), 10, 70)
    for _ in range(20):
        surface.set_at((rng.randrange(w), rng.randrange(40, horizon - 60)), CRYSTAL[0])
    return surface


def _paint_near(width):
    w, h = width // PIXEL, LAYER_HEIGHT // PIXEL
    horizon = HORIZON // PIXEL
    surface = pygame.Surface((w, h), pygame.SRCALPHA)
    rng = random.Random(5503)
    body, shade, light = (30, 21, 44), (22, 15, 33), (76, 54, 104)
    glow = ((72, 30, 34), (108, 42, 34), (160, 60, 36))
    _column(surface, w // 6, 0, horizon, 56, body, shade, light, glow)
    stump = w * 2 // 3
    _column(surface, stump, horizon - 120, horizon, 50, body, shade, light, glow)
    _wrap_polygon(surface, body, [(stump - 4, horizon - 120), (stump + 18, horizon - 142),
                                  (stump + 34, horizon - 128), (stump + 54, horizon - 120)])
    # Fallen drums at its foot.
    for x, size in ((stump + 70, 22), (stump - 40, 16)):
        _wrap_rect(surface, body, (x, horizon - size, size + 8, size))
        _wrap_rect(surface, light, (x, horizon - size, size + 8, 1))
    # Chains dropping out of the dark from far above.
    for x in (w // 6 + 90, w // 2 - 20, w - 70):
        length = rng.randint(140, 300)
        for y in range(0, length, 6):
            link = (x - 2, y, 5, 4) if (y // 6) % 2 else (x - 1, y, 3, 5)
            _wrap_rect(surface, (44, 32, 60), link)
            _wrap_rect(surface, (78, 58, 100), (link[0], link[1], 1, 1))
        if rng.random() < 0.7:
            _wrap_polygon(surface, (90, 30, 34), [(x - 9, length), (x + 9, length),
                                                  (x + 9, length + 30), (x, length + 22),
                                                  (x - 9, length + 30)])
            _wrap_rect(surface, (180, 120, 60), (x - 9, length, 18, 2))
    _stalactites(surface, rng, body, 7, 90)
    return surface


class ArenaBackdrop:
    """The painted parallax layers, positioned against the arena's floor line.

    ``floor_y`` is the world y of the floor top; ``rest_y`` the camera y at
    which a layer's lava horizon sits exactly on that floor line.
    """

    def __init__(self, floor_y, rest_y):
        self.floor_y, self.rest_y = floor_y, rest_y
        self.layers = []
        for (factor, width), paint in ((ABYSS, _paint_abyss), (FAR, _paint_far),
                                       (NEAR, _paint_near)):
            image = paint(width)
            image = pygame.transform.scale(image, (image.get_width() * PIXEL,
                                                   image.get_height() * PIXEL))
            self.layers.append((factor, image))

    def draw(self, screen, camera):
        cx, cy = camera
        width, height = screen.get_size()
        screen.fill(VOID[0])
        for factor, image in self.layers:
            tile = image.get_width()
            horizon = (self.floor_y - HORIZON_LIFT - self.rest_y) + (self.rest_y - cy) * factor
            y = round(horizon - HORIZON)
            if y >= height or y + image.get_height() <= 0:
                continue
            x = -round(cx * factor) % tile - tile
            blits = []
            while x < width:
                blits.append((image, (x, y)))
                x += tile
            screen.blits(blits, doreturn=False)


class ArenaAir:
    """Dust hanging in the hall's air and embers rising off the lava below.

    Positions are world pixels inside ``bounds``; nothing here touches the
    simulation, and a fixed seed keeps runs reproducible.
    """

    DUST = ((150, 136, 170), (120, 108, 140), (190, 176, 200))
    EMBERS = ((255, 150, 60), (255, 206, 120), (255, 112, 44))

    def __init__(self, bounds, dust=46, embers=34, seed=5504):
        self.bounds = pygame.Rect(bounds)
        self.random = random.Random(seed)
        self.dust = [self._mote() for _ in range(dust)]
        self.embers = [self._ember(spread=True) for _ in range(embers)]

    def _mote(self):
        rnd, box = self.random, self.bounds
        return [rnd.uniform(box.left, box.right), rnd.uniform(box.top, box.bottom),
                rnd.uniform(-7, 7), rnd.uniform(-4, 3), rnd.uniform(0, 6.28),
                rnd.choice((1, 1, 2)), rnd.choice(self.DUST)]

    def _ember(self, spread=False):
        rnd, box = self.random, self.bounds
        y = rnd.uniform(box.top, box.bottom) if spread else box.bottom - rnd.uniform(0, 30)
        life = rnd.uniform(3.0, 6.5)
        return [rnd.uniform(box.left, box.right), y, rnd.uniform(-6, 6),
                -rnd.uniform(18, 42), rnd.uniform(0, 6.28), life,
                rnd.uniform(0, life) if spread else life, rnd.choice(self.EMBERS)]

    def update(self, dt):
        box = self.bounds
        for mote in self.dust:
            mote[4] += dt
            mote[0] += (mote[2] + math.sin(mote[4] * 0.6) * 4) * dt
            mote[1] += (mote[3] + math.cos(mote[4] * 0.45) * 3) * dt
            if not box.collidepoint(mote[0], mote[1]):
                mote[0] = box.left + (mote[0] - box.left) % box.width
                mote[1] = box.top + (mote[1] - box.top) % box.height
        for n, ember in enumerate(self.embers):
            ember[4] += dt
            ember[6] -= dt
            ember[0] += (ember[2] + math.sin(ember[4] * 1.7) * 10) * dt
            ember[1] += ember[3] * dt
            if ember[6] <= 0 or ember[1] < box.top:
                self.embers[n] = self._ember()

    def draw_dust(self, screen, camera):
        cx, cy = camera
        width, height = screen.get_size()
        for x, y, _, _, phase, size, color in self.dust:
            sx, sy = round(x - cx), round(y - cy)
            if 0 <= sx < width and 0 <= sy < height and math.sin(phase * 0.8) > -0.6:
                screen.fill(color, (sx, sy, size, size))

    def draw_embers(self, screen, camera):
        """Additive, after the light map: embers are their own light."""
        cx, cy = camera
        width, height = screen.get_size()
        add = pygame.BLEND_RGB_ADD
        for x, y, _, _, phase, life, left, color in self.embers:
            sx, sy = round(x - cx), round(y - cy)
            if not (1 <= sx < width - 1 and 1 <= sy < height - 1):
                continue
            k = min(1.0, left / 0.8, (life - left) / 0.5) * (0.75 + 0.25 * math.sin(phase * 9))
            if k <= 0.05:
                continue
            halo = tuple(round(c * 0.28 * k) for c in color)
            core = tuple(round(c * k) for c in color)
            screen.fill(halo, (sx - 1, sy - 1, 3, 3), special_flags=add)
            screen.fill(core, (sx, sy, 1 + (k > 0.6), 1 + (k > 0.6)), special_flags=add)
