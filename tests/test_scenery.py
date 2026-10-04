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

    def test_themes_use_original_art_and_distinct_landmarks(self):
        bands = [{p['name'] for p in self.scenery['props']
                  if lo <= p['y'] < hi}
                 for lo, hi in [(0, 25), (25, 50), (50, 75), (75, 100)]]
        self.assertIn('mine_tall_frame', bands[0])
        self.assertIn('cart', bands[0])
        self.assertIn('dirt_stalagmite', bands[1])
        self.assertIn('vines', bands[1])
        self.assertIn('blue_crystal', bands[2])
        self.assertIn('purple_crystal', bands[2])
        self.assertIn('ruin_arch', bands[3])
        self.assertIn('red_crystal', bands[3])
        self.assertFalse({'mine_frame', 'mine_rail', 'cart'} & bands[1])
        self.assertFalse({'ruin_arch', 'dungeon_arch', 'banner'} & bands[2])
        self.assertFalse({'fern', 'vines', 'moss_vines', 'small_plants'} & bands[3])
        for prop in self.scenery['props']:
            self.assertIn(prop['name'], SPRITES)
            if prop.get('repeat_y'):
                continue
            _, _, source_w, source_h = SPRITES[prop['name']]['rect']
            self.assertAlmostEqual(prop['w'] / prop['h'], source_w / source_h)

    def test_arena_ladder_reaches_the_roof_gate_from_the_floor(self):
        ladders = [p for p in self.scenery['props']
                   if p['name'] == 'ladder' and p['x'] > 75]
        self.assertTrue(ladders)
        ladder = max(ladders, key=lambda p: p['h'])
        self.assertEqual(ladder['y'], 78)
        self.assertEqual(ladder['y'] + ladder['h'], 97)
        self.assertGreaterEqual(ladder['x'], 95)
        self.assertLessEqual(ladder['x'] + ladder['w'], 102)
        self.assertTrue(ladder['repeat_y'])
        self.assertEqual(self.rows[77][math.floor(ladder['x'])], '#')

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
