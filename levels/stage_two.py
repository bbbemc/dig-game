"""The Sinking Mine: waterline, dirt shelves, floating ledges and enemies."""

from levels.common import stage_scenery


def build_stage_two():
    from level import HEIGHT, WIDTH
    from scenery import _Placement
    from tiles import SPRITES

    rows = [['#'] * WIDTH for _ in range(HEIGHT)]
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            rows[y][x] = ' '

    def platform(x1, y1, x2, y2=None):
        y2 = y1 if y2 is None else y2
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                rows[y][x] = 'S'

    # Keep only a thin stone floor below a deep, broad water basin.
    platform(1, 14, WIDTH - 2)
    platform(1, 9, 4)
    platform(21, 9, 22)
    for y in range(9, 14):
        rows[y][4] = 'W'
        for x in range(5, 21):
            rows[y][x] = 'W'
    for y in range(10, 14):
        for x in range(1, 23):
            rows[y][x] = 'W'

    # Lowered shooter shelf and jump-sized ledges across the upper chamber.
    platform(1, 6, 3)
    platform(5, 8, 6)
    platform(9, 7, 10)
    platform(13, 6, 14)
    platform(17, 6, 20)

    rows = [''.join(row) for row in rows]
    entities = {
        'P': [(2, 8)],
        'E': [(19, 5)],
        'M': [(3, 5), (21, 8)],
        'G': [],
    }
    door = (19, 3, 2, 3)
    scenery = stage_scenery(rows, door, [(6, 7), (10, 6)])
    scenery['enemy_spawn_offsets'] = {'M': [(-2, 0)]}
    layout = _Placement(rows, SPRITES)
    layout.floor('small_rocks', 5.2, 7, 0.55, 0.45, layer='back', search=0)
    layout.floor('blue_crystal', 9.0, 6, 0.65, 0.8, layer='back', search=0)
    layout.ceiling('stone_stalactite', 11.5, 3, 0.85, 0.95,
                   layer='back', search=0)
    layout.floor('small_rocks', 17.5, 5, 0.55, 0.45, layer='back', search=0)
    scenery['props'] = layout.props
    return rows, entities, scenery, []
