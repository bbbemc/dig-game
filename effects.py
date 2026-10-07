"""Pooled, capped particles: dig debris, landing dust, lava embers, water
splashes and slow dust motes in lantern light. Deterministic, camera culled.

A particle is a short list ``[x, y, vx, vy, life, max_life, colour, size,
gravity, drag]``; dead ones are dropped in a single pass each update and no
emitter may exceed MAX_PARTICLES in total.
"""
import math
import random

from config import CELL, MAX_PARTICLES

DIRT = ((158, 112, 73), (122, 82, 52), (186, 138, 92))
DUST = ((150, 128, 104), (124, 104, 86), (176, 156, 130))
EMBERS = ((255, 214, 120), (255, 150, 52), (240, 96, 34))
SPLASH = ((150, 214, 255), (91, 194, 255), (210, 240, 255))
MOTE = ((214, 190, 150), (190, 170, 140))


class Particles:
    def __init__(self):
        self.items = []
        self.random = random.Random(42)

    def _add(self, x, y, vx, vy, life, color, size=2, gravity=450.0, drag=0.0):
        if len(self.items) >= MAX_PARTICLES:
            return False
        self.items.append([x, y, vx, vy, life, life, color, size, gravity, drag])
        return True

    def dirt(self, world, removed, palette=None):
        """Clods thrown from freshly dug cells, coloured by their ground."""
        rnd = self.random
        for i in removed[::max(1, len(removed) // 12)][:12]:
            x, y = world.coords(i)
            colors = palette(x, y) if palette else DIRT
            if not self._add(x * CELL + CELL / 2, y * CELL + CELL / 2,
                             rnd.uniform(-65, 65), rnd.uniform(-100, -35),
                             rnd.uniform(.2, .5), rnd.choice(colors), rnd.choice((1, 2, 2))):
                break

    def dust(self, x, y, strength=1.0):
        """A low puff where boots meet the floor after a fall."""
        rnd = self.random
        for _ in range(round(4 + 6 * strength)):
            side = rnd.choice((-1, 1))
            if not self._add(x + side * rnd.uniform(2, 12), y - rnd.uniform(0, 3),
                             side * rnd.uniform(20, 70) * strength, rnd.uniform(-38, -10),
                             rnd.uniform(.25, .5), rnd.choice(DUST), rnd.choice((1, 2)), 60.0, 3.0):
                break

    def ember(self, x, y):
        rnd = self.random
        self._add(x, y, rnd.uniform(-12, 12), rnd.uniform(-60, -30), rnd.uniform(.6, 1.2),
                  rnd.choice(EMBERS), rnd.choice((1, 1, 2)), -8.0, 0.6)

    def splash(self, x, y, strength=1.0):
        rnd = self.random
        for _ in range(round(5 + 5 * strength)):
            if not self._add(x + rnd.uniform(-10, 10), y, rnd.uniform(-60, 60),
                             rnd.uniform(-150, -60) * strength, rnd.uniform(.25, .45),
                             rnd.choice(SPLASH), rnd.choice((1, 2)), 520.0):
                break

    def mote(self, x, y):
        rnd = self.random
        self._add(x, y, rnd.uniform(-5, 5), rnd.uniform(-5, 3), rnd.uniform(2.5, 4.5),
                  rnd.choice(MOTE), 1, 0.0, 0.0)

    def count(self, gravity):
        return sum(1 for p in self.items if p[8] == gravity)

    def update(self, dt):
        alive = []
        for p in self.items:
            p[4] -= dt
            if p[4] > 0:
                p[3] += p[8] * dt
                if p[9]:
                    damping = max(0.0, 1 - p[9] * dt)
                    p[2] *= damping
                    p[3] *= damping
                if p[8] == 0.0:
                    p[2] += math.sin(p[4] * 2.1 + p[1] * 0.05) * 6 * dt
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                alive.append(p)
        self.items = alive

    def draw(self, screen, camera):
        cx, cy = camera
        width, height = screen.get_size()
        fill = screen.fill
        for x, y, _, _, life, max_life, color, size, gravity, _ in self.items:
            sx, sy = round(x - cx), round(y - cy)
            if 0 <= sx < width and 0 <= sy < height:
                if gravity == 0.0:
                    # Motes fade in and out instead of popping.
                    fade = min(1.0, life / max_life * 3, (max_life - life) * 2)
                    color = tuple(round(c * (0.35 + 0.65 * fade)) for c in color)
                fill(color, (sx, sy, size if life > max_life * 0.35 else 1, size))
