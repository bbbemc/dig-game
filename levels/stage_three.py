"""Dirt Caverns: a flooded cache, ladder shaft and lava-crossing tunnel."""

from levels.common import stage_scenery


def build_stage_three():
    from level import HEIGHT, WIDTH
    from scenery import _Placement
    from tiles import SPRITES

    rows = [['R'] * WIDTH for _ in range(HEIGHT)]
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            rows[y][x] = ' '

    def platform(x1, y1, x2, y2=None, material='#'):
        y2 = y1 if y2 is None else y2
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                rows[y][x] = material

    # A raised starting shelf overlooks the dirt-filled left chamber.
    platform(1, 7, 7)
    platform(1, 8, 7, 14)
    # Keep the shaft open beside the starting chamber.
    platform(8, 14, 11, 14)

    # An abandoned flooded cache fills the upper-right room.
    platform(16, 1, 16, 5)
    platform(22, 1, 22, 5)
    platform(17, 5, 21, 5)
    for y in range(2, 5):
        for x in range(17, 22):
            rows[y][x] = 'W'

    # The right chamber stays dirt-filled except for the door.
    platform(22, 11, 22, material='#')
    platform(19, 14, 22, material='#')

    # Fill the marked right chamber with diggable dirt, leaving only the door
    # and the purple shooter alcove clear.
    for y in range(6, 15):
        for x in range(15, 23):
            rows[y][x] = '#'
    rows[12][21] = ' '
    rows[6][15] = ' '
    rows[7][15] = ' '
    platform(15, 8, 16, material='#')

    # Lava follows the green-marked stepped channel. A dirt cell at its left
    # edge contains the pool and prevents it flowing back into the shaft.
    for y, x1, x2 in ((14, 12, 16), (13, 15, 16),
                      (12, 15, 16), (11, 17, 21), (10, 17, 21)):
        for x in range(x1, x2 + 1):
            rows[y][x] = 'L'
    for y in range(10, 15):
        rows[y][17] = 'L'
    rows[13][11] = '#'
    rows[11][16] = '#'
    platform(12, 13, 14, material='#')
    platform(14, 12, 16, material='#')
    for y in range(12, 15):
        for x in (17, 18):
            rows[y][x] = 'L'

    rows = [''.join(row) for row in rows]
    entities = {
        'P': [(3, 6)],
        'E': [(21, 12)],
        'M': [(15, 7)],
        'G': [],
    }
    door = (21, 12, 1, 2)
    scenery = stage_scenery(rows, door, [(5, 6), (6, 6), (10, 13)])

    layout = _Placement(rows, SPRITES)
    layout.ladder(8, 13, width=0.85, top=8)
    layout.mine_set(1.3, 3.2, 6, lamp=2.2, braces=False)
    layout.floor('toolbox', 5.2, 6, 0.8, 0.64, search=0)
    layout.floor('small_rocks', 6.3, 6, 0.5, 0.5, search=0)
    layout.rails(9.2, 10.8, 14)
    layout.floor('torch', 20.2, 11, 0.4, 1.0,
                 (2.8, (255, 172, 70)), layer='back')
    layout.ceiling('dirt_stalactite', 12.2, 3, 0.8, 0.9,
                   layer='back', search=0)
    layout.floor('small_rocks', 11.2, 13, 0.5, 0.45,
                 layer='back', search=0)
    scenery['props'] = layout.props
    scenery['structures'] = layout.structures
    scenery['lights'] = []
    return rows, entities, scenery, []
