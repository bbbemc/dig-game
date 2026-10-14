"""Water Chamber: swim under a rock barrier, collect a bomb, and open the exit."""

from levels.common import stage_scenery


def build_stage_four():
    from level import HEIGHT, WIDTH
    from scenery import _Placement
    from tiles import SPRITES

    rows = [['#'] * WIDTH for _ in range(HEIGHT)]
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            rows[y][x] = ' '

    def fill(x1, y1, x2, y2, material):
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                rows[y][x] = material

    # High start bank on the left and a stone landing shelf at the exit.
    fill(1, 7, 4, 14, '#')
    fill(16, 7, 22, 7, 'R')

    # Extend the dirt barrier through the upper chamber as marked.
    fill(12, 1, 15, 7, '#')

    # Add depth below the pool so its surface rises into the side pockets.
    for y in range(8, 15):
        for x in range(5, 23):
            rows[y][x] = 'W'

    # Rock piers create the submerged route. The low middle pier is moved
    # left, as in the revised sketch.
    fill(7, 8, 7, 12, 'R')
    fill(15, 8, 15, 12, 'R')
    fill(10, 12, 10, 14, 'R')
    fill(20, 12, 20, 14, 'R')

    # Rock closes the surface gap between the tall piers; swim underneath it.
    fill(8, 8, 14, 8, 'R')

    # A breakable stone gate blocks the dry path to the exit.
    fill(19, 6, 19, 7, 'S')

    rows = [''.join(row) for row in rows]
    entities = {
        'P': [(2, 6)],
        'E': [(21, 6)],
        'M': [(17, 6)],
        'G': [],
    }
    door = (21, 5, 1, 2)
    scenery = stage_scenery(rows, door, [(20, 11)])

    layout = _Placement(rows, SPRITES)
    layout.mine_set(1.2, 3.1, 5, lamp=2.0, braces=False)
    layout.floor('small_rocks', 3.2, 6, 0.55, 0.45,
                 layer='back', search=0)
    layout.ceiling('stone_stalactite', 11.4, 3, 0.85, 0.95,
                   layer='back', search=0)
    layout.floor('blue_crystal', 18.4, 6, 0.65, 0.8,
                 layer='back', search=0)
    scenery['props'] = layout.props
    scenery['structures'] = layout.structures
    scenery['lights'] = []
    return rows, entities, scenery, []
