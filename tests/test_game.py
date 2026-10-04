"""Headless integration checks using the authored map and real game systems."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import CELL, MACRO, PHYSICS_HZ, SCREEN_H, SCREEN_W
from level import EMPTY, LAVA, WATER
from main import Game
from physics import Player
from tiles import TileArt


class LocalLookup(dict):
    """Fail if a contact query iterates the world's liquid collection."""

    def __init__(self, values):
        super().__init__(values)
        self.lookups = 0

    def get(self, key, default=None):
        self.lookups += 1
        return super().get(key, default)

    def __iter__(self):
        raise AssertionError("Contact checks must query only overlapping cells")

    def items(self):
        raise AssertionError("Contact checks must query only overlapping cells")

    def values(self):
        raise AssertionError("Contact checks must query only overlapping cells")


class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.game = Game(self.art)

    def test_spawn_and_camera_at_map_edges(self):
        game = self.game
        self.assertEqual(tuple(game.player.pos), (400, 408))
        self.assertTrue(game.player.grounded)
        self.assertFalse(game.player.overlaps_terrain())
        game.player.pos.update(0, 0)
        self.assertEqual(game.camera(), (0, 0))
        game.player.pos.update(game.world.pixel_width, game.world.pixel_height)
        self.assertEqual(game.camera(), (game.world.pixel_width - SCREEN_W,
                                         game.world.pixel_height - SCREEN_H))

    def test_jump_survives_frames_shorter_than_physics_tick(self):
        game = self.game
        initial_y = game.player.pos.y
        tick = 1 / PHYSICS_HZ
        game.update(tick / 3, jump=True)
        self.assertEqual(game.player.pos.y, initial_y)
        self.assertTrue(game.jump_pending)
        game.update(tick / 3)
        self.assertEqual(game.player.pos.y, initial_y)
        game.update(tick / 3)
        self.assertLess(game.player.pos.y, initial_y)
        self.assertLess(game.player.velocity.y, 0)
        self.assertFalse(game.jump_pending)

    def test_excavating_player_floor_triggers_gravity_and_keeps_wall(self):
        game = self.game
        y = game.player.rect.bottom // CELL
        x = game.player.rect.centerx // CELL
        original_y = game.player.pos.y
        background = bytes(game.world.background)
        game.excavate((x, y))
        self.assertEqual(game.world.foreground[game.world.index(x, y)], EMPTY)
        game.update(1 / 30)
        self.assertGreater(game.player.pos.y, original_y)
        self.assertFalse(game.player.grounded)
        self.assertEqual(bytes(game.world.background), background)
        self.assertTrue(game.particles.items)

    def test_excavating_real_reservoir_releases_water_into_new_chamber(self):
        game = self.game
        # Carve a safe chamber beneath the first sealed water reservoir.
        game.world.dig(137, 95, radius=3)
        game.player = Player(game.world, 135 * CELL, 93 * CELL)
        self.assertTrue(game.player.drop_to_ground())
        self.assertTrue(game.world.solid(137, 90))
        self.assertEqual(game.liquids.mass_at(137, 90), 0)
        game.excavate((137, 90))
        self.assertFalse(game.world.solid(137, 90))
        for _ in range(60):
            game.update(1 / 60)
        self.assertGreater(game.liquids.mass_at(137, 90), 0.1)
        self.assertEqual(game.liquids.type_at(137, 90), WATER)
        self.assertEqual(game.state, "play")
        self.assertFalse(game.player.overlaps_terrain())

    def test_restart_constructs_fresh_game_state(self):
        game = self.game
        original_terrain = bytes(game.world.foreground)
        game.excavate((game.player.rect.centerx // CELL,
                       game.player.rect.bottom // CELL))
        game.update(0.1, horizontal=1, jump=True)
        game.hp, game.state = 20, "lose"
        fresh = Game(self.art)
        self.assertIsNot(fresh.world, game.world)
        self.assertIsNot(fresh.liquids, game.liquids)
        self.assertEqual(bytes(fresh.world.foreground), original_terrain)
        self.assertEqual((fresh.hp, fresh.state), (100, "play"))
        self.assertEqual(tuple(fresh.player.pos), (400, 408))
        self.assertEqual(tuple(fresh.player.velocity), (0, 0))
        self.assertEqual(fresh.physics_accumulator, 0)
        self.assertEqual(fresh.fluid_accumulator, 0)
        self.assertEqual(fresh.world_time, 0)
        self.assertFalse(fresh.jump_pending)
        self.assertIsNone(fresh.last_dig)
        self.assertFalse(fresh.particles.items)
        self.assertFalse(fresh.renderer.cache)

    def test_all_authored_spawns_stay_clear_after_gravity(self):
        game = self.game
        actors = [game.player, game.boss, *game.monsters]
        for actor in actors:
            self.assertTrue(actor.grounded)
            self.assertFalse(actor.overlaps_terrain())
        for _ in range(120):
            game.update(1 / 60)
        for actor in actors:
            self.assertFalse(actor.overlaps_terrain())
            self.assertGreaterEqual(actor.rect.left, 0)
            self.assertLessEqual(actor.rect.right, game.world.pixel_width)
            self.assertLessEqual(actor.rect.bottom, game.world.pixel_height)
        self.assertEqual(game.state, "play")

    def test_movement_and_jump_loop_in_each_layer(self):
        game = self.game
        pockets = ((10, 7), (55, 36), (59, 60), (21, 82))
        for layer, (x, y) in enumerate(pockets, 1):
            with self.subTest(layer=layer):
                game.player = Player(game.world, x * MACRO, y * MACRO)
                self.assertTrue(game.player.drop_to_ground())
                start = game.player.pos.copy()
                for frame in range(30):
                    game.update(1 / 60, horizontal=1, jump=frame == 0)
                self.assertGreater(game.player.pos.x, start.x + MACRO)
                for _ in range(30):
                    game.update(1 / 60, horizontal=-1)
                self.assertAlmostEqual(game.player.pos.x, start.x)
                self.assertTrue(game.player.grounded)
                self.assertFalse(game.player.overlaps_terrain())
                self.assertEqual(game.player.rect.centery // (25 * MACRO) + 1, layer)
                self.assertEqual(game.state, "play")

    def test_idle_game_remains_playable_with_sealed_reservoirs(self):
        game = self.game
        initial = game.player.pos.copy()
        for _ in range(900):
            game.update(1 / 60)
        self.assertEqual(game.state, "play")
        self.assertEqual(game.hp, 100)
        self.assertEqual(game.player.pos, initial)
        self.assertTrue(game.player.grounded)
        self.assertFalse(game.player.overlaps_terrain())

    def test_contact_queries_only_visit_actor_cells(self):
        game = self.game
        guard = LocalLookup(game.liquids.types)
        game.liquids.types = guard
        self.assertFalse(game.touches(game.player.rect, LAVA))
        self.assertLessEqual(guard.lookups, 25)

    def test_player_lava_contact_loses(self):
        game = self.game
        # Move into an existing full reservoir; no private fluid mutation.
        game.player.pos.update(83 * MACRO, 36 * MACRO)
        game.player.rect.topleft = round(game.player.pos.x), round(game.player.pos.y)
        self.assertTrue(game.touches(game.player.rect, LAVA))
        game.update(0)
        self.assertEqual((game.hp, game.state), (0, "lose"))

    def test_boss_lava_contact_wins(self):
        game = self.game
        game.boss.pos.update(83 * MACRO, 36 * MACRO)
        game.boss.rect.topleft = round(game.boss.pos.x), round(game.boss.pos.y)
        self.assertTrue(game.touches(game.boss.rect, LAVA))
        game.update(0)
        self.assertEqual(game.state, "win")
        self.assertEqual(game.hp, 100)

    def test_arena_ladder_roof_release_and_escape_wins(self):
        game = self.game
        # Replay the arena puzzle from its floor, including the actual ladder.
        game.player = Player(game.world, 98 * MACRO + 4, 96 * MACRO)
        self.assertTrue(game.player.drop_to_ground())
        self.assertTrue(game.renderer.ladder_at(game.player.rect))
        for _ in range(360):
            game.update(1 / 60, vertical=-1)
        self.assertEqual(game.player.rect.top, 78 * MACRO)
        self.assertEqual(game.state, "play")
        for target in ((492, 387), (492, 382), (492, 377)):
            game.excavate(target)
        for _ in range(480):
            game.update(1 / 60, horizontal=-1)
            if game.state != "play":
                break
        self.assertEqual(game.state, "win")
        self.assertGreater(game.hp, 0)
        self.assertFalse(game.player.overlaps_terrain())

    def test_space_jump_detaches_from_verified_ladder_with_neutral_input(self):
        game = self.game
        game.player = Player(game.world, 98 * MACRO + 4, 85 * MACRO)
        tick = 1 / PHYSICS_HZ
        game.update(tick, vertical=-1)
        self.assertTrue(game.player.on_ladder)
        hanging_y = game.player.pos.y
        game.update(tick)
        self.assertEqual(game.player.pos.y, hanging_y)
        game.update(tick, jump=True)
        self.assertLess(game.player.pos.y, hanging_y)
        self.assertFalse(game.player.on_ladder)
        for _ in range(10):
            game.update(tick, vertical=-1)
        self.assertFalse(game.player.on_ladder)
        self.assertLess(game.player.velocity.y, -130)


if __name__ == "__main__":
    unittest.main()
