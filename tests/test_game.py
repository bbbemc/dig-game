"""Headless integration checks using the authored map and real game systems."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import CELL, MACRO, PHYSICS_HZ, SCREEN_H, SCREEN_W
from level import DIRT, EMPTY, LAVA, ROCK, WATER
from main import Game, jump_requested
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
        self.assertEqual(tuple(game.player.pos), (120, 128))
        self.assertTrue(game.player.grounded)
        self.assertFalse(game.player.overlaps_terrain())
        game.player.pos.update(0, 0)
        self.assertEqual(game.camera(), (0, 0))
        game.player.pos.update(game.world.pixel_width, game.world.pixel_height)
        self.assertEqual(game.camera(), (0, 0))

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

    def test_excavating_visible_dirt_has_no_player_reach_limit(self):
        game = self.game
        target = (32, 47)
        self.assertGreater((target[0] - game.player.rect.centerx // CELL) ** 2
                           + (target[1] - game.player.rect.centery // CELL) ** 2,
                           18 ** 2)
        self.assertEqual(game.world.foreground[game.world.index(*target)], DIRT)
        game.excavate(target)
        self.assertEqual(game.world.foreground[game.world.index(*target)], EMPTY)

    def test_excavating_real_reservoir_releases_water_into_new_chamber(self):
        game = self.game
        # Open the diggable floor of the upper-right water cup.
        x, y = 16 * 5 + 2, 4 * 5 + 2
        self.assertTrue(game.world.solid(x, y))
        self.assertEqual(game.liquids.mass_at(x, y), 0)
        game.world.dig(x, y, radius=4)
        self.assertFalse(game.world.solid(x, y))
        for _ in range(60):
            game.update(1 / 60)
        released = sum(mass for index, mass in game.liquids.mass.items()
                       if game.liquids.types[index] == WATER
                       and abs(index % game.world.width - x) < 20
                       and index // game.world.width >= y)
        self.assertGreater(released, 0.1)
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
        self.assertEqual(tuple(fresh.player.pos), (120, 128))
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

    def test_grounded_enemies_stay_in_place(self):
        game = self.game
        starts = [actor.pos.copy() for actor in game.monsters]
        for _ in range(60):
            game.update(1 / 60)
        self.assertEqual([actor.pos for actor in game.monsters], starts)

    def test_enemy_falls_when_its_floor_is_dug_away(self):
        game = self.game
        enemy = game.monsters[0]
        start_y = enemy.pos.y
        floor_y = enemy.rect.bottom // CELL
        center_x = enemy.rect.centerx // CELL
        game.world.dig(center_x, floor_y, radius=5)
        for _ in range(60):
            game.update(1 / 60)
        self.assertGreater(enemy.pos.y, start_y)
        self.assertNotIn(enemy, game.monsters)

    def test_wall_blocks_enemy_line_of_sight(self):
        game = self.game
        enemy = game.monsters[0]
        enemy.pos.update(360, 368)
        enemy._sync_rect()
        game.player.pos.update(480, 368)
        game.player._sync_rect()
        wall_x = 420 // CELL
        wall_y = 376 // CELL
        game.world.set_terrain(game.world.index(wall_x, wall_y), ROCK)
        self.assertFalse(game._can_enemy_see_player(enemy))
        game.update(0)
        self.assertFalse(game.projectiles)

    def test_visible_enemy_projectile_deals_fifty_damage(self):
        game = self.game
        enemy = game.monsters[0]
        enemy.pos.update(360, 368)
        enemy._sync_rect()
        game.player.pos.update(480, 368)
        game.player._sync_rect()
        self.assertTrue(game._can_enemy_see_player(enemy))
        game.update(0)
        self.assertEqual(len(game.projectiles), 1)
        for _ in range(45):
            game.update(1 / 60)
            if game.hp < 100:
                break
        self.assertEqual(game.hp, 50)
        self.assertFalse(game.projectiles)

    def test_movement_and_jump_loop_across_stage_ledges(self):
        game = self.game
        start = game.player.pos.copy()
        for frame in range(15):
            game.update(1 / 60, horizontal=1, jump=frame == 0)
        self.assertGreater(game.player.pos.x, start.x)
        for _ in range(15):
            game.update(1 / 60, horizontal=-1)
        self.assertAlmostEqual(game.player.pos.x, start.x, delta=2)
        self.assertFalse(game.player.overlaps_terrain())
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

    def test_player_lava_contact_is_instant_death(self):
        game = self.game
        game.player.pos.update(14 * MACRO, 12 * MACRO)
        game.player.rect.topleft = round(game.player.pos.x), round(game.player.pos.y)
        self.assertTrue(game.touches(game.player.rect, LAVA))
        game.update(0)
        self.assertEqual((game.hp, game.state), (0, "lose"))

    def test_enemy_and_boss_die_in_lava(self):
        game = self.game
        game.player.pos.update(240, 128)
        game.player._sync_rect()
        game.monsters[0].pos.update(13 * MACRO, 12 * MACRO)
        game.monsters[0]._sync_rect()
        self.assertTrue(game.touches(game.monsters[0].rect, LAVA))
        game.update(0)
        self.assertFalse(game.monsters)
        self.assertTrue(game.boss_alive)
        game.boss.pos.update(16 * MACRO, 12 * MACRO)
        game.boss.rect.topleft = round(game.boss.pos.x), round(game.boss.pos.y)
        self.assertTrue(game.touches(game.boss.rect, LAVA))
        game.update(0)
        self.assertFalse(game.boss_alive)
        self.assertEqual(game.state, "play")
        self.assertEqual(game.hp, 100)

    def test_open_exit_completes_stage_without_key(self):
        game = self.game
        self.assertFalse(any(game.world.solid(x, y)
                             for x in range(game.exit_door.left // CELL,
                                            game.exit_door.right // CELL)
                             for y in range(game.exit_door.top // CELL,
                                            game.exit_door.bottom // CELL)))
        game.player.pos.update(20 * MACRO, 9 * MACRO - game.player.size)
        game.player._sync_rect()
        for _ in range(12):
            game.update(1 / 60, horizontal=1)
            if game.state == "win":
                break
        self.assertEqual(game.state, "win")
        self.assertGreater(game.hp, 0)
        self.assertFalse(game.player.overlaps_terrain())

    def test_first_stage_ladder_connects_spawn_shelf_to_corridor(self):
        game = self.game
        game.player.pos.update(8 * MACRO, 9 * MACRO)
        game.player._sync_rect()
        self.assertTrue(game.renderer.ladder_at(game.player.rect))
        for _ in range(90):
            game.update(1 / 60, vertical=-1)
        self.assertLess(game.player.pos.y, 9 * MACRO)
        self.assertEqual(game.state, "play")

    def test_w_climbs_ladder_while_space_still_jumps(self):
        game = self.game
        game.player.pos.update(8 * MACRO, 9 * MACRO)
        game.player._sync_rect()
        self.assertTrue(game.renderer.ladder_at(game.player.rect))
        self.assertFalse(jump_requested(pygame.K_w, True))
        self.assertFalse(jump_requested(pygame.K_UP, True))
        self.assertTrue(jump_requested(pygame.K_SPACE, True))
        self.assertTrue(jump_requested(pygame.K_w, False))
        start_y = game.player.pos.y
        for _ in range(30):
            game.update(1 / 60, vertical=-1,
                        jump=jump_requested(pygame.K_w, True))
        self.assertLess(game.player.pos.y, start_y)


if __name__ == "__main__":
    unittest.main()
