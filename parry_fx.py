"""Cinematic, procedural pixel-art combat effects.

Everything is drawn with hard-edged pygame primitives (no antialiasing, no
assets) in the lantern palette the rest of the game uses, and everything
expensive is built once and cached:

* the impact flash and the sword-clash slash are pre-rendered frame strips;
* shockwave rings reuse one scratch surface per size and blend additively,
  so they fade to transparent (a dark rim just inside the gold ring stands in
  for shader distortion);
* the screen-edge flash and impact vignette are pre-built gradient strips
  that only change their alpha;
* sparks are a pooled list of short trail lines.

``CombatEffects`` holds the live effects in world pixels. They age with real
frame time, so sparks, flashes and rings keep moving through a hitstop.
"""

import math
import random

import pygame

from config import PARRY_FLASH_TIME, SCREEN_W, SCREEN_H

ARC = ((255, 250, 226), (255, 222, 128), (232, 163, 50))
STEPS = 8
_cache = {}
WHITE = (255, 255, 255)
# Spark and slash colour ramps, hottest first.
GOLD = ((255, 255, 255), (255, 242, 178), (255, 208, 86), (255, 150, 44), (206, 80, 28))
EMBER = ((255, 236, 200), (255, 170, 96), (246, 104, 50), (214, 52, 36), (130, 26, 26))
RING_GOLD = ((255, 222, 120), (240, 140, 44))
RING_RED = ((255, 120, 70), (200, 44, 36))
EDGE_GOLD, EDGE_RED, EDGE_ORANGE = (255, 196, 80), (232, 58, 40), (255, 140, 52)
# Short-lived light at an impact: radius and colour per kind.
LIGHTS = {'clash': (96, (255, 226, 160)), 'perfect': (136, (255, 220, 140)),
          'break': (140, (255, 110, 60)), 'deathblow': (140, (255, 90, 70))}
FLASH_FRAMES = 5
SLASH_FRAMES = 7
EDGE = 84                       # px depth of the screen-edge glow


def _scaled(color, k):
    return tuple(max(0, min(255, round(c * k))) for c in color)


# -- the guard arc while the window is open (drawn before lighting) ------------
def _arc_image(step, facing, strength_level):
    """A crescent in front of the miner that sweeps from top to bottom."""
    key = ('arc', step, facing, strength_level)
    if key in _cache:
        return _cache[key]
    size = 64
    image = pygame.Surface((size, size), pygame.SRCALPHA)
    centre = size // 2
    t = step / (STEPS - 1)
    sweep = -1.15 + 2.3 * t                # leading edge, radians from horizontal
    alpha = 255 if strength_level else 210
    for ring, color in enumerate(ARC):
        radius = 23 - ring * 3
        rect = pygame.Rect(centre - radius, centre - radius, radius * 2, radius * 2)
        trail = 1.15 if strength_level else 0.6 + 0.5 * t   # the arc grows as it swings
        start, stop = max(-1.15, sweep - trail), sweep
        if stop - start < 0.12:
            continue
        # pygame angles run counter-clockwise from +x; screen y points down.
        pygame.draw.arc(image, (*color, alpha - ring * 40), rect, -stop, -start, 2)
    # A motion streak: a few faint pixels behind the leading edge.
    for n in range(3):
        angle = sweep - 0.3 - n * 0.25
        x = centre + round(math.cos(angle) * (27 + n))
        y = centre + round(math.sin(angle) * (27 + n))
        image.fill((255, 236, 170, 140 - n * 40), (x, y, 2, 2))
    if facing < 0:
        image = pygame.transform.flip(image, True, False)
    _cache[key] = image
    return image


def guard_arc(screen, player_box, facing, progress, strength=1.0):
    """``player_box`` is the miner's screen rect; ``progress`` 0..1 of the window."""
    step = max(0, min(STEPS - 1, round(progress * (STEPS - 1))))
    image = _arc_image(step, facing, strength > 1.0)
    rect = image.get_rect(center=(player_box.centerx + facing * 4, player_box.centery - 2))
    screen.blit(image, rect)


# -- impact flash ---------------------------------------------------------------
def _ray(surface, color, centre, angle, length, width):
    """A tapered, diamond-shaped ray: sharp pixel silhouette, no smoothing."""
    cx, cy = centre
    dx, dy = math.cos(angle), math.sin(angle)
    px, py = -dy * width, dx * width
    base = 0.18 * length
    points = [(cx - dx * 2, cy - dy * 2), (cx + dx * base + px, cy + dy * base + py),
              (cx + dx * length, cy + dy * length), (cx + dx * base - px, cy + dy * base - py)]
    pygame.draw.polygon(surface, color, [(round(x), round(y)) for x, y in points])


def flash_frames(scale=1.0, tint='gold'):
    """Pre-rendered impact flash on black, for additive blending.

    It appears at full size almost instantly, then the rays stretch and cool
    while the white core shrinks around a golden centre.
    """
    key = ('flash', scale, tint)
    if key in _cache:
        return _cache[key]
    size = round(72 * scale) | 1
    centre = (size // 2, size // 2)
    edge = (255, 206, 84) if tint == 'gold' else (255, 112, 60)
    middle = (255, 238, 170) if tint == 'gold' else (255, 186, 140)
    frames = []
    for k in range(FLASH_FRAMES):
        t = k / (FLASH_FRAMES - 1)
        fade = 1.0 - 0.8 * t
        surface = pygame.Surface((size, size))
        surface.fill((0, 0, 0))
        grow = 0.75 if k == 0 else 1.0
        long_ray = (14 + 18 * min(1.0, 0.4 + t * 1.4)) * scale * grow
        width = max(1.0, (3.2 - 2.2 * t) * scale)
        for n in range(4):                        # the cross
            _ray(surface, _scaled(edge, fade), centre, n * math.pi / 2, long_ray, width + 1)
            _ray(surface, _scaled(middle, fade), centre, n * math.pi / 2, long_ray * 0.8, width)
        for n in range(4):                        # short diagonal glints
            _ray(surface, _scaled(edge, fade * 0.8), centre, math.pi / 4 + n * math.pi / 2,
                 long_ray * 0.42, max(1.0, width - 1))
        core = max(2, round((7 - 4 * t) * scale * grow))
        pygame.draw.circle(surface, _scaled(WHITE, fade), centre, core)
        pygame.draw.circle(surface, _scaled((255, 214, 92) if tint == 'gold' else (255, 150, 70),
                                            fade), centre, max(1, core // 2))
        if k >= 1:                                # specks thrown outward
            reach = (8 + 14 * t) * scale
            for n in range(8):
                angle = n * math.pi / 4 + math.pi / 8
                x = round(centre[0] + math.cos(angle) * reach)
                y = round(centre[1] + math.sin(angle) * reach)
                surface.fill(_scaled(middle, fade), (x, y, 2, 2))
        frames.append(surface)
    _cache[key] = frames
    return frames


# -- sword-clash slash ----------------------------------------------------------
def _ease_out(t):
    return 1 - (1 - t) ** 3


def slash_frames(perfect=False, facing=1):
    """A curved slash at the impact: white edge, gold body, lagging orange trail.

    Rendered pixel by pixel once (a crescent whose head sweeps fast and whose
    tail follows), so it keeps a hard pixel silhouette at any size.
    """
    key = ('slash', perfect, facing)
    if key in _cache:
        return _cache[key]
    if facing < 0:
        frames = [pygame.transform.flip(f, True, False) for f in slash_frames(perfect, 1)]
        _cache[key] = frames
        return frames
    radius, width = (27, 9.5) if perfect else (21, 7.0)
    size = 2 * radius + 10
    c = size / 2
    start, span = -1.3, 2.6
    frames = []
    for k in range(SLASH_FRAMES):
        t = k / (SLASH_FRAMES - 1)
        head = start + span * _ease_out(min(1.0, t / 0.42))
        tail = start + span * max(0.0, (t - 0.18) / 0.82) ** 1.6
        shift = min(len(GOLD) - 3, int(t * 2.6))      # colours cool as it fades
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        trail_head, trail_tail = head - 0.45, max(start, tail - 0.25)
        for y in range(size):
            dy = y + 0.5 - c
            for x in range(size):
                dx = x + 0.5 - c
                r = math.hypot(dx, dy)
                if r > radius + 0.5 or r < radius - 2 * width - 4:
                    continue
                angle = math.atan2(dy, dx)
                color = None
                if tail <= angle <= head and head - tail > 0.05:
                    u = (angle - tail) / (head - tail)
                    w = width * (u ** 0.45) * ((1 - u) ** 0.25) * 1.45
                    depth = (radius - r) / max(1.0, w)
                    if 0 <= depth <= 1:
                        color = GOLD[shift + (0 if depth < 0.28 else 1 if depth < 0.62 else 2)]
                if color is None and trail_tail <= angle <= trail_head and trail_head - trail_tail > 0.05:
                    inner = radius - width - 2
                    u = (angle - trail_tail) / (trail_head - trail_tail)
                    w = width * 0.55 * math.sin(math.pi * u) ** 0.8
                    depth = (inner - r) / max(1.0, w)
                    if 0 <= depth <= 1:
                        color = GOLD[min(len(GOLD) - 1, shift + 3)]
                if color is not None:
                    surface.set_at((x, y), color)
        frames.append(surface)
    _cache[key] = frames
    return frames


def blade_streak(screen, x, y, facing, age, life=0.12):
    """The other blade: a straight streak crossing the slash at the impact."""
    t = max(0.0, min(1.0, age / life))
    length = round(20 * min(1.0, t / 0.3) + 4)
    color = GOLD[1 if t < 0.4 else 2 if t < 0.75 else 3]
    for n in range(length + 1):
        k = n / max(1, length)
        px = round(x + facing * (length * 0.9 - n * 1.5))
        py = round(y - length * 0.75 + n * 1.25)
        screen.fill(color, (px, py, 2 if k < 0.7 else 1, 2))


# -- shockwave ------------------------------------------------------------------
def _scratch(name, side):
    key = ('scratch', name, side)
    if key not in _cache:
        _cache[key] = pygame.Surface((side, side))
    return _cache[key]


def shockwave(screen, x, y, age, life, radius, palette=RING_GOLD):
    """Layered expanding rings that fade out by blending additively."""
    t = age / life
    if not 0 <= t < 1:
        return
    r = 4 + (radius - 4) * (1 - (1 - t) ** 3)       # starts small, expands fast
    k = (1 - t) ** 1.4
    side = 2 * radius + 8
    centre = (side // 2, side // 2)
    glow = _scratch('glow', side)
    glow.fill((0, 0, 0))
    pygame.draw.circle(glow, _scaled(palette[0], k), centre, round(r), 2 if t < 0.45 else 1)
    pygame.draw.circle(glow, _scaled(palette[1], 0.85 * k), centre, round(r * 0.8), 1)
    pygame.draw.circle(glow, _scaled(palette[1], 0.35 * k), centre, round(r * 0.62), 1)
    top_left = (round(x) - centre[0], round(y) - centre[1])
    screen.blit(glow, top_left, special_flags=pygame.BLEND_RGB_ADD)
    if r > 8:            # a dark rim inside the bright one reads as heat distortion
        rim = _scratch('rim', side)
        rim.fill((0, 0, 0))
        pygame.draw.circle(rim, _scaled((70, 60, 50), k), centre, round(r) - 3, 1)
        screen.blit(rim, top_left, special_flags=pygame.BLEND_RGB_SUB)


# -- screen-space edge flash and vignette ----------------------------------------
def _edge_strips(color, depth=EDGE, peak=150):
    """Four gradient strips (top, bottom, left, right) framing the screen."""
    key = ('edge', color, depth, peak)
    if key in _cache:
        return _cache[key]

    def alpha(d):
        return 255 if d < 2 else round(peak * (1 - d / depth) ** 2.2)

    top = pygame.Surface((SCREEN_W, depth), pygame.SRCALPHA)
    side = pygame.Surface((depth, SCREEN_H - 2 * depth), pygame.SRCALPHA)
    for d in range(depth):
        top.fill((*color, alpha(d)), (0, d, SCREEN_W, 1))
        side.fill((*color, alpha(d)), (d, 0, 1, SCREEN_H - 2 * depth))
    corner = pygame.Surface((depth, depth), pygame.SRCALPHA)
    for y in range(depth):
        for x in range(depth):
            corner.set_at((x, y), (*color, alpha(min(x, y))))
    top.blit(corner, (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
    top.blit(pygame.transform.flip(corner, True, False), (SCREEN_W - depth, 0),
             special_flags=pygame.BLEND_RGBA_MAX)
    strips = [(top, (0, 0)),
              (pygame.transform.flip(top, False, True), (0, SCREEN_H - depth)),
              (side, (0, depth)),
              (pygame.transform.flip(side, True, False), (SCREEN_W - depth, depth))]
    _cache[key] = strips
    return strips


def edge_flash(screen, color, alpha, depth=EDGE, peak=150):
    if alpha <= 0:
        return
    for surface, position in _edge_strips(color, depth, peak):
        surface.set_alpha(alpha)
        screen.blit(surface, position)


# -- small markers ----------------------------------------------------------------
def dizzy(screen, box, time, count=3, color=(255, 236, 140), size=2):
    """Sparks circling above a stunned head."""
    phase = int(time * 10)
    for n in range(count):
        angle = phase * 0.6 + n * 2 * math.pi / count
        px = box.centerx + round(math.cos(angle) * box.w * 0.4)
        screen.fill(color, (px, box.y - 6 + round(math.sin(angle) * 2), size, size))


def deathblow_mark(screen, x, y, time):
    """Sekiro's red dot: a pulsing pixel diamond over a guard-broken enemy."""
    pulse = 1 if int(time * 6) % 2 else 0
    r = 3 + pulse
    screen.fill((40, 12, 12), (x - r - 1, y - 1, 2 * r + 3, 3))
    screen.fill((40, 12, 12), (x - 1, y - r - 1, 3, 2 * r + 3))
    for dy in range(-r, r + 1):
        half = r - abs(dy)
        screen.fill((226, 46, 40), (x - half, y + dy, 2 * half + 1, 1))
    screen.fill((255, 170, 150), (x - 1, y - 1, 2, 2))


def glow_sprite(color, radius=4):
    """A tiny soft dot on black for additive glows around hot spark heads."""
    key = ('glow', color, radius)
    if key not in _cache:
        side = radius * 2 + 1
        surface = pygame.Surface((side, side))
        surface.fill((0, 0, 0))
        for r in range(radius, 0, -1):
            pygame.draw.circle(surface, _scaled(color, 0.32 * (1 - r / (radius + 1)) ** 1.2),
                               (radius, radius), r)
        _cache[key] = surface
    return _cache[key]


def warm():
    """Build the cached frames up front so the first parry never hitches."""
    for perfect in (False, True):
        for facing in (1, -1):
            slash_frames(perfect, facing)
    for scale, tint in ((1.0, 'gold'), (1.35, 'gold'), (1.6, 'red'), (1.25, 'red')):
        flash_frames(scale, tint)
    for color in (EDGE_GOLD, EDGE_RED, EDGE_ORANGE):
        _edge_strips(color)
    _edge_strips((6, 3, 2), 120, 170)
    for color in (GOLD[1], EMBER[1]):
        glow_sprite(color)


# -- pooled trail sparks ----------------------------------------------------------
class Sparks:
    """Metallic sparks: short glowing trail lines, pooled and capped.

    A spark is ``[x, y, vx, vy, life, max_life, size, gravity, drag, ramp]``.
    Bigger sparks fall harder; a few fast ones keep their speed and fly far.
    """
    LIMIT = 180
    TRAIL = 0.022            # seconds of motion each trail shows

    def __init__(self):
        self.items = []
        self.random = random.Random(31)

    def burst(self, x, y, direction, count, ramp=GOLD, spread=1.05, strays=0.2,
              speed=(120.0, 330.0), far=0.18, radial=False):
        rnd = self.random
        base = 0.0 if direction >= 0 else math.pi
        for n in range(count):
            if len(self.items) >= self.LIMIT:
                break
            if radial or rnd.random() < strays:
                angle = rnd.uniform(0, 2 * math.pi)
            else:
                angle = base + rnd.uniform(-spread, spread)
            flyer = rnd.random() < far
            velocity = rnd.uniform(400, 560) if flyer else rnd.uniform(*speed)
            size = 3 if rnd.random() < 0.15 else 2 if rnd.random() < 0.45 else 1
            life = rnd.uniform(0.2, 0.42) * (1.35 if flyer else 1.0)
            self.items.append([x, y, math.cos(angle) * velocity,
                               math.sin(angle) * velocity - 70, life, life, size,
                               200.0 + 150.0 * size, 2.4 if flyer else 4.6, ramp])

    def update(self, dt):
        if not dt:
            return
        alive = []
        for p in self.items:
            p[4] -= dt
            if p[4] <= 0:
                continue
            damping = max(0.0, 1 - p[8] * dt)
            p[2] *= damping
            p[3] = p[3] * damping + p[7] * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            alive.append(p)
        self.items = alive

    def draw(self, screen, camera):
        cx, cy = camera
        width, height = screen.get_size()
        line = pygame.draw.line
        fill = screen.fill
        for x, y, vx, vy, life, max_life, size, _, _, ramp in self.items:
            sx, sy = round(x - cx), round(y - cy)
            if not (-8 <= sx < width + 8 and -8 <= sy < height + 8):
                continue
            heat = life / max_life                    # 1 fresh .. 0 dying
            index = 0 if heat > 0.8 else 1 if heat > 0.55 else 2 if heat > 0.3 else 3
            tail = (round(sx - vx * self.TRAIL), round(sy - vy * self.TRAIL))
            line(screen, ramp[min(len(ramp) - 1, index + 1)], tail, (sx, sy),
                 2 if size >= 2 and heat > 0.45 else 1)
            head = max(1, round(size * min(1.0, heat * 2.2)))   # shrinks as it dies
            fill(ramp[index], (sx - head // 2, sy - head // 2, head, head))
            if size >= 2 and heat > 0.35:
                glow = glow_sprite(ramp[1])
                screen.blit(glow, (sx - 4, sy - 4), special_flags=pygame.BLEND_RGB_ADD)


# -- the live effects ------------------------------------------------------------
class CombatEffects:
    """Live combat effects in world pixels, aged with real frame time."""

    def __init__(self):
        self.flashes = []    # [x, y, age, life, scale, tint, light kind]
        self.slashes = []    # [x, y, facing, age, life, perfect]
        self.streaks = []    # [x, y, facing, age, life]
        self.rings = []      # [x, y, age, life, radius, palette]  (age < 0: delayed)
        self.popups = []     # [text, x, y, age, life, colour]
        self.sparks = Sparks()
        self.edge = None     # [age, life, colour, peak alpha]
        self.vignette = None  # [age, life, peak alpha]

    def _screen(self, color, life, alpha, vignette=0):
        if self.edge is None or alpha >= self.edge[3] * (1 - self.edge[0] / self.edge[1]):
            self.edge = [0.0, life, color, alpha]
        if vignette:
            self.vignette = [0.0, life * 0.8, vignette]

    def parry(self, x, y, facing, perfect=False):
        """A successful parry: flash, slash, shockwave, sparks, gold edge."""
        if perfect:
            self.flashes.append([x, y, 0.0, PARRY_FLASH_TIME, 1.35, 'gold', 'perfect'])
            self.slashes.append([x, y, facing, 0.0, 0.18, True])
            self.rings.append([x, y, 0.0, 0.2, 40, RING_GOLD])
            self.rings.append([x, y, -0.04, 0.18, 30, RING_GOLD])
            self.sparks.burst(x, y, facing, 44, spread=1.2, far=0.25)
            self._screen(EDGE_GOLD, 0.24, 140, vignette=44)
        else:
            self.flashes.append([x, y, 0.0, PARRY_FLASH_TIME, 1.0, 'gold', 'clash'])
            self.slashes.append([x, y, facing, 0.0, 0.14, False])
            self.rings.append([x, y, 0.0, 0.2, 30, RING_GOLD])
            self.sparks.burst(x, y, facing, 30)
            self._screen(EDGE_GOLD, 0.16, 88)
        self.streaks.append([x, y, facing, 0.0, 0.12])

    def guard_break(self, x, y, radius=64):
        """The player's guard shatters: red flash, big shockwave, red edge."""
        self.flashes.append([x, y, 0.0, 0.12, 1.6, 'red', 'break'])
        self.rings.append([x, y, 0.0, 0.36, radius, RING_RED])
        self.rings.append([x, y, -0.06, 0.3, round(radius * 0.7), RING_RED])
        self.sparks.burst(x, y, 1, 40, ramp=EMBER, radial=True, speed=(140.0, 380.0))
        self._screen(EDGE_RED, 0.36, 170, vignette=80)

    def enemy_break(self, x, y, boss=False):
        self.flashes.append([x, y, 0.0, 0.1, 1.25, 'red', 'break'])
        self.rings.append([x, y, 0.0, 0.3, 60 if boss else 44, RING_RED])
        self.sparks.burst(x, y, 1, 32, ramp=EMBER, radial=True)
        self._screen(EDGE_ORANGE, 0.2, 84)

    def deathblow(self, x, y):
        self.flashes.append([x, y, 0.0, 0.12, 1.6, 'red', 'deathblow'])
        self.rings.append([x, y, 0.0, 0.34, 52, RING_RED])
        self.sparks.burst(x, y, 1, 36, ramp=EMBER, radial=True, speed=(160.0, 400.0))
        self._screen(EDGE_RED, 0.24, 110)

    def popup(self, text, x, y, color, life=0.7):
        self.popups.append([text, x, y, 0.0, life, color])

    def update(self, dt):
        if not dt:
            return
        for group in (self.flashes, self.rings):
            for item in group:
                item[2] += dt
        for group in (self.slashes, self.streaks):
            for item in group:
                item[3] += dt
        for item in self.popups:
            item[2] -= 26 * dt          # popups drift upward
            item[3] += dt
        self.flashes = [f for f in self.flashes if f[2] < f[3]]
        self.rings = [r for r in self.rings if r[2] < r[3]]
        self.slashes = [s for s in self.slashes if s[3] < s[4]]
        self.streaks = [s for s in self.streaks if s[3] < s[4]]
        self.popups = [p for p in self.popups if p[3] < p[4]]
        self.sparks.update(dt)
        for name in ('edge', 'vignette'):
            effect = getattr(self, name)
            if effect is not None:
                effect[0] += dt
                if effect[0] >= effect[1]:
                    setattr(self, name, None)

    def lights(self):
        """(kind, x, y, radius, colour, phase) for the lighting pass."""
        for x, y, age, life, _, _, kind in self.flashes:
            radius, color = LIGHTS[kind]
            # Quantised radius keeps the lighting's sprite cache small.
            yield ('flash', x, y, max(16, round(radius * (1 - age / life) / 16) * 16), color, 0)

    def draw(self, screen, camera):
        """World-space effects, drawn emissive after the light map."""
        cx, cy = camera
        for x, y, age, life, radius, palette in self.rings:
            if age >= 0:
                shockwave(screen, x - cx, y - cy, age, life, radius, palette)
        for x, y, facing, age, life, perfect in self.slashes:
            frames = slash_frames(perfect, facing)
            image = frames[min(len(frames) - 1, int(age / life * len(frames)))]
            radius = image.get_width() // 2
            # The crescent wraps the impact on the attacker's side.
            screen.blit(image, (round(x - cx - radius + facing * 4), round(y - cy - radius)))
        for x, y, facing, age, life in self.streaks:
            blade_streak(screen, round(x - cx), round(y - cy), facing, age, life)
        self.sparks.draw(screen, camera)
        for x, y, age, life, scale, tint, _ in self.flashes:
            frames = flash_frames(scale, tint)
            image = frames[min(len(frames) - 1, int(age / life * len(frames)))]
            half = image.get_width() // 2
            screen.blit(image, (round(x - cx) - half, round(y - cy) - half),
                        special_flags=pygame.BLEND_RGB_ADD)

    def draw_screen(self, screen):
        """Screen-space impact vignette and edge flash (short, never opaque)."""
        if self.vignette is not None:
            age, life, peak = self.vignette
            edge_flash(screen, (6, 3, 2), round(peak * (1 - age / life) ** 1.5), 120, 170)
        if self.edge is not None:
            age, life, color, peak = self.edge
            t = age / life
            rise = min(1.0, t / 0.12)                 # snaps on, then eases away
            edge_flash(screen, color, round(peak * rise * (1 - t) ** 1.6))
