"""Enemy potion drops, collection, healing and speed effects."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (CELL, HEAL_POTION_AMOUNT, MACRO, PLAYER_MAX_HP, SCREEN_H,
                    SCREEN_W, SPEED_POTION_DURATION, SPEED_POTION_MULTIPLIER,
                    POTION_COLLECT_DISTANCE, POTION_PICKUP_RANGE,
                    POTION_HOMING_SPEED, WATER_MOVE_SPEED)
from main import Game
from potions import Potion
from tiles import TileArt


class FixedRoll:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


class PotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.game = Game(self.art)

    def kill(self, enemy):
        self.game.monsters = [other for other in self.game.monsters
                              if other is not enemy]

    def test_projectile_enemy_drops_speed_potion_and_walker_drops_health(self):
        game = self.game
        game.potions.random = FixedRoll(0.49)
        shooter = next(enemy for enemy in game.monsters
                       if enemy.shoots_projectiles)
        self.kill(shooter)
        self.assertEqual([(p.kind, p.rect.center) for p in game.potions.drops],
                         [('speed', shooter.rect.center)])

        walker = next(enemy for enemy in game.monsters
                      if not enemy.shoots_projectiles)
        self.kill(walker)
        self.assertEqual([p.kind for p in game.potions.drops],
                         ['speed', 'health'])

    def test_drop_chance_is_fifty_percent(self):
        game = self.game
        game.potions.random = FixedRoll(0.5)
        self.assertFalse(game.potions.drop('speed', (0, 0)))
        game.potions.random = FixedRoll(0.499)
        self.assertTrue(game.potions.drop('health', (0, 0)))

    def test_speed_potion_increases_speed_and_expires_after_twenty_seconds(self):
        game = self.game
        game.potions.random = FixedRoll(0)
        game.potions.drop('speed', game.player.rect.center)
        game.update(0)
        self.assertEqual(game.player.speed_multiplier, SPEED_POTION_MULTIPLIER)
        self.assertEqual(game.potions.speed_timer, SPEED_POTION_DURATION)
        self.assertEqual(game.potions.drops, [])

        game.player.update(1 / 120, 1, swimming=True)
        self.assertAlmostEqual(game.player.velocity.x,
                               WATER_MOVE_SPEED * SPEED_POTION_MULTIPLIER)
        game.potions.update(SPEED_POTION_DURATION - 0.1)
        self.assertEqual(game.player.speed_multiplier, SPEED_POTION_MULTIPLIER)
        game.potions.update(0.1)
        self.assertEqual(game.player.speed_multiplier, 1.0)
        self.assertEqual(game.potions.speed_timer, 0)

    def test_health_potion_restores_fifty_hp_without_overhealing(self):
        game = self.game
        game.hp = 30
        game.potions.random = FixedRoll(0)
        game.potions.drop('health', game.player.rect.center)
        game.update(0)
        self.assertEqual(game.hp, 30 + HEAL_POTION_AMOUNT)
        self.assertEqual(game.potions.drops, [])

        game.hp = PLAYER_MAX_HP - 20
        game.potions.drop('health', game.player.rect.center)
        game.update(0)
        self.assertEqual(game.hp, PLAYER_MAX_HP)

    def test_health_potion_stays_when_player_is_already_at_full_health(self):
        game = self.game
        game.potions.random = FixedRoll(0)
        game.potions.drop('health', game.player.rect.center)
        game.update(0)
        self.assertEqual(game.hp, PLAYER_MAX_HP)
        self.assertEqual(len(game.potions.drops), 1)

    def test_potions_are_collected_within_quarter_screen_range(self):
        game = self.game
        game.hp = 40
        player_x, player_y = game.player.rect.center
        game.potions.drops.append(Potion(
            'health', (player_x + POTION_PICKUP_RANGE - 1, player_y)))
        game.potions.update(0)
        potion = game.potions.drops[0]
        self.assertTrue(potion.homing)
        self.assertEqual(game.hp, 40)
        for _ in range(60):
            game.potions.update(1 / 60)
            if not game.potions.drops:
                break
        self.assertEqual(game.hp, 40 + HEAL_POTION_AMOUNT)
        self.assertEqual(game.potions.drops, [])

    def test_potions_outside_quarter_screen_range_are_not_collected(self):
        game = self.game
        game.hp = 40
        player_x, player_y = game.player.rect.center
        game.potions.drops.append(Potion(
            'health', (player_x + POTION_PICKUP_RANGE + 1, player_y)))
        game.potions.update(0)
        self.assertEqual(game.hp, 40)
        self.assertEqual(len(game.potions.drops), 1)
        self.assertFalse(game.potions.drops[0].homing)

    def test_potion_homes_toward_player_at_limited_speed(self):
        game = self.game
        player_x, player_y = game.player.rect.center
        game.potions.drops.append(Potion(
            'speed', (player_x + POTION_PICKUP_RANGE, player_y)))
        game.potions.update(0.1)
        potion = game.potions.drops[0]
        self.assertTrue(potion.homing)
        self.assertAlmostEqual(potion.pos.x,
                               player_x + POTION_PICKUP_RANGE
                               - POTION_HOMING_SPEED * 0.1)
        self.assertAlmostEqual(potion.pos.y, player_y)
        self.assertEqual(game.potions.speed_timer, 0)

    def test_homing_potion_is_collected_when_it_reaches_the_player(self):
        game = self.game
        game.hp = 40
        player_x, player_y = game.player.rect.center
        potion = Potion('health',
                        (player_x + POTION_COLLECT_DISTANCE + 1, player_y))
        game.potions.drops.append(potion)
        game.potions.update(1 / 60)
        self.assertEqual(game.hp, 40 + HEAL_POTION_AMOUNT)
        self.assertNotIn(potion, game.potions.drops)

    def test_boss_does_not_drop_a_potion(self):
        game = Game(self.art, stage=6, seed=1)
        boss = game.boss
        game.potions.random = FixedRoll(0)
        game.monsters = [enemy for enemy in game.monsters if enemy is not boss]
        self.assertEqual(game.potions.drops, [])

    def test_potions_render_with_the_existing_assets(self):
        game = self.game
        game.potions.random = FixedRoll(0)
        game.potions.drop('speed', game.player.rect.center)
        game.potions.drop('health', (game.player.rect.centerx + 40,
                                     game.player.rect.centery))
        game.draw(pygame.Surface((SCREEN_W, SCREEN_H)))

    def test_speed_timer_is_shown_at_bottom_left_and_counts_down(self):
        from ui import GameUI
        ui = GameUI()
        surface = pygame.Surface((SCREEN_W, SCREEN_H))
        game = self.game
        game.potions.speed_timer = 12.2
        messages = []
        ui.text = lambda _surface, message, *_args, **_kwargs: messages.append(message)

        ui.speed_potion_timer(surface, game)

        self.assertIn('SPEED', messages)
        self.assertIn('13s', messages)
        self.assertEqual(surface.get_at((31, SCREEN_H - 28))[:3], (43, 220, 255))

        messages.clear()
        game.potions.speed_timer = 0
        ui.speed_potion_timer(surface, game)
        self.assertEqual(messages, [])


if __name__ == "__main__":
    unittest.main()
