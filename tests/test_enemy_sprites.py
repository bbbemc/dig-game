"""Enemy sprites load, face the right way and stand on the floor."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

import enemy_sprites
from config import CELL, MACRO, SCREEN_H, SCREEN_W
from main import Game
from tiles import TileArt


class EnemySpriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.game = Game(TileArt(CELL, MACRO))

    def test_every_kind_has_art_with_transparency(self):
        for kind in ('gunner', 'walker', 'boss'):
            image = enemy_sprites.sprite(kind)
            self.assertIsNotNone(image, kind)
            self.assertEqual(image.get_at((0, 0)).a, 0, kind)  # corners are see-through

    def test_kinds_match_the_enemies(self):
        kinds = {enemy_sprites.kind_of(m) for m in self.game.monsters}
        self.assertEqual(kinds, {'gunner', 'walker', 'boss'})

    def test_enemies_turn_toward_the_player(self):
        gunner = next(m for m in self.game.monsters if enemy_sprites.kind_of(m) == 'gunner')
        self.assertTrue(enemy_sprites.facing_right(gunner, gunner.rect.centerx + 100))
        self.assertFalse(enemy_sprites.facing_right(gunner, gunner.rect.centerx - 100))

    def test_sprite_feet_sit_on_the_collision_box_floor(self):
        screen = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        walker = next(m for m in self.game.monsters if enemy_sprites.kind_of(m) == 'walker')
        camera = (walker.rect.centerx - SCREEN_W // 2, walker.rect.centery - SCREEN_H // 2)
        self.assertTrue(enemy_sprites.draw(screen, walker, camera))
        bottom = walker.rect.bottom - camera[1]
        drawn = [y for y in range(SCREEN_H) if screen.get_at((walker.rect.centerx - camera[0], y)).a]
        self.assertTrue(drawn)
        self.assertLessEqual(max(drawn), bottom)
        self.assertGreater(max(drawn), bottom - 6)

    def test_full_frame_draws_with_sprites(self):
        self.game.draw(pygame.display.get_surface())


if __name__ == "__main__":
    unittest.main()
