"""Bomb pickups, throwing and explosions on the real stage."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import CELL, MACRO, SCREEN_H, SCREEN_W, BOMB_MAX_CARRY, BOMB_SPAWN_COUNT, BOMB_FUSE
from level import DIRT, EMPTY, ROCK, STONE, WATER
from main import Game
from tiles import TileArt


class BombTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def test_stage_one_has_no_bombs_by_default(self):
        game = Game(self.art)
        self.assertFalse(game.bombs.enabled)
        self.assertEqual(game.bombs.pickups, [])
        self.assertFalse(game.bombs.throw((0, 0)))

    def test_forced_stage_places_random_subset_of_spots(self):
        game = Game(self.art, bombs=True)
        self.assertTrue(game.bombs.enabled)
        self.assertEqual(len(game.bombs.pickups), BOMB_SPAWN_COUNT)
        for rect in game.bombs.pickups:
            self.assertFalse(game.world.solid(rect.centerx // CELL, rect.centery // CELL))

    def test_pickup_is_collected_up_to_the_carry_limit(self):
        game = Game(self.art, bombs=True)
        bombs = game.bombs
        bombs.carried = BOMB_MAX_CARRY - 1
        bombs.pickups = [game.player.rect.copy(), game.player.rect.copy()]
        bombs.update(0)
        self.assertEqual(bombs.carried, BOMB_MAX_CARRY)
        self.assertEqual(len(bombs.pickups), 1)

    def test_explosion_removes_dirt_and_stone_but_not_rock(self):
        game = Game(self.art, bombs=True)
        world = game.world
        cx, cy = world.width // 2, world.height // 2
        dirt, stone, rock = world.index(cx, cy), world.index(cx + 1, cy), world.index(cx - 1, cy)
        world.foreground[dirt], world.foreground[stone], world.foreground[rock] = DIRT, STONE, ROCK
        game.player.pos.update(0, 0)  # keep the player out of the blast
        game.bombs.explode(pygame.Vector2(cx * CELL + 4, cy * CELL + 4))
        self.assertEqual(world.foreground[dirt], EMPTY)
        self.assertEqual(world.foreground[stone], EMPTY)
        self.assertEqual(world.foreground[rock], ROCK)

    def test_explosion_kills_nearby_monster_and_hurts_player(self):
        game = Game(self.art, bombs=True)
        monster = game.monsters[0]
        hp = game.hp
        game.bombs.explode(pygame.Vector2(monster.rect.center))
        self.assertNotIn(monster, game.monsters)
        game.bombs.explode(pygame.Vector2(game.player.rect.center))
        self.assertLess(game.hp, hp)

    def test_thrown_bomb_explodes_after_fuse(self):
        game = Game(self.art, bombs=True)
        game.bombs.carried = 1
        self.assertTrue(game.bombs.throw(pygame.Vector2(game.player.rect.center) + (80, 0)))
        self.assertEqual(game.bombs.carried, 0)
        exploded = []
        game.bombs.explode = lambda center: exploded.append(center)
        for _ in range(int(BOMB_FUSE * 60) + 5):
            game.bombs.update(1 / 60)
        self.assertEqual(len(exploded), 1)
        self.assertEqual(game.bombs.thrown, [])

    def test_bomb_in_water_fizzles(self):
        game = Game(self.art, bombs=True)
        game.bombs.carried = 1
        game.bombs.throw((0, 0))
        exploded = []
        game.bombs.explode = lambda center: exploded.append(center)
        real_touches = game.touches
        game.touches = lambda rect, kind: kind == WATER or real_touches(rect, kind)
        game.bombs.update(1 / 60)
        self.assertEqual(game.bombs.thrown, [])
        self.assertEqual(exploded, [])


if __name__ == "__main__":
    unittest.main()
