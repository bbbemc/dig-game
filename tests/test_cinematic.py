"""Cinematic parry polish: bottom-centre posture bar, layered VFX, audio, feel."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import math
import time
import unittest
import wave
from array import array

import pygame

import parry_fx
from audio import EVENTS, SFX_DIR, SoundBank
from combat import give_posture
from config import (CELL, MACRO, SCREEN_W, SCREEN_H, FLUID_HZ, PARRY_ACTIVE_TIME,
                    PARRY_RECOVERY_TIME, PARRY_COOLDOWN, PARRY_HITSTOP, PERFECT_PARRY_HITSTOP,
                    PARRY_SHAKE_PX, PERFECT_SHAKE_PX, PERFECT_SHAKE_TIME, PERFECT_RECOIL_PX,
                    PARRY_SPARKS, PERFECT_SPARKS, PARRY_PERFECT_TIME, GUARD_BREAK_HITSTOP,
                    GUARD_BREAK_SHAKE_PX, PLAYER_MAX_POSTURE, PLAYER_STUN_DURATION,
                    POSTURE_BAR_WIDTH, POSTURE_BAR_HEIGHT, POSTURE_BAR_HOLD,
                    POSTURE_RECOVERY_DELAY, SFX_HEADROOM, WALKER_SIZE, WALKER_SPEED,
                    WALKER_CONTACT_DAMAGE)
from main import Game, Projectile
from physics import Actor
from posture_hud import FADE_OUT
from tiles import TileArt
from ui import GameUI

STEP = 1 / 60
CYCLE = PARRY_ACTIVE_TIME + PARRY_RECOVERY_TIME + PARRY_COOLDOWN


def frames_for(seconds):
    return round(seconds / STEP)


class CinematicCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)
        parry_fx.warm()

    def setUp(self):
        game = Game(self.art)
        game.monsters = []
        game.player.pos.update(10 * MACRO, 9 * MACRO + 8)
        game.player._sync_rect()
        game.player.drop_to_ground()
        game.miner.facing_right = True
        game.sounds.reset_limits()
        game.sounds.requests.clear()
        self.game, self.ui = game, GameUI()
        self.ui.start(game)

    def step(self, n=1, draw=False, **inputs):
        for _ in range(n):
            self.game.update(STEP, **inputs)
            self.ui.update(STEP, self.game)
            if draw:
                self.game.draw(self.screen)
                self.ui.draw(self.screen, self.game, (0, 0))

    def bullet(self, side=1):
        rect = self.game.player.rect
        x = rect.right + 6 if side > 0 else rect.left - 6
        self.game.projectiles.append(Projectile((x, rect.centery), (-240 * side, 0), None))

    def walker(self, x):
        game = self.game
        enemy = Actor(game.world, x, game.player.pos.y - 8, size=WALKER_SIZE, speed=WALKER_SPEED)
        enemy.drop_to_ground()
        enemy.shoots_projectiles = False
        enemy.contact_damage = WALKER_CONTACT_DAMAGE
        enemy.patrol_left, enemy.patrol_right = x - 80, x + 80
        enemy.chase_left, enemy.chase_right = x - 160, x + 160
        enemy.patrol_direction, enemy.chase_timer = -1, 0.0
        give_posture(enemy)
        game.monsters.append(enemy)
        return enemy

    def normal_parry(self):
        """Press, then let a bullet arrive after the perfect timing has passed."""
        self.game.press_e()
        self.step(frames_for(PARRY_PERFECT_TIME) + 2)
        self.bullet()
        self.step(1)

    def perfect_parry(self):
        self.game.press_e()
        self.bullet()
        self.step(1)


class PostureBarTests(CinematicCase):
    # 1, 2 ------------------------------------------------------------
    def test_bar_sits_at_the_bottom_centre(self):
        hud = self.ui.posture
        self.assertEqual(hud.rect.center, (SCREEN_W // 2, SCREEN_H - 75))
        self.assertGreater(hud.rect.top, SCREEN_H * 0.8)       # not the top-left HUD
        hud.visibility = 1.0
        self.assertEqual(hud.bar_rect(), hud.rect)
        # Nothing is drawn over the player's head for posture any more.
        self.game.combat.posture.value = 2
        self.step(10, draw=True)
        self.assertEqual(self.ui.posture.value, 2)

    def test_bar_scale_fits_960x640(self):
        hud = self.ui.posture
        self.assertTrue(300 <= POSTURE_BAR_WIDTH <= 360)
        self.assertTrue(14 <= POSTURE_BAR_HEIGHT <= 20)
        x, y = hud.origin
        w, h = hud.canvas.get_size()
        self.assertTrue(x >= 0 and x + w <= SCREEN_W and y + h <= SCREEN_H)  # caps included
        self.assertEqual(x + w // 2, SCREEN_W // 2)                          # centred
        # The tutorial prompt moves up out of the bar's way while it shows.
        hud.visibility = 1.0
        self.assertLessEqual(552 - 72 + 54, hud.rect.top - 8)

    # 3, 4 ------------------------------------------------------------
    def test_bar_fades_and_slides_in_when_combat_starts(self):
        hud = self.ui.posture
        self.step(30)
        self.assertEqual(hud.visibility, 0.0)                  # exploring: hidden
        walker = self.walker(self.game.player.rect.right + 120)
        walker.chase_timer = 5.0                               # it is hunting the player
        seen, slides = [], []
        for _ in range(20):
            self.step(1, draw=True)
            seen.append(hud.visibility)
            slides.append(hud.bar_rect().y)
        self.assertEqual(seen[-1], 1.0)
        self.assertTrue(all(b >= a for a, b in zip(seen, seen[1:])))      # smooth, no pop
        self.assertGreater(len(set(seen)), 5)
        self.assertGreater(slides[0], slides[-1])                          # slid upward
        self.assertLess(hud.appear, 0.6)                                   # golden arrival glow

    def test_bar_holds_then_fades_out_and_a_new_fight_cancels_it(self):
        hud = self.ui.posture
        self.perfect_parry()
        self.step(30)
        self.assertEqual(hud.visibility, 1.0)
        self.step(frames_for(POSTURE_BAR_HOLD) - 40)
        self.assertEqual(hud.visibility, 1.0)                  # still holding at ~4 s
        self.step(50)
        self.assertLess(hud.visibility, 1.0)                   # fading out
        low = hud.visibility
        self.assertGreater(hud.bar_rect().y, hud.rect.y)       # sliding down
        self.perfect_parry()                                   # a new interaction...
        self.step(3)
        self.assertGreater(hud.visibility, low)                # ...cancels the fade
        self.step(frames_for(0.25 + POSTURE_BAR_HOLD + FADE_OUT) + 10)
        self.assertEqual(hud.visibility, 0.0)                  # and later it does hide

    # 8 ---------------------------------------------------------------
    def test_bar_follows_the_real_posture(self):
        hud, combat = self.ui.posture, self.game.combat
        for expected in (1, 2):
            self.game.hp, self.game.hurt_timer = 100, 0
            self.bullet()
            self.step(2)
            self.assertEqual((hud.value, combat.posture.value), (expected, expected))
            self.assertLess(hud.pulse, 0.1)                    # the new point pulses
            self.step(30, draw=True)
            self.assertAlmostEqual(hud.shown, expected / PLAYER_MAX_POSTURE, places=2)
            self.assertEqual(hud.level(), expected)
        self.assertIn('posture_damage', self.game.sounds.requests)
        combat.posture.calm = POSTURE_RECOVERY_DELAY + 1.0    # recovery drains smoothly
        self.step(10)
        self.assertLess(hud.shown, 2 / PLAYER_MAX_POSTURE)
        self.assertEqual(hud.value, 2)

    # 9 ---------------------------------------------------------------
    def test_three_failed_defences_break_the_bar_and_stun(self):
        hud, game = self.ui.posture, self.game
        for _ in range(PLAYER_MAX_POSTURE):
            game.hp, game.hurt_timer = 100, 0
            self.bullet()
            self.step(2, draw=True)
        self.assertFalse(game.combat.can_act())
        self.assertTrue(hud.broken)
        self.assertEqual(hud.level(), 3)
        self.assertTrue(hud.shards)                            # the breaking animation
        self.assertIn('POSTURE BROKEN!', [p[0] for p in game.fx.popups])
        self.step(frames_for(PLAYER_STUN_DURATION + GUARD_BREAK_HITSTOP) + 2, draw=True)
        self.assertFalse(hud.broken)
        self.assertLess(hud.heal_age, 0.5)                     # healing shimmer


class VfxTests(CinematicCase):
    # 5 ---------------------------------------------------------------
    def test_a_parry_layers_every_effect(self):
        game = self.game
        self.normal_parry()
        fx = game.fx
        self.assertEqual(game.perfect_parries, 0)
        self.assertEqual(len(fx.flashes), 1)                   # impact flash
        self.assertEqual(len(fx.slashes), 1)                   # sword-clash arc
        self.assertEqual(len(fx.streaks), 1)                   # the opposing blade
        self.assertTrue(fx.rings)                              # shockwave
        self.assertEqual(len(fx.sparks.items), PARRY_SPARKS)   # 25-45 sparks
        self.assertIsNotNone(fx.edge)                          # golden edge flash
        self.assertAlmostEqual(game.hitstop, PARRY_HITSTOP)   # set this frame
        self.assertEqual(game.kick[2], PARRY_SHAKE_PX)
        self.assertEqual([p[0] for p in fx.popups], ['PARRY!'])
        self.assertTrue(list(fx.lights()))                     # the cave lights up
        self.assertGreater(game.miner.recoil, 0)
        for _ in range(12):                                    # and every layer draws
            self.step(1, draw=True)

    def test_a_perfect_parry_is_bigger(self):
        game = self.game
        self.perfect_parry()
        fx = game.fx
        self.assertEqual(game.perfect_parries, 1)
        self.assertEqual(len(fx.sparks.items), PERFECT_SPARKS)
        self.assertTrue(fx.slashes[0][5])                      # the perfect slash
        self.assertEqual(len(fx.rings), 2)
        self.assertIsNotNone(fx.vignette)
        self.assertAlmostEqual(game.hitstop, PERFECT_PARRY_HITSTOP)
        self.assertEqual((game.kick[2], game.kick[4]), (PERFECT_SHAKE_PX, PERFECT_RECOIL_PX))
        self.assertEqual([p[0] for p in fx.popups], ['PERFECT!'])

    def test_sparks_fly_out_fade_and_shrink(self):
        self.perfect_parry()
        sparks = self.game.fx.sparks
        start = [(p[0], p[1]) for p in sparks.items]
        self.step(6)
        moved = [math.hypot(p[0] - x, p[1] - y) for p, (x, y) in zip(sparks.items, start)]
        self.assertGreater(max(moved), 20)                     # some travel far...
        self.assertLess(min(moved), max(moved) / 2)            # ...others less
        self.assertGreater(len({p[6] for p in sparks.items}), 1)
        self.step(60)
        self.assertFalse(sparks.items)                         # all faded away

    # 10 --------------------------------------------------------------
    def test_guard_break_effects(self):
        game = self.game
        game.combat.posture.value = PLAYER_MAX_POSTURE - 1
        self.bullet()
        self.step(1)
        fx = game.fx
        self.assertAlmostEqual(game.hitstop, GUARD_BREAK_HITSTOP)
        self.assertEqual(game.kick[2], GUARD_BREAK_SHAKE_PX)
        self.assertEqual(fx.edge[2], parry_fx.EDGE_RED)
        self.assertIsNotNone(fx.vignette)
        self.assertGreaterEqual(max(r[4] for r in fx.rings), 64)   # a large shockwave
        self.assertTrue(all(p[9] is parry_fx.EMBER for p in fx.sparks.items))
        self.assertIn('guard_break', game.sounds.requests)
        self.assertNotEqual(game.player.knockback, 0)          # staggered backward
        self.assertEqual(game.miner.animation(game.player)[0], 'recoil')

    # 11 --------------------------------------------------------------
    def test_camera_returns_to_rest_after_a_recoiling_shake(self):
        game = self.game
        for _ in range(120):
            game.follow_camera(STEP)
        rest = game.render_camera
        # (The view is clamped at the world's left edge here, so recoil rightward.)
        game.camera_kick(PERFECT_SHAKE_TIME, PERFECT_SHAKE_PX, 1, PERFECT_RECOIL_PX)
        offsets = []
        for _ in range(frames_for(PERFECT_SHAKE_TIME) + 10):
            game.follow_camera(STEP)
            offsets.append(game.render_camera[0] - rest[0])
        limit = PERFECT_SHAKE_PX + PERFECT_RECOIL_PX
        self.assertTrue(all(abs(x) <= limit for x in offsets))
        self.assertGreater(max(offsets), 2)                    # it recoiled along the attack
        self.assertEqual(offsets[-10:], [0] * 10)
        self.assertEqual(game.render_camera, rest)

    # 12 --------------------------------------------------------------
    def test_hitstop_never_blocks_and_effects_keep_moving(self):
        game = self.game
        original_sleep = time.sleep
        time.sleep = lambda *_: self.fail('the game loop must not sleep')
        try:
            self.perfect_parry()
            self.assertGreater(game.hitstop, 0)
            before = [(p[0], p[1]) for p in game.fx.sparks.items]
            start = time.perf_counter()
            self.step(1, draw=True)
            self.assertLess(time.perf_counter() - start, 0.05)    # returns at once
            after = [(p[0], p[1]) for p in game.fx.sparks.items]
            self.assertNotEqual(before, after)                    # VFX stay responsive
            self.step(frames_for(PERFECT_PARRY_HITSTOP) + 1)
            self.assertEqual(game.hitstop, 0)                     # and it ends
        finally:
            time.sleep = original_sleep
        x = game.player.pos.x
        self.step(10, horizontal=1)
        self.assertGreater(game.player.pos.x, x)                  # play goes on

    # 13, 14 ----------------------------------------------------------
    def test_pause_freezes_effects_and_the_bar(self):
        game, ui = self.game, self.ui
        self.perfect_parry()
        self.step(3)
        ui.screen = 'paused'
        hud = ui.posture
        snapshot = (hud.visibility, hud.hold, hud.time, len(game.fx.sparks.items),
                    game.hitstop, game.fx.edge and game.fx.edge[0])
        for _ in range(120):
            ui.update(STEP, game)
            game.draw(self.screen)
            ui.draw(self.screen, game, (0, 0))
        self.assertEqual((hud.visibility, hud.hold, hud.time, len(game.fx.sparks.items),
                          game.hitstop, game.fx.edge and game.fx.edge[0]), snapshot)

    def test_restart_resets_effects_and_the_bar(self):
        self.perfect_parry()
        self.step(5)
        fresh = Game(self.art)
        self.ui.start(fresh)
        fx = fresh.fx
        self.assertEqual((fx.flashes, fx.slashes, fx.rings, fx.sparks.items), ([], [], [], []))
        self.assertIsNone(fx.edge)
        self.assertIsNone(fresh.kick)
        hud = self.ui.posture
        self.assertEqual((hud.visibility, hud.hold, hud.shown, hud.shards), (0.0, 0.0, 0.0, []))

    # 15 --------------------------------------------------------------
    def test_liquids_keep_their_step_through_hitstops(self):
        game = self.game
        steps = []
        original = game.liquids.step
        game.liquids.step = lambda dt: (steps.append(dt), original(dt))
        for _ in range(3):                                     # three parries in ~3 s
            self.perfect_parry()
            self.step(frames_for(CYCLE) + 2)
        seconds = 3 * (frames_for(CYCLE) + 3) * STEP
        self.assertAlmostEqual(len(steps), seconds * FLUID_HZ, delta=2)
        self.assertTrue(all(dt == 1 / FLUID_HZ for dt in steps))


class AudioTests(CinematicCase):
    # 6 ---------------------------------------------------------------
    def test_parries_play_metallic_clashes_and_alternate(self):
        game = self.game
        played = []
        for _ in range(4):
            game.sounds.reset_limits()
            game.sounds.last_variant.pop('parry_clash', None)
            self.normal_parry()
            if game.sounds.enabled:
                played.append(game.sounds.played[-1])
            self.step(frames_for(CYCLE) + 2)
        self.assertEqual(list(game.sounds.requests).count('parry_clash'), 4)
        if game.sounds.enabled:
            self.assertTrue(all(event == 'parry_clash' for event, _, _ in played))
        self.perfect_parry()
        self.assertEqual(game.sounds.requests[-1], 'parry_perfect')

    def test_clash_files_are_bright_and_failed_hits_dull(self):
        def brightness(name):
            with wave.open(str(SFX_DIR / f'{name}.wav')) as file:
                channels = file.getnchannels()
                data = array('h', file.readframes(int(file.getframerate() * 0.12)))[::channels]
            energy = sum(v * v for v in data)
            change = sum((b - a) ** 2 for a, b in zip(data, data[1:]))
            return change / energy        # high for bright, metallic sounds
        for name in ('parry_clash_01', 'parry_clash_02', 'parry_clash_03', 'parry_perfect'):
            self.assertGreater(brightness(name), 3 * brightness('parry_failed'), name)
        with wave.open(str(SFX_DIR / 'parry_clash_01.wav')) as file:
            self.assertEqual(file.getnchannels(), 2)          # wide, layered resonance

    # 7 ---------------------------------------------------------------
    def test_sounds_starting_together_cannot_clip(self):
        bank = SoundBank()
        if not bank.enabled:
            self.skipTest('no mixer')
        bank.preload()
        started = []
        for event in EVENTS:                                  # everything at once
            index = bank.play(event)
            if index is not None:
                started.append((bank.variants[event][index], bank.played[-1][2]))
        self.assertLessEqual(sum(level for _, level in bank.onsets), SFX_HEADROOM + 1e-6)
        # Mix what actually started, transients aligned, as the mixer would.
        rate, size, channels = bank.format
        length = int(rate * 0.05) * channels
        mix = [0.0] * length
        for sound, channel_volume in started:
            raw = array('h')
            raw.frombytes(sound.get_raw())
            gain = sound.get_volume() * channel_volume / 32768
            for n in range(min(length, len(raw))):
                mix[n] += raw[n] * gain
        self.assertLessEqual(max(abs(v) for v in mix), 1.0)

    def test_repeated_parries_stay_within_the_budget(self):
        game = self.game
        if not game.sounds.enabled:
            self.skipTest('no mixer')
        game.sounds.reset_limits()
        for _ in range(5):
            self.perfect_parry()
            self.step(frames_for(CYCLE) + 2)
        volumes = [v for event, _, v in game.sounds.played if event == 'parry_perfect']
        self.assertTrue(volumes)
        self.assertTrue(all(v <= game.sounds.volume + 1e-9 for v in volumes))


class PerformanceTests(CinematicCase):
    # 16 --------------------------------------------------------------
    def test_heavy_combat_frames_stay_near_60_fps(self):
        game = self.game
        walker = self.walker(game.player.rect.right + 100)
        walker.chase_timer = 5.0
        costs = []
        for n in range(240):
            if n % 60 == 0:
                game.press_e()
                self.bullet()
            if n == 150:
                game.combat.posture.value = PLAYER_MAX_POSTURE - 1
                game.hurt_timer = 0
                self.bullet(side=-1)
            start = time.perf_counter()
            self.step(1, draw=True)
            costs.append((time.perf_counter() - start) * 1000)
        costs.sort()
        mean = sum(costs) / len(costs)
        p95 = costs[int(len(costs) * 0.95)]
        self.assertLess(mean, 1000 / 60, f'mean {mean:.2f} ms')
        self.assertLess(p95, 1000 / 60 * 1.5, f'p95 {p95:.2f} ms')


if __name__ == '__main__':
    unittest.main()
