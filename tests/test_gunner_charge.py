"""Gunners always charge (and warn) before a shot, even on first sight."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import CELL, MACRO, SCREEN_H, SCREEN_W, GUNNER_READY, TELEGRAPH_TIME
import enemy_sprites
from main import Game
from tiles import TileArt


class GunnerChargeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def setUp(self):
        self.game = Game(self.art, stage=1)
        self.gunner = next(m for m in self.game.monsters if m.shoots_projectiles)
        self.game.monsters = [self.gunner]

    def step(self, seconds):
        shots = []
        for _ in range(round(seconds * 60)):
            before = len(self.game.projectiles)
            self.game.update(1 / 60)
            self.game.hp = 100
            if len(self.game.projectiles) > before:
                shots.append(self.game.world_time)
        return shots

    def stand_in_view(self):
        g, e = self.game, self.gunner
        g.player.pos.update(e.rect.x - 140, e.rect.bottom - g.player.rect.h)
        g.player.velocity.update(0, 0)
        g.player._sync_rect()

    def hide(self):
        g = self.game
        g.player.pos.update(3 * MACRO, 3 * MACRO)    # the spawn ledge, out of sight
        g.player.velocity.update(0, 0)
        g.player._sync_rect()

    def test_charge_is_longer_than_the_animation(self):
        self.assertGreater(GUNNER_READY, enemy_sprites.CHARGE_TIME)
        self.assertGreater(GUNNER_READY, TELEGRAPH_TIME)

    def test_first_sighting_charges_before_firing(self):
        self.stand_in_view()
        start = self.game.world_time
        charged = aimed = False
        for _ in range(round(GUNNER_READY * 60) + 10):
            self.step(1 / 60)
            name, _ = enemy_sprites.animation(self.gunner, self.game.player.rect.center,
                                              self.game.world_time)
            charged |= name == 'charge'
            aimed |= self.gunner.aiming
            if self.game.projectiles:
                break
        self.assertTrue(self.game.projectiles, 'never fired')
        self.assertTrue(charged and aimed)
        self.assertGreaterEqual(self.game.world_time - start, GUNNER_READY - 2 / 60)

    def test_seeing_again_after_hiding_charges_again(self):
        self.hide()
        self.assertEqual(self.step(3.0), [])
        self.assertGreaterEqual(self.gunner.shot_cooldown, GUNNER_READY - 1e-9)
        self.stand_in_view()
        start = self.game.world_time
        shots = self.step(1.0)
        self.assertTrue(shots)
        self.assertGreaterEqual(shots[0] - start, GUNNER_READY - 2 / 60)


if __name__ == "__main__":
    unittest.main()
