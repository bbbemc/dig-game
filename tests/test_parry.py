"""Parry (E): timing, enemy-attack integration, effects and edge cases."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (CELL, MACRO, SCREEN_W, SCREEN_H, PROJECTILE_DAMAGE, PARRY_ACTIVE_TIME,
                    PARRY_RECOVERY_TIME, PARRY_COOLDOWN, PARRY_STUN_DURATION,
                    PARRY_HITSTOP, PERFECT_PARRY_HITSTOP, WALKER_SIZE, WALKER_SPEED,
                    WALKER_CONTACT_DAMAGE)
from level import DIRT, EMPTY, LAVA
from main import Game, Projectile
from parry import ACTIVE, COOLDOWN, READY, RECOVERY, Parry
from physics import Actor
from tiles import TileArt
from ui import GameUI

STEP = 1 / 60
CYCLE = PARRY_ACTIVE_TIME + PARRY_RECOVERY_TIME + PARRY_COOLDOWN


class ParryTimingTests(unittest.TestCase):
    def test_states_run_ready_active_recovery_cooldown_ready(self):
        parry = Parry()
        self.assertTrue(parry.start())
        seen = [parry.state]
        events = []
        for _ in range(200):
            events += parry.update(0.01)
            if parry.state != seen[-1]:
                seen.append(parry.state)
        self.assertEqual(seen, [ACTIVE, RECOVERY, COOLDOWN, READY])
        self.assertEqual(events, ['whiff', 'ready'])

    def test_timing_is_the_same_at_any_frame_rate(self):
        for fps in (20, 30, 60, 144, 240):
            parry, dt = Parry(), 1 / fps
            parry.start()
            t, active_end, ready = 0.0, None, None
            while ready is None:
                parry.update(dt)
                t += dt
                if active_end is None and parry.state != ACTIVE:
                    active_end = t
                if parry.state == READY:
                    ready = t
            with self.subTest(fps=fps):
                self.assertAlmostEqual(active_end, PARRY_ACTIVE_TIME, delta=dt + 1e-9)
                self.assertAlmostEqual(ready, CYCLE, delta=dt + 1e-9)

    def test_a_long_frame_carries_time_across_phases(self):
        parry = Parry()
        parry.start()
        parry.update(PARRY_ACTIVE_TIME + PARRY_RECOVERY_TIME + 0.1)
        self.assertEqual(parry.state, COOLDOWN)
        self.assertAlmostEqual(parry.timer, PARRY_COOLDOWN - 0.1)

    def test_cannot_start_again_until_ready(self):
        parry = Parry()
        self.assertTrue(parry.start())
        for state in (ACTIVE, RECOVERY, COOLDOWN):
            while parry.state != state:
                parry.update(0.01)
            self.assertFalse(parry.start())
        while parry.state != READY:
            parry.update(0.01)
        self.assertTrue(parry.start())


class ParryGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def setUp(self):
        game = Game(self.art)
        game.monsters = []
        # The stage 1 walkway: open, flat floor at macro row 10.
        game.player.pos.update(10 * MACRO, 9 * MACRO + 8)
        game.player._sync_rect()
        game.player.drop_to_ground()
        game.miner.facing_right = True
        self.game = game

    def frames(self, n, **inputs):
        for _ in range(n):
            self.game.update(STEP, **inputs)

    def shooter(self, x):
        enemy = Actor(self.game.world, x, self.game.player.pos.y, size=24, speed=32)
        enemy.drop_to_ground()
        enemy.shoots_projectiles, enemy.shot_cooldown = True, 10.0
        enemy.contact_damage = 20
        self.game.monsters.append(enemy)
        return enemy

    def walker(self, x):
        game = self.game
        enemy = Actor(game.world, x, game.player.pos.y - 8, size=WALKER_SIZE, speed=WALKER_SPEED)
        enemy.drop_to_ground()
        enemy.shoots_projectiles = False
        enemy.contact_damage = WALKER_CONTACT_DAMAGE
        enemy.patrol_left, enemy.patrol_right = x - 80, x + 80
        enemy.chase_left, enemy.chase_right = x - 160, x + 160
        enemy.patrol_direction, enemy.chase_timer = -1, 0.0
        game.monsters.append(enemy)
        return enemy

    def bullet(self, side=1, owner=None, dy=0):
        rect = self.game.player.rect
        x = rect.right + 6 if side > 0 else rect.left - 6
        shot = Projectile((x, rect.centery + dy), (-240 * side, 0), owner)
        self.game.projectiles.append(shot)
        return shot

    # 1, 2, 3 ---------------------------------------------------------
    def test_press_e_opens_the_window_and_guards(self):
        self.assertTrue(self.game.start_parry())
        self.assertEqual(self.game.parry.state, ACTIVE)
        self.assertTrue(self.game.miner.guarding)
        self.assertEqual(self.game.miner.animation(self.game.player)[0], 'idle')  # wind-up
        self.frames(3)
        self.assertEqual(self.game.miner.animation(self.game.player)[0], 'dig')   # guard

    def test_holding_e_parries_once(self):
        # The game only reacts to KEYDOWN, and key repeat stays disabled, so a
        # held key produces one event; repeated presses while busy do nothing.
        self.assertEqual(pygame.key.get_repeat(), (0, 0))
        presses = 0
        for _ in range(round(CYCLE / STEP) - 2):   # held for almost a full cycle
            presses += self.game.start_parry()
            self.frames(1)
        self.assertEqual(presses, 1)

    def test_press_during_cooldown_does_nothing(self):
        self.game.start_parry()
        self.frames(round((PARRY_ACTIVE_TIME + PARRY_RECOVERY_TIME) / STEP) + 2)
        self.assertEqual(self.game.parry.state, COOLDOWN)
        self.assertFalse(self.game.start_parry())
        self.frames(round(PARRY_COOLDOWN / STEP) + 2)
        self.assertTrue(self.game.start_parry())

    # 4, 5 ------------------------------------------------------------
    def test_attack_in_the_window_deals_no_damage(self):
        shooter = self.shooter(self.game.player.pos.x + 200)
        self.game.start_parry()
        self.bullet(owner=shooter)
        self.frames(3)
        self.assertEqual(self.game.hp, 100)
        self.assertFalse(self.game.projectiles)
        self.assertTrue(self.game.parry.succeeded)
        self.assertEqual(self.game.parry.state, RECOVERY)
        # It lands right after the press: a perfectly timed parry.
        self.assertEqual([p[0] for p in self.game.fx.popups], ['PERFECT!'])

    def test_attack_after_the_window_hurts_normally(self):
        self.game.start_parry()
        self.frames(round(PARRY_ACTIVE_TIME / STEP) + 2)
        self.bullet()
        self.frames(3)
        self.assertEqual(self.game.hp, 100 - PROJECTILE_DAMAGE)

    def test_attack_without_parry_hurts(self):
        self.bullet()
        self.frames(3)
        self.assertEqual(self.game.hp, 100 - PROJECTILE_DAMAGE)

    # 6, 7 ------------------------------------------------------------
    def test_parried_walker_is_stunned_and_knocked_back(self):
        game = self.game
        walker = self.walker(game.player.rect.right - 6)
        start_x = walker.pos.x
        game.start_parry()
        self.frames(1)
        self.assertEqual(game.hp, 100)
        self.assertGreater(walker.stun_timer, 0)
        self.assertGreater(walker.knockback, 0)            # pushed away (to the right)
        self.frames(round(PARRY_HITSTOP / STEP) + 12)
        self.assertGreater(walker.pos.x, start_x + 8)
        self.assertEqual(game.hp, 100)                       # stunned: no contact damage
        self.frames(round(PARRY_STUN_DURATION / STEP) + 5)
        self.assertEqual(walker.stun_timer, 0)

    def test_parried_shooter_stops_firing_while_stunned(self):
        game = self.game
        shooter = self.shooter(game.player.pos.x + 200)
        game.start_parry()
        self.bullet(owner=shooter)
        self.frames(2)
        self.assertGreater(shooter.stun_timer, 0)
        shooter.shot_cooldown = 0
        game.update_enemy_combat(0)
        self.assertFalse(game.projectiles)

    def test_hitstop_freezes_the_world_briefly(self):
        game = self.game
        game.start_parry()
        self.bullet()
        self.frames(1)
        self.assertGreater(game.hitstop, 0)
        walker = self.walker(game.player.pos.x - 200)
        walker.velocity.y = 200
        frozen = walker.pos.copy()
        self.frames(1)
        self.assertEqual(walker.pos, frozen)
        self.frames(round(PARRY_HITSTOP / STEP) + 2)
        self.assertEqual(game.hitstop, 0)

    def test_boss_is_pushed_less_than_a_walker(self):
        game = Game(self.art, stage=6, seed=3)
        boss = game.boss
        game.monsters = [boss]
        game.player.pos.update(boss.rect.left - game.player.size + 4, boss.pos.y + 32)
        game.player._sync_rect()
        game.miner.facing_right = True
        game.start_parry()
        game.update(STEP)
        self.assertEqual(game.hp, 100)
        self.assertGreater(boss.stun_timer, 0)
        self.assertLess(abs(boss.knockback), 340)
        self.assertEqual(boss.hp, boss.max_hp)               # a parry is not a kill

    # 8, 9 ------------------------------------------------------------
    def test_attack_from_behind_is_not_parried(self):
        self.game.start_parry()                              # facing right
        self.bullet(side=-1)                                 # arrives from the left
        self.frames(3)
        self.assertEqual(self.game.hp, 100 - PROJECTILE_DAMAGE)
        self.assertFalse(self.game.parry.succeeded)

    def test_walker_behind_hurts_during_the_window(self):
        game = self.game
        walker = self.walker(game.player.rect.left - WALKER_SIZE + 6)
        game.start_parry()
        self.frames(1)
        self.assertEqual(game.hp, 100 - WALKER_CONTACT_DAMAGE)
        self.assertEqual(getattr(walker, 'stun_timer', 0), 0)

    def test_lava_cannot_be_parried(self):
        game = self.game
        lava = next(i for i, kind in game.liquids.types.items()
                    if kind == LAVA and game.liquids.mass[i] > 0.9)
        x, y = game.world.coords(lava)
        game.start_parry()
        game.player.pos.update(x * CELL - 8, y * CELL - 20)
        game.player._sync_rect()
        game.update(0)
        self.assertEqual((game.hp, game.state), (0, 'lose'))

    def test_bomb_blasts_ignore_the_parry(self):
        game = self.game
        game.start_parry()
        game.bombs.explode(pygame.Vector2(game.player.rect.center))
        self.assertLess(game.hp, 100)
        self.assertFalse(game.parry.succeeded)

    def test_drowning_ignores_the_parry(self):
        game = Game(self.art, stage=3)           # its flooded cache, as in test_game
        game.monsters = []
        game.player.pos.update(18 * MACRO + 4, 2 * MACRO + 4)
        game.player._sync_rect()
        self.assertTrue(game.fully_submerged(game.player.rect))
        game.oxygen = 0
        game.start_parry()
        for _ in range(10):
            game.update_oxygen(0.1)
        self.assertEqual(game.hp, 75)
        self.assertFalse(game.parry.succeeded)

    # 10, 11 ----------------------------------------------------------
    def test_parry_works_in_the_air_and_keeps_gravity(self):
        game = self.game
        self.frames(1, jump=True)
        self.frames(6)
        self.assertFalse(game.player.grounded)
        game.start_parry()
        before = game.player.pos.y
        self.bullet()
        self.frames(2)
        self.assertEqual(game.hp, 100)
        self.frames(round(PERFECT_PARRY_HITSTOP / STEP) + 40)
        self.assertNotEqual(game.player.pos.y, before)       # still airborne physics
        self.assertTrue(game.player.grounded)                # and lands normally

    def test_parry_keeps_walking_and_digging(self):
        game = self.game
        start = game.player.pos.x
        game.start_parry()
        self.frames(10, horizontal=-1)
        self.assertLess(game.player.pos.x, start - 20)
        x, y = game.player.rect.centerx // CELL, game.player.rect.bottom // CELL + 2
        self.assertEqual(game.world.foreground[game.world.index(x, y)], DIRT)
        game.excavate((x, y))
        self.assertEqual(game.world.foreground[game.world.index(x, y)], EMPTY)
        self.assertTrue(game.miner.facing_right)             # facing held while guarding

    # 12 --------------------------------------------------------------
    def test_simultaneous_hits_are_one_parry_and_the_window_closes(self):
        game = self.game
        game.start_parry()
        self.bullet(dy=-6)
        self.bullet(dy=6)
        self.frames(1)
        self.assertEqual(game.hp, 100)                       # both land in that frame
        self.assertEqual(len(game.fx.popups), 1)             # one parry, one feedback
        self.assertEqual(game.parry.state, RECOVERY)
        self.frames(round(PARRY_HITSTOP / STEP) + 2)
        self.bullet()
        self.frames(3)
        self.assertEqual(game.hp, 100 - PROJECTILE_DAMAGE)   # no chaining
        self.assertFalse(game.start_parry())                 # cooldown still applies

    # 13, 14 ----------------------------------------------------------
    def test_restart_resets_the_parry(self):
        self.game.start_parry()
        self.bullet()
        self.frames(1)
        fresh = Game(self.art)
        self.assertEqual(fresh.parry.state, READY)
        self.assertEqual((fresh.hitstop, fresh.fx.popups, fresh.fx.flashes), (0.0, [], []))
        self.assertFalse(fresh.miner.guarding)

    def test_pause_freezes_parry_timers(self):
        game, ui = self.game, GameUI()
        ui.start(game)
        game.start_parry()
        self.frames(3)
        ui.screen = 'paused'
        timer, state = game.parry.timer, game.parry.state
        for _ in range(120):     # paused frames: the main loop only draws
            ui.update(STEP, game)
            game.draw(self.screen)
            ui.draw(self.screen, game, (0, 0))
        self.assertEqual((game.parry.timer, game.parry.state), (timer, state))

    def test_effects_draw_without_errors(self):
        game, ui = self.game, GameUI()
        ui.start(game)
        game.start_parry()
        self.bullet()
        for _ in range(40):
            game.update(STEP)
            game.draw(self.screen)
            ui.draw(self.screen, game, (0, 0))


if __name__ == '__main__':
    unittest.main()
