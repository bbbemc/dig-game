"""Dig energy: measured per stage, spent by digging, and a hard stop when empty."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (CELL, MACRO, SCREEN_H, SCREEN_W, DIG_BUDGET_MARGIN,
                    DIG_BUDGET_EXTRA, DIG_SHORTCUT_MARGIN)
from dig_budget import DigMeter, budget_for, plan_shortcut, plan_stage
from level import DIRT, EMPTY, build_level
from main import Game
from tiles import TileArt
from ui import GameUI
from world import World


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

    def test_meter_draws_in_the_hud(self):
        game = Game(self.art)
        ui = GameUI()
        ui.start(game)
        screen = pygame.display.get_surface()
        game.dig_meter.remaining = 0
        ui.draw(screen, game, (0, 0))  # full and empty meter must both draw


if __name__ == "__main__":
    unittest.main()
