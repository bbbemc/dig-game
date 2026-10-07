"""Geometry regressions for the real decorated level and constrained caves."""

import math
import unittest

from level import build_level
from scenery import _Placement
from tiles import SPRITES


class SceneryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, _, cls.scenery, _ = build_level()

    def test_every_prop_stays_in_empty_geology_and_has_real_support(self):
        for prop in self.scenery['props']:
            x0 = math.floor(prop['x'] + 1e-7)
            y0 = math.floor(prop['y'] + 1e-7)
            x1 = math.ceil(prop['x'] + prop['w'] - 1e-7)
            y1 = math.ceil(prop['y'] + prop['h'] - 1e-7)
            with self.subTest(prop=prop['name'], position=(prop['x'], prop['y'])):
                self.assertGreater(prop['w'], 0)
                self.assertGreater(prop['h'], 0)
                self.assertTrue(all(self.rows[y][x] == ' '
                                    for y in range(y0, y1)
                                    for x in range(x0, x1)))
                self.assertTrue(prop['support_cells'])
                for x, y in prop['support_cells']:
                    self.assertIn(self.rows[y][x], '#R')
                    if prop['attachment'] == 'floor':
                        self.assertEqual(y, round(prop['y'] + prop['h']))
                    elif prop['attachment'] == 'ceiling':
                        self.assertEqual(y, round(prop['y']) - 1)
                    elif prop['attachment'] == 'wall_left':
                        self.assertEqual(x, round(prop['x']) - 1)
                    elif prop['attachment'] == 'wall_right':
                        self.assertEqual(x, round(prop['x'] + prop['w']))
                    else:
                        self.fail('Unattached prop: ' + prop['name'])

    def test_physical_bodies_do_not_overlap_within_a_drawing_layer(self):
        props = self.scenery['props']
        for index, first in enumerate(props):
            for second in props[index + 1:]:
                if first['layer'] != second['layer']:
                    continue
                for ax, ay, aw, ah in first['occupancy_rects']:
                    for bx, by, bw, bh in second['occupancy_rects']:
                        intersects = (ax < bx + bw and ax + aw > bx and
                                      ay < by + bh and ay + ah > by)
                        self.assertFalse(intersects, (first['name'], second['name']))

    def test_stage_uses_existing_mine_and_cave_art_as_decoration(self):
        names = {prop['name'] for prop in self.scenery['props']}
        self.assertTrue({'ladder', 'cobweb', 'crate', 'blue_crystal',
                         'small_rocks', 'torch'} <= names)
        self.assertTrue(self.scenery['structures'])
        self.assertTrue(any(light for structure in self.scenery['structures']
                            for light in structure['lamps']))
        for prop in self.scenery['props']:
            self.assertIn(prop['name'], SPRITES)
            if prop.get('repeat_y'):
                continue
            _, _, source_w, source_h = SPRITES[prop['name']]['rect']
            self.assertAlmostEqual(prop['w'] / prop['h'], source_w / source_h)

    def test_ladder_links_spawn_shelf_and_corridor(self):
        ladder = next(p for p in self.scenery['props'] if p['name'] == 'ladder')
        self.assertEqual(ladder['y'], 4)
        self.assertEqual(ladder['y'] + ladder['h'], 10)
        self.assertEqual(self.rows[4][7], '#')
        self.assertEqual(self.rows[4][8], ' ')
        self.assertEqual(self.rows[3][8], ' ')
        self.assertEqual(self.rows[10][8], '#')

    def test_locked_exit_is_undiggable_and_stage_metadata_is_authored(self):
        self.assertEqual(self.scenery['exit_door'], (21, 8, 1, 2))
        self.assertEqual(self.scenery['key_spawn'], (3, 3))
        self.assertTrue(all(self.rows[y][21] == 'R' for y in range(8, 10)))
        self.assertEqual(self.rows[10][13], '#')
        self.assertEqual(self.rows[11][13], ' ')
        self.assertEqual(self.rows[12][15], 'L')
        self.assertEqual(self.rows[3][16], 'W')

    def test_wide_prop_cannot_be_anchored_only_at_its_center(self):
        rows = ['RRRRRRR', 'R     R', 'RR    R', 'R     R', 'RRRRRRR']
        placement = _Placement(rows, SPRITES)
        # The center column has floor support, but the footprint hits a ledge.
        self.assertIsNone(placement.floor('crate', 2, 2, 3, 3, search=0))
        # Fluids are also excluded from the full drawing footprint.
        rows = ['RRRRRRR', 'R     R', 'R  W  R', 'R     R', 'RRRRRRR']
        placement = _Placement(rows, SPRITES)
        self.assertIsNone(placement.floor('crate', 2, 2, 3, 3, search=0))


if __name__ == '__main__':
    unittest.main()
