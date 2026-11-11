"""The Stage 5.5 boss intro: the clip plays, can be skipped, and hands over
to the fight (fade in, gates shut, wide view, intro line)."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import ARENA_ZOOM, CELL, CUTSCENE_FADE_IN, MACRO, SCREEN_H, SCREEN_W
from main import Game
from tiles import TileArt
from ui import GameUI

try:
    import imageio_ffmpeg  # noqa: F401  (optional: without it the cutscene is skipped)
    HAVE_FFMPEG = True
except ImportError:
    HAVE_FFMPEG = False


@unittest.skipUnless(HAVE_FFMPEG, "imageio-ffmpeg is not installed")
class BossIntroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def setUp(self):
        from cutscene import load_boss_intro
        self.clip = load_boss_intro()
        self.assertIsNotNone(self.clip)
        self.game = Game(self.art, stage=5, bonus_room=True)
        self.ui = GameUI()
        self.screen = pygame.Surface((SCREEN_W, SCREEN_H))

    def tearDown(self):
        self.clip.finish()                 # stops its ffmpeg reader

    def play(self, seconds):
        for _ in range(round(seconds * 60)):
            self.ui.update(1 / 60, self.game)

    def test_the_clip_plays_full_screen_and_the_game_waits(self):
        clip = self.clip
        self.assertAlmostEqual(clip.duration, 11.0, delta=0.2)
        self.assertEqual(clip.image.get_size(), (SCREEN_W, SCREEN_H))
        self.ui.start(self.game, cutscene=clip)
        self.assertEqual(self.ui.screen, 'cutscene')
        self.assertFalse(self.ui.dialog.active)          # the intro line waits
        time_before = self.game.world_time
        self.play(2.0)
        self.assertEqual(self.ui.screen, 'cutscene')
        self.assertGreater(clip.index, 50)               # ~30 fps of video went by
        self.assertEqual(self.game.world_time, time_before)
        self.ui.draw(self.screen, self.game, (0, 0))
        self.assertNotEqual(self.screen.get_at((SCREEN_W // 2, SCREEN_H // 2))[:3], (0, 0, 0))

    def test_the_end_of_the_clip_starts_the_fight(self):
        self.ui.start(self.game, cutscene=self.clip)
        self.play(self.clip.duration + 0.2)
        self.assertEqual(self.ui.screen, 'game')
        self.assertTrue(self.game.arena_locked)
        self.assertEqual(self.game.zoom, ARENA_ZOOM)
        self.assertTrue(self.ui.dialog.active)
        self.assertGreater(self.ui.fade_in, 0)
        self.game.draw(self.screen)
        self.ui.draw(self.screen, self.game, (0, 0))   # fading in from black
        self.play(CUTSCENE_FADE_IN + 0.1)
        self.assertEqual(self.ui.fade_in, 0)

    def test_a_skip_ends_the_clip_on_the_next_frame(self):
        self.ui.start(self.game, cutscene=self.clip)
        self.play(0.5)
        self.ui.skip_cutscene()
        self.play(1 / 60)
        self.assertEqual(self.ui.screen, 'game')
        self.assertTrue(self.game.arena_locked)

    def test_rooms_without_a_cutscene_start_as_before(self):
        self.clip.skip()
        stage = Game(self.art, stage=1)
        self.ui.start(stage)
        self.assertEqual(self.ui.screen, 'game')
        self.assertTrue(self.ui.dialog.active)
        self.assertEqual(self.ui.fade_in, 0)


if __name__ == '__main__':
    unittest.main()
