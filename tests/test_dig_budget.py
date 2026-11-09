"""Dig energy: measured per stage, spent by digging, and a hard stop when empty."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (CELL, MACRO, SCREEN_H, SCREEN_W, DIG_BUDGET_MARGIN, DIG_KILL_REFILL,
                    DIG_ORBS_PER_KILL, DIG_ORB_DROP_CHANCE,
                    DIG_BUDGET_EXTRA, DIG_SHORTCUT_MARGIN)
from dig_budget import DigMeter, budget_for, plan_shortcut, plan_stage
from level import DIRT, EMPTY, LAVA, build_level
from main import Game
from tiles import TileArt
from ui import GameUI
from world import World


class Always:
    """A stand-in random source: every roll succeeds (or, with 0.99, fails)."""

    def __init__(self, value=0.0):
        self.value = value

    def random(self):
        return self.value

    def uniform(self, a, b):
        return (a + b) / 2


class DigBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def test_every_stage_has_a_route_to_boss_and_exit(self):
        for stage in range(1, 7):
            with self.subTest(stage=stage):
                rows, entities, scenery, _ = build_level(stage, None)
                world = World(rows)
                world.sculpt(scenery.get('sculpt', {}))
                door = scenery['exit_door']
                goals = list(entities['B']) + [(door[0], door[1] + door[3] - 1)]
                minimum, route = plan_stage(world, entities['P'][0], goals)
                self.assertEqual(route[0], entities['P'][0])
                self.assertIn(entities['B'][0], route)
                self.assertEqual(route[-1], goals[-1])
                self.assertGreater(minimum, 0)

    def test_budget_leaves_room_for_mistakes_but_not_unlimited(self):
        meter = DigMeter(1000)
        self.assertEqual(meter.capacity, budget_for(1000))
        self.assertGreater(meter.capacity, 1000)
        self.assertLessEqual(meter.capacity, 1000 * DIG_BUDGET_MARGIN + DIG_BUDGET_EXTRA + 1)
        # A costly shortcut raises the meter to fit it with a small margin.
        self.assertEqual(DigMeter(1000, 2000).capacity, round(2000 * DIG_SHORTCUT_MARGIN))

    def test_digging_straight_down_fits_with_room_for_human_error(self):
        for stage in range(1, 6):
            with self.subTest(stage=stage):
                rows, entities, scenery, _ = build_level(stage, None)
                world = World(rows)
                world.sculpt(scenery.get('sculpt', {}))
                door = scenery['exit_door']
                goals = list(entities['B']) + [(door[0], door[1] + door[3] - 1)]
                minimum, _ = plan_stage(world, entities['P'][0], goals)
                shortcut, route = plan_shortcut(world, entities['P'][0], goals)
                capacity = DigMeter(minimum, shortcut).capacity
                # The direct tunnel is much shorter than the cave route...
                self.assertLess(len(route), 150)
                # ...fits with room for real, imperfect digging (~1.35x wider).
                self.assertGreaterEqual(capacity, shortcut * 1.35)
                self.assertGreaterEqual(capacity, shortcut * DIG_SHORTCUT_MARGIN)
                self.assertLess(capacity - shortcut, capacity - minimum)

    def test_digging_spends_exactly_the_cells_removed(self):
        game = Game(self.art)
        world = game.world
        x, y = world.width // 2, world.height // 2
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                world.foreground[world.index(x + dx, y + dy)] = DIRT
        before = game.dig_meter.remaining
        game.excavate((x, y))
        removed = sum(world.foreground[world.index(x + dx, y + dy)] == EMPTY
                      for dy in range(-4, 5) for dx in range(-4, 5))
        self.assertGreater(removed, 0)
        self.assertEqual(before - game.dig_meter.remaining, removed)

    def test_empty_meter_stops_digging(self):
        game = Game(self.art)
        world = game.world
        x, y = world.width // 2, world.height // 2
        world.foreground[world.index(x, y)] = DIRT
        game.dig_meter.remaining = 0
        game.excavate((x, y))
        self.assertEqual(world.foreground[world.index(x, y)], DIRT)

    def _kill_one(self, game):
        game.orbs.random = Always()
        enemy = next(m for m in game.monsters if m is not game.boss)
        game.monsters = [m for m in game.monsters if m is not enemy]
        return enemy

    def test_kill_bursts_orbs_that_refill_when_collected(self):
        game = Game(self.art)
        meter = game.dig_meter
        meter.remaining = 0
        enemy = self._kill_one(game)
        self.assertEqual(len(game.orbs.orbs), DIG_ORBS_PER_KILL)
        self.assertEqual(meter.remaining, 0)  # nothing until the orbs are picked up
        self.assertFalse(any(orb.homing for orb in game.orbs.orbs))
        for orb in game.orbs.orbs:  # the player walks over to them
            orb.pos.update(game.player.rect.center)
        game.orbs.update(1 / 60)
        self.assertEqual(game.orbs.orbs, [])
        self.assertAlmostEqual(meter.remaining, meter.capacity * DIG_KILL_REFILL,
                               delta=DIG_ORBS_PER_KILL)
        self.assertGreater(game.dig_gain_timer, 0)

    def test_orbs_settle_on_the_floor_and_wait(self):
        game = Game(self.art)
        enemy = self._kill_one(game)
        start = len(game.orbs.orbs)
        for _ in range(240):
            game.orbs.update(1 / 60)
        self.assertEqual(len(game.orbs.orbs), start)
        for orb in game.orbs.orbs:
            self.assertLess(abs(orb.vel.y), 1)  # resting, not falling forever

    def test_lava_kill_orbs_fly_to_the_player(self):
        game = Game(self.art)
        meter = game.dig_meter
        meter.remaining = 0
        enemy = next(m for m in game.monsters if m is not game.boss)
        game.orbs.random = Always()
        game.touches = lambda rect, kind: rect == enemy.rect and kind == LAVA
        game.monsters = [m for m in game.monsters if m is not enemy]
        self.assertTrue(all(orb.homing for orb in game.orbs.orbs))
        for _ in range(60 * 20):
            game.orbs.update(1 / 60)
            if not game.orbs.orbs:
                break
        self.assertEqual(game.orbs.orbs, [])
        self.assertGreater(meter.remaining, 0)

    def test_bomb_kill_spills_orbs_and_boss_kill_does_not(self):
        game = Game(self.art)
        game.orbs.random = Always()
        enemy = next(m for m in game.monsters if m is not game.boss)
        game.bombs.explode(pygame.Vector2(enemy.rect.center))
        self.assertGreater(len(game.orbs.orbs), 0)
        game.orbs.orbs = []
        game.monsters = [m for m in game.monsters if m is not game.boss]
        self.assertEqual(game.orbs.orbs, [])

    def test_a_failed_roll_drops_nothing(self):
        game = Game(self.art)
        game.orbs.random = Always(0.99)
        enemy = next(m for m in game.monsters if m is not game.boss)
        game.monsters = [m for m in game.monsters if m is not enemy]
        self.assertEqual(game.orbs.orbs, [])

    def test_about_seventy_percent_of_kills_drop_orbs(self):
        import random
        from dig_orbs import OrbSystem
        orbs = OrbSystem(None, random.Random(2024))
        drops = sum(orbs.drop((0, 0), homing=False) for _ in range(2000))
        self.assertAlmostEqual(drops / 2000, DIG_ORB_DROP_CHANCE, delta=0.04)

    def test_refill_never_overfills(self):
        meter = DigMeter(1000, 1500)
        meter.refill(0.5)
        self.assertEqual(meter.remaining, meter.capacity)

    def test_meter_draws_in_the_hud(self):
        game = Game(self.art)
        ui = GameUI()
        ui.start(game)
        screen = pygame.display.get_surface()
        game.dig_meter.remaining = 0
        game.dig_gain, game.dig_gain_timer = 300, 1.0
        ui.draw(screen, game, (0, 0))  # empty meter and refill popup must draw


if __name__ == "__main__":
    unittest.main()
