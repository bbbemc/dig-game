"""Rooms: placement checks, prices, one of each type, expanding and buffs."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

import pygame

from config import (CELL, MACRO, SCREEN_H, SCREEN_W, BOMB_MAX_CARRY,
                    DIRT_GUN_COOLDOWN, PARRY_COOLDOWN)
from level import DIRT, EMPTY
from main import Game
import rooms
from tiles import TileArt

# Stage 1's big cave: open from macro row 5 to 9 between columns 8 and 22,
# solid floor at pixel y 400.
FLOOR_Y = 400


class RoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((SCREEN_W, SCREEN_H))
        cls.art = TileArt(CELL, MACRO)

    def setUp(self):
        self.game = Game(self.art, stage=1)
        self.rooms = self.game.rooms
        self.game.gold = 500

    def place(self, x, size='M'):
        r = self.rooms
        if not r.build_mode:
            r.press_b()
        r.pick_size(rooms.SIZE_NAMES.index(size) + 1)
        r.update_blueprint((x, FLOOR_Y - 20))
        return r.blueprint

    def build(self, x, kind, size='M'):
        rect, reason, _ = self.place(x, size)
        self.assertIsNone(reason)
        self.assertTrue(self.rooms.confirm())
        self.assertEqual(self.rooms.menu[0], 'build')
        return self.rooms.choose(kind)

    def test_blueprint_settles_on_the_floor_and_is_green_in_open_space(self):
        rect, reason, room = self.place(420, 'M')
        self.assertIsNone(reason)
        self.assertIsNone(room)
        self.assertEqual(rect.size, rooms.SIZES['M'])
        self.assertEqual(rect.bottom * CELL, FLOOR_Y)

    def test_dirt_liquid_and_doors_turn_it_red(self):
        rect, reason, _ = self.place(150, 'S')         # inside the rock
        self.assertEqual(reason, 'DIG MORE SPACE')
        world = self.game.world
        free = pygame.Rect(48, 42, 12, 8)
        self.assertIsNone(self.rooms.check(free))
        world.foreground[world.index(free.x + 3, free.y + 2)] = DIRT
        self.assertEqual(self.rooms.check(free), 'DIG MORE SPACE')
        world.foreground[world.index(free.x + 3, free.y + 2)] = EMPTY
        self.game.liquids.types[world.index(free.x + 3, free.y + 2)] = 3
        self.assertEqual(self.rooms.check(free), 'NO WATER OR LAVA')
        del self.game.liquids.types[world.index(free.x + 3, free.y + 2)]
        self.assertEqual(self.rooms.check(free.move(0, -4)), 'NEED SOLID FLOOR')
        _, reason, _ = self.place(self.game.exit_door.centerx, 'S')
        self.assertEqual(reason, 'BLOCKS A DOOR')

    def test_building_charges_gold_and_each_type_once(self):
        self.assertIsNone(self.build(420, 'forge', 'M'))
        self.assertEqual(self.game.gold, 500 - 40)
        self.assertEqual(self.game.bombs.carried, BOMB_MAX_CARRY)
        rect, reason, _ = self.place(560, 'S')
        self.assertIsNone(reason)
        self.rooms.confirm()
        self.assertEqual(self.rooms.choose('forge'), 'BUILT')
        self.rooms.close()
        _, reason, _ = self.place(420, 'S')             # the room is in the way
        self.assertEqual(self.rooms.blueprint[2], self.rooms.rooms[0])

    def test_not_enough_gold(self):
        self.game.gold = 10
        self.assertEqual(self.build(420, 'kitchen', 'S'), 'NEED 20 G')
        self.assertEqual(self.rooms.rooms, [])
        self.assertEqual(self.game.gold, 10)

    def test_three_rooms_at_most(self):
        self.assertIsNone(self.build(400, 'forge', 'S'))
        self.assertIsNone(self.build(560, 'herald', 'S'))
        self.assertIsNone(self.build(700, 'kitchen', 'S'))
        self.assertEqual(self.game.gold, 500 - 25 - 30 - 20)
        _, reason, _ = self.place(860, 'S')
        self.assertEqual(reason, 'ROOM LIMIT 3/3')

    def test_buffs(self):
        game = self.game
        game.hp = 20
        self.assertIsNone(self.build(400, 'kitchen', 'S'))
        self.assertEqual(game.hp, 50)
        self.assertAlmostEqual(game.max_oxygen, 120.0)
        game.dig_meter.remaining = 0
        self.assertIsNone(self.build(560, 'herald', 'L'))
        self.assertEqual(game.dig_meter.remaining, round(game.dig_meter.capacity * 0.6))
        self.assertAlmostEqual(game.combat.parry.cooldown_scale, 0.5)
        game.gun.aim = (game.player.rect.centerx + 100, game.player.rect.centery)
        game.gun.fire()
        self.assertAlmostEqual(game.gun.cooldown, DIRT_GUN_COOLDOWN * 0.5)
        parry = game.combat.parry
        parry.start()
        parry.update(0.5)          # past the window and the recovery
        self.assertLessEqual(parry.timer, PARRY_COOLDOWN * 0.5 + 1e-6)
        self.assertIsNone(self.build(740, 'forge', 'S'))
        points = [self.rooms.posture_points(1) for _ in range(20)]
        self.assertEqual(sum(points), 23)        # +15%: 20 hits do 23 points

    def test_expand_pays_the_difference_and_upgrades(self):
        game = self.game
        self.assertIsNone(self.build(420, 'kitchen', 'S'))
        room = self.rooms.rooms[0]
        game.player.pos.update(room.pixels.centerx - 16, FLOOR_Y - 32)
        game.player._sync_rect()
        self.rooms.press_b()
        self.assertEqual(self.rooms.menu, ('expand', room))
        gold, hp = game.gold, game.hp = (game.gold, 10)
        self.assertIsNone(self.rooms.choose('expand'))
        self.assertEqual(room.size, 'M')
        self.assertEqual(game.gold, gold - 10)
        self.assertEqual(game.hp, 40)              # the extra 30 HP of a bigger kitchen
        self.assertAlmostEqual(game.max_oxygen, 140.0)
        self.assertEqual(room.rect.size, rooms.SIZES['M'])
        self.assertEqual(room.rect.bottom * CELL, FLOOR_Y)

    def test_expand_needs_the_space(self):
        self.assertIsNone(self.build(420, 'forge', 'S'))
        room = self.rooms.rooms[0]
        world = self.game.world
        for x in range(room.rect.x - 4, room.rect.right + 4):     # wall it in
            for y in (room.rect.y - 1, room.rect.y - 2):
                world.foreground[world.index(x, y)] = DIRT
            world.foreground[world.index(room.rect.x - 1, room.rect.bottom - 1)] = DIRT
            world.foreground[world.index(room.rect.right, room.rect.bottom - 1)] = DIRT
        self.rooms.open_expand(room)
        self.assertEqual(self.rooms.choose('expand'), 'DIG MORE SPACE')
        self.assertEqual(room.size, 'S')

    def test_build_mode_blocks_digging_and_esc_backs_out(self):
        r = self.rooms
        self.assertFalse(r.busy)
        r.press_b()
        self.assertTrue(r.busy)
        self.place(420, 'S')
        r.confirm()
        self.assertIsNotNone(r.menu)
        self.assertTrue(r.cancel())          # closes the menu
        self.assertTrue(r.build_mode)
        self.assertTrue(r.cancel())          # leaves Build Mode
        self.assertFalse(r.cancel())

    def test_bonus_room_keeps_the_buffs_but_builds_nothing(self):
        game = self.game
        self.assertIsNone(self.build(420, 'kitchen', 'M'))
        bonus = Game(self.art, stage=1, bonus_room=True, return_game=game)
        bonus.inherit_player_state(game)
        self.assertAlmostEqual(bonus.max_oxygen, 140.0)
        bonus.rooms.press_b()
        self.assertFalse(bonus.rooms.build_mode)

    def test_rooms_draw(self):
        self.assertIsNone(self.build(420, 'forge', 'M'))
        self.assertIsNone(self.build(600, 'herald', 'S'))
        screen = pygame.Surface((SCREEN_W, SCREEN_H))
        self.rooms.press_b()
        self.rooms.update_blueprint((720, FLOOR_Y - 20))
        self.game.draw(screen)
        for kind in rooms.ORDER:
            for size in rooms.SIZE_NAMES:
                image = rooms.room_image(kind, size)
                w, h = rooms.SIZES[size]
                self.assertEqual(image.get_size(), (w * CELL, h * CELL))
        self.assertTrue(list(self.rooms.lights()))
        from ui import GameUI
        ui = GameUI()
        self.rooms.confirm()
        self.rooms.draw_hud(screen, ui, (0, 0))
        self.assertEqual(len(self.rooms.buttons), 2)   # close + the one unbuilt type


if __name__ == "__main__":
    unittest.main()
