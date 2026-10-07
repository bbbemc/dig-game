"""Lightweight lantern, lava and helmet-lamp lighting for the cave view.

A screen-sized light map starts at a depth-dependent ambient level with a
gentle vignette and receives additive radial lights; multiplying the frame
by it dims unlit earth while lanterns, lava and the miner's lamp keep their
surroundings at full colour. A small additive bloom then warms the air right
around each flame. Every light sprite is rendered once per radius, colour and
intensity step, so flicker and pulse only pick a cached surface per frame.
"""

import math

import pygame

from config import MACRO

LEVELS = 6
# Ambient light map colour by depth (macro row); lerped between bands.
AMBIENT = ((0, (214, 204, 192)), (25, (200, 194, 188)), (50, (184, 188, 204)),
           (75, (202, 182, 170)), (100, (198, 174, 164)))
# Intensity range and flicker speed by light kind.
BEHAVIOUR = {'lamp': (0.86, 1.0, 1.0), 'torch': (0.78, 1.0, 1.5),
             'crystal': (0.8, 1.0, 0.18), 'lava': (0.82, 1.0, 0.25),
             'water': (0.85, 1.0, 0.2), 'helmet': (1.0, 1.0, 0.0)}
# Warm air glow added on top of the frame: radius and peak (R, G, B).
BLOOM = {'lamp': (74, (58, 36, 12)), 'torch': (84, (66, 40, 12)), 'lava': (96, (60, 22, 4)),
         'crystal': (60, (22, 22, 34))}


def ambient_at(row):
    for (y0, c0), (y1, c1) in zip(AMBIENT, AMBIENT[1:]):
        if row <= y1:
            t = max(0.0, min(1.0, (row - y0) / (y1 - y0)))
            # Ease the band changes so descending never pops.
            t = t * t * (3 - 2 * t)
            return tuple(round(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
    return AMBIENT[-1][1]


def _profile(distance, radius):
    """Bright core, warm middle glow, faint wide falloff (all in [0, 1])."""
    t = distance / radius
    if t >= 1:
        return 0.0
    core = math.exp(-(distance / max(4.0, radius * 0.12)) ** 2)
    middle = (1 - min(1.0, t / 0.5)) ** 1.6
    wide = (1 - t) ** 2
    return min(1.0, 0.45 * core + 0.45 * middle + 0.4 * wide)


def radial(radius, color, strength):
    """Additive light sprite drawn as fine concentric rings."""
    radius = max(2, round(radius))
    surface = pygame.Surface((radius * 2, radius * 2), 0, 32)
    surface.fill((0, 0, 0))
    for r in range(radius, 0, -1):
        k = _profile(r - 0.5, radius) * strength
        pygame.draw.circle(surface, tuple(min(255, round(c * k)) for c in color), (radius, radius), r)
    return surface


class Lighting:
    def __init__(self, size):
        self.size = size
        self.map = pygame.Surface(size, 0, 32)
        self.sprites = {}
        self.visible = 0
        self.draw_calls = 0
        # Vignette: full light in the middle, ~80% in the far corners.
        small = pygame.Surface((32, 22), 0, 32)
        for y in range(22):
            for x in range(32):
                d = math.hypot((x - 15.5) / 16, (y - 10.5) / 11)
                v = round(255 - 52 * max(0.0, d - 0.45) ** 1.4 / 0.8)
                small.set_at((x, y), (v, v, v))
        self.vignette = pygame.transform.smoothscale(small, size)

    def _sprite(self, kind, radius, color, level, bloom=False):
        key = (kind, round(radius), color, level, bloom)
        if key not in self.sprites:
            low, high, _ = BEHAVIOUR[kind]
            k = low + (high - low) * level / (LEVELS - 1)
            if bloom:
                size, tint = BLOOM[kind]
                if kind == 'crystal':
                    tint = tuple(min(255, round(c * 0.25)) for c in color)
                self.sprites[key] = radial(size * (0.85 + 0.15 * k), tint, k)
            else:
                self.sprites[key] = radial(radius * (0.92 + 0.08 * k), color, k)
        return self.sprites[key]

    @staticmethod
    def _level(kind, t, phase):
        _, _, speed = BEHAVIOUR[kind]
        if kind in ('lamp', 'torch'):
            wave = 0.6 * math.sin(t * 7.3 * speed + phase) + 0.4 * math.sin(t * 13.1 * speed + phase * 2.3)
        else:
            wave = math.sin(t * 6.0 * speed + phase)
        return max(0, min(LEVELS - 1, round((wave * 0.5 + 0.5) * (LEVELS - 1))))

    def draw(self, screen, camera, t, sources, player=None):
        """``sources``: (kind, world x, world y, radius px, colour, phase)."""
        cx, cy = camera
        width, height = self.size
        light_map = self.map
        light_map.fill(ambient_at((cy + height / 2) / MACRO))
        light_map.blit(self.vignette, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        adds, blooms = [], []
        for kind, x, y, radius, color, phase in sources:
            sx, sy = x - cx, y - cy
            if not (-radius < sx < width + radius and -radius < sy < height + radius):
                continue
            level = self._level(kind, t, phase)
            sprite = self._sprite(kind, radius, color, level)
            adds.append((sprite, (round(sx - sprite.get_width() / 2), round(sy - sprite.get_height() / 2))))
            if kind in BLOOM:
                glow = self._sprite(kind, radius, color, level, bloom=True)
                blooms.append((glow, (round(sx - glow.get_width() / 2), round(sy - glow.get_height() / 2))))
        if player is not None:
            x, y = player
            sprite = self._sprite('helmet', 150, (150, 140, 120), 0)
            adds.append((sprite, (round(x - cx - 150), round(y - cy - 150))))
        flags = pygame.BLEND_RGB_ADD
        light_map.blits([(s, p, None, flags) for s, p in adds], doreturn=False)
        screen.blit(light_map, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        screen.blits([(s, p, None, flags) for s, p in blooms], doreturn=False)
        self.visible = len(adds)
        self.draw_calls = len(adds) + len(blooms) + 3
