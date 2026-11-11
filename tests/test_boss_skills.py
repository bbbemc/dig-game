"""The Colossus's skills: shockwave, leap slam, phase 2, and the opening pause."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (BOSS_ARENA_HP, BOSS_ENRAGE_HP, BOSS_ENRAGE_SPEED, BOSS_FIGHT_GRACE,
                    BOSS_QUAKE_KITE, BOSS_SPEED, BOSS_WAVE_DAMAGE, CELL, MACRO,
                    SCREEN_H, SCREEN_W)
from level import DIRT
from levels.boss_arena import FLOOR, PLATFORMS
from main import Game
from tiles import TileArt


class BossSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def setUp(self):
        self.game = Game(self.art, stage=5, bonus_room=True)
        self.boss, self.skills = self.game.boss, self.game.boss_skills
        self.game.start_boss_fight()

    def place(self, x, row=FLOOR - 1):
        player = self.game.player
        player.pos.update(x, row * MACRO)
        player._sync_rect()
        player.drop_to_ground()

    def run_for(self, seconds, keep_alive=True, **keys):
        for _ in range(round(seconds * 60)):
            if keep_alive:
                self.game.hp = max(self.game.hp, 10 ** 5)
            self.game.update(1 / 60, **keys)

    def dirt_in(self, platform):
        left, right, row, _ = platform
        world = self.game.world
        return sum(world.foreground[world.index(x, y)] == DIRT
                   for x in range(left * 5, (right + 1) * 5) for y in range(row * 5, row * 5 + 5))

    def test_the_arena_boss_is_tougher_and_quicker(self):
        self.assertEqual(self.boss.max_hp, BOSS_ARENA_HP)
        self.assertGreater(self.boss.max_hp, 3)
        self.assertGreater(BOSS_SPEED, 62.0)
        self.assertEqual(self.boss.speed, BOSS_SPEED)

    def test_the_boss_holds_still_while_the_miner_gets_ready(self):
        self.place(self.boss.rect.left - 120)
        x = self.boss.rect.x
        self.run_for(BOSS_FIGHT_GRACE - 0.3)
        self.assertEqual(self.boss.rect.x, x)
        self.assertIsNone(getattr(self.boss, 'melee_state', None))
        self.run_for(1.5)
        self.assertNotEqual(self.boss.rect.x, x)       # then it comes for the miner

    def test_keeping_out_of_reach_brings_a_shockwave(self):
        self.skills.grace = 0
        seen = set()
        for _ in range(round((BOSS_QUAKE_KITE + 2.5) * 60)):
            self.game.player.pos.x = self.boss.rect.left - 300   # stay out of reach
            self.game.player._sync_rect()
            self.game.hp = max(self.game.hp, 10 ** 5)
            self.game.update(1 / 60)
            seen.add(self.skills.state)
            if self.skills.waves:
                break
        self.assertIn('quake_windup', seen)
        self.assertEqual(sorted(w.direction for w in self.skills.waves), [-1, 1])

    def test_a_wave_hurts_a_miner_who_stands_and_cannot_be_parried(self):
        self.skills.grace = 0
        self.place(self.boss.rect.left - 250)
        self.skills._slam()
        self.skills.state = None
        hp = self.game.hp
        for _ in range(80):
            self.game.press_e() if self.game.parry.can_parry() else None
            self.game.update(1 / 60)
        self.assertEqual(self.game.hp, hp - BOSS_WAVE_DAMAGE)

    def test_jumping_clears_a_wave(self):
        self.skills.grace = 0
        self.place(self.boss.rect.left - 250)
        self.skills._slam()
        self.skills.state = None
        wave = next(w for w in self.skills.waves if w.direction < 0)
        hp, jumped = self.game.hp, False
        warned = False
        for _ in range(120):
            gap = wave.rect.left - self.game.player.rect.right
            warned |= any(getattr(s, 'unparryable', False)
                          for _, _, s in self.game.incoming_threats())
            jump = not jumped and 0 < gap < 45
            jumped |= jump
            self.game.update(1 / 60, jump=jump)
            if wave.dead or wave.x < self.game.player.rect.left - 60:
                break
        self.assertTrue(warned)
        self.assertEqual(self.game.hp, hp)
        self.assertFalse(wave.hit)

    def test_a_wave_stops_at_a_wall_and_at_a_pit(self):
        from boss_skills import Shockwave, WAVE_LIFE
        floor = FLOOR * MACRO
        wall = Shockwave(4 * MACRO, floor, -1, 320.0)        # 2 macros from the left wall
        self.skills.waves = [wall]
        for _ in range(60):
            self.skills._update_waves(1 / 60)
        self.assertTrue(wall.dead)
        self.assertLess(wall.age, WAVE_LIFE)
        world = self.game.world
        for x in range(18 * 5, 21 * 5):                       # dig out a cracked floor patch
            for y in range(FLOOR * 5, FLOOR * 5 + 5):
                if world.foreground[world.index(x, y)] == DIRT:
                    world.set_terrain(world.index(x, y), 0)
        pit = Shockwave(16 * MACRO, floor, 1, 320.0)
        self.skills.waves = [pit]
        for _ in range(60):
            self.skills._update_waves(1 / 60)
        self.assertTrue(pit.dead)
        self.assertLess(pit.x, 21 * MACRO)

    def test_camping_on_a_dirt_ledge_brings_a_leap_that_caves_it_in(self):
        self.skills.grace = 0
        ledge = PLATFORMS[0]
        self.place((ledge[0] + 2) * MACRO, ledge[2] - 1)
        before = self.dirt_in(ledge)
        states = []
        for _ in range(60 * 7):
            self.game.hp = max(self.game.hp, 10 ** 5)
            self.game.update(1 / 60)
            if self.skills.state and (not states or states[-1] != self.skills.state):
                states.append(self.skills.state)
        self.assertEqual(states[:3], ['leap_crouch', 'leap_air', 'leap_land'])
        self.assertGreater(before, 0)
        self.assertEqual(self.dirt_in(ledge), 0)
        self.assertEqual(self.boss.rect.bottom, FLOOR * MACRO)   # it hopped back down

    def test_a_leap_onto_the_stone_altar_hops_back_down(self):
        self.skills.grace = 0
        altar = PLATFORMS[1]
        self.place((altar[0] + 3) * MACRO, altar[2] - 1)
        self.run_for(8.0)
        self.assertEqual(self.dirt_in(altar), 0)                   # stone: nothing caved in
        self.assertTrue(self.game.world.solid(altar[0] * 5 + 2, altar[2] * 5 + 2))
        self.assertEqual(self.boss.rect.bottom, FLOOR * MACRO)

    def test_the_leap_lands_on_the_miner_who_stays(self):
        self.skills.grace = 0
        ledge = PLATFORMS[0]
        self.place((ledge[0] + 2) * MACRO, ledge[2] - 1)
        self.skills.ledge_time = 99
        hurt = False
        for _ in range(60 * 3):
            before = self.game.hp
            self.game.update(1 / 60)
            hurt |= self.game.hp < before
            if self.skills.state == 'leap_land':
                break
        self.assertTrue(hurt)

    def test_a_stagger_cancels_a_wind_up(self):
        self.skills.grace = 0
        self.skills._begin('quake_windup', 0.85)
        self.boss.broken, self.boss.stun_timer = True, 2.0
        self.skills.update(1 / 60)
        self.assertIsNone(self.skills.state)
        self.assertIsNone(self.boss.skill_pose)

    def test_phase_two_is_faster_and_swings_twice(self):
        self.skills.grace = 0
        self.boss.hp = BOSS_ENRAGE_HP
        self.game.update(1 / 60)
        self.assertTrue(self.skills.enraged)
        self.assertIn('ENRAGED!', [p[0] for p in self.game.fx.popups])
        self.assertAlmostEqual(self.boss.speed, BOSS_SPEED * BOSS_ENRAGE_SPEED)
        self.assertLess(self.skills.tempo, 1.0)
        self.place(self.boss.rect.left - 50)
        starts, prev = [], None
        for n in range(60 * 4):
            self.game.hp = max(self.game.hp, 10 ** 5)
            self.game.combat.posture.value = 0
            self.game.update(1 / 60)
            state = self.boss.melee_state
            if state == 'windup' and prev != 'windup':
                starts.append(n / 60)
            prev = state
        self.assertGreaterEqual(len(starts), 3)
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        self.assertLess(gaps[0], gaps[1])       # the combo's second swing comes quick

    def test_the_boss_cannot_hurt_by_touch_in_mid_air(self):
        self.skills.grace = 0
        self.skills._begin('leap_air', 0.8)
        self.skills.leap = (pygame.Vector2(self.boss.pos), pygame.Vector2(self.boss.pos))
        self.game.player.pos.update(self.boss.rect.centerx, self.boss.rect.centery)
        self.game.player._sync_rect()
        hp = self.game.hp
        self.game.update(1 / 60)
        self.assertEqual(self.game.hp, hp)


if __name__ == '__main__':
    unittest.main()
