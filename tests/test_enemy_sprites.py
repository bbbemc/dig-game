"""Enemy sprites load, face the right way, stand on the floor and animate."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

import enemy_sprites
from config import CELL, ENEMY_FIRE_INTERVAL, MACRO, SCREEN_H, SCREEN_W
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

    def enemy(self, kind):
        return next(m for m in self.game.monsters if enemy_sprites.kind_of(m) == kind)

    def test_every_animation_frame_is_cut_from_the_sheets(self):
        for kind, rows in enemy_sprites.ANIMATIONS.items():
            anims = enemy_sprites.frames(kind)
            self.assertIsNotNone(anims, kind)
            base = enemy_sprites.sprite(kind)
            size = (base.get_width() + 2 * enemy_sprites.PAD_X,
                    base.get_height() + enemy_sprites.PAD_TOP)
            for name, count in rows:
                self.assertEqual(len(anims[name]), count, (kind, name))
                for image in anims[name]:
                    self.assertEqual(image.get_size(), size)
                    self.assertEqual(image.get_at((0, 0)).a, 0)       # see-through
                    # a foot stays planted on the bottom edge, like the still sprite
                    self.assertTrue(any(image.get_at((x, y)).a for x in range(size[0])
                                        for y in (size[1] - 2, size[1] - 1)), (kind, name))

    def test_walk_frames_differ_and_follow_the_ground_walked(self):
        walker = self.enemy('walker')
        walker.velocity.x = 40
        seen = set()
        for step in range(16):
            walker.pos.x += enemy_sprites.STRIDE['walker']
            name, index = enemy_sprites.animation(walker, (walker.rect.centerx + 500, 0))
            self.assertEqual(name, 'walk')
            seen.add(index)
        walker.velocity.x = 0
        self.assertEqual(seen, set(range(8)))
        frames = enemy_sprites.frames('walker')['walk']
        self.assertNotEqual(pygame.image.tobytes(frames[0], 'RGBA'),
                            pygame.image.tobytes(frames[1], 'RGBA'))

    def test_animation_follows_what_the_enemy_is_doing(self):
        walker, gunner = self.enemy('walker'), self.enemy('gunner')
        near = (walker.rect.centerx - 30, walker.rect.centery)
        self.assertEqual(enemy_sprites.animation(walker, near, 5.0), ('attack', 0))  # readied
        walker.attack_time = 5.0                                # a contact hit lands
        self.assertEqual(enemy_sprites.animation(walker, near, 5.0)[0], 'attack')
        self.assertGreater(enemy_sprites.animation(walker, near, 5.15)[1], 1)   # swinging
        self.assertEqual(enemy_sprites.animation(walker, near, 6.0), ('attack', 0))
        walker.attack_time = -99.0
        self.assertFalse(enemy_sprites.facing_right(walker, near, 'attack'))
        self.assertEqual(enemy_sprites.animation(walker, (walker.rect.x + 900, 0))[0], 'idle')
        gunner.shot_cooldown = ENEMY_FIRE_INTERVAL          # just fired
        self.assertEqual(enemy_sprites.animation(gunner), ('fire', 0))
        gunner.shot_cooldown = 0.3                          # about to fire
        self.assertEqual(enemy_sprites.animation(gunner)[0], 'charge')
        gunner.shot_cooldown = 0.0
        gunner.stun_timer = 0.5
        self.assertEqual(enemy_sprites.animation(gunner, time=3.0)[0], 'stun')
        gunner.hurt_time = 2.9                              # flinch comes first
        self.assertEqual(enemy_sprites.animation(gunner, time=3.0)[0], 'hurt')
        gunner.stun_timer, gunner.hurt_time = 0.0, -99.0

    def test_contact_hit_and_parry_mark_the_enemy(self):
        game = Game(TileArt(CELL, MACRO))
        walker = next(m for m in game.monsters if enemy_sprites.kind_of(m) == 'walker')
        game.world_time = 4.0
        game._parried(walker, 1)
        self.assertEqual(walker.hurt_time, 4.0)
        self.assertEqual(enemy_sprites.animation(walker, None, 4.05)[0], 'hurt')

    def test_defeated_enemy_plays_its_death_then_is_cleared(self):
        game = Game(TileArt(CELL, MACRO))
        walker = next(m for m in game.monsters if enemy_sprites.kind_of(m) == 'walker')
        game.world_time = 1.0
        game.monsters = [m for m in game.monsters if m is not walker]
        self.assertEqual(len(game.dying), 1)
        death = game.dying[0]
        self.assertEqual(death.midbottom, walker.rect.midbottom)
        screen = pygame.Surface((SCREEN_W, SCREEN_H))
        game.draw(screen)                                  # draws the death frame
        self.assertFalse(death.done(1.2))
        self.assertTrue(death.done(1.0 + death.duration))
        for _ in range(60):
            game.update(1 / 60)
        self.assertEqual(game.dying, [])

    def test_shots_leave_from_the_cannon_tip(self):
        game = Game(TileArt(CELL, MACRO))
        gunner = next(m for m in game.monsters if enemy_sprites.kind_of(m) == 'gunner')
        left = enemy_sprites.muzzle(gunner, False)
        right = enemy_sprites.muzzle(gunner, True)
        self.assertLess(left[0], gunner.rect.left)        # past the body, at the barrel
        self.assertGreater(right[0], gunner.rect.right)
        self.assertEqual(left[1], right[1])
        start = game._muzzle(gunner)
        self.assertIn(tuple(start), {tuple(map(float, left)), tuple(map(float, right)),
                                     tuple(map(float, gunner.rect.center))})

    def test_frame_rates_stay_between_8_and_20_fps(self):
        for fps in (enemy_sprites.IDLE_FPS, enemy_sprites.ATTACK_FPS, enemy_sprites.STUN_FPS,
                    enemy_sprites.CHARGE_FPS, enemy_sprites.DEATH_FPS):
            self.assertTrue(8 <= fps <= 20, fps)

    def test_full_frame_draws_with_sprites(self):
        self.game.draw(pygame.display.get_surface())


if __name__ == "__main__":
    unittest.main()
