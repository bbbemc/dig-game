"""Headless integration checks using the authored map and real game systems."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import CELL, MACRO, PHYSICS_HZ, SCREEN_H, SCREEN_W
from level import DIRT, EMPTY, LAVA, ROCK, STONE, WATER, build_level
from main import Game, jump_requested, next_stage_number
from physics import Player
from tiles import TileArt
from ui import GameUI


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


def chamber_pickups(game):
    """Bomb pickups inside the stage's authored opening map."""
    return [rect for rect in game.bombs.pickups
            if game.in_chamber(rect.centerx // MACRO, rect.centery // MACRO)]


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
        # The expanded world scrolls; the camera stops at its far corner.
        self.assertGreaterEqual(game.world.pixel_width, 4 * SCREEN_W)
        self.assertGreaterEqual(game.world.pixel_height, 4 * SCREEN_H)
        game.player.pos.update(game.world.pixel_width, game.world.pixel_height)
        self.assertEqual(game.camera(), (game.world.pixel_width - SCREEN_W,
                                         game.world.pixel_height - SCREEN_H))

    def test_all_three_stages_construct_with_their_own_layout(self):
        games = [Game(self.art, stage=stage) for stage in (1, 2, 3)]
        self.assertEqual([game.stage_name for game in games], [
            "ABANDONED MINE", "THE SINKING MINE", "DIRT CAVERNS"])
        self.assertEqual(len({bytes(game.world.foreground) for game in games}), 3)
        for game in games:
            self.assertTrue(game.player.grounded)
            self.assertFalse(game.player.overlaps_terrain())
            self.assertTrue(game.renderer.items)
            game.draw(pygame.Surface((SCREEN_W, SCREEN_H)))
        self.assertEqual(len(games[1].chamber_monsters), 2)
        self.assertTrue(all(enemy.shoots_projectiles
                            for enemy in games[1].chamber_monsters))
        self.assertGreater(games[1].liquids.initial_mass, 0)
        self.assertEqual(len(chamber_pickups(games[1])), 2)
        self.assertEqual(len(games[2].chamber_monsters), 1)
        self.assertGreater(games[2].liquids.initial_mass, 0)
        self.assertEqual(len(chamber_pickups(games[2])), 3)

    def test_stage_select_screen_can_load_each_stage_and_go_back(self):
        ui = GameUI()
        ui.screen = "stage_select"
        ui.draw(pygame.Surface((SCREEN_W, SCREEN_H)), self.game, (0, 0))
        buttons = {label: rect for rect, label in ui.buttons}
        self.assertTrue({
            "STAGE 1", "STAGE 2", "STAGE 3", "STAGE 4", "BACK TO MENU"
        } <= buttons.keys())
        stage_names = {
            1: "ABANDONED MINE",
            2: "THE SINKING MINE",
            3: "DIRT CAVERNS",
            4: "WATER CHAMBER",
            5: "THE SINKING MINE",
        }
        for stage, name in stage_names.items():
            label = f"STAGE {stage}"
            self.assertEqual(ui.click(buttons[label].center), label)
            game = Game(self.art, stage=stage)
            self.assertEqual(game.stage_name, name)

    def test_water_chamber_pool_fills_the_circled_upper_band(self):
        game = Game(self.art, stage=4)
        rows = build_level(4)[0]
        self.assertEqual(rows[1][12:16], "####")
        self.assertEqual(rows[7][12:16], "####")
        self.assertEqual(rows[7][16:19], "RRR")
        self.assertEqual(rows[7][19], "S")
        self.assertEqual(rows[7][20:23], "RRR")
        self.assertEqual(rows[8][5:7], "WW")
        self.assertEqual(rows[8][7:16], "R" * 9)
        self.assertEqual(rows[8][16:23], "W" * 7)
        self.assertEqual(rows[14][5:7], "WW")
        self.assertEqual(rows[14][10], "R")
        self.assertEqual(rows[14][20], "R")
        self.assertGreater(game.liquids.initial_mass, 2500)
        for _ in range(120):
            game.liquids.step(1 / 40)
        for x in (*range(5 * 5, 7 * 5), *range(16 * 5, 23 * 5)):
            self.assertAlmostEqual(game.liquids.mass_at(x, 8 * 5 + 2), 1.0)

    def test_stage_five_marked_areas_and_grounded_exit(self):
        game = Game(self.art, stage=5)
        rows, _, scenery, _ = build_level(5)
        self.assertEqual(rows[8][1:23], "L" * 22)
        self.assertTrue(all(rows[y][x] == "#"
                            for y in range(1, 6)
                            for x in range(15, 19)))
        self.assertEqual(rows[3][21], "W")
        self.assertEqual(rows[8][11:13], "LL")
        self.assertTrue(all(rows[y][4] == "#" and rows[y][5] == "S"
                            for y in range(9, 15)))
        self.assertTrue(all(rows[y][7:19] == " " * 12
                            for y in range(10, 14)))
        self.assertEqual(rows[14][7:19], "S" * 12)
        self.assertEqual(build_level(5)[1]["M"][2], (12, 12))
        self.assertEqual(scenery["chamber_gate"], (21, 12, 1, 2))
        self.assertEqual(rows[14][21], "#")
        self.assertEqual(game.chamber_gate.bottom, 14 * MACRO)

    def test_stage_clear_offers_next_stage_then_play_again(self):
        ui = GameUI()
        surface = pygame.Surface((SCREEN_W, SCREEN_H))
        ui.draw_end(surface, (0, 0), self.game, True)
        labels = {label for _, label in ui.buttons}
        self.assertIn("NEXT STAGE", labels)
        stage_two = Game(self.art, stage=2)
        ui.draw_end(surface, (0, 0), stage_two, True)
        labels = {label for _, label in ui.buttons}
        self.assertIn("NEXT STAGE", labels)
        stage_five = Game(self.art, stage=5)
        ui.draw_end(surface, (0, 0), stage_five, True)
        labels = {label for _, label in ui.buttons}
        self.assertIn("NEXT STAGE", labels)  # The Deep Descent follows
        final_game = Game(self.art, stage=6, seed=1)
        ui.draw_end(surface, (0, 0), final_game, True)
        labels = {label for _, label in ui.buttons}
        self.assertIn("PLAY AGAIN", labels)
        self.assertIn("MAIN MENU", labels)
        self.assertNotIn("NEXT STAGE", labels)

    def test_next_stage_number_advances_and_stops_at_the_final_stage(self):
        self.assertEqual(next_stage_number(1), 2)
        self.assertEqual(next_stage_number(2), 3)
        self.assertEqual(next_stage_number(3), 4)
        self.assertEqual(next_stage_number(4), 5)
        self.assertEqual(next_stage_number(5), 6)
        with self.assertRaises(ValueError):
            next_stage_number(6)
        with self.assertRaises(ValueError):
            next_stage_number(0)

    def test_next_stage_number_builds_the_stage_after_the_current_game(self):
        expected_names = {
            2: "THE SINKING MINE",
            3: "DIRT CAVERNS",
            4: "WATER CHAMBER",
            5: "THE SINKING MINE",
        }
        for current_stage, next_stage in enumerate(range(2, 6), start=1):
            current = Game(self.art, stage=current_stage)
            self.assertEqual(next_stage_number(current.stage_number), next_stage)
            following = Game(self.art, stage=next_stage)
            self.assertEqual(following.stage_number, next_stage)
            self.assertEqual(following.stage_name, expected_names[next_stage])
        self.assertEqual(len(Game(self.art, stage=3).chamber_monsters), 1)

    def test_dirt_caverns_has_contained_lava_and_a_purple_shooter(self):
        game = Game(self.art, stage=3)
        self.assertGreater(game.liquids.initial_mass, 0)
        self.assertTrue(game.renderer.ladders)
        prop_names = {item['prop']['name'] for item in game.renderer.items}
        self.assertTrue({'ladder', 'toolbox', 'small_rocks'} <= prop_names)
        self.assertTrue(game.renderer.scenery['structures'])
        self.assertEqual(build_level(3)[0][7][1:8], '#######')
        rows = build_level(3)[0]
        self.assertTrue(all(rows[y][9] == ' ' for y in range(1, 8)))
        self.assertEqual(rows[6][15:23], ' #######')
        self.assertEqual(rows[7][15:23], ' #######')
        self.assertEqual(rows[8][15:17], '##')
        self.assertEqual(rows[12][14:17], '###')
        self.assertEqual(rows[12][17:19], 'LL')
        self.assertEqual(rows[12][21], ' ')
        self.assertEqual(rows[10][17:23], 'LLLLL#')
        self.assertEqual(rows[11][17:23], 'LLLLL#')
        self.assertEqual(rows[11][16], '#')
        self.assertEqual(rows[13][11], '#')
        self.assertEqual(rows[13][12:15], '###')
        self.assertEqual(rows[13][17:19], 'LL')
        self.assertEqual(rows[14][12:19], 'LLLLLLL')
        self.assertEqual(len(game.chamber_monsters), 1)
        self.assertTrue(game.monsters[0].shoots_projectiles)
        self.assertEqual(tuple(game.monsters[0].pos),
                         (15 * MACRO, 7 * MACRO + 16))
        self.assertEqual(len(chamber_pickups(game)), 3)

        for _ in range(30):
            game.update(0.1)
        leaked_lava = [
            game.world.coords(index)
            for index, kind in game.liquids.types.items()
            if kind == LAVA
            and game.world.coords(index)[0] // 5 <= 16
            and game.world.coords(index)[1] // 5 <= 12
        ]
        self.assertFalse(leaked_lava)

        shooter = game.monsters[0]
        game.player.pos.update(13 * MACRO, 7 * MACRO + 16)
        game.player._sync_rect()
        self.assertTrue(game._can_enemy_see_player(shooter))
        game.update_enemy_combat(0)
        self.assertTrue(game.projectiles)

    def test_stage_two_platform_route_reaches_the_exit(self):
        game = Game(self.art, stage=2)
        game.monsters.clear()
        route = (
            (25, 1, False),
            (30, 1, True),
            (8, 1, False),
            (30, 1, True),
            (25, 1, False),
            (30, 1, True),
            (20, 1, False),
            (30, 1, True),
            (29, 1, False),
        )
        for frames, horizontal, jump in route:
            for frame in range(frames):
                game.update(1 / 60, horizontal=horizontal,
                            jump=jump and frame == 0)
        # The authored door is now the gate into the expanded world.
        self.assertTrue(game.player.rect.colliderect(game.chamber_gate))
        self.assertEqual(game.state, "play")
        self.assertEqual(game.bombs.carried, 2)

    def test_stage_two_middle_platforms_are_small_and_separated(self):
        rows = build_level(2)[0]
        self.assertEqual(rows[8][5:7], "SS")
        self.assertEqual(rows[8][7:9], "  ")
        self.assertEqual(rows[7][9:11], "SS")
        self.assertEqual(rows[7][11:13], "  ")
        self.assertEqual(rows[6][13:15], "SS")
        self.assertEqual(rows[6][15:17], "  ")

    def test_stage_five_changes_only_the_leftmost_frame_column_to_dirt(self):
        game = Game(self.art, stage=5)
        rows = build_level(5)[0]
        for y in range(9, 15):
            self.assertEqual(rows[y][4], "#")
            self.assertEqual(rows[y][5], "S")
            self.assertEqual(game.renderer.scenery["materials"][4, y], "dirt")
            self.assertEqual(game.renderer.scenery["materials"][5, y], "stone")
            self.assertEqual(
                game.world.foreground[game.world.index(
                    4 * (MACRO // CELL) + 2, y * (MACRO // CELL) + 2)],
                DIRT,
            )
            self.assertEqual(
                game.world.foreground[game.world.index(
                    5 * (MACRO // CELL) + 2, y * (MACRO // CELL) + 2)],
                STONE,
            )
        dirt_cell = game.world.index(
            4 * (MACRO // CELL) + 2, 9 * (MACRO // CELL) + 2)
        self.assertTrue(game.world.dig(*game.world.coords(dirt_cell), radius=3))
        self.assertEqual(game.world.foreground[dirt_cell], EMPTY)
        stone_cell = game.world.index(
            5 * (MACRO // CELL) + 2, 9 * (MACRO // CELL) + 2)
        self.assertEqual(game.world.foreground[stone_cell], STONE)

    def test_stage_two_fills_circled_dirt_openings_with_water(self):
        game = Game(self.art, stage=2)
        rows = build_level(2)[0]
        for y in range(10, 14):
            self.assertEqual(rows[y][1:4], "WWW")
            self.assertEqual(rows[y][20:23], "WWW")
        self.assertFalse([box for box, _ in game.renderer.ladders
                          if game.in_chamber(box.centerx // MACRO, box.centery // MACRO)])
        self.assertGreater(game.liquids.initial_mass, 2200)

    def test_stage_two_has_deep_water_and_a_clear_shooter_lane(self):
        game = Game(self.art, stage=2)
        shooters = game.chamber_monsters
        self.assertEqual(len(shooters), 2)
        self.assertGreaterEqual(game.liquids.initial_mass, 2200)
        self.assertFalse(game.world.solid(12 * 5 + 2, 11 * 5 + 2))
        self.assertFalse(game.world.solid(12 * 5 + 2, 13 * 5 + 2))
        self.assertTrue(game.world.solid(12 * 5 + 2, 14 * 5 + 2))
        rows = build_level(2)[0]
        self.assertEqual(rows[6][3], "S")
        self.assertEqual(rows[6][2], "S")
        self.assertEqual(rows[3][4], " ")
        self.assertIn("stone", game.renderer.scenery["materials"].values())

        left_shooter = min(shooters, key=lambda enemy: enemy.pos.x)
        self.assertLess(left_shooter.pos.y, 240)
        game.player.pos.update(140, left_shooter.pos.y - 70)
        game.player._sync_rect()
        self.assertTrue(game._can_enemy_see_player(left_shooter))
        game.update(0)
        self.assertEqual(len(game.projectiles), 1)
        for _ in range(8):
            game.update(1 / 60)
        self.assertEqual(len(game.projectiles), 1)

        right_shooter = max(shooters, key=lambda enemy: enemy.pos.x)
        left_shooter.shot_cooldown = 10
        game.player.pos.update(600, right_shooter.pos.y)
        game.player._sync_rect()
        self.assertTrue(game._can_enemy_see_player(right_shooter))
        game.update(0)
        self.assertEqual(len(game.projectiles), 2)

    def test_stage_two_stone_platforms_survive_digging_and_bombs(self):
        game = Game(self.art, stage=2)
        platform_cell = game.world.index(5 * 5 + 1, 8 * 5 + 1)
        self.assertEqual(game.world.foreground[platform_cell], ROCK)
        self.assertFalse(game.world.dig(5 * 5 + 1, 8 * 5 + 1, radius=2))
        game.bombs.explode(pygame.Vector2(
            (5 * 5 + 1) * CELL, (8 * 5 + 1) * CELL))
        self.assertEqual(game.world.foreground[platform_cell], ROCK)

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
        actors = [game.player, *game.monsters]
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

    def test_grounded_shooter_stays_in_place(self):
        game = self.game
        shooter = next(actor for actor in game.monsters
                       if actor.shoots_projectiles)
        start = shooter.pos.copy()
        for _ in range(60):
            game.update(1 / 60)
        self.assertEqual(shooter.pos, start)

    def test_larger_walker_patrols_its_range_without_shooting(self):
        game = self.game
        walker = next(actor for actor in game.monsters
                      if not actor.shoots_projectiles)
        self.assertGreater(walker.size, game.monsters[0].size)
        start_x = walker.pos.x
        for _ in range(300):
            game.update(1 / 60)
            self.assertGreaterEqual(walker.pos.x, walker.patrol_left)
            self.assertLessEqual(walker.pos.x, walker.patrol_right)
        self.assertNotEqual(walker.pos.x, start_x)
        self.assertFalse(game.projectiles)

    def test_walker_follows_player_beyond_patrol_range_and_remembers_sight(self):
        game = self.game
        walker = next(actor for actor in game.monsters
                      if not actor.shoots_projectiles)
        game.player.pos.update(900, 360)
        game.player._sync_rect()
        self.assertTrue(game._can_enemy_see_player(walker))
        start_x = walker.pos.x
        game.update(0.1)
        self.assertGreater(walker.pos.x, start_x)

        game.world.set_terrain(game.world.index(104, 47), ROCK)
        self.assertFalse(game._can_enemy_see_player(walker))
        start_x = walker.pos.x
        game.update(0.1)
        self.assertGreater(walker.pos.x, start_x)

        walker.pos.update(850, 240)
        walker._sync_rect()
        game.world.set_terrain(game.world.index(104, 47), EMPTY)
        game.player.pos.update(40, 240)
        game.player._sync_rect()
        game.update(0.1)
        self.assertLessEqual(walker.pos.x, walker.patrol_right)

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

    def test_enemy_line_of_sight_reaches_across_lava_pool_area(self):
        game = self.game
        walker = next(enemy for enemy in game.monsters
                      if not enemy.shoots_projectiles)
        game.player.pos.update(360, walker.pos.y)
        game.player._sync_rect()
        distance = pygame.Vector2(game.player.rect.center).distance_to(
            walker.rect.center)
        self.assertGreater(distance, 360)
        self.assertTrue(game._can_enemy_see_player(walker))

    def test_enemy_line_of_sight_is_limited_to_450_pixels(self):
        game = self.game
        enemy = game.monsters[0]
        enemy.pos.update(200, 40)
        enemy._sync_rect()
        game.player.pos.update(645, 40)
        game.player._sync_rect()
        self.assertTrue(game._can_enemy_see_player(enemy))
        game.player.pos.update(696, 40)
        game.player._sync_rect()
        self.assertFalse(game._can_enemy_see_player(enemy))

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

    def test_oxygen_drains_only_when_fully_submerged_and_refills_in_air(self):
        game = Game(self.art, stage=3)
        game.monsters.clear()
        game.player.pos.update(18 * MACRO + 4, 2 * MACRO + 4)
        game.player._sync_rect()
        self.assertTrue(game.fully_submerged(game.player.rect))

        for _ in range(100):
            game.update_oxygen(0.1)
        self.assertAlmostEqual(game.oxygen, 50, places=5)
        for _ in range(100):
            game.update_oxygen(0.1)
        self.assertEqual(game.oxygen, 0)

        game.player.pos.y = MACRO + 24
        game.player._sync_rect()
        self.assertFalse(game.fully_submerged(game.player.rect))
        for _ in range(70):
            game.update_oxygen(0.1)
        self.assertAlmostEqual(game.oxygen, 100, places=5)

    def test_partial_submersion_does_not_drain_oxygen(self):
        game = Game(self.art, stage=3)
        game.player.pos.update(18 * MACRO + 4, 2 * MACRO - 16)
        game.player._sync_rect()
        self.assertTrue(game.touches(game.player.rect, WATER))
        self.assertFalse(game.fully_submerged(game.player.rect))
        game.update_oxygen(0.1)
        self.assertEqual(game.oxygen, 100)

    def test_empty_oxygen_deals_twenty_five_damage_per_second(self):
        game = Game(self.art, stage=3)
        game.monsters.clear()
        game.player.pos.update(18 * MACRO + 4, 2 * MACRO + 4)
        game.player._sync_rect()
        game.oxygen = 0
        for _ in range(10):
            game.update_oxygen(0.1)
        self.assertEqual(game.hp, 75)
        self.assertEqual(game.state, 'play')

        for _ in range(30):
            game.update_oxygen(0.1)
        self.assertEqual(game.hp, 0)
        self.assertEqual(game.state, 'lose')

    def test_enemies_die_in_lava(self):
        game = self.game
        game.player.pos.update(240, 128)
        game.player._sync_rect()
        shooter = next(enemy for enemy in game.monsters
                       if enemy.shoots_projectiles)
        shooter.pos.update(13 * MACRO, 12 * MACRO)
        shooter._sync_rect()
        self.assertTrue(game.touches(shooter.rect, LAVA))
        game.update(0)
        self.assertEqual(len(game.chamber_monsters), 1)
        self.assertFalse(game.chamber_monsters[0].shoots_projectiles)
        self.assertEqual(game.state, "play")
        self.assertEqual(game.hp, 100)

    def test_walker_contact_deals_twenty_five_damage(self):
        game = self.game
        walker = next(enemy for enemy in game.monsters
                      if not enemy.shoots_projectiles)
        game.player.pos.update(walker.pos)
        game.player._sync_rect()
        game.update(0)
        self.assertEqual(game.hp, 75)

    def test_exit_stays_closed_until_all_enemies_are_cleared(self):
        game = self.game
        self.assertFalse(any(game.world.solid(x, y)
                             for x in range(game.exit_door.left // CELL,
                                            game.exit_door.right // CELL)
                             for y in range(game.exit_door.top // CELL,
                                            game.exit_door.bottom // CELL)))
        game.player.pos.update(game.exit_door.left, game.exit_door.top)
        game.player._sync_rect()
        game.update(0)
        self.assertFalse(game.exit_open)
        self.assertEqual(game.state, "play")
        game.monsters.clear()
        self.assertTrue(game.exit_open)
        game.update(0)
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
