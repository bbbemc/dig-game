"""Dirt orbs: little brown beads that burst out of a defeated enemy.

Each orb refills a share of the dig meter when the player touches it. Orbs
from an ordinary kill bounce out and settle on the floor; walking close pulls
them in. An enemy that dies in lava cannot be reached, so its orbs fly
straight to the player instead.
"""
import math
import random

import pygame

from config import CELL, GRAVITY, DIG_KILL_REFILL, DIG_ORBS_PER_KILL, DIG_ORB_MAGNET

ORB_RADIUS = 4
COLLECT_DISTANCE = 18
HOMING_SPEED = 420.0
BOUNCE = 0.45
FRICTION = 0.82
BURST_DELAY = 0.35  # lava orbs pop up first, then fly to the player

BROWN = (124, 78, 40)
DARK = (66, 40, 22)
SHINE = (196, 146, 92)


class DirtOrb:
    def __init__(self, x, y, vx, vy, homing):
        self.pos = pygame.Vector2(x, y)
        self.vel = pygame.Vector2(vx, vy)
        self.homing = homing
        self.delay = BURST_DELAY if homing else 0.0
        self.age = 0.0


class OrbSystem:
    def __init__(self, game, rng=None):
        self.game = game
        self.orbs = []
        self.random = rng or random.Random(7)

    def burst(self, center, homing):
        """Spill one kill's worth of orbs from a point."""
        for n in range(DIG_ORBS_PER_KILL):
            angle = math.pi * (1.15 + 0.7 * n / max(1, DIG_ORBS_PER_KILL - 1))
            speed = self.random.uniform(70, 140)
            self.orbs.append(DirtOrb(center[0], center[1],
                                     math.cos(angle) * speed, math.sin(angle) * speed,
                                     homing))

    def _solid(self, x, y):
        return self.game.world.solid(math.floor(x / CELL), math.floor(y / CELL))

    def update(self, dt):
        game = self.game
        target = pygame.Vector2(game.player.rect.center)
        share = DIG_KILL_REFILL / DIG_ORBS_PER_KILL
        kept = []
        for orb in self.orbs:
            orb.age += dt
            to_player = target - orb.pos
            distance = to_player.length()
            if distance < COLLECT_DISTANCE:
                gained = game.dig_meter.refill(share)
                game.dig_gain = (game.dig_gain if game.dig_gain_timer > 0 else 0) + gained
                game.dig_gain_timer = 1.6
                continue
            if not orb.homing and distance < DIG_ORB_MAGNET:
                orb.homing, orb.delay = True, 0.0
            if orb.homing and orb.delay <= 0:
                # Fly straight to the player, through walls: lava orbs must arrive.
                orb.vel = to_player * (HOMING_SPEED / max(distance, 1))
                orb.pos += orb.vel * dt
            else:
                orb.delay -= dt
                self._fall(orb, dt)
            kept.append(orb)
        self.orbs = kept

    def _fall(self, orb, dt):
        orb.vel.y += GRAVITY * dt
        nx = orb.pos.x + orb.vel.x * dt
        if self._solid(nx, orb.pos.y):
            orb.vel.x *= -BOUNCE
        else:
            orb.pos.x = nx
        ny = orb.pos.y + orb.vel.y * dt
        edge = ny + (ORB_RADIUS if orb.vel.y > 0 else -ORB_RADIUS)
        if self._solid(orb.pos.x, edge):
            if orb.vel.y > 0:
                orb.vel.x *= FRICTION
            orb.vel.y = -orb.vel.y * BOUNCE if abs(orb.vel.y) > 60 else 0.0
        else:
            orb.pos.y = ny

    def draw(self, screen, camera, time):
        for orb in self.orbs:
            bob = 0 if orb.homing else round(math.sin(time * 5 + orb.pos.x) * 1)
            x = round(orb.pos.x - camera[0])
            y = round(orb.pos.y - camera[1]) + bob
            if not (-8 < x < screen.get_width() + 8 and -8 < y < screen.get_height() + 8):
                continue
            pygame.draw.circle(screen, DARK, (x, y), ORB_RADIUS + 1)
            pygame.draw.circle(screen, BROWN, (x, y), ORB_RADIUS)
            pygame.draw.rect(screen, SHINE, (x - 2, y - 2, 2, 2))
