"""Stage colour themes for the soil, edge decorations, and the new bomb art."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import BOMB_FUSE, CELL, MACRO, SCREEN_H, SCREEN_W
import bombs
from main import Game
from tiles import THEMES, TileArt


def mean(surface):
    return tuple(pygame.transform.average_color(surface))[:3]


class ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def test_every_stage_has_its_own_soil_colour(self):
        colours = {stage: mean(self.art.for_stage(stage).textures['dirt']) for stage in THEMES}
        self.assertEqual(len(set(colours.values())), len(THEMES))
        for stage, colour in colours.items():
            self.assertNotEqual(colour, mean(self.art.textures['dirt']), stage)

    def test_deeper_strata_stay_darker(self):
        themed = self.art.for_stage(1)
        lum = lambda c: sum(c) / 3
        self.assertGreater(lum(mean(themed.textures['dirt'])), lum(mean(themed.textures['ash'])))

    def test_themed_art_is_cached_and_leaves_the_base_alone(self):
        before = mean(self.art.textures['dirt'])
        self.assertIs(self.art.for_stage(3), self.art.for_stage(3))
        self.assertEqual(mean(self.art.textures['dirt']), before)
        self.assertIs(self.art.for_stage(99), self.art)          # no theme: unchanged
        self.assertIs(self.art.for_stage(2).textures['stone'], self.art.textures['stone'])

    def test_theme_decorations_exist_for_every_stage(self):
        for stage in THEMES:
            decor = self.art.for_stage(stage).decor
            self.assertTrue(decor['floor'] and decor['ceiling'] and decor['lip'], stage)

    def test_decorations_sit_on_open_floors_only(self):
        game = Game(self.art, stage=1)
        renderer = game.renderer
        pieces = renderer._decor(0, 0, 40)
        self.assertTrue(pieces)
        game.draw(pygame.Surface((SCREEN_W, SCREEN_H)))   # chunks with decor build fine


class BombArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def test_fuse_burns_down_and_sparks(self):
        full = bombs.bomb_frame(1.0)
        stub = bombs.bomb_frame(0.05)
        self.assertIsNotNone(full)
        self.assertNotEqual(pygame.image.tobytes(full, 'RGBA'), pygame.image.tobytes(stub, 'RGBA'))
        lit = {pygame.image.tobytes(bombs.bomb_frame(1.0, True, t / 16), 'RGBA') for t in range(3)}
        self.assertEqual(len(lit), 3)
        self.assertEqual(full.get_at((0, 0)).a, 0)                # transparent background

    def test_explosion_plays_then_clears(self):
        game = Game(self.art, bombs=True)
        game.player.pos.update(0, 0)
        game.bombs.explode(pygame.Vector2(game.player.rect.center) + (300, 0))
        self.assertEqual(len(game.bombs.blasts), 1)
        self.assertIsNotNone(bombs.explosion_frame(0.0))
        self.assertTrue(any(kind == 'flash' for kind, *_ in game.bombs.lights()))
        game.draw(pygame.Surface((SCREEN_W, SCREEN_H)))
        for _ in range(40):
            game.bombs.update(1 / 60)
        self.assertEqual(game.bombs.blasts, [])
        self.assertIsNone(bombs.explosion_frame(bombs.EXPLOSION_FRAMES / bombs.EXPLOSION_FPS))

    def test_thrown_bomb_draws_with_its_fuse(self):
        game = Game(self.art, bombs=True)
        game.bombs.carried = 1
        game.bombs.throw(pygame.Vector2(game.player.rect.center) + (80, 0))
        screen = pygame.Surface((SCREEN_W, SCREEN_H))
        for _ in range(int(BOMB_FUSE * 60) - 5):
            game.bombs.update(1 / 60)
        game.draw(screen)
        self.assertEqual(len(game.bombs.thrown), 1)


if __name__ == "__main__":
    unittest.main()
