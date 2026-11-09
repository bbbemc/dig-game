"""Enemy-dropped potions and their player effects."""

import math
import random
from pathlib import Path

import pygame

from config import (HEAL_POTION_AMOUNT, PLAYER_MAX_HP, POTION_DROP_CHANCE,
                    POTION_COLLECT_DISTANCE, POTION_HOMING_SPEED,
                    POTION_PICKUP_RANGE, POTION_SIZE,
                    SPEED_POTION_DURATION, SPEED_POTION_MULTIPLIER,
                    SPEED_POTION_WATER_MULTIPLIER)
from level import WATER

ASSETS = Path(__file__).with_name('assets')
_images = {}


def potion_image(kind):
    """Load and cache a potion sprite, or return None if its asset is missing."""
    if kind not in _images:
        try:
            image = pygame.image.load(str(ASSETS / f'{kind}_potion.png'))
            if pygame.display.get_surface() is not None:
                image = image.convert_alpha()
            _images[kind] = pygame.transform.scale(
                image, (POTION_SIZE, POTION_SIZE))
        except (pygame.error, FileNotFoundError):
            _images[kind] = None
    return _images[kind]


class Potion:
    def __init__(self, kind, center):
        self.kind = kind
        self.pos = pygame.Vector2(center)
        self.rect = pygame.Rect(0, 0, POTION_SIZE, POTION_SIZE)
        self.homing = False
        self.sync_rect()

    def sync_rect(self):
        self.rect.center = round(self.pos.x), round(self.pos.y)


class PotionSystem:
    def __init__(self, game, rng=None):
        self.game = game
        self.drops = []
        self.random = rng or random.Random()
        self.speed_timer = 0.0

    def drop(self, kind, center):
        """Roll for a potion drop; returns whether one was created."""
        if kind not in ('speed', 'health'):
            raise ValueError(f'Unknown potion type: {kind}')
        if self.random.random() >= POTION_DROP_CHANCE:
            return False
        self.drops.append(Potion(kind, center))
        return True

    def update(self, dt):
        self.speed_timer = max(0.0, self.speed_timer - dt)
        if self.speed_timer <= 1e-9:
            self.speed_timer = 0.0
        self._apply_speed_multiplier()
        player = self.game.player.rect
        player_center = pygame.Vector2(player.center)
        pickup_range_squared = POTION_PICKUP_RANGE ** 2
        for potion in self.drops[:]:
            if potion.kind == 'health' and self.game.hp >= PLAYER_MAX_HP:
                continue
            to_player = player_center - potion.pos
            distance = to_player.length()
            if not potion.homing:
                if distance > POTION_PICKUP_RANGE:
                    continue
                potion.homing = True
            if distance <= POTION_COLLECT_DISTANCE:
                self._collect(potion)
                continue
            if distance:
                travel = min(distance, POTION_HOMING_SPEED * dt)
                potion.pos += to_player * (travel / distance)
                potion.sync_rect()
                if distance - travel <= POTION_COLLECT_DISTANCE:
                    self._collect(potion)

    def _collect(self, potion):
        if potion.kind == 'speed':
            self.speed_timer = SPEED_POTION_DURATION
            self._apply_speed_multiplier()
        elif self.game.hp < PLAYER_MAX_HP:
            self.game.hp = min(PLAYER_MAX_HP,
                               self.game.hp + HEAL_POTION_AMOUNT)
        else:
            return
        self.drops.remove(potion)

    def _apply_speed_multiplier(self):
        if self.speed_timer <= 0:
            multiplier = 1.0
        elif self.game.touches(self.game.player.rect, WATER):
            multiplier = SPEED_POTION_WATER_MULTIPLIER
        else:
            multiplier = SPEED_POTION_MULTIPLIER
        self.game.player.speed_multiplier = multiplier

    def draw(self, screen, camera, time):
        for potion in self.drops:
            bob = 0 if potion.homing else round(math.sin(time * 4 + potion.rect.x) * 2)
            rect = potion.rect.move(-camera[0], -camera[1] + bob)
            image = potion_image(potion.kind)
            if image is not None:
                screen.blit(image, rect.topleft)
                continue
            color = (43, 220, 255) if potion.kind == 'speed' else (255, 65, 91)
            pygame.draw.rect(screen, (30, 22, 20), rect)
            pygame.draw.rect(screen, color, rect.inflate(-6, -6))
