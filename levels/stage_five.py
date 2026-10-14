"""The Sinking Mine: breach a flooded tank, cool a lava seam, then dig below."""

from levels.common import stage_scenery


def build_stage_five():
    from level import HEIGHT, WIDTH
    from scenery import _Placement
    from tiles import SPRITES

    rows = [['#'] * WIDTH for _ in range(HEIGHT)]
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            rows[y][x] = ' '

    def fill(x1, y1, x2, y2, material='#'):
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                rows[y][x] = material

    # Starting nook and the dirt wall the player must excavate through.
    fill(1, 7, 5, 9)
    fill(6, 1, 6, 7)

    # Upper enemy floor; leave the right end open for the bomb pickup.
    fill(7, 7, 19, 7)

    # Purple-marked earth closes the upper approach and frames a sealed,
    # blue-marked reservoir. Digging the floor releases the water.
    fill(15, 1, 18, 5)
    fill(18, 1, 22, 1)
    fill(18, 2, 18, 6)
    fill(22, 2, 22, 6)
    fill(18, 6, 22, 7)
    for y in range(2, 6):
        for x in range(19, 22):
            rows[y][x] = 'W'

    # Purple-marked lava reaches both edges of the playable map. The rock
    # boundary remains intact so the liquid stays inside the mine.
    for x in range(1, WIDTH - 1):
        rows[8][x] = 'L'
    # Build the lower water pocket before the marked yellow zone is cleared.
    fill(1, 9, 22, 14)
    fill(8, 10, 16, 13, ' ')
    for x in range(9, 15):
        rows[10][x] = 'W'
    fill(8, 11, 16, 11, '#')

    # Open the lower guard room above a two-row dirt floor.
    fill(7, 12, 18, 12, ' ')
    fill(7, 13, 18, 14, '#')

    # A separate exit pocket, reached through the lower bank.
    fill(20, 10, 22, 13, ' ')
    fill(19, 10, 19, 14, '#')

    # Replace green-marked dirt with bombable stone around the open rooms.
    for y in range(9, 15):
        for x in range(4, 20):
            if rows[y][x] == '#':
                rows[y][x] = 'S'
    # Make only the leftmost stone-frame column diggable.
    fill(4, 9, 4, 14, '#')

    # The yellow-marked rectangle is an open cavern: remove its water and
    # stone so the guard room has a clear central space.
    fill(7, 10, 18, 13, ' ')

    rows = [''.join(row) for row in rows]
    entities = {
        'P': [(2, 6)],
        'E': [(21, 12)],
        'M': [(10, 6), (14, 6), (12, 12)],
        'G': [],
    }
    door = (21, 12, 1, 2)
    # Keep the original pickup on the far right and add two more beside it.
    scenery = stage_scenery(rows, door, [(15, 6), (16, 6), (17, 6)])
    # Give the marked strip the normal brown dirt appearance at every depth.
    # The rest of the lower frame stays bombable stone.
    for y in range(9, 15):
        scenery['materials'][4, y] = 'dirt'

    layout = _Placement(rows, SPRITES)
    layout.mine_set(1.2, 3.2, 5, lamp=2.0, braces=False)
    layout.floor('small_rocks', 4.2, 6, 0.55, 0.45,
                 layer='back', search=0)
    layout.ceiling('stone_stalactite', 8.5, 3, 0.8, 0.9,
                   layer='back', search=0)
    layout.floor('blue_crystal', 18.2, 5, 0.65, 0.8,
                 layer='back', search=0)
    layout.floor('torch', 21.8, 10, 0.4, 1.0,
                 (2.8, (255, 172, 70)), layer='back')
    scenery['props'] = layout.props
    scenery['structures'] = layout.structures
    scenery['lights'] = []
    return rows, entities, scenery, []
