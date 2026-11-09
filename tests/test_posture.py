"""Posture, guard breaks, enemy posture, deathblows, combat audio and feel."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest
import wave
from array import array

import pygame

from audio import EVENTS, SFX_DIR, SoundBank
from combat import (DEAD, GUARD_BROKEN, NORMAL, PARRY_ACTIVE, PARRY_RECOVERY, STUNNED,
                    PlayerCombat, Posture, give_posture)
from config import (CELL, MACRO, SCREEN_W, SCREEN_H, PROJECTILE_DAMAGE, PARRY_ACTIVE_TIME,
                    PARRY_RECOVERY_TIME, PARRY_COOLDOWN, PARRY_HITSTOP, PARRY_SHAKE_TIME,
                    PARRY_SHAKE_PX, PLAYER_MAX_POSTURE, PLAYER_STUN_DURATION,
                    GUARD_BREAK_TIME, GUARD_BREAK_HITSTOP, POSTURE_RECOVERY_DELAY,
                    POSTURE_RECOVERY_INTERVAL, NORMAL_ENEMY_MAX_POSTURE, BOSS_MAX_POSTURE,
                    ENEMY_STUN_DURATION, BOSS_STAGGER_DURATION, WALKER_SIZE, WALKER_SPEED,
                    WALKER_CONTACT_DAMAGE, FLUID_HZ)
from level import DIRT
from main import Game, Projectile
from physics import Actor
from tiles import TileArt
from ui import GameUI

STEP = 1 / 60
CYCLE = PARRY_ACTIVE_TIME + PARRY_RECOVERY_TIME + PARRY_COOLDOWN


def frames_for(seconds):
    return round(seconds / STEP)


class PostureUnitTests(unittest.TestCase):
    def test_recovery_waits_then_returns_a_point_per_interval(self):
        posture = Posture(3, POSTURE_RECOVERY_DELAY, POSTURE_RECOVERY_INTERVAL)
        posture.add()
        posture.add()
        t, seen = 0.0, []
        while posture.value and t < 20:
            posture.update(STEP)
            t += STEP
            if not seen or seen[-1][1] != posture.value:
                seen.append((t, posture.value))
        first = POSTURE_RECOVERY_DELAY + POSTURE_RECOVERY_INTERVAL
        self.assertAlmostEqual(seen[1][0], first, delta=STEP + 1e-9)            # 2 -> 1
        self.assertAlmostEqual(seen[2][0], first + POSTURE_RECOVERY_INTERVAL,   # 1 -> 0
                               delta=STEP + 1e-9)
        self.assertEqual([value for _, value in seen], [2, 1, 0])

    def test_a_new_point_restarts_the_delay(self):
        posture = Posture(3, POSTURE_RECOVERY_DELAY, POSTURE_RECOVERY_INTERVAL)
        posture.add()
        for _ in range(frames_for(POSTURE_RECOVERY_DELAY + 1)):
            posture.update(STEP)
        posture.add()                                   # 2, calm back to 0
        for _ in range(frames_for(POSTURE_RECOVERY_DELAY + 1)):
            posture.update(STEP)
        self.assertEqual(posture.value, 2)

    def test_states_are_deterministic_and_never_stick(self):
        combat = PlayerCombat()
        self.assertEqual(combat.state, NORMAL)
        combat.start_parry()
        self.assertEqual(combat.state, PARRY_ACTIVE)
        combat.update(PARRY_ACTIVE_TIME + 0.01)
        self.assertEqual(combat.state, PARRY_RECOVERY)
        combat.update(PARRY_RECOVERY_TIME)
        self.assertEqual(combat.state, NORMAL)          # cooldown is spent in NORMAL
        self.assertFalse(combat.start_parry())
        for _ in range(PLAYER_MAX_POSTURE - 1):
            self.assertEqual(combat.take_hit(), 'posture')
        combat.parry.state = 'active'                   # a break interrupts the parry
        self.assertEqual(combat.take_hit(), 'guard_break')
        self.assertEqual(combat.parry.state, 'ready')
        seen, t, recoil_end = [combat.state], 0.0, None
        for _ in range(frames_for(PLAYER_STUN_DURATION) + 2):
            combat.update(STEP)
            t += STEP
            if combat.state != seen[-1]:
                seen.append(combat.state)
                recoil_end = recoil_end or t
        self.assertEqual(seen, [GUARD_BROKEN, STUNNED, NORMAL])
        self.assertAlmostEqual(recoil_end, GUARD_BREAK_TIME, delta=STEP + 1e-9)
        self.assertEqual(combat.posture.value, 0)
        combat.die()
        self.assertEqual(combat.state, DEAD)
        self.assertFalse(combat.start_parry())


class CombatTestCase(unittest.TestCase):
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
        game.sounds.reset_limits()
        game.sounds.requests.clear()
        self.game = game

    def frames(self, n, **inputs):
        for _ in range(n):
            self.game.update(STEP, **inputs)

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

    def shooter(self, x):
        enemy = Actor(self.game.world, x, self.game.player.pos.y, size=24, speed=32)
        enemy.drop_to_ground()
        enemy.shoots_projectiles, enemy.shot_cooldown = True, 10.0
        enemy.contact_damage = 20
        give_posture(enemy)
        self.game.monsters.append(enemy)
        return enemy

    def bullet(self, side=1, owner=None):
        rect = self.game.player.rect
        x = rect.right + 6 if side > 0 else rect.left - 6
        shot = Projectile((x, rect.centery), (-240 * side, 0), owner)
        self.game.projectiles.append(shot)
        return shot

    def parry_bullet(self, owner):
        """One perfect parry of a bullet, then wait until the parry is ready."""
        self.assertTrue(self.game.press_e())
        self.bullet(owner=owner)
        self.frames(2)
        self.frames(frames_for(CYCLE + PARRY_HITSTOP) + 2)

    def break_guard(self):
        """Fill the player's posture with real enemy bullets (HP topped up)."""
        game = self.game
        for _ in range(PLAYER_MAX_POSTURE):
            game.hp = 100
            game.hurt_timer = 0
            self.bullet()
            self.frames(2)
        self.assertEqual(game.combat_state, GUARD_BROKEN)


class PlayerPostureTests(CombatTestCase):
    # 1, 2 ------------------------------------------------------------
    def test_press_e_activates_the_parry(self):
        self.assertTrue(self.game.press_e())
        self.assertEqual(self.game.combat_state, PARRY_ACTIVE)
        self.assertIn('parry_whoosh', self.game.sounds.requests)

    def test_holding_e_does_not_spam(self):
        self.assertEqual(pygame.key.get_repeat(), (0, 0))   # held key: one KEYDOWN
        presses = 0
        for _ in range(frames_for(CYCLE) - 2):
            presses += self.game.press_e()
            self.frames(1)
        self.assertEqual(presses, 1)

    # 3, 5, 6 ---------------------------------------------------------
    def test_perfect_parry_prevents_damage_and_posture(self):
        self.game.press_e()
        self.bullet()
        self.frames(3)
        self.assertEqual((self.game.hp, self.game.combat.posture.value), (100, 0))

    def test_failed_parry_hit_adds_one_posture(self):
        game = self.game
        game.press_e()
        self.frames(frames_for(PARRY_ACTIVE_TIME) + 2)      # too early: window closed
        self.bullet()
        self.frames(3)
        self.assertEqual(game.hp, 100 - PROJECTILE_DAMAGE)
        self.assertEqual(game.combat.posture.value, 1)
        self.assertIn('parry_failed', game.sounds.requests)

    def test_one_attack_counts_once(self):
        game = self.game
        walker = self.walker(game.player.rect.right - 6)
        walker.chase_left = walker.chase_right = walker.pos.x   # it stays in contact
        self.frames(frames_for(0.5))                             # within one hurt grace
        self.assertEqual((game.hp, game.combat.posture.value),
                         (100 - WALKER_CONTACT_DAMAGE, 1))
        self.bullet(side=-1)                                    # lands during the grace
        self.frames(3)
        self.assertEqual(game.combat.posture.value, 1)

    def test_wrong_press_or_environment_adds_no_posture(self):
        game = self.game
        game.press_e()
        self.frames(frames_for(CYCLE) + 4)                       # a whiff: nobody attacked
        self.assertEqual(game.combat.posture.value, 0)
        game.bombs.explode(pygame.Vector2(game.player.rect.center))   # blast damage
        self.assertLess(game.hp, 100)
        game.oxygen, game.oxygen_damage_timer = 0, 0
        game.hp = 100
        game.update_oxygen(0)                                  # drowning path untouched
        self.assertEqual(game.combat.posture.value, 0)
        self.assertNotIn('parry_failed', game.sounds.requests)

    def test_lava_death_is_not_a_guard_break(self):
        game = self.game
        from level import LAVA
        lava = next(i for i, kind in game.liquids.types.items()
                    if kind == LAVA and game.liquids.mass[i] > 0.9)
        x, y = game.world.coords(lava)
        game.player.pos.update(x * CELL - 8, y * CELL - 20)
        game.player._sync_rect()
        game.update(0)
        game.update(STEP)
        self.assertEqual((game.state, game.combat_state, game.combat.posture.value),
                         ('lose', DEAD, 0))

    # 7, 8 ------------------------------------------------------------
    def test_three_failed_defences_break_the_guard(self):
        game = self.game
        self.break_guard()
        self.assertEqual(game.combat.posture.value, PLAYER_MAX_POSTURE)
        self.assertIn('guard_break', game.sounds.requests)
        self.assertEqual([p[0] for p in game.fx.popups][-1], 'POSTURE BROKEN!')
        self.assertTrue(game.fx.rings)                           # shockwave
        self.assertGreater(game.miner.break_flash, 0)            # red/orange flash
        self.assertEqual(game.miner.animation(game.player)[0], 'recoil')

    def test_guard_break_stuns_for_its_duration(self):
        game = self.game
        self.break_guard()
        t = 0.0
        while not game.combat.can_act() and t < 5:
            game.update(STEP)
            t += STEP
        # Stun time is combat time, so the guard-break hitstop comes on top.
        self.assertAlmostEqual(t, PLAYER_STUN_DURATION + GUARD_BREAK_HITSTOP, delta=2 * STEP)

    # 9, 10, 11 -------------------------------------------------------
    def test_stunned_player_cannot_act(self):
        game = self.game
        self.break_guard()
        self.frames(frames_for(GUARD_BREAK_HITSTOP) + 1)
        self.assertNotEqual(game.player.knockback, 0)            # staggered backward
        while game.player.knockback:
            self.frames(1)                                      # the stagger settles
        x, y = game.player.pos.x, game.player.pos.y
        self.frames(20, horizontal=1, jump=True, vertical=-1)
        self.assertEqual((game.player.pos.x, game.player.pos.y), (x, y))   # no walk, no jump
        self.assertFalse(game.press_e())                                   # no parry
        self.assertFalse(game.can_act())                                   # no bombs (main loop)
        cx, cy = game.player.rect.centerx // CELL, game.player.rect.bottom // CELL + 2
        index = game.world.index(cx, cy)
        self.assertEqual(game.world.foreground[index], DIRT)
        game.excavate((cx, cy))
        self.assertEqual(game.world.foreground[index], DIRT)               # no digging
        self.assertEqual(game.combat_state, STUNNED)
        self.assertEqual(game.miner.animation(game.player)[0], 'stagger')

    def test_gravity_and_collision_continue_while_stunned(self):
        game = self.game
        game.player.pos.y -= 3 * MACRO                # high in the open air
        game.player._sync_rect()
        game.player.velocity.y = 0
        floor = None
        game.combat.posture.value = PLAYER_MAX_POSTURE - 1
        self.bullet()
        self.frames(2)
        self.assertFalse(game.combat.can_act())
        start = game.player.pos.y
        for _ in range(frames_for(PLAYER_STUN_DURATION - 0.1)):
            game.update(STEP, horizontal=1)
            if game.player.grounded and floor is None:
                floor = game.player.pos.y
        self.assertGreater(game.player.pos.y, start + 2 * MACRO)  # it fell...
        self.assertTrue(game.player.grounded)                    # ...and landed on the floor
        self.assertFalse(game.player.overlaps_terrain())
        self.assertFalse(game.combat.can_act())

    def test_player_returns_to_normal_after_the_stun(self):
        game = self.game
        self.break_guard()
        self.frames(frames_for(PLAYER_STUN_DURATION + GUARD_BREAK_HITSTOP) + 2)
        self.assertEqual(game.combat_state, NORMAL)
        self.assertEqual(game.combat.posture.value, 0)
        self.assertIsNone(game.miner.pose)
        self.assertIn('stun_recover', game.sounds.requests)
        x = game.player.pos.x
        self.frames(10, horizontal=1)
        self.assertGreater(game.player.pos.x, x + 10)
        self.assertTrue(game.press_e())

    # 12 --------------------------------------------------------------
    def test_posture_recovers_in_game_but_not_while_stunned(self):
        game = self.game
        game.combat.posture.value = 2
        self.frames(frames_for(POSTURE_RECOVERY_DELAY + POSTURE_RECOVERY_INTERVAL) - 3)
        self.assertEqual(game.combat.posture.value, 2)
        self.frames(6)
        self.assertEqual(game.combat.posture.value, 1)
        self.frames(frames_for(POSTURE_RECOVERY_INTERVAL) + 2)
        self.assertEqual(game.combat.posture.value, 0)
        self.break_guard()                            # full posture during the stun
        for _ in range(frames_for(PLAYER_STUN_DURATION - 0.1)):
            game.update(STEP)
            self.assertEqual(game.combat.posture.value, PLAYER_MAX_POSTURE)

    # 20, 21 ----------------------------------------------------------
    def test_pause_freezes_combat_timers(self):
        game, ui = self.game, GameUI()
        ui.start(game)
        game.combat.posture.value = 2
        self.frames(30)
        self.break_guard()
        ui.screen = 'paused'
        snapshot = (game.combat.stun, game.combat.posture.value, game.combat.posture.calm,
                    game.hitstop, game.parry.timer)
        for _ in range(240):         # paused frames: the main loop only draws
            ui.update(STEP, game)
            game.draw(self.screen)
            ui.draw(self.screen, game, (0, 0))
        self.assertEqual((game.combat.stun, game.combat.posture.value, game.combat.posture.calm,
                          game.hitstop, game.parry.timer), snapshot)

    def test_restart_resets_combat(self):
        self.break_guard()
        fresh = Game(self.art)
        self.assertEqual((fresh.combat_state, fresh.combat.posture.value, fresh.combat.stun),
                         (NORMAL, 0, 0.0))
        self.assertEqual((fresh.hitstop, fresh.kick, fresh.fx.popups), (0.0, None, []))
        self.assertIsNone(fresh.miner.pose)
        self.assertTrue(all(enemy.posture.value == 0 and not enemy.broken
                            for enemy in fresh.monsters))

    def test_death_overrides_the_stun(self):
        game = self.game
        self.break_guard()
        game.hurt_timer = 0
        game.hp = 10
        self.bullet()
        self.frames(frames_for(GUARD_BREAK_HITSTOP) + 3)
        self.assertEqual((game.state, game.combat_state), ('lose', DEAD))
        self.assertIsNone(game.miner.pose)


class EnemyPostureTests(CombatTestCase):
    # 4, 13, 14 -------------------------------------------------------
    def test_perfect_parry_adds_enemy_posture(self):
        shooter = self.shooter(self.game.player.pos.x + 200)
        self.parry_bullet(shooter)
        self.assertEqual(shooter.posture.value, 1)
        self.assertEqual(self.game.combat.posture.value, 0)

    def test_enemy_posture_fills_and_breaks(self):
        game = self.game
        shooter = self.shooter(game.player.pos.x + 200)
        for _ in range(NORMAL_ENEMY_MAX_POSTURE - 1):
            self.parry_bullet(shooter)
        self.assertFalse(shooter.broken)
        game.press_e()
        self.bullet(owner=shooter)
        self.frames(1)
        self.assertEqual(shooter.posture.value, NORMAL_ENEMY_MAX_POSTURE)
        self.assertTrue(shooter.broken)
        self.assertAlmostEqual(shooter.stun_timer, ENEMY_STUN_DURATION)
        self.assertIn('enemy_guard_break', game.sounds.requests)
        self.assertIn('BREAK!', [p[0] for p in game.fx.popups])
        shooter.shot_cooldown = 0                      # its attack stays cancelled
        game.update_enemy_combat(STEP)
        self.assertFalse(game.projectiles)
        self.frames(frames_for(ENEMY_STUN_DURATION + GUARD_BREAK_HITSTOP) + 2)
        self.assertFalse(shooter.broken)
        self.assertEqual(shooter.posture.value, 0)

    def test_broken_walker_is_open_to_a_deathblow(self):
        game = self.game
        walker = self.walker(game.player.rect.right - 6)
        walker.posture.value = NORMAL_ENEMY_MAX_POSTURE - 1
        game.press_e()
        self.frames(1)
        self.assertTrue(walker.broken)
        self.frames(frames_for(GUARD_BREAK_HITSTOP) + 20)
        self.assertEqual(game.hp, 100)                  # helpless: no contact damage
        self.assertIs(game.deathblow_target(), walker)  # it stayed within reach
        self.assertTrue(game.press_e())
        self.assertNotIn(walker, game.monsters)
        self.assertIn('deathblow', game.sounds.requests)

    def test_enemy_posture_recovers(self):
        walker = self.walker(self.game.player.pos.x - 300)
        walker.posture.add()
        self.frames(frames_for(POSTURE_RECOVERY_DELAY + POSTURE_RECOVERY_INTERVAL) + 3)
        self.assertEqual(walker.posture.value, 0)

    def test_boss_has_a_larger_meter_and_only_staggers(self):
        game = Game(self.art, stage=6, seed=3)
        boss = game.boss
        game.monsters = [boss]
        self.assertEqual(boss.posture.maximum, BOSS_MAX_POSTURE)
        boss.posture.value = BOSS_MAX_POSTURE - 1
        game.player.pos.update(boss.rect.left - game.player.size + 4, boss.pos.y + 32)
        game.player._sync_rect()
        game.miner.facing_right = True
        game.press_e()
        game.update(STEP)
        self.assertTrue(boss.broken)
        self.assertAlmostEqual(boss.stun_timer, BOSS_STAGGER_DURATION)
        self.assertEqual(boss.hp, boss.max_hp)           # posture never kills the boss
        self.assertIsNone(game.deathblow_target())       # and there is no deathblow
        game.update(GUARD_BREAK_HITSTOP + STEP)
        game.press_e()
        self.assertIn(boss, game.monsters)
        # Existing boss mechanics still apply while it staggers: bombs hurt it.
        game.bombs.explode(pygame.Vector2(boss.rect.center))
        self.assertEqual(boss.hp, boss.max_hp - 1)
        self.assertIn(boss, game.monsters)


class FeelTests(CombatTestCase):
    # 15, 16 ----------------------------------------------------------
    def test_perfect_parry_plays_a_metallic_clash(self):
        game = self.game
        game.press_e()
        self.bullet()
        self.frames(2)
        self.assertIn('parry_perfect', game.sounds.requests)
        if game.sounds.enabled:
            event, index, volume = game.sounds.played[-1]
            self.assertEqual(event, 'parry_perfect')
            self.assertEqual(len(game.sounds._event('parry_clash')), 9)   # 3 takes x 3 pitches

    def test_guard_break_sound_is_distinct(self):
        self.break_guard()
        requests = list(self.game.sounds.requests)
        self.assertIn('guard_break', requests)
        self.assertNotIn('parry_clash', requests)
        files = {name: (SFX_DIR / f'{name}.wav').read_bytes()
                 for name in ('guard_break', 'parry_clash_01', 'enemy_guard_break')}
        self.assertEqual(len(set(files.values())), 3)

    # 17 --------------------------------------------------------------
    def test_sparks_burst_from_the_impact_point(self):
        game = self.game
        game.press_e()
        shot = self.bullet()
        start = pygame.Vector2(shot.pos)
        game.update(STEP)
        sparks = game.fx.sparks.items
        self.assertTrue(25 <= len(sparks) <= 45)
        for x, y, *_ in sparks:                    # spawned there, one frame of travel
            self.assertLess(pygame.Vector2(x, y).distance_to(start), 16)
        self.assertGreater(len({p[6] for p in sparks}), 1)        # mixed sizes
        self.assertTrue(game.fx.flashes and game.fx.slashes)

    # 18 --------------------------------------------------------------
    def test_hitstop_freezes_combat_but_not_liquids(self):
        game = self.game
        walker = self.walker(game.player.pos.x + 150)
        walker.velocity.y = -150
        game.press_e()
        self.bullet()
        self.frames(1)
        self.assertGreater(game.hitstop, 0)
        steps = []
        original = game.liquids.step
        game.liquids.step = lambda dt: (steps.append(dt), original(dt))
        frozen = (walker.pos.copy(), game.player.pos.copy(), game.parry.timer)
        self.frames(frames_for(PARRY_HITSTOP) - 1)
        self.assertEqual((walker.pos, game.player.pos, game.parry.timer), frozen)
        self.assertGreaterEqual(len(steps), 1)               # liquids kept their step
        self.assertTrue(all(dt == 1 / FLUID_HZ for dt in steps))
        self.frames(30)
        self.assertEqual(game.hitstop, 0)
        self.assertNotEqual(walker.pos, frozen[0])           # motion resumes
        self.assertTrue(walker.grounded)
        self.assertFalse(walker.overlaps_terrain())

    # 19 --------------------------------------------------------------
    def test_camera_kick_is_bounded_smooth_and_returns_to_rest(self):
        game = self.game
        for _ in range(120):
            game.follow_camera(STEP)                  # settle the view
        rest, view = game.render_camera, game.view.copy()
        game.camera_kick(PARRY_SHAKE_TIME, PARRY_SHAKE_PX, 1)
        game.camera_kick(PARRY_SHAKE_TIME, 1, -1)      # a weaker kick cannot override
        self.assertEqual(game.kick[2], PARRY_SHAKE_PX)
        offsets = []
        for _ in range(frames_for(PARRY_SHAKE_TIME) + 10):
            game.follow_camera(STEP)
            offsets.append((game.render_camera[0] - rest[0], game.render_camera[1] - rest[1]))
            self.assertEqual(game.view, view)          # the base view never moves
        self.assertTrue(any(offsets))
        self.assertTrue(all(abs(x) <= PARRY_SHAKE_PX and abs(y) <= PARRY_SHAKE_PX
                            for x, y in offsets))
        self.assertEqual(offsets[-10:], [(0, 0)] * 10)    # exactly at rest, no drift
        self.assertIsNone(game.kick)

    # 22 --------------------------------------------------------------
    def test_existing_mechanics_still_work_after_combat(self):
        game = self.game
        walker = self.walker(game.player.rect.right - 6)
        game.press_e()
        self.frames(frames_for(CYCLE) + 4)
        x = game.player.pos.x
        self.frames(10, horizontal=-1)
        self.assertLess(game.player.pos.x, x - 20)              # walking
        self.frames(1, jump=True)
        self.frames(4)
        self.assertLess(game.player.velocity.y, 0)              # jumping
        self.frames(60)
        self.assertTrue(game.player.grounded)                   # gravity and landing
        cx, cy = game.player.rect.centerx // CELL, game.player.rect.bottom // CELL + 2
        game.excavate((cx, cy))
        self.assertNotEqual(game.world.foreground[game.world.index(cx, cy)], DIRT)   # digging
        game.update_stage_progress()
        self.assertIn(walker, game.monsters)

    def test_effects_and_ui_draw_through_a_whole_fight(self):
        game, ui = self.game, GameUI()
        ui.start(game)
        walker = self.walker(game.player.rect.right - 6)
        walker.posture.value = NORMAL_ENEMY_MAX_POSTURE - 1
        game.press_e()
        for n in range(240):
            if n == 40:
                game.press_e()                                  # deathblow
            if n == 80:
                game.combat.posture.value = PLAYER_MAX_POSTURE - 1
                self.bullet()
            game.update(STEP)
            game.draw(self.screen)
            ui.draw(self.screen, game, (0, 0))
        self.assertNotIn(walker, game.monsters)


class AudioAssetTests(unittest.TestCase):
    def test_wav_assets_exist_and_do_not_clip(self):
        names = [name for files, _, _ in EVENTS.values() for name in files]
        self.assertEqual(len(names), 11)
        for name in names:
            path = SFX_DIR / f'{name}.wav'
            with self.subTest(name=name):
                self.assertTrue(path.exists())
                with wave.open(str(path)) as file:
                    self.assertIn(file.getnchannels(), (1, 2))
                    self.assertEqual(file.getsampwidth(), 2)
                    duration = file.getnframes() / file.getframerate()
                    samples = array('h', file.readframes(file.getnframes()))
                self.assertTrue(0.15 <= duration <= 1.5)
                peak = max(abs(v) for v in samples) / 32768
                self.assertTrue(0.5 < peak < 0.95)                 # loud, with headroom
                self.assertLess(abs(samples[-1]), 64)              # faded tail: no click

    def test_missing_files_fall_back_to_synthesis(self):
        bank = SoundBank(directory='/nonexistent/combat')
        if not bank.enabled:
            self.skipTest('no mixer')
        bank.preload()
        self.assertEqual(set(bank.sources.values()), {'synth'})
        self.assertIsNotNone(bank.play('guard_break'))

    def test_playback_is_limited(self):
        bank = SoundBank()
        if not bank.enabled:
            self.skipTest('no mixer')
        bank.preload()
        self.assertEqual(set(bank.sources.values()), {'file'})
        self.assertIsNotNone(bank.play('parry_clash'))
        self.assertIsNone(bank.play('parry_clash'))             # same instant: one only
        first = bank.played[-1][1]
        bank.reset_limits()
        bank.last_variant['parry_clash'] = first
        self.assertNotEqual(bank.play('parry_clash'), first)    # no back-to-back repeat
        for _ in range(4):
            bank.reset_limits()
            bank.play('parry_clash')
        busy = [c for c in bank.channels['parry_clash'] if c.get_busy()]
        self.assertLessEqual(len(busy), 2)

    def test_silent_bank_never_crashes(self):
        bank = SoundBank()
        bank.enabled = False
        self.assertIsNone(bank.play('parry_clash'))
        self.assertIsNone(bank.play('no_such_event'))


if __name__ == '__main__':
    unittest.main()
