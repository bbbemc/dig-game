"""Deterministic cell-level shaping that makes excavated rooms look hand dug.

The macro map stays the authority for level design and validation. This pass
only adjusts 8-pixel cells along cave boundaries before the simulation starts:

* rounded upper corners and an uneven, gently undulating ceiling;
* small bumps and shallow cavities in the upper part of walls.

Floors, the bottom macro row of every wall, prop footprints and anchors,
actor spawns, liquids (with a margin) and the scripted boss area are never
touched, and narrow passages are left as wide as they were authored.
"""

from math import ceil, floor

from config import SCALE
from level import DIRT, ROCK
from tiles import coordinate_hash

KINDS = {'#': DIRT, 'R': ROCK}
MIN_SPAN = 3            # macros of open space required before narrowing
LIQUID_MARGIN = 2       # macros kept untouched around reservoirs
BOSS_AREA = (60, 74, 119, 98)


def _wave(i, salt, period=4):
    """Smooth value noise in [0, 1) along one axis."""
    knot, step = divmod(i, period)
    a = coordinate_hash(knot, salt) % 1000 / 1000
    b = coordinate_hash(knot + 1, salt) % 1000 / 1000
    t = step / period
    t = t * t * (3 - 2 * t)
    return a + (b - a) * t


class _Map:
    def __init__(self, rows):
        self.rows = rows
        self.width, self.height = len(rows[0]), len(rows)

    def char(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.rows[y][x]
        return 'R'

    def empty(self, x, y):
        return self.char(x, y) == ' '

    def solid(self, x, y):
        return self.char(x, y) in '#R'

    def span(self, x, y, dx, dy):
        n = 0
        while self.empty(x + dx * n, y + dy * n):
            n += 1
        return n


def _protected_macros(cave, scenery, entities, pools):
    macros = set()
    x0, y0, x1, y1 = BOSS_AREA
    macros.update((x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1))
    for x, y, w, h in pools:
        for yy in range(y - LIQUID_MARGIN, y + h + LIQUID_MARGIN):
            for xx in range(x - LIQUID_MARGIN, x + w + LIQUID_MARGIN):
                macros.add((xx, yy))
    for points in entities.values():
        for x, y in points:
            floor_y = y + cave.span(x, y, 0, 1)
            macros.update((xx, yy) for yy in range(y - 1, floor_y + 1) for xx in range(x - 1, x + 2))
    for item in list(scenery['props']) + list(scenery.get('structures', ())):
        anchors = item.get('anchors') or [(mx, my, None) for mx, my in item.get('support_cells', ())]
        macros.update((mx, my) for mx, my, *_ in anchors)
    return macros


def _protected_cells(scenery):
    """Cells under every drawn prop or timber piece, plus a one-cell margin."""
    boxes = [(p['x'], p['y'], p['w'], p['h']) for p in scenery['props']]
    for structure in scenery.get('structures', ()):
        boxes.extend((p['x'], p['y'], p['w'], p['h']) for p in structure['pieces'])
    cells = set()
    for x, y, w, h in boxes:
        for cy in range(floor(y * SCALE) - 1, ceil((y + h) * SCALE) + 1):
            for cx in range(floor(x * SCALE) - 1, ceil((x + w) * SCALE) + 1):
                cells.add((cx, cy))
    return cells


def sculpt_caves(rows, scenery, entities, pools):
    """Return {'fill': [(x, y, kind)], 'carve': [(x, y)]} in simulation cells."""
    cave = _Map(rows)
    blocked_macros = _protected_macros(cave, scenery, entities, pools)
    blocked_cells = _protected_cells(scenery)
    fill, carve = {}, set()

    def free(cx, cy):
        return ((cx // SCALE, cy // SCALE) not in blocked_macros
                and (cx, cy) not in blocked_cells)

    def add(cx, cy, kind):
        if free(cx, cy) and cave.empty(cx // SCALE, cy // SCALE):
            fill[cx, cy] = kind

    def remove(cx, cy):
        mx, my = cx // SCALE, cy // SCALE
        if free(cx, cy) and cave.char(mx, my) == '#':
            carve.add((cx, cy))

    for my in range(1, cave.height - 1):
        for mx in range(1, cave.width - 1):
            if not cave.empty(mx, my) or (mx, my) in blocked_macros:
                continue
            tall = cave.span(mx, my, 0, 1) >= MIN_SPAN
            wide_right = cave.span(mx, my, 1, 0) >= MIN_SPAN
            wide_left = cave.span(mx, my, -1, 0) >= MIN_SPAN
            floor_row = cave.solid(mx, my + 1)
            # Uneven ceiling: 0-2 cells lower, or a one-cell pocket upward.
            if tall and cave.solid(mx, my - 1):
                kind = KINDS[cave.char(mx, my - 1)]
                for cx in range(mx * SCALE, mx * SCALE + SCALE):
                    level = _wave(cx, my * 7 + 3, 5)
                    if level < 0.14 and kind == DIRT:
                        remove(cx, my * SCALE - 1)
                    for depth in range(2 if level > 0.78 else (1 if level > 0.44 else 0)):
                        add(cx, my * SCALE + depth, kind)
            # Rounded upper corners where a ceiling meets a wall.
            for side, wide in ((-1, wide_right), (1, wide_left)):
                if tall and wide and cave.solid(mx, my - 1) and cave.solid(mx + side, my) \
                        and cave.solid(mx + side, my - 1):
                    kind = KINDS[cave.char(mx + side, my)]
                    radius = 4 + coordinate_hash(mx, my * 3 + side) % 3
                    for j in range(radius):
                        for i in range(radius):
                            if (radius - i - 0.5) ** 2 + (radius - j - 0.5) ** 2 > radius ** 2:
                                cx = mx * SCALE + (i if side < 0 else SCALE - 1 - i)
                                add(cx, my * SCALE + j, kind)
            # Upper walls: shallow bumps and cavities, never at floor level.
            if floor_row:
                continue
            for side, wide in ((-1, wide_right), (1, wide_left)):
                if not (wide and cave.solid(mx + side, my)):
                    continue
                kind = KINDS[cave.char(mx + side, my)]
                edge = mx * SCALE if side < 0 else mx * SCALE + SCALE - 1
                for cy in range(my * SCALE, my * SCALE + SCALE):
                    level = _wave(cy, mx * 11 + side, 4)
                    if level > 0.7:
                        add(edge, cy, kind)
                    elif level < 0.16 and kind == DIRT:
                        remove(edge + side, cy)
    return {'fill': sorted((x, y, kind) for (x, y), kind in fill.items()),
            'carve': sorted(carve)}
