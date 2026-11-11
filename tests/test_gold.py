"""Gold placement, collection, enemy rewards, and wallet HUD."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (CELL, MACRO, SCREEN_H, SCREEN_W,
                    POTION_COLLECT_DISTANCE, POTION_HOMING_SPEED,
                    POTION_PICKUP_RANGE)
from gold import COIN_VALUE, GoldCoin
from level import DIRT
from main import Game, retry_gold_checkpoint
from tiles import TileArt
from ui import GameUI


class GoldSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def test_player_starts_with_zero_gold_and_level_coins_are_embedded_in_dirt(self):
        game = Game(self.art, stage=1)
        self.assertEqual(game.gold, 0)
        self.assertEqual(game.player.gold, 0)
        self.assertEqual(game.gold_system.coins, [])
        self.assertTrue(game.gold_system.hidden)
        self.assertEqual(set(game.gold_system.hidden.values()), {COIN_VALUE})
        self.assertTrue(all(game.world.foreground[index] == DIRT
                            for index in game.gold_system.hidden))
        self.assertIsNotNone(game.gold_system.ore_image)

    def test_starting_gold_is_restored_to_the_player_on_a_new_level(self):
        game = Game(self.art, stage=2, starting_gold=10)
        self.assertEqual(game.gold, 10)
        self.assertEqual(game.player.gold, 10)
        self.assertEqual(game.gold_checkpoint, 10)

    def test_retry_uses_the_unchanged_gold_checkpoint(self):
        game = Game(self.art, stage=1, starting_gold=10)
        game.gold = 25

        checkpoint = retry_gold_checkpoint(game)
        restarted = Game(self.art, stage=1, starting_gold=checkpoint)
        restarted.gold = 37
        repeated_retry = Game(
            self.art, stage=1,
            starting_gold=retry_gold_checkpoint(restarted))

        self.assertEqual(checkpoint, 10)
        self.assertEqual(restarted.gold_checkpoint, 10)
        self.assertEqual(repeated_retry.gold, 10)
        self.assertEqual(repeated_retry.gold_checkpoint, 10)

    def test_new_level_checkpoints_the_carried_gold_and_bonus_keeps_parent_checkpoint(self):
        first_level = Game(self.art, stage=1, starting_gold=10)
        first_level.gold = 25
        next_level = Game(self.art, stage=2, starting_gold=first_level.gold)
        self.assertEqual(next_level.gold_checkpoint, 25)

        half_level = Game(self.art, stage=1, bonus_room=True)
        half_level.inherit_player_state(first_level)
        half_level.gold = 40
        self.assertEqual(half_level.gold_checkpoint, 10)
        self.assertEqual(retry_gold_checkpoint(half_level), 10)

    def test_digging_gold_bearing_dirt_collects_five_gold(self):
        game = Game(self.art, stage=1)
        x, y = game.world.width // 2, game.world.height // 2
        index = game.world.index(x, y)
        game.world.set_terrain(index, DIRT)
        game.gold_system.hidden[index] = COIN_VALUE

        game.excavate((x, y))

        self.assertEqual(game.gold, 5)
        self.assertEqual(game.player.gold, 5)
        self.assertNotIn(index, game.gold_system.hidden)
        self.assertIn('+5 G', [popup[0] for popup in game.fx.popups])

    def test_gold_ore_is_drawn_in_the_dirt_until_dug(self):
        game = Game(self.art, stage=1)
        index = next(iter(game.gold_system.hidden))
        game.gold_system.hidden = {index: COIN_VALUE}
        surface = pygame.Surface((game.world.pixel_width,
                                  game.world.pixel_height), pygame.SRCALPHA)

        game.gold_system.draw(surface, (0, 0), 0)
        self.assertFalse(surface.get_bounding_rect().size == (0, 0))

        game.gold_system.dug([index])
        surface.fill((0, 0, 0, 0))
        game.gold_system.draw(surface, (0, 0), 0)
        self.assertEqual(surface.get_bounding_rect().size, (0, 0))

    def test_touching_a_coin_collects_it(self):
        game = Game(self.art, stage=1)
        game.gold_system.coins = [
            GoldCoin(game.player.rect.center, value=COIN_VALUE)]

        game.gold_system.update(1 / 60)

        self.assertEqual(game.gold, COIN_VALUE)
        self.assertEqual(game.gold_system.coins, [])

    def test_dropped_coin_uses_potion_magnet_range_and_speed(self):
        game = Game(self.art, stage=1)
        player_x, player_y = game.player.rect.center
        coin = GoldCoin((player_x + POTION_PICKUP_RANGE + 1, player_y),
                        value=15, dropped=True)
        game.gold_system.coins = [coin]

        game.gold_system.update(0)
        self.assertFalse(coin.homing)
        self.assertEqual(coin.pos.x, player_x + POTION_PICKUP_RANGE + 1)

        coin.pos.update(player_x + POTION_PICKUP_RANGE, player_y)
        game.gold_system.update(0.1)
        self.assertTrue(coin.homing)
        self.assertAlmostEqual(
            coin.pos.x, player_x + POTION_PICKUP_RANGE - POTION_HOMING_SPEED * 0.1)
        self.assertEqual(coin.pos.y, player_y)
        self.assertEqual(game.gold, 0)

        coin.pos.update(player_x + POTION_COLLECT_DISTANCE + 1, player_y)
        coin.homing = True
        game.gold_system.update(1 / POTION_HOMING_SPEED)
        self.assertEqual(game.gold, 15)
        self.assertEqual(game.gold_system.coins, [])

    def test_regular_enemy_and_boss_drop_their_gold_values(self):
        game = Game(self.art, stage=1)
        enemy = next(monster for monster in game.monsters
                     if monster is not game.boss)
        game.monsters = [monster for monster in game.monsters
                         if monster is not enemy]
        self.assertEqual(game.gold_system.coins[-1].value, 15)

        boss_game = Game(self.art, stage=6, seed=3)
        boss = boss_game.boss
        boss_game.monsters = [monster for monster in boss_game.monsters
                              if monster is not boss]
        self.assertEqual(boss_game.gold_system.coins[-1].value, 50)

    def test_wallet_hud_draws_coin_and_gold_amount(self):
        game = Game(self.art, stage=1)
        game.gold = 50
        ui = GameUI()
        screen = pygame.Surface((SCREEN_W, SCREEN_H))
        screen.fill((0, 0, 0))

        ui.gold_wallet(screen, game)

        self.assertNotEqual(screen.get_at((34, 79))[:3], (0, 0, 0))
        self.assertEqual(game.player.gold, 50)


if __name__ == '__main__':
    unittest.main()
