"""Stage 5.5: the Colossus's arena - room size, ledges, camera, lock and HUD."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (ARENA_ZOOM, ARENA_ZOOM_DELAY, ARENA_ZOOM_TIME, BOSS_SIZE, CELL,
                    MACRO, PLAYER_MAX_HP, SCREEN_H, SCREEN_W)
from level import DIRT
from levels.boss_arena import (CEILING, FLOOR, LADDERS, PLATFORMS, build_boss_arena)
from main import Game
from tiles import TileArt
from ui import GameUI


class ArenaLayoutTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.entities, self.scenery, _ = build_boss_arena()

    def test_room_is_wider_than_the_screen_and_fills_the_zoomed_view(self):
        width, height = len(self.rows[0]) * MACRO, len(self.rows) * MACRO
        self.assertGreaterEqual(width, 1.5 * SCREEN_W)
        self.assertLessEqual(width, 2 * SCREEN_W)
        self.assertGreaterEqual(height, SCREEN_H / ARENA_ZOOM)

    def test_the_ceiling_leaves_at_least_twice_the_boss_height_above_it(self):
        boss_top = FLOOR * MACRO - BOSS_SIZE
        ceiling = (CEILING + 2) * MACRO          # the lowest stalactite bumps
        self.assertGreaterEqual(boss_top - ceiling, 2 * BOSS_SIZE)

    def test_ledges_clear_the_boss_and_its_swing_and_each_has_a_ladder(self):
        self.assertTrue(2 <= len(PLATFORMS) <= 4)
        self.assertGreaterEqual(len({y for _, _, y, _ in PLATFORMS}), 2)
        ladder_tops = {}
        for column, top in LADDERS:
            ladder_tops.setdefault(column, []).append(top)
        for left, right, y, _ in PLATFORMS:
            # The boss walks beneath: its full height fits under the ledge.
            self.assertGreaterEqual((FLOOR - y - 1) * MACRO, BOSS_SIZE)
            # A miner standing on it is above the greatsword's strip (top - 8).
            self.assertLess(y * MACRO, FLOOR * MACRO - BOSS_SIZE - 8)
            beside = [top for column in (left - 1, right + 1)
                      for top in ladder_tops.get(column, ())]
            self.assertTrue(any(top <= y - 1 for top in beside), (left, right, y))
        ladders = [p for p in self.scenery['props'] if p['name'] == 'ladder']
        self.assertEqual(len(ladders), len(LADDERS))

    def test_some_ledges_and_floor_patches_can_be_dug_but_the_boss_cannot_fall_in(self):
        ledge_dirt = sum(row.count('#') for row in self.rows[:FLOOR])
        floor = self.rows[FLOOR]
        self.assertGreater(ledge_dirt, 0)
        patch = 0
        for x, char in enumerate(floor):
            patch = patch + 1 if char == '#' else 0
            self.assertLess(patch * MACRO, BOSS_SIZE)
        self.assertIn('#', floor)
        self.assertTrue(all(char == 'R' for char in self.rows[FLOOR + 1]))

    def test_the_boss_starts_far_from_the_miner(self):
        (px, _), (bx, _) = self.entities['P'][0], self.entities['B'][0]
        self.assertGreaterEqual(bx - px, 20)

    def test_the_hall_is_dressed_with_lights_chains_banners_and_columns(self):
        props = [p['name'] for p in self.scenery['props']]
        pieces = [piece.get('name', piece['kind']) for s in self.scenery['structures']
                  for piece in s['pieces']]
        self.assertGreaterEqual(props.count('torch'), 6)
        self.assertTrue(any('crystal' in name for name in props))
        self.assertGreaterEqual(pieces.count('banner'), 3)
        self.assertGreaterEqual(pieces.count('chain'), 6)
        self.assertGreaterEqual(pieces.count('dungeon_column'), 4)
        self.assertTrue(any(s['lamps'] for s in self.scenery['structures']))


class ArenaGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def setUp(self):
        self.game = Game(self.art, stage=5, bonus_room=True)
        self.screen = pygame.Surface((SCREEN_W, SCREEN_H))

    def run_for(self, seconds, **keys):
        for _ in range(round(seconds * 60)):
            self.game.update(1 / 60, **keys)

    def test_the_view_eases_out_to_the_arena_zoom_and_stays_in_the_room(self):
        game = self.game
        self.assertEqual(game.zoom, 1.0)
        self.run_for(ARENA_ZOOM_DELAY + ARENA_ZOOM_TIME / 2)
        self.assertTrue(ARENA_ZOOM < game.zoom < 1.0)
        self.run_for(ARENA_ZOOM_TIME)
        self.assertEqual(game.zoom, ARENA_ZOOM)
        width, height = game.view_size
        self.assertEqual((width, height), (round(SCREEN_W / ARENA_ZOOM), round(SCREEN_H / ARENA_ZOOM)))
        for x in (0, game.world.pixel_width - game.player.size):
            game.player.pos.update(x, game.player.pos.y)
            game.player._sync_rect()
            self.run_for(1.5)
            cx, cy = game.render_camera
            self.assertTrue(0 <= cx <= game.world.pixel_width - width)
            self.assertTrue(0 <= cy <= game.world.pixel_height - height)
        game.draw(self.screen)

    def test_the_camera_leans_toward_the_boss(self):
        game = self.game
        self.run_for(ARENA_ZOOM_DELAY + ARENA_ZOOM_TIME + 0.1)
        game.player.pos.update(18 * MACRO, game.player.pos.y)
        game.player._sync_rect()
        width = game.view_size[0]
        centred = game.player.rect.centerx - width / 2
        self.assertGreater(game.camera()[0], centred)

    def test_mouse_points_map_through_the_zoom(self):
        game = self.game
        self.run_for(ARENA_ZOOM_DELAY + ARENA_ZOOM_TIME + 0.1)
        world = game.to_world(480, 320)
        screen = game.to_screen(*world)
        self.assertAlmostEqual(screen[0], 480, delta=1)
        self.assertAlmostEqual(screen[1], 320, delta=1)

    def test_walking_in_seals_both_gates_and_shakes_the_hall(self):
        game = self.game
        self.assertFalse(game.arena_locked)
        game.player.pos.update(game.arena_lock_x + 4, game.player.pos.y)
        game.player._sync_rect()
        game.update_stage_progress()
        self.assertTrue(game.arena_locked)
        self.assertGreater(game.shake, 0)
        self.assertFalse(game.exit_open)
        game.draw(self.screen)

    def test_the_greatsword_slam_shakes_harder_in_the_arena(self):
        game = self.game
        boss = game.boss
        game.player.pos.update(boss.rect.left - 40, game.player.pos.y)
        game.player._sync_rect()
        game.player.drop_to_ground()
        game.hp = 10 ** 6
        peak = 0.0
        for _ in range(240):
            game.hp = 10 ** 6
            game.update(1 / 60)
            peak = max(peak, game.shake)
            if getattr(boss, 'melee_slammed', False):
                break
        self.assertTrue(getattr(boss, 'melee_slammed', False))
        self.assertGreater(peak, 0.55)

    def test_the_rear_wall_fades_into_the_backdrop_in_the_open_hall(self):
        mask = self.game.renderer.backdrop_mask
        self.assertIsNotNone(mask)
        middle = (29 * MACRO + 20, 7 * MACRO + 20)     # open air, 4+ macros from rock
        near_rock = (20 * MACRO, 10 * MACRO + 4)       # right under the altar
        self.assertEqual(mask.get_at(middle).a, 0)
        self.assertEqual(mask.get_at(near_rock).a, 255)
        regular = Game(self.art, stage=1)
        self.assertIsNone(regular.renderer.backdrop_mask)
        self.assertEqual(regular.zoom, 1.0)

    def test_digging_a_dirt_ledge_opens_it(self):
        game = self.game
        left, right, y, materials = PLATFORMS[0]
        x = left + materials.index('#')
        cell = (x * MACRO + MACRO // 2) // CELL, (y * MACRO + MACRO // 2) // CELL
        self.assertEqual(game.world.foreground[game.world.index(*cell)], DIRT)
        game.excavate(cell)
        self.assertFalse(game.world.solid(*cell))


class ArenaHudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def setUp(self):
        self.game = Game(self.art, stage=5, bonus_room=True)
        self.ui = GameUI()
        self.ui.start(self.game, intro=False)
        self.screen = pygame.Surface((SCREEN_W, SCREEN_H))

    def test_health_reads_against_the_real_maximum(self):
        self.game.hp = PLAYER_MAX_HP - 5
        texts = []
        original = self.ui.text

        def record(surface, message, *args, **kwargs):
            texts.append(message)
            return original(surface, message, *args, **kwargs)

        self.ui.text = record
        self.ui.health(self.screen, self.game)
        self.assertIn(f'{PLAYER_MAX_HP - 5} / {PLAYER_MAX_HP}', texts)

    def test_area_plate_shows_the_stage_once(self):
        texts = []
        original = self.ui.text

        def record(surface, message, *args, **kwargs):
            texts.append(message)
            return original(surface, message, *args, **kwargs)

        self.ui.text = record
        self.ui.area(self.screen, self.game)
        self.assertEqual(texts, ['S5.5', 'THE DEEP DESCENT'])

    def test_boss_bar_appears_when_the_gates_seal_and_drains_after_a_hit(self):
        game, ui = self.game, self.ui
        ui.update(1.0, game)
        self.assertEqual(ui.boss_bar_alpha, 0.0)       # far away, gates open
        game.arena_locked = True
        ui.update(1.0, game)
        self.assertEqual(ui.boss_bar_alpha, 1.0)
        game.boss.hp -= 1
        ui.update(0.1, game)
        self.assertGreater(ui.boss_trail, game.boss.hp)  # the trail lags behind
        ui.update(2.0, game)
        self.assertEqual(ui.boss_trail, game.boss.hp)
        ui.draw_game(self.screen, game, (0, 0))
        bar_pixel = self.screen.get_at((SCREEN_W // 2 - 200, SCREEN_H - 64 + 30))[:3]
        self.assertGreater(bar_pixel[0], 120)          # red health fill on screen


if __name__ == '__main__':
    unittest.main()
