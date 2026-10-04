"""Headless checks for gravity, cell collisions, and excavated terrain."""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest

from config import CELL, GRAVITY, JUMP_SPEED, MAX_FRAME_DT, MOVE_SPEED
from level import EMPTY, LAVA, ROCK, WATER
from physics import Actor, Player, drop_to_ground
from world import World


def room(width=24, height=24):
    rows = ["R" * width]
    rows.extend("R" + " " * (width - 2) + "R" for _ in range(height - 2))
    rows.append("R" * width)
    return World(rows, scale=1)


class PhysicsTests(unittest.TestCase):
    def test_spawn_drops_to_first_floor_without_overlap(self):
        world = room()
        for x in range(1, world.width - 1):
            world.set_terrain(world.index(x, 12), ROCK)
        player = Player(world, 5 * CELL, 4 * CELL)
        self.assertTrue(drop_to_ground(player))
        self.assertEqual(player.pos.y, 12 * CELL - player.size)
        self.assertEqual(player.rect.bottom, 12 * CELL)
        self.assertTrue(player.grounded)
        self.assertFalse(player.overlaps_terrain())

    def test_obstructed_spawn_finds_clear_position(self):
        world = room()
        for y in range(4, 8):
            for x in range(4, 8):
                world.set_terrain(world.index(x, y), ROCK)
        actor = Player(world, 4 * CELL, 4 * CELL)
        self.assertTrue(actor.drop_to_ground())
        self.assertTrue(actor.grounded)
        self.assertFalse(actor.overlaps_terrain())

    def test_no_spawn_space_reports_failure(self):
        actor = Player(World(["R" * 8 for _ in range(8)], scale=1), 16, 16)
        self.assertFalse(actor.drop_to_ground())

    def test_grounded_jump_and_airborne_rejump(self):
        player = Player(room(), 5 * CELL, 4 * CELL)
        player.drop_to_ground()
        floor_y = player.pos.y
        player.update(1 / 60, 0, jump=True)
        self.assertLess(player.pos.y, floor_y)
        self.assertLess(player.velocity.y, 0)
        self.assertFalse(player.grounded)
        upward_speed = player.velocity.y
        player.update(1 / 60, 0, jump=True)
        self.assertGreater(player.velocity.y, upward_speed)
        for _ in range(90):
            player.update(1 / 60, 0)
        self.assertEqual(player.pos.y, floor_y)
        self.assertTrue(player.grounded)
        self.assertEqual(player.velocity.y, 0)

    def test_wall_stops_fast_actor_at_cell_face(self):
        world = room(60, 30)
        for y in range(1, world.height - 1):
            world.set_terrain(world.index(15, y), ROCK)
        actor = Actor(world, 8 * CELL, 8 * CELL, speed=20000)
        actor.update(MAX_FRAME_DT, 1)
        self.assertEqual(actor.rect.right, 15 * CELL)
        self.assertEqual(actor.velocity.x, 0)
        self.assertTrue(actor.hit_wall)
        self.assertFalse(actor.overlaps_terrain())

    def test_ceiling_stops_upward_movement(self):
        world = room()
        for x in range(1, world.width - 1):
            world.set_terrain(world.index(x, 12), ROCK)
        actor = Actor(world, 5 * CELL, 13 * CELL)
        actor.velocity.y = -1000
        actor.update(MAX_FRAME_DT, 0)
        self.assertGreaterEqual(actor.pos.y, 13 * CELL)
        self.assertTrue(actor.hit_ceiling)
        self.assertFalse(actor.overlaps_terrain())

    def test_excavating_support_starts_fall(self):
        world = room()
        for x in range(1, world.width - 1):
            world.set_terrain(world.index(x, 12), ROCK)
        player = Player(world, 5 * CELL, 4 * CELL)
        player.drop_to_ground()
        floor_y = player.pos.y
        for x in range(5, 9):
            world.set_terrain(world.index(x, 12), EMPTY)
        player.update(1 / 60, 0)
        self.assertGreater(player.pos.y, floor_y)
        self.assertGreater(player.velocity.y, 0)
        self.assertFalse(player.grounded)

    def test_new_reaction_stone_cannot_leave_actor_embedded(self):
        world = room()
        player = Player(world, 5 * CELL, 8 * CELL)
        world.set_terrain(world.index(6, 9), ROCK)
        self.assertTrue(player.overlaps_terrain())
        player.update(1 / 60, 0)
        self.assertFalse(player.overlaps_terrain())

    def test_water_and_lava_do_not_support_actor(self):
        rows = ["R" * 24]
        rows.extend("R" + " " * 22 + "R" for _ in range(10))
        rows.append("R" + "W" * 11 + "L" * 11 + "R")
        rows.extend("R" + " " * 22 + "R" for _ in range(11))
        rows.append("R" * 24)
        world = World(rows, scale=1)
        self.assertIn(WATER, world.initial_liquids.values())
        self.assertIn(LAVA, world.initial_liquids.values())
        player = Player(world, 5 * CELL, 4 * CELL)
        player.drop_to_ground()
        self.assertEqual(player.rect.bottom, 23 * CELL)

    def test_ladder_requires_explicit_input(self):
        player = Player(room(), 5 * CELL, 10 * CELL)
        initial_y = player.pos.y
        player.update(1 / 60, 0, climb=-1)
        self.assertTrue(player.on_ladder)
        self.assertLess(player.pos.y, initial_y)
        player.update(1 / 60, 0)
        self.assertFalse(player.on_ladder)
        self.assertGreater(player.velocity.y, -130)

    def test_verified_ladder_holds_only_after_climbing(self):
        player = Player(room(), 5 * CELL, 10 * CELL)
        player.update(1 / 120, 0, ladder_attached=True)
        self.assertFalse(player.on_ladder)
        self.assertGreater(player.velocity.y, 0)
        player.update(1 / 120, 0, climb=-1, ladder_attached=True)
        self.assertTrue(player.on_ladder)
        hanging_y = player.pos.y
        player.update(1 / 60, 0, ladder_attached=True)
        self.assertTrue(player.on_ladder)
        self.assertEqual(player.pos.y, hanging_y)
        self.assertEqual(player.velocity.y, 0)

    def test_neutral_ladder_jump_and_held_up_keep_jump_velocity(self):
        player = Player(room(), 5 * CELL, 12 * CELL)
        player.update(1 / 120, 0, climb=-1, ladder_attached=True)
        player.update(1 / 120, 0, jump=True, ladder_attached=True)
        self.assertFalse(player.on_ladder)
        self.assertAlmostEqual(player.velocity.y, -JUMP_SPEED + GRAVITY / 120)
        for _ in range(12):
            player.update(1 / 120, 0, climb=-1, ladder_attached=True)
        self.assertFalse(player.on_ladder)
        self.assertAlmostEqual(player.velocity.y, -JUMP_SPEED + GRAVITY * 13 / 120)

    def test_leaving_verified_ladder_restores_gravity(self):
        player = Player(room(), 5 * CELL, 10 * CELL)
        player.update(1 / 120, 0, climb=-1, ladder_attached=True)
        player.update(1 / 120, 0, ladder_attached=True)
        self.assertTrue(player.on_ladder)
        player.update(1 / 120, 0, ladder_attached=False)
        self.assertFalse(player.on_ladder)
        self.assertGreater(player.velocity.y, 0)

    def test_swimming_reduces_fall_and_allows_buoyant_jump(self):
        normal = Player(room(60, 60), 40, 40)
        swimmer = Player(room(60, 60), 80, 40)
        normal.update(0.1, 0)
        swimmer.update(0.1, 0, swimming=True)
        self.assertLess(swimmer.pos.y - 40, normal.pos.y - 40)
        swimmer.update(1 / 60, 0, jump=True, swimming=True)
        self.assertLess(swimmer.velocity.y, 0)

    def test_bounds_and_large_frame_clamp(self):
        player = Player(room(), CELL, 5 * CELL)
        player.update(5, -1)
        self.assertEqual(player.pos.x, CELL)
        self.assertFalse(player.overlaps_terrain())
        moving = Player(room(100, 60), 40, 40)
        moving.update(5, 1)
        self.assertAlmostEqual(moving.pos.x, 40 + MOVE_SPEED * MAX_FRAME_DT)

    def test_frame_rate_independent_motion(self):
        positions = []
        for fps in (30, 60, 120):
            player = Player(room(100, 100), 40, 40)
            for _ in range(fps):
                player.update(1 / fps, 1)
            positions.append(tuple(player.pos))
        for position in positions[1:]:
            self.assertAlmostEqual(position[0], positions[0][0], places=7)
            self.assertAlmostEqual(position[1], positions[0][1], places=7)


if __name__ == "__main__":
    unittest.main()
