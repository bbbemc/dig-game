"""Fluid invariants and behavior through the public World integration."""

import unittest
from unittest.mock import patch

from level import EMPTY, DIRT, WATER, LAVA, STONE
from world import World
from liquids import LiquidSystem, FULL


def liquid(rows):
    world = World(rows, scale=1)
    return world, LiquidSystem(world)


class LiquidTests(unittest.TestCase):
    def assert_consistent(self, system):
        self.assertEqual(system.occupied, set(system.types))
        self.assertEqual(system.occupied, set(system.mass))
        self.assertEqual(system.occupied, set(system._units))
        self.assertTrue(all(value > 0 for value in system._units.values()))
        self.assertEqual(set().union(*system.chunks.values()) if system.chunks else set(),
                         system.occupied)
        for i, amount in system._units.items():
            self.assertEqual(system.mass[i], amount / FULL)
            self.assertEqual(system.world.foreground[i], EMPTY)

    def test_falling_and_spreading_conserve_every_unit(self):
        _, system = liquid([
            'RRRRRRRRRRRRR',
            'R    WWW    R',
            'R     W     R',
            'R           R',
            'R   R   R   R',
            'R           R',
            'RRRRRRRRRRRRR',
        ])
        original = sum(system._units.values())
        for _ in range(350):
            system.step()
            self.assertEqual(sum(system._units.values()), original)
            self.assert_consistent(system)
        self.assertGreater(system.mass_at(2, 5), 0)
        self.assertEqual(system.mass_at(6, 1), 0)

    def test_reflection_is_preserved_during_asymmetric_flow(self):
        rows = [
            'RRRRRRRRRRRRR',
            'R WW        R',
            'R W    R    R',
            'R      R    R',
            'R   R       R',
            'R           R',
            'RRRRRRRRRRRRR',
        ]
        world, original = liquid(rows)
        _, mirrored = liquid([row[::-1] for row in rows])
        for _ in range(90):
            original.step()
            mirrored.step()
            reflected = {(i // world.width) * world.width + world.width - 1 - i % world.width: mass
                         for i, mass in original._units.items()}
            self.assertEqual(reflected, mirrored._units)

    def test_dictionary_order_cannot_change_transfers(self):
        rows = ['RRRRRRRRR', 'R WWW   R', 'R  W R  R', 'R       R', 'RRRRRRRRR']
        _, first = liquid(rows)
        _, reverse = liquid(rows)
        for _ in range(130):
            reverse._units = dict(reversed(list(reverse._units.items())))
            reverse.types = dict(reversed(list(reverse.types.items())))
            reverse.mass = dict(reversed(list(reverse.mass.items())))
            first.step()
            reverse.step()
            self.assertEqual(first._units, reverse._units)
            self.assertEqual(first.types, reverse.types)

    def test_settled_pool_sleeps_and_digging_wakes_it(self):
        world, system = liquid([
            'RRRRRRR', 'RWWWWWR', 'RWWWWWR', 'RWWWWWR',
            'RRR#RRR', 'R     R', 'RRRRRRR',
        ])
        for _ in range(80):
            system.step()
        self.assertEqual(system.active_count, 0)
        unchanged = dict(system._units)
        system.step()
        self.assertEqual(system.last_processed, 0)
        self.assertEqual(unchanged, system._units)
        world.dig(3, 4, radius=0)
        system.step()
        self.assertGreater(system.last_processed, 0)
        self.assertGreater(system.mass_at(3, 4), 0)
        self.assertEqual(system.total_mass, 15)

    def test_lava_falls_more_slowly_than_water(self):
        rows = ['RRRRRRR', 'R  W  R', 'R     R', 'R     R', 'RRRRRRR']
        _, water = liquid(rows)
        _, lava = liquid([row.replace('W', 'L') for row in rows])
        water.step()
        lava.step()
        self.assertEqual(water.mass_at(3, 1), 0)
        self.assertGreater(lava.mass_at(3, 1), 0.5)
        self.assertGreater(water.mass_at(3, 2), lava.mass_at(3, 2))

    def test_contact_evaporates_all_water_and_solidifies_all_lava(self):
        world, system = liquid([
            'RRRRRRRRRRRRRR',
            'RWWWWWWWLLLLLR',
            'RRRRRRRRRRRRRR',
        ])
        initial = system.total_mass
        system.step()
        self.assertTrue(system.reactions)
        self.assertEqual(system.reacted_mass, 0)
        self.assertEqual(bytes(world.foreground).count(STONE), 0)
        for _ in range(10):
            system.step()
        self.assertEqual(system.reacted_mass, 0)
        self.assertLess(system.render_mass(world.index(2, 1), 1), 1)
        for _ in range(100):
            system.step()
            self.assertEqual(system.total_mass + system.reacted_mass, initial)
        self.assertEqual(system.total_mass, 0)
        self.assertEqual(system.evaporated_mass, 7)
        self.assertEqual(system.solidified_mass, 5)
        self.assertEqual(system.reacted_mass, initial)
        self.assertEqual(bytes(world.foreground).count(STONE), 5)
        self.assertFalse(system.reactions)
        self.assertFalse(system.frozen)
        self.assert_consistent(system)

    def test_water_and_lava_disappear_over_reaction_duration(self):
        world, system = liquid([
            'RRRRRRRR',
            'RWWLL RR',
            'RRRRRRRR',
        ])
        system.step()
        self.assertTrue(system.reactions)
        self.assertEqual(system.reacted_mass, 0)
        self.assertEqual(bytes(world.foreground).count(STONE), 0)
        self.assertEqual(system.total_mass, 4)
        self.assertEqual(system.type_at(2, 1), WATER)
        self.assertEqual(system.type_at(3, 1), LAVA)
        water = world.index(2, 1)
        self.assertGreater(system.render_mass(water, 1), 0.9)
        for _ in range(4):
            system.step()
        self.assertGreater(system.mass_at(2, 1), 0.9)
        self.assertLess(system.render_mass(water, 1), 0.9)
        for _ in range(100):
            system.step()
        self.assertEqual(system.reacted_mass, 4)
        self.assertEqual(system.evaporated_mass, 2)
        self.assertEqual(system.solidified_mass, 2)
        self.assertEqual(bytes(world.foreground).count(STONE), 2)
        self.assertEqual(system.total_mass, 0)
        self.assertFalse(system.types)

    def test_reaction_consumes_unmatched_water_too(self):
        world, system = liquid([
            'RRRRRR',
            'RWWL R',
            'R    R',
            'RRRRRR',
        ])
        initial = system.total_mass
        for _ in range(30):
            system.step()
        self.assertEqual(system.evaporated_mass, 2)
        self.assertEqual(system.solidified_mass, 1)
        self.assertEqual(system.total_mass, 0)
        self.assertEqual(system.reacted_mass, initial)
        self.assertEqual(world.foreground[world.index(3, 1)], STONE)

    def test_full_pool_reaction_work_is_bounded_and_finishes(self):
        world, system = liquid([
            'RRRRRRRRR', 'RWWWLLLWR', 'RWWWLLLWR', 'RWWWLLLWR', 'RRRRRRRRR',
        ])
        initial = system.total_mass
        with patch('liquids.REACTION_STEP_LIMIT', 3):
            for _ in range(150):
                system.step()
                self.assertLessEqual(system.reaction_work, 3)
                self.assertEqual(system.total_mass + system.reacted_mass, initial)
        self.assertEqual(system.reacted_mass, initial)
        self.assertGreater(system.evaporated_mass, 0)
        self.assertGreater(system.solidified_mass, 0)
        self.assertFalse(system.frozen)
        self.assertEqual(system.total_mass + system.reacted_mass, initial)

    def test_contact_reacts_the_full_large_reservoir(self):
        _, system = liquid(['R' * 80, 'R' + 'W' * 38 + 'L' * 40 + 'R', 'R' * 80])
        initial = system.total_mass
        for _ in range(50):
            system.step()
            self.assertEqual(system.total_mass + system.reacted_mass, initial)
        self.assertEqual(system.reacted_mass, initial)
        self.assertEqual(system.total_mass, 0)
        self.assertFalse(system.frozen)

    def test_water_uses_more_fluid_ticks_than_lava_per_second(self):
        from config import FLUID_HZ, WATER_FLOW_RATE, LAVA_FLOW_RATE
        self.assertGreater(FLUID_HZ * WATER_FLOW_RATE,
                           FLUID_HZ * LAVA_FLOW_RATE)

    def test_opposite_inflows_never_overwrite_or_destroy_mass(self):
        _, system = liquid(['RRRRRRR', 'RW L  R', 'RRRRRRR'])
        initial = system.total_mass
        system.step()
        self.assertEqual(system.total_mass, initial)
        self.assertTrue(system.reactions)
        for _ in range(100):
            system.step()
        self.assertEqual(system.total_mass + system.reacted_mass, initial)

    def test_visible_chunks_include_drained_cell_for_interpolation(self):
        world, system = liquid(['RRRRR', 'R W R', 'R   R', 'RRRRR'])
        source = world.index(2, 1)
        system.step()
        self.assertNotIn(source, system.occupied)
        self.assertIn(source, set(system.visible_indices(0, 0, 5, 4)))
        self.assertEqual(system.render_type(source), WATER)
        self.assertEqual(system.interpolated_mass(source, 0), 1)
        self.assertEqual(system.interpolated_mass(source, 0.5), 0.5)
        self.assertEqual(system.interpolated_mass(source, 1), 0)
        system.step()
        self.assertNotIn(source, set(system.visible_indices(0, 0, 5, 4)))

    def test_wall_edges_are_closed_and_queries_are_safe(self):
        _, system = liquid(['W  ', '   ', 'RRR'])
        for _ in range(120):
            system.step()
            self.assertEqual(system.total_mass, 1)
        self.assertEqual(system.type_at(-1, 0), EMPTY)
        self.assertEqual(system.mass_at(3, 0), 0)
        self.assertTrue(all(0 <= i < 9 for i in system.occupied))


if __name__ == '__main__':
    unittest.main()
