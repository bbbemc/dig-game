"""Presentation regressions: opaque layers, seamless ground, strata, cave
shaping, structures, particles, the miner sprite, camera and lighting."""

import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import math
import unittest
from collections import Counter

import pygame

from caves import LIQUID_MARGIN
from config import CELL, MACRO, MAX_PARTICLES, SCALE, SCREEN_H, SCREEN_W
from effects import Particles
from level import DIRT, ROCK, build_level
from lighting import Lighting
from main import Game
from pixel_art import miner_frames
from tiles import DEPTH_ZONES, TileArt, stratum
from world import World

ARGB = (0xFF0000, 0xFF00, 0xFF, 0xFF000000)


class VisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)
        cls.rows, cls.entities, cls.scenery, _ = build_level()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_rear_layer_blending_stays_opaque_in_alpha_display_formats(self):
        # macOS windows use ARGB; blending onto an alpha-masked surface that
        # lacks SRCALPHA zeroes the alpha, which the window shows as black.
        sprite = pygame.Surface((40, 40), pygame.SRCALPHA)
        sprite.fill((200, 100, 50, 249))
        layer = pygame.Surface((40, 40), 0, 32)
        layer.fill((31, 26, 37))
        layer.blit(sprite, (0, 0))
        converted = layer.convert(pygame.Surface((1, 1), 0, 32, ARGB))
        self.assertEqual(converted.get_at((5, 5)).a, 255)
        game = Game(self.art)
        game.draw(pygame.Surface((SCREEN_W, SCREEN_H)))
        for back, _ in game.renderer.cache.values():
            argb = back.convert(pygame.Surface((1, 1), 0, 32, ARGB))
            self.assertTrue(all(argb.get_at((x, y)).a == 255
                                for y in range(0, 320, 16) for x in range(0, 320, 16)))
        for surface in (*self.art.textures.values(), *self.art.walls.values(),
                        *self.art.liquid_textures.values()):
            self.assertEqual(surface.get_masks()[3], 0)

    def test_ground_textures_wrap_without_a_seam(self):
        for group in ('dirt', 'deep', 'stone', 'dark'):
            texture = self.art.textures[group]
            width, height = texture.get_size()

            def column_gap(a, b):
                return sum(abs(texture.get_at((a, y))[c] - texture.get_at((b, y))[c])
                           for y in range(0, height, 2) for c in range(3))
            interior = sum(column_gap(x, x + 1) for x in (60, 170, 299)) / 3
            with self.subTest(group=group):
                self.assertLess(column_gap(width - 1, 0), interior * 1.6)

    def test_macro_details_follow_the_requested_mix_and_repeat_exactly(self):
        counts = Counter()
        for y in range(5, 45):
            for x in range(4, 120):
                detail = self.art.ground(DIRT, x, y)[4]
                counts['plain' if detail is None else 'detail'] += 1
                self.assertEqual(detail, self.art.ground(DIRT, x, y)[4])
        plain = counts['plain'] / sum(counts.values())
        self.assertGreater(plain, 0.58)
        self.assertLess(plain, 0.72)

    def test_strata_crossfade_continuously(self):
        for kind, zones in DEPTH_ZONES.items():
            for x in (3, 40, 97):
                previous = None
                for y in range(30, 95):
                    upper, lower, shares = stratum(zones, x, y)
                    if lower is None:
                        previous = None
                        continue
                    self.assertEqual(list(shares), sorted(shares))
                    if previous is not None and previous[0] == (upper, lower):
                        self.assertLess(abs(shares[0] - previous[1]), 0.3)
                    previous = ((upper, lower), shares[-1])

    def test_cave_shaping_spares_floors_liquids_and_props(self):
        plan = self.scenery['sculpt']
        self.assertTrue(plan['fill'] and plan['carve'])
        liquids = {(x, y) for y, row in enumerate(self.rows) for x, ch in enumerate(row) if ch in 'WL'}
        for x, y, kind in plan['fill']:
            mx, my = x // SCALE, y // SCALE
            self.assertEqual(self.rows[my][mx], ' ')
            self.assertIn(kind, (DIRT, ROCK))
            # Never at floor level, so walkable floors stay flat.
            self.assertNotIn(self.rows[my + 1][mx], '#R')
        for x, y in plan['carve']:
            self.assertEqual(self.rows[y // SCALE][x // SCALE], '#')
        for x, y, *_ in plan['fill'] + [(*c, None) for c in plan['carve']]:
            mx, my = x // SCALE, y // SCALE
            self.assertFalse(any(abs(mx - lx) < LIQUID_MARGIN and abs(my - ly) < LIQUID_MARGIN
                                 for lx, ly in liquids))
        # The plan is deterministic, so a restart rebuilds the same caves.
        self.assertEqual(build_level()[2]['sculpt'], plan)

    def test_rendering_never_changes_collision(self):
        game = Game(self.art)
        before = bytes(game.world.foreground)
        screen = pygame.Surface((SCREEN_W, SCREEN_H))
        for _ in range(3):
            game.update(1 / 60)
            game.draw(screen)
        self.assertEqual(bytes(game.world.foreground), before)

    def test_structures_stand_in_open_cave_on_solid_anchors(self):
        structures = self.scenery['structures']
        self.assertGreaterEqual(len(structures), 8)
        for structure in structures:
            for piece in structure['pieces']:
                x0, y0 = math.floor(piece['x'] + 1e-7), math.floor(piece['y'] + 1e-7)
                x1 = math.ceil(piece['x'] + piece['w'] - 1e-7)
                y1 = math.ceil(piece['y'] + piece['h'] - 1e-7)
                with self.subTest(piece=piece['kind'], x=piece['x'], y=piece['y']):
                    self.assertTrue(all(self.rows[y][x] == ' ' for y in range(y0, y1) for x in range(x0, x1)))
            for mx, my, _ in structure['anchors']:
                self.assertIn(self.rows[my][mx], '#R')
        # The opening room keeps its timber, lamps and cart on track.
        opening = [s for s in structures if 5 <= s['x'] < 17 and 3 <= s['y'] < 11]
        self.assertTrue(any(p['kind'] == 'brace' for s in opening for p in s['pieces']))
        self.assertTrue(any(p['kind'] == 'rail' for s in opening for p in s['pieces']))
        self.assertGreaterEqual(sum(len(s['lamps']) for s in opening), 2)

    def test_particles_are_capped(self):
        particles = Particles()
        world = World(['RRRR', 'R  R', 'RRRR'])
        for _ in range(60):
            particles.dust(10, 10)
            particles.splash(10, 10)
            particles.ember(10, 10)
            particles.dirt(world, list(range(world.width * world.height)))
        self.assertLessEqual(len(particles.items), MAX_PARTICLES)
        for _ in range(400):
            particles.update(1 / 60)
        self.assertFalse(particles.items)

    def test_miner_frames_fill_the_collision_box_from_the_floor(self):
        frames = miner_frames()
        for name in ('idle', 'walk', 'dig'):
            for frame in frames[name]:
                self.assertEqual(frame.get_size(), (32, 32))
                bounds = frame.get_bounding_rect()
                self.assertEqual(bounds.bottom, 32, name)
                self.assertGreaterEqual(bounds.h, 28, name)

    def test_camera_eases_but_cuts_on_teleport(self):
        game = Game(self.art)
        start = game.render_camera
        game.player.pos.x += 120
        game.update(1 / 60)
        moved = game.render_camera[0] - start[0]
        self.assertGreater(moved, 0)
        self.assertLess(moved, 120)
        game.player.pos.update(96 * MACRO, 90 * MACRO)
        game.draw(pygame.Surface((SCREEN_W, SCREEN_H)))
        self.assertEqual(game.render_camera, game.camera())

    def test_lamps_light_their_surroundings_and_dim_the_rest(self):
        lighting = Lighting((SCREEN_W, SCREEN_H))
        screen = pygame.Surface((SCREEN_W, SCREEN_H))
        screen.fill((120, 120, 120))
        lighting.draw(screen, (0, 0), 0.0, [('lamp', 480, 320, 120, (255, 172, 70), 0.0)])
        near, far = screen.get_at((480, 330)), screen.get_at((40, 40))
        self.assertGreaterEqual(near.r, 120)
        self.assertLess(far.r, 110)
        self.assertGreater(far.r, 40)


if __name__ == '__main__':
    unittest.main()
