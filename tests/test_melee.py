"""Walkers and the boss wind up (with a warning) before a swing lands."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (CELL, MACRO, SCREEN_H, SCREEN_W, MELEE_WINDUP, MELEE_TELL,
                    MELEE_STRIKE, MELEE_RECOVER, TELEGRAPH_TIME)
import enemy_sprites
from main import Game, Projectile
from tiles import TileArt
from ui import GameUI


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
        self.step(MELEE_TELL * 0.5 + 0.05)             # past the strike
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
        self.assertTrue(game.threats)
        self.assertIsNotNone(self.walker.telegraph_eta)

    def test_projectile_and_contact_telegraph_within_three_tenths_of_a_second(self):
        game = self.game
        game.monsters = []
        p = game.player.rect
        far_shot = Projectile(pygame.Vector2(p.left - 120, p.centery), pygame.Vector2(240, 0))
        near_shot = Projectile(pygame.Vector2(p.left - 50, p.centery), pygame.Vector2(240, 0))
        game.projectiles = [far_shot]
        self.assertEqual(game.incoming_threats(), [])          # ~0.5 s out: not yet
        game.projectiles = [near_shot]
        threats = game.incoming_threats()
        self.assertEqual(len(threats), 1)
        side, eta, source = threats[0]
        self.assertEqual(side, -1)
        self.assertLessEqual(eta, TELEGRAPH_TIME)
        self.assertIs(source, near_shot)

        # Contact collision telegraph when running toward an enemy.
        game.projectiles = []
        w = self.walker
        game.monsters = [w]
        w.melee_state = None
        w.pos.update(p.right + 20, p.bottom - w.rect.h)
        w._sync_rect()
        game.player.velocity.x = 176.0
        threats = game.incoming_threats()
        self.assertEqual(len(threats), 1)
        self.assertEqual(threats[0][0], 1)
        self.assertLessEqual(threats[0][1], TELEGRAPH_TIME)

    def test_offscreen_arrows_point_toward_offscreen_enemies(self):
        game = Game(self.art, stage=6)
        ui = GameUI()
        ui.start(game)
        ui.screen = 'game'
        gunner = next(m for m in game.monsters if m.shoots_projectiles)
        game.monsters = [gunner]
        cx, cy = game.render_camera
        p = game.player.rect
        gunner.pos.update(cx + SCREEN_W + 60, p.y)
        gunner._sync_rect()
        surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ui.offscreen_arrows(surface, game, {id(gunner)})
        # An arrow is drawn near the right edge at the player's height.
        right_strip = surface.subsurface((SCREEN_W - 45, p.centery - cy - 25, 30, 50))
        self.assertGreater(right_strip.get_bounding_rect(min_alpha=1).w, 0)


class BossMeleeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def test_boss_blade_hurts_only_when_it_reaches_the_ground(self):
        game = Game(self.art, stage=6)
        boss = game.boss
        game.monsters = [boss]
        game.player.pos.update(boss.rect.x - 60, boss.rect.bottom - game.player.rect.h)
        game.player.velocity.update(0, 0)
        game.player._sync_rect()
        hit_frame = None
        for _ in range(120):
            game.update(1 / 60)
            if game.hp < 100:
                hit_frame = enemy_sprites.animation(boss, game.player.rect.center, game.world_time)
                break
        self.assertIsNotNone(hit_frame)
        self.assertEqual(hit_frame, ('attack', 3))     # the frame with the sword in the ground

    def swing_gaps(self, hp):
        """Seconds between the boss's swings (wind-up starts) at ``hp``."""
        game = Game(self.art, stage=6)
        boss = game.boss
        boss.max_hp, boss.hp = 3, hp
        game.monsters = [boss]
        game.player.pos.update(boss.rect.x - 60, boss.rect.bottom - game.player.rect.h)
        game.player.velocity.update(0, 0)
        game.player._sync_rect()
        starts, last = [], None
        for _ in range(360):
            game.update(1 / 60)
            game.hp, game.hurt_timer = 100, 0.0
            game.combat.stun = 0.0
            state = getattr(boss, 'melee_state', None)
            if state == 'windup' and last != 'windup':
                starts.append(game.world_time)
            last = state
        return [b - a for a, b in zip(starts, starts[1:])]

    def test_last_phase_swings_faster(self):
        calm, rage = self.swing_gaps(3), self.swing_gaps(1)
        self.assertTrue(calm and rage)
        self.assertLess(max(rage), min(calm) * 0.7)
        from config import BOSS_RAGE_WINDUP, MELEE_TELL
        self.assertGreater(BOSS_RAGE_WINDUP, MELEE_TELL)   # the warning still shows

    def test_a_boss_of_one_hp_is_never_enraged(self):
        game = Game(self.art, stage=6)
        game.boss.max_hp = game.boss.hp = 1
        self.assertFalse(game.enraged(game.boss))


if __name__ == "__main__":
    unittest.main()
