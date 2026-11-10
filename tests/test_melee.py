"""Walkers and the boss wind up (with a warning) before a swing lands."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (CELL, MACRO, SCREEN_H, SCREEN_W, MELEE_WINDUP, MELEE_TELL,
                    MELEE_STRIKE, MELEE_RECOVER)
import enemy_sprites
from main import Game
from tiles import TileArt


class MeleeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def setUp(self):
        self.game = Game(self.art, stage=1)
        game = self.game
        self.walker = next(m for m in game.monsters if enemy_sprites.kind_of(m) == 'walker')
        # Only this walker: no stray shots in the timings below.
        game.monsters = [self.walker]
        game.dying = []
        w = self.walker
        game.player.pos.update(w.rect.x - 50, w.rect.bottom - game.player.rect.h)
        game.player.velocity.update(0, 0)
        game.player._sync_rect()

    def step(self, seconds):
        for _ in range(round(seconds * 60)):
            self.game.update(1 / 60)

    def test_wind_up_comes_before_the_hit(self):
        game, w = self.game, self.walker
        game.update(1 / 60)
        self.assertEqual(w.melee_state, 'windup')
        self.assertEqual(enemy_sprites.animation(w, game.player.rect.center, 0)[0], 'attack')
        self.step(MELEE_WINDUP - 0.1)
        self.assertEqual(game.hp, 100)                 # no damage during the wind-up
        self.step(0.15)
        self.assertLess(game.hp, 100)                  # the strike lands

    def test_parry_on_the_warning_deflects_the_swing(self):
        game, w = self.game, self.walker
        game.update(1 / 60)
        self.step(MELEE_WINDUP - MELEE_TELL * 0.5)
        self.assertEqual(w.melee_state, 'windup')
        game.press_e()
        self.step(0.15)
        self.assertEqual(game.hp, 100)
        self.assertGreater(w.stun_timer, 0)            # parried: stunned
        self.assertIsNone(w.melee_state)               # the swing is cancelled

    def test_walker_holds_its_ground_between_swings(self):
        game, w = self.game, self.walker
        self.step(MELEE_WINDUP + MELEE_STRIKE + MELEE_RECOVER + 0.1)
        x = w.pos.x
        game.hp = 100
        self.step(0.4)                                 # cooling down, player in reach
        self.assertAlmostEqual(w.pos.x, x, delta=1)
        self.assertEqual(game.hp, 100)                 # no shove damage between swings

    def test_warning_is_drawn(self):
        game = self.game
        game.update(1 / 60)
        self.step(MELEE_WINDUP - MELEE_TELL * 0.5)
        screen = pygame.Surface((SCREEN_W, SCREEN_H))
        game.draw(screen)


if __name__ == "__main__":
    unittest.main()
