"""The Deep Descent: generated layout, playability and large-world systems."""

import math
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from config import CELL, MACRO, SCREEN_W, SCREEN_H, DEEP_OPEN_RANGE, BOSS_HP, CHUNK_CACHE_LIMIT
from level import WIDTH, HEIGHT, WATER, LAVA, build_level, validate_level
from levels.deep_world import LAYER_COUNT, generate_deep_world, world_size
from liquids import LiquidSystem
from world import World

SEEDS = (1, 2, 3, 4, 5, 6)


class GeneratedLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worlds = [generate_deep_world(seed) for seed in SEEDS]

    def test_world_is_much_wider_and_deeper_than_an_authored_stage(self):
        for generator, rows in self.worlds:
            self.assertGreaterEqual(len(rows[0]), 4 * WIDTH)
            self.assertGreaterEqual(len(rows), 4 * HEIGHT)
            self.assertEqual(len(generator.tops), LAYER_COUNT)

    def test_each_layer_is_mostly_diggable_terrain(self):
        lo, hi = DEEP_OPEN_RANGE
        for generator, rows in self.worlds:
            for k in range(LAYER_COUNT):
                with self.subTest(seed=generator.seed, layer=k):
                    self.assertTrue(lo - 0.03 <= generator.open_share(k) <= hi + 0.03)
                    top, bottom = generator.band(k)
                    solid = [c for row in rows[top:bottom + 1] for c in row[1:-1] if c in '#RS']
                    self.assertGreater(solid.count('#') / len(solid), 0.6)  # mostly dirt; rockier with depth

    def test_route_zig_zags_through_the_layers(self):
        for generator, _ in self.worlds:
            for k in range(LAYER_COUNT):
                top, bottom = generator.band(k)
                xs = [x for x, y in generator.route if top <= y <= bottom]
                # Even layers run left to right, odd layers back again.
                self.assertLess(xs[0] - xs[-1] if k % 2 == 0 else xs[-1] - xs[0], -20)

    def test_exit_is_walkable_from_spawn_and_targets_are_diggable(self):
        for generator, _ in self.worlds:
            walked = generator.walk_reachable(generator.entities['P'][0])
            self.assertIn(generator.entities['E'][0], walked)
            dug = generator.dig_reachable(generator.entities['P'][0])
            for kind in 'MGB':
                for point in generator.entities[kind]:
                    self.assertIn(point, dug)

    def test_water_and_lava_never_touch_at_start(self):
        for generator, rows in self.worlds:
            for region in generator.regions(' WL'):
                kinds = {rows[y][x] for x, y in region}
                self.assertFalse('W' in kinds and 'L' in kinds)
            self.assertIn('W', ''.join(rows))
            self.assertIn('L', ''.join(rows))
            validate_level(rows, generator.entities, size=None)

    def test_same_seed_builds_the_same_world(self):
        self.assertEqual(generate_deep_world(11)[1], generate_deep_world(11)[1])
        self.assertNotEqual(generate_deep_world(11)[1], generate_deep_world(12)[1])

    def test_size_settings_change_the_playable_area(self):
        generator, rows = generate_deep_world(3, columns=80, layer_rows=22)
        self.assertEqual((len(rows[0]), len(rows)), world_size(80, 22)[:2])
        self.assertIn(generator.entities['E'][0],
                      generator.walk_reachable(generator.entities['P'][0]))


class EveryStageExpandedTests(unittest.TestCase):
    """All six stages are large generated worlds; 1-5 keep their authored map."""

    @classmethod
    def setUpClass(cls):
        cls.stages = {stage: build_level(stage, None if stage < 6 else 6) for stage in range(1, 7)}

    def test_every_stage_is_four_to_six_times_wider_and_deeper(self):
        for stage, (rows, *_) in self.stages.items():
            with self.subTest(stage=stage):
                self.assertTrue(4 * WIDTH <= len(rows[0]) <= 6 * WIDTH)
                self.assertTrue(4 * HEIGHT <= len(rows) <= 6 * HEIGHT)
                self.assertGreaterEqual(len(rows[0]) * len(rows), 16 * WIDTH * HEIGHT)

    def test_every_stage_is_mostly_terrain(self):
        for stage, (rows, *_) in self.stages.items():
            inner = [c for row in rows[1:-1] for c in row[1:-1]]
            solid = sum(c in '#RS' for c in inner) / len(inner)
            with self.subTest(stage=stage):
                self.assertTrue(0.62 <= solid <= 0.75, solid)

    def test_authored_map_is_embedded_unchanged_with_a_gate(self):
        from level import build_authored_level
        for stage in range(1, 6):
            rows = self.stages[stage][0]
            authored = build_authored_level(stage)[0]
            for y in range(HEIGHT - 1):
                with self.subTest(stage=stage, row=y):
                    self.assertEqual(rows[y][:WIDTH - 1], authored[y][:WIDTH - 1])
            self.assertIn(' ', ''.join(rows[y][WIDTH - 1] for y in range(1, HEIGHT - 1)))

    def test_stages_differ_and_exits_are_far_from_spawn(self):
        layouts = {tuple(rows) for rows, *_ in self.stages.values()}
        self.assertEqual(len(layouts), 6)
        for stage, (rows, entities, scenery, _) in self.stages.items():
            (px, py), (ex, ey) = entities['P'][0], entities['E'][0]
            with self.subTest(stage=stage):
                self.assertGreater(ey - py, 3 * HEIGHT)
                self.assertGreater(len(scenery['route']), 6 * len(rows[0]) // 2)
                self.assertEqual(len(entities['B']), 1)

    def test_generated_world_is_walkable_from_every_gate(self):
        from levels.expanded import PROFILES, chamber_for
        for stage in range(1, 7):
            profile = {k: v for k, v in PROFILES[stage].items() if k not in ('hint', 'boss_hp')}
            generator, _ = generate_deep_world(
                700 + stage, profile=profile, chamber=chamber_for(stage) if stage < 6 else None)
            with self.subTest(stage=stage):
                self.assertIn(generator.entities['E'][0],
                              generator.walk_reachable(generator.walk_start))


class SceneryTests(unittest.TestCase):
    def test_props_sit_in_open_cave_on_real_support(self):
        rows, _, scenery, _ = build_level(6, 4)
        self.assertGreater(len(scenery['props']), 150)
        names = set()
        for prop in scenery['props']:
            names.add(prop['name'])
            x0, y0 = math.floor(prop['x'] + 1e-7), math.floor(prop['y'] + 1e-7)
            x1 = math.ceil(prop['x'] + prop['w'] - 1e-7)
            y1 = math.ceil(prop['y'] + prop['h'] - 1e-7)
            self.assertTrue(all(rows[y][x] == ' ' for y in range(y0, y1) for x in range(x0, x1)))
            self.assertTrue(all(rows[y][x] in '#RS' for x, y in prop['support_cells']))
        # Each biome contributes its own decoration.
        self.assertTrue({'ladder', 'crate'} & names)
        self.assertTrue(names & {'red_mushroom', 'fern', 'dirt_stalagmite', 'small_plants'})
        self.assertTrue(names & {'blue_crystal', 'purple_crystal', 'small_purple_crystal'})
        self.assertTrue(names & {'volcanic_rubble', 'red_crystal', 'bones', 'ribs'})
        self.assertGreater(len(scenery['props']), 60)


class DeepGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        from tiles import TileArt
        cls.art = TileArt(CELL, MACRO)

    def game(self, seed=5):
        from main import Game
        return Game(self.art, stage=6, seed=seed)

    def test_spawn_is_grounded_and_camera_clamps_to_world(self):
        game = self.game()
        self.assertTrue(game.player.grounded)
        self.assertFalse(game.player.overlaps_terrain())
        self.assertGreater(game.world.pixel_width, 2 * SCREEN_W)
        self.assertGreater(game.world.pixel_height, 4 * SCREEN_H)
        game.player.pos.update(game.world.pixel_width - 40, game.world.pixel_height - 60)
        game.player._sync_rect()
        for _ in range(240):
            game.follow_camera(1 / 60)
        self.assertEqual(game.render_camera, (game.world.pixel_width - SCREEN_W,
                                              game.world.pixel_height - SCREEN_H))
        game.player.pos.update(0, 0)
        game.player._sync_rect()
        game.follow_camera(0)
        self.assertEqual(game.render_camera, (0, 0))

    def test_layers_are_reported_by_depth(self):
        game = self.game()
        tops = game.layers['tops']
        self.assertEqual([game.layer_at(top * MACRO + 5) for top in tops], [1, 2, 3, 4])

    def test_exit_opens_only_after_the_boss_falls(self):
        game = self.game()
        self.assertIsNotNone(game.boss)
        game.monsters = [game.boss]
        self.assertFalse(game.exit_open)
        for hit in range(BOSS_HP):
            self.assertIn(game.boss, game.monsters)
            game.bombs.explode(pygame.Vector2(game.boss.rect.center))
        self.assertNotIn(game.boss, game.monsters)
        self.assertTrue(game.exit_open)

    def test_other_enemies_do_not_hold_the_exit_shut(self):
        game = self.game()
        game.monsters.remove(game.boss)
        self.assertTrue(game.monsters)
        self.assertTrue(game.exit_open)

    def test_distant_enemies_pause(self):
        game = self.game()
        far = [enemy for enemy in game.monsters if not game._enemy_active(enemy)]
        self.assertTrue(far)
        before = [enemy.pos.copy() for enemy in far]
        for enemy in far:
            enemy.velocity.y = 200
        game.update(1 / 30)
        self.assertEqual(before, [enemy.pos for enemy in far])

    def test_chunk_cache_stays_bounded_while_travelling(self):
        game = self.game()
        for x, y in game.renderer.scenery['route'][::3]:
            game.player.pos.update(x * MACRO, y * MACRO)
            game.player._sync_rect()
            game.follow_camera(0)
            game.draw(self.screen)
        self.assertLessEqual(len(game.renderer.cache), CHUNK_CACHE_LIMIT)

    def test_lights_are_culled_to_the_view(self):
        game = self.game()
        view = pygame.Rect(0, 0, SCREEN_W, SCREEN_H)
        near = list(game.renderer.lights_near(view))
        self.assertLess(len(near), len(game.renderer.lights))
        margin = view.inflate(game.renderer.lights_near.__defaults__[0] * 2, 0)
        self.assertTrue(all(margin.left <= l['x'] <= margin.right for l in near))


class LargeWorldLiquidTests(unittest.TestCase):
    def test_contact_only_reacts_the_touching_bodies(self):
        world = World(['RRRRRRRRRRRR',
                       'RWWLLRRWWRLR',
                       'RRRRRRRRRRRR'], scale=1)
        system = LiquidSystem(world)
        for _ in range(60):
            system.step()
        self.assertEqual(system.type_at(7, 1), WATER)   # a separate pool survives
        self.assertEqual(system.type_at(10, 1), LAVA)
        self.assertEqual(system.evaporated_mass, 2)
        self.assertEqual(system.solidified_mass, 2)
        # A second contact later still reacts.
        world.set_terrain(world.index(9, 1), 0)
        for _ in range(60):
            system.step()
        self.assertEqual(system.type_at(7, 1), 0)
        self.assertEqual(system.solidified_mass, 3)

    def test_focus_defers_moving_liquid_far_from_the_player(self):
        rows = ['R' * 40] + ['R' + ' ' * 38 + 'R'] * 4 + ['R' * 40]
        rows[1] = 'RW' + ' ' * 37 + 'R'
        world = World(rows, scale=1)
        system = LiquidSystem(world)
        system.focus, system.focus_radius = (38, 4), 5
        far = world.index(1, 1)
        for _ in range(10):
            system.step()
        self.assertEqual(system.mass_at(1, 1), 1.0)     # waits, unchanged
        self.assertIn(far, system.active)
        system.focus = (1, 1)
        system.step()
        self.assertLess(system.mass_at(1, 1), 1.0)       # resumes nearby


if __name__ == '__main__':
    unittest.main()
