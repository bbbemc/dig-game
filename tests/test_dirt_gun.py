"""The dirt pistol: costs dig energy, builds dirt where it hits, chips guards."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import CELL, MACRO, SCREEN_H, SCREEN_W, DIRT_GUN_COOLDOWN
import dirt_gun
from level import DIRT, EMPTY
from main import Game
from tiles import TileArt


class DirtGunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def setUp(self):
        self.game = Game(self.art)
        for _ in range(5):
            self.game.update(1 / 60)

    def run_for(self, seconds):
        for _ in range(round(seconds * 60)):
            self.game.update(1 / 60)
            self.game.hp = max(self.game.hp, 50)

    def test_shot_costs_dig_energy_and_respects_the_cooldown(self):
        game, gun = self.game, self.game.gun
        before = game.dig_meter.remaining
        gun.aim = (game.player.rect.centerx + 200, game.player.rect.centery)
        self.assertTrue(gun.fire())
        self.assertFalse(gun.fire())                 # still cooling down
        self.assertEqual(game.dig_meter.remaining, before - gun.cost)
        self.assertEqual(len(gun.clods), 1)
        self.run_for(DIRT_GUN_COOLDOWN + 0.02)
        self.assertTrue(gun.fire())

    def test_empty_meter_clicks(self):
        game, gun = self.game, self.game.gun
        game.dig_meter.remaining = gun.cost - 1
        gun.aim = (game.player.rect.centerx + 200, game.player.rect.centery)
        self.assertFalse(gun.fire())
        self.assertEqual(gun.clods, [])
        self.assertEqual(game.dig_meter.remaining, gun.cost - 1)

    def test_clod_leaves_dirt_where_it_hits(self):
        game, gun = self.game, self.game.gun
        world = game.world
        dirt = sum(v == DIRT for v in world.foreground)
        rect = game.player.rect
        gun.aim = (rect.centerx - 150, rect.centery - 150)   # the chamber's upper wall
        gun.fire()
        self.run_for(1.0)
        self.assertEqual(gun.clods, [])
        self.assertGreater(sum(v == DIRT for v in world.foreground), dirt)
        # Never inside the player.
        for y in range(rect.top // CELL, (rect.bottom - 1) // CELL + 1):
            for x in range(rect.left // CELL, (rect.right - 1) // CELL + 1):
                self.assertNotEqual(world.foreground[world.index(x, y)], DIRT)

    def test_deposit_skips_liquids_and_actors(self):
        game = self.game
        world = game.world
        rect = game.player.rect
        placed = game.gun.deposit(pygame.Vector2(rect.center))
        cells = [pygame.Rect(world.coords(i)[0] * CELL, world.coords(i)[1] * CELL, CELL, CELL)
                 for i in placed]
        self.assertFalse(any(c.colliderect(rect) for c in cells))
        for i in placed:
            x, y = world.coords(i)
            self.assertEqual(game.liquids.type_at(x, y), EMPTY)

    def test_three_hits_break_a_guard(self):
        game, gun = self.game, self.game.gun
        enemy = next(m for m in game.monsters if getattr(m, 'posture', None) is not None
                     and not getattr(m, 'is_boss', False))
        for _ in range(3):
            clod = dirt_gun.Clod(enemy.rect.center, (300, 0))
            gun.hit(enemy, clod)
        self.assertTrue(enemy.broken)
        self.assertEqual(enemy.hurt_time, game.world_time)

    def test_art_loads_and_the_gun_draws(self):
        for name, cell, count in (('dirt_gun_sheet.png', dirt_gun.GUN_FRAME, dirt_gun.FIRE_FRAMES),
                                  ('dirt_clod_sheet.png', dirt_gun.CLOD_FRAME, dirt_gun.CLOD_FRAMES),
                                  ('dirt_splat_sheet.png', dirt_gun.SPLAT_FRAME, dirt_gun.SPLAT_FRAMES)):
            frames = dirt_gun._frames(name, cell)
            self.assertIsNotNone(frames, name)
            self.assertGreaterEqual(len(frames[-1]), count, name)
            self.assertEqual(frames[0][0].get_at((0, 0)).a, 0)       # see-through
        for fps in (dirt_gun.IDLE_FPS, dirt_gun.FIRE_FPS, dirt_gun.CLOD_FPS, dirt_gun.SPLAT_FPS):
            self.assertTrue(8 <= fps <= 20)
        game = self.game
        game.gun.aim = (game.player.rect.centerx - 100, game.player.rect.centery - 40)
        game.gun.fire()
        game.update(1 / 60)
        game.draw(pygame.Surface((SCREEN_W, SCREEN_H)))
        self.assertFalse(game.miner.facing_right)     # faces where the gun points


if __name__ == "__main__":
    unittest.main()
