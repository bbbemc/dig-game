"""The hidden two-floor mine between a stage's main level and its return door."""

from level import HEIGHT, WIDTH
from levels.common import stage_scenery
from scenery import _Placement
from tiles import SPRITES


def build_bonus_stage():
    width, height = WIDTH * 2, HEIGHT * 2 + 2
    rows = [['#'] * width for _ in range(height)]
    for y in range(1, 32):
        for x in range(1, width - 1):
            rows[y][x] = ' '

    def profile(points):
        values = []
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            span = x1 - x0
            values.extend(round(y0 + (y1 - y0) * step / span)
                          for step in range(span))
        values.append(points[-1][1])
        return values

    def fill_columns(surface, top, bottom, material='#'):
        for x, first_y in enumerate(surface, 1):
            for y in range(first_y, bottom + 1):
                rows[y][x] = material

    # Uneven ceiling and floor profiles make each chamber feel like a cave.
    ceiling = profile([(1, 3), (7, 1), (14, 2), (21, 1), (29, 3),
                       (36, 1), (42, 2), (46, 1)])
    for x, last_y in enumerate(ceiling, 1):
        for y in range(1, last_y + 1):
            rows[y][x] = '#'

    upper_floor = profile([(1, 15), (6, 14), (11, 16), (17, 14),
                           (22, 13), (28, 16), (34, 14), (39, 13),
                           (44, 15), (46, 14)])
    fill_columns(upper_floor, 0, 16)

    # An uneven rock seam separates the floors, thickening into outcrops.
    seam_top = profile([(1, 18), (6, 17), (11, 18), (16, 17),
                        (19, 16), (23, 17), (27, 18), (32, 17),
                        (36, 16), (40, 17), (46, 18)])
    for x, top in enumerate(seam_top, 1):
        for y in range(top, 19):
            rows[y][x] = 'R'

    # Natural rock ribs rise from the seam beneath the upper shooter and
    # from the lower cave floor beneath its two shooters.
    for x, top in zip(range(16, 23), (16, 15, 14, 14, 15, 16, 17)):
        for y in range(top, 19):
            rows[y][x] = 'R'

    # The lower chamber has its own sloping roof and a rolling dirt floor.
    lower_ceiling = profile([(1, 20), (9, 19), (17, 20), (25, 19),
                             (33, 20), (40, 19), (46, 20)])
    for x, first_y in enumerate(lower_ceiling, 1):
        for y in range(first_y, 21):
            rows[y][x] = '#'
    lower_floor = profile([(1, 30), (6, 30), (11, 28), (16, 29),
                           (21, 27), (27, 28), (33, 26), (39, 28),
                           (44, 27), (46, 29)])
    fill_columns(lower_floor, 0, 31)

    for x, top in zip(range(15, 22), (30, 29, 28, 28, 29, 30, 31)):
        for y in range(top, 32):
            rows[y][x] = 'R'
    for x, top in zip(range(33, 40), (29, 28, 27, 27, 28, 29, 30)):
        for y in range(top, 32):
            rows[y][x] = 'R'

    # Keep a clear ladder shaft through the rock seam and lower roof.
    for y in range(14, 22):
        for x in range(44, 47):
            rows[y][x] = ' '

    rows = [''.join(row) for row in rows]
    door = (8, 13, 1, 2)
    scenery = stage_scenery(rows, door, [(5, 13)])
    scenery['key_pickup'] = (6, 29)
    layout = _Placement(rows, SPRITES)
    layout.ladder(45, 26, width=0.8, top=5)
    layout.ceiling('cobweb', 11, 3, 0.8, 0.8, layer='back', search=0)
    layout.floor('crate', 8, 16, 0.9, 0.9, layer='back', search=0)
    layout.floor('blue_crystal', 29, 16, 0.8, 1.0, layer='back', search=0)
    layout.floor('small_rocks', 9, 31, 0.8, 0.45, layer='back', search=0)
    layout.floor('torch', 34, 31, 0.55, 1.0, layer='back', search=0)
    scenery['props'] = layout.props

    entities = {
        'P': [(8, 14)],
        'E': [(door[0], door[1])],
        'M': [(19, 12), (18, 25), (36, 24)],
        'G': [(27, 12)],
    }
    return rows, entities, scenery, []


def build_water_bonus_stage():
    """A fully submerged cavern, modestly larger than a regular stage."""
    width, height = 28, 18
    rows = [['#'] + ['W'] * (width - 2) + ['#']
            for _ in range(height)]
    rows[0] = rows[-1] = ['#'] * width

    door = (3, 15, 1, 2)
    dirt_column_x = door[0] + 2
    for y in range(13, 17):
        rows[y][dirt_column_x] = '#'
    for x in range(dirt_column_x, dirt_column_x + 3):
        rows[16][x] = '#'
    scenery = stage_scenery(rows, door, [(6, 14)])
    scenery['key_pickup'] = (24, 4)
    entities = {
        'P': [(door[0], door[1])],
        'E': [(door[0], door[1])],
        'M': [(8, 6), (22, 11)],
        'G': [],
    }
    rows = [''.join(row) for row in rows]
    return rows, entities, scenery, []


def build_final_boss_bonus_stage():
    """Extract Stage 6's boss arena as the Stage 5.5 final encounter."""
    from copy import deepcopy

    from levels.expanded import build_stage

    source_rows, source_entities, source_scenery, _ = build_stage(6)
    x0, top, x1, bottom = source_scenery['boss_arena']
    left, right = x0 - 1, x1 + 1
    upper, lower = top - 1, bottom + 1
    rows = [list(row[left:right + 1]) for row in source_rows[upper:lower + 1]]
    width, height = len(rows[0]), len(rows)
    rows[0] = ['R'] * width
    rows[-1] = ['R'] * width
    for row in rows:
        row[0] = row[-1] = 'R'
    rows = [''.join(row) for row in rows]

    source_door = source_scenery['exit_door']
    entry_door = (source_door[0] - left, source_door[1] - upper,
                  source_door[2], source_door[3])
    exit_door = (width - 4, entry_door[1] + 1, 1, entry_door[3])
    boss_x, boss_y = source_entities['B'][0]
    player_spawn = (entry_door[0], entry_door[1])
    arena = (x0 - left, top - upper, x1 - left, bottom - upper)
    scenery = stage_scenery(rows, exit_door)
    scenery.update({
        'entry_door': entry_door,
        'boss_arena': arena,
        'boss_hp': source_scenery['boss_hp'],
        'final_boss_room': True,
        'seed': source_scenery['seed'],
    })

    def shift_box(box):
        x, y, w, h = box
        return (x - left, y - upper, w, h)

    def in_room(item):
        return (left <= item['x'] and item['x'] + item['w'] <= right + 1
                and upper <= item['y'] and item['y'] + item['h'] <= lower + 1)

    def shift_item(item):
        item = deepcopy(item)
        item['x'] -= left
        item['y'] -= upper
        if 'support' in item:
            item['support'] = (item['support'][0] - left,
                               item['support'][1] - upper)
        if 'support_cells' in item:
            item['support_cells'] = [(x - left, y - upper)
                                     for x, y in item['support_cells']]
        if 'occupancy_rects' in item:
            item['occupancy_rects'] = [shift_box(box)
                                       for box in item['occupancy_rects']]
        if 'pieces' in item:
            for piece in item['pieces']:
                piece['x'] -= left
                piece['y'] -= upper
        if 'anchors' in item:
            item['anchors'] = [(x - left, y - upper, attachment)
                               for x, y, attachment in item['anchors']]
        if 'lamps' in item:
            for lamp in item['lamps']:
                lamp['x'] -= left
                lamp['y'] -= upper
        if 'contact_shadow' in item:
            item['contact_shadow'] = [(x - left, width)
                                      for x, width in item['contact_shadow']]
        return item

    scenery['props'] = [shift_item(item) for item in source_scenery['props']
                        if in_room(item)]
    scenery['structures'] = [
        shift_item(item) for item in source_scenery['structures']
        if in_room(item)]
    scenery['materials'] = {
        (x - left, y - upper): material
        for (x, y), material in source_scenery['materials'].items()
        if left <= x <= right and upper <= y <= lower
    }

    entities = {
        'P': [player_spawn],
        'E': [(entry_door[0], entry_door[1])],
        'M': [],
        'G': [],
        'B': [(boss_x - left, boss_y - upper)],
    }
    return rows, entities, scenery, []
