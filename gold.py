"""Gold ore embedded in diggable earth, plus enemy-dropped gold coins."""

import math
import random

import pygame

from config import (CELL, GRAVITY, MACRO, POTION_COLLECT_DISTANCE,
                    POTION_HOMING_SPEED, POTION_PICKUP_RANGE)
from level import DIRT

COIN_VALUE = 5
COIN_SIZE = 20
DROP_SPEED = 130.0
BOUNCE = 0.35


def draw_coin_icon(surface, center, size=COIN_SIZE):
    """Draw a crisp, blocky gold coin at the requested pixel size."""
    x, y = center
    radius = max(4, size // 2)
    pygame.draw.circle(surface, (73, 39, 19), (x, y), radius)
    pygame.draw.circle(surface, (180, 103, 23), (x, y), radius - 1)
    pygame.draw.circle(surface, (255, 202, 61), (x - 1, y - 1), radius - 3)
    pygame.draw.circle(surface, (236, 151, 28), (x, y), radius - 5)
    pygame.draw.rect(surface, (255, 235, 137),
                     (x - radius // 2, y - radius // 2, 2, max(2, radius // 2)))
    pygame.draw.rect(surface, (137, 72, 20),
                     (x + 1, y - radius // 2 + 1, 2, radius))


class GoldCoin:
    def __init__(self, pos, value=COIN_VALUE, velocity=(0, 0), dropped=False,
                 homing=False):
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(velocity)
        self.value = value
        self.dropped = dropped
        self.homing = homing
        self.age = 0.0


class GoldSystem:
    def __init__(self, game, entities, scenery, rng=None):
        self.game = game
        self.coins = []
        self.hidden = {}
        self.random = rng or random.Random(game.seed)
        self.ore_image = game.renderer.art.sprite('ore_gold', 24, 28)
        self._place_level_coins(entities, scenery)

    def _place_level_coins(self, entities, scenery):
        world = self.game.world
        spawn_x, spawn_y = entities['P'][0]
        spawn = pygame.Vector2(spawn_x * MACRO + MACRO / 2,
                               spawn_y * MACRO + MACRO / 2)
        doors = [scenery['exit_door']]
        if scenery.get('bonus_door'):
            doors.append(scenery['bonus_door'])

        hidden_candidates = []
        safe_radius_squared = (2 * MACRO) ** 2
        for y in range(1, world.height - 1):
            for x in range(1, world.width - 1):
                center = pygame.Vector2(x * CELL + CELL / 2,
                                        y * CELL + CELL / 2)
                if center.distance_squared_to(spawn) < safe_radius_squared:
                    continue
                coin_rect = pygame.Rect(0, 0, COIN_SIZE, COIN_SIZE)
                coin_rect.center = center
                if any(coin_rect.colliderect(
                        pygame.Rect(dx * MACRO, dy * MACRO, dw * MACRO, dh * MACRO))
                       for dx, dy, dw, dh in doors):
                    continue
                index = world.index(x, y)
                kind = world.foreground[index]
                if kind == DIRT:
                    hidden_candidates.append(index)

        self.random.shuffle(hidden_candidates)
        count = max(8, min(64, world.width * world.height // 1800))
        self.hidden = {index: COIN_VALUE for index in hidden_candidates[:count]}

    def dug(self, removed):
        """Collect every coin whose dirt cell was just removed."""
        world = self.game.world
        for index in removed:
            value = self.hidden.pop(index, None)
            if value is None:
                continue
            x, y = world.coords(index)
            self.collect(value, (x * CELL + CELL // 2, y * CELL + CELL // 2))

    def drop(self, center, value):
        """Drop one enemy-value coin; it homes when within potion pickup range."""
        angle = self.random.uniform(-math.pi * 0.85, -math.pi * 0.15)
        speed = self.random.uniform(DROP_SPEED * 0.55, DROP_SPEED)
        velocity = (math.cos(angle) * speed, math.sin(angle) * speed)
        self.coins.append(GoldCoin(center, value, velocity, dropped=True,
                                   homing=False))

    def collect(self, value, pos):
        game = self.game
        game.gold += value
        game.fx.popup(f'+{value} G', pos[0], pos[1] - 12, (255, 207, 72), 0.8)

    def _solid(self, x, y):
        return self.game.world.solid(math.floor(x / CELL), math.floor(y / CELL))

    def update(self, dt):
        game = self.game
        player = game.player.rect
        kept = []
        for coin in self.coins:
            coin.age += dt
            player_center = pygame.Vector2(player.center)
            delta = player_center - coin.pos
            distance = delta.length()
            if not coin.homing:
                if distance > POTION_PICKUP_RANGE:
                    if coin.dropped:
                        self._fall(coin, dt)
                    kept.append(coin)
                    continue
                coin.homing = True
            if distance <= POTION_COLLECT_DISTANCE:
                self.collect(coin.value, coin.pos)
                continue
            if distance:
                travel = min(distance, POTION_HOMING_SPEED * dt)
                coin.pos += delta * (travel / distance)
                if distance - travel <= POTION_COLLECT_DISTANCE:
                    self.collect(coin.value, coin.pos)
                    continue
            kept.append(coin)
        self.coins = kept

    def _fall(self, coin, dt):
        if dt <= 0:
            return
        if coin.dropped:
            coin.velocity.y += GRAVITY * dt
            nx = coin.pos.x + coin.velocity.x * dt
            if self._solid(nx, coin.pos.y):
                coin.velocity.x *= -BOUNCE
            else:
                coin.pos.x = nx
            ny = coin.pos.y + coin.velocity.y * dt
            edge = ny + (COIN_SIZE / 2 if coin.velocity.y > 0 else -COIN_SIZE / 2)
            if self._solid(coin.pos.x, edge):
                if coin.velocity.y > 0 and abs(coin.velocity.y) > 60:
                    coin.velocity.y = -coin.velocity.y * BOUNCE
                    coin.velocity.x *= 0.65
                else:
                    coin.velocity.y = 0
                    coin.velocity.x *= 0.8
                    if abs(coin.velocity.x) < 4:
                        coin.velocity.x = 0
            else:
                coin.pos.y = ny

    def draw(self, surface, camera, time):
        world = self.game.world
        image_width, image_height = self.ore_image.get_size()
        for index in self.hidden:
            x, y = world.coords(index)
            center_x = x * CELL + CELL // 2 - camera[0]
            center_y = y * CELL + CELL // 2 - camera[1]
            if (-image_width < center_x < surface.get_width() + image_width
                    and -image_height < center_y < surface.get_height() + image_height):
                surface.blit(self.ore_image, self.ore_image.get_rect(
                    center=(center_x, center_y)))
        for coin in self.coins:
            x = round(coin.pos.x - camera[0])
            bob = (round(math.sin(time * 4 + coin.pos.x * 0.1) * 2)
                   if not coin.dropped else 0)
            y = round(coin.pos.y - camera[1]) + bob
            if -COIN_SIZE < x < surface.get_width() + COIN_SIZE and \
                    -COIN_SIZE < y < surface.get_height() + COIN_SIZE:
                draw_coin_icon(surface, (x, y))
