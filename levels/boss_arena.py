"""Stage 5.5: the Colossus's arena, an authored hall built for the final fight.

The room is wider than the view (44 x 21 macros against the 24 x 16 screen)
and tall enough that the 134 px boss has over three times its height of air
above it. Floating ledges at different heights let the miner climb away from
a swing: every ledge clears the boss's head, so it walks beneath them, and
each is reached by a ladder. The dirt cores of the two middle ledges and two
cracked floor patches can be dug (a drop-through hole, or a foxhole below
the greatsword's reach); everything else is ancient stone.

All positions are macro tiles. Decoration only uses the shared sprite sheet,
so the arena keeps the Deep Descent's palette; arena_backdrop.py paints the
parallax depth seen through the open middle of the hall.
"""

from math import floor

from scenery import _Placement, _hung_lamp, _piece
from tiles import SPRITES

WIDTH, HEIGHT = 44, 21
FLOOR = 18                  # top row of the arena floor
CEILING = 2                 # lowest row of the flat ceiling
ENTRY_DOOR = (2, 16, 1, 2)
EXIT_DOOR = (41, 16, 1, 2)
PLAYER_SPAWN = (2, 16)
BOSS_SPAWN = (31, 14)
BOSS_PATROL = (24, 40)      # macros it paces until it spots the miner
LOCK_COLUMN = 7             # crossing this column seals both gates
# Floating ledges: (left, right, row, materials). '#' is diggable dirt.
PLATFORMS = (
    (8, 12, 13, 'R###R'),            # left, over the boss's head
    (16, 23, 9, 'RRRRRRRR'),         # the high altar in the middle
    (31, 35, 13, 'R###R'),           # right, above the boss's spawn
    (37, 41, 8, 'RRRRR'),            # high shelf on the right wall
)
LADDERS = ((7, 12), (15, 8), (36, 7))   # (column, top row)
CRACKED_FLOOR = ((18, 20), (26, 28))    # dirt patches in the top floor row
STALACTITES = (7, 8, 13, 25, 26, 33, 40)  # ceiling bumps one row lower

WARM = (3.2, (255, 172, 70))
BLUE = (2.6, (64, 147, 255))
PURPLE = (2.6, (178, 86, 247))
EMBER = (2.2, (255, 91, 38))
AMBIENT = (150, 136, 162)   # a darker, violet light map: flames and crystals carry the room


def _rows():
    rows = [[' '] * WIDTH for _ in range(HEIGHT)]
    for y in range(HEIGHT):
        for x in range(WIDTH):
            wall = x <= 1 or x >= WIDTH - 2
            if y <= CEILING or y >= FLOOR or wall:
                rows[y][x] = 'R'
    for x in STALACTITES:
        rows[CEILING + 1][x] = 'R'
    for left, right in CRACKED_FLOOR:
        for x in range(left, right + 1):
            rows[FLOOR][x] = '#'
    for left, right, y, materials in PLATFORMS:
        for x, char in zip(range(left, right + 1), materials):
            rows[y][x] = char
    return rows


def _materials(rows):
    """Masonry walls, carved stone floors and ledges, dark rock elsewhere."""
    materials = {}
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char == ' ':
                continue
            exposed = any(0 <= x + dx < WIDTH and 0 <= y + dy < HEIGHT
                          and rows[y + dy][x + dx] == ' '
                          for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if char == '#':
                materials[x, y] = 'ancient_dirt'
            elif (x <= 1 or x >= WIDTH - 2) and CEILING < y < FLOOR:
                materials[x, y] = 'dungeon'
            elif y >= FLOOR:
                materials[x, y] = 'ancient' if y == FLOOR else 'volcanic'
            elif y <= CEILING + 1 and y > 0:
                materials[x, y] = 'ore_blue' if exposed and (x * 7 + y) % 5 == 0 else 'dark'
            elif exposed:
                materials[x, y] = 'ancient'
            else:
                materials[x, y] = 'dark'
    return materials


def _ceiling_row(rows, x):
    """The lowest solid row of the ceiling above column ``x``."""
    y = 1
    while rows[y + 1][x] != ' ':
        y += 1
    return y


def _column(layout, x, top, bottom, width, shade=170):
    """A stone column of stacked dungeon_column sprites from ``top`` to ``bottom``."""
    rect = SPRITES['dungeon_column']['rect']
    span = bottom - top
    segment = width * rect[3] / rect[2]
    count = max(1, round(span / segment))
    height = span / count
    pieces = [_piece('sprite', x - width / 2, top + n * height, width, height,
                     name='dungeon_column') for n in range(count)]
    anchors = [(floor(x), bottom, 'floor')]
    if layout.solid(floor(x), top - 1):
        anchors.append((floor(x), top - 1, 'ceiling'))
    return layout.structure(pieces, anchors, layer='back', shade=shade,
                            contact=[(x - width / 2 - 0.1, width + 0.2)])


def _hanging(layout, rows, x, length, ornament=None, lamp=False):
    """A long chain from the high ceiling, ending in a banner or a lantern."""
    top = _ceiling_row(rows, floor(x)) + 1
    pieces, lamps = [], []
    if lamp:
        pieces, light = _hung_lamp(x, top, length)
        lamps.append(light)
    else:
        pieces.append(_piece('chain', x - 0.12, top, 0.24, length))
        if ornament == 'banner':
            pieces.append(_piece('sprite', x - 0.62, top + length - 0.1, 1.24, 1.9,
                                 name='banner'))
        elif ornament == 'bones':
            pieces.append(_piece('sprite', x - 0.6, top + length - 0.1, 1.2, 1.1,
                                 name='hanging_bones'))
    return layout.structure(pieces, [(floor(x), top - 1, 'ceiling')], layer='back',
                            lamps=lamps)


def _decorate(rows):
    layout = _Placement([''.join(row) for row in rows], SPRITES)
    for column, top in LADDERS:        # climbable props reserve their space first
        layout.ladder(column, FLOOR - 1, top=top)

    # Columns frame the hall and hold up the high ledges.
    _column(layout, 4.6, CEILING + 1, FLOOR, 1.5)
    _column(layout, 16.8, 10, FLOOR, 1.1)
    _column(layout, 22.2, 10, FLOOR, 1.1)
    _column(layout, 39.0, 9, FLOOR, 1.3)

    # Chains from the roof carry the two middle ledges, banners and lanterns,
    # so the height of the room reads at a glance.
    for left, right, y, _ in (PLATFORMS[0], PLATFORMS[2]):
        for x in (left + 0.3, right + 0.7):
            top = _ceiling_row(rows, floor(x)) + 1
            layout.structure([_piece('chain', x - 0.12, top, 0.24, y - top)],
                             [(floor(x), top - 1, 'ceiling')], layer='back')
    _hanging(layout, rows, 10.5, 3.2, 'banner')
    _hanging(layout, rows, 27.5, 5.0, 'banner')
    _hanging(layout, rows, 33.5, 3.4, 'banner')
    _hanging(layout, rows, 39.5, 1.6, 'banner')
    _hanging(layout, rows, 19.5, 2.6, lamp=True)
    _hanging(layout, rows, 29.5, 3.6, lamp=True)
    _hanging(layout, rows, 24.6, 1.4, 'bones')

    # Flames and crystals: warm pools along the floor, cold glints between.
    for x in (6, 13, 25, 30):
        layout.floor('torch', x, FLOOR - 1, 0.55, 1.9, WARM, search=0.5)
    layout.floor('torch', 16, 8, 0.5, 1.6, WARM, search=0.5)
    layout.floor('torch', 23, 8, 0.5, 1.6, WARM, search=0.5)
    layout.floor('torch', 40, 7, 0.5, 1.6, WARM, search=0.5)
    layout.wall('torch', 2, 11, 0.45, 1.5, side='left', glow=WARM)
    layout.wall('torch', 41, 12, 0.45, 1.5, side='right', glow=WARM)
    layout.floor('purple_crystal', 10, FLOOR - 1, 1.3, 1.5, PURPLE, layer='back')
    layout.floor('blue_crystal', 34, FLOOR - 1, 1.3, 1.5, BLUE, layer='back')
    layout.floor('red_crystal', 21, FLOOR - 1, 1.1, 1.3, EMBER, layer='back', search=1)
    layout.floor('small_purple_crystal', 9, 12, 0.55, 0.85, PURPLE, search=0.5)
    layout.floor('tiny_purple_cluster', 33, 12, 0.6, 0.65, search=0.5)
    layout.floor('small_purple_crystal', 20, 8, 0.55, 0.85, PURPLE, search=0.5)
    layout.ceiling('blue_crystal', 26, CEILING + 2, 0.9, 1.0, BLUE, flip=True, search=0.5)

    # Stalactites and the remains of earlier challengers.
    for x, name, w, h in ((5, 'stone_stalactite', 1.4, 1.5), (13, 'thin_stalactite', 0.5, 1.2),
                          (25, 'stone_stalactite', 1.2, 1.3), (33, 'thin_stalactite', 0.5, 1.1),
                          (8, 'thin_stalactite', 0.45, 0.9), (36, 'thin_stalactite', 0.45, 0.9)):
        layout.ceiling(name, x, CEILING + 2, w, h, search=0.5)
    for x, name, w, h, layer in ((11, 'bones', 1.0, 0.65, 'front'), (14, 'skull', 0.5, 0.65, 'front'),
                                 (19, 'ruin_rubble', 0.8, 1.0, 'back'), (24, 'broken_pillar', 0.8, 1.6, 'back'),
                                 (27, 'ribs', 0.7, 0.7, 'front'), (29, 'volcanic_rubble', 0.9, 0.7, 'back'),
                                 (37, 'small_skull', 0.45, 0.7, 'front'), (3, 'volcanic_rubble', 0.8, 0.6, 'back'),
                                 (35, 'small_stalagmite', 0.6, 0.95, 'back')):
        layout.floor(name, x, FLOOR - 1, w, h, layer=layer, search=1)
    layout.floor('ruin_pillar', 18, 8, 0.6, 0.9, layer='back', search=0.5)
    return layout


def build_boss_arena():
    rows = _rows()
    layout = _decorate(rows)
    rows = [''.join(row) for row in rows]
    scenery = {
        'props': layout.props,
        'structures': layout.structures,
        'materials': _materials(rows),
        'lights': [],
        'exit_door': EXIT_DOOR,
        'bomb_spawns': (),
        'entry_door': ENTRY_DOOR,
        'boss_arena': (2, CEILING + 1, WIDTH - 3, FLOOR - 1),
        'boss_patrol': BOSS_PATROL,
        'boss_hp': 3,
        'final_boss_room': True,
        'arena_lock_column': LOCK_COLUMN,
        'backdrop': True,
        'ambient': AMBIENT,
    }
    entities = {
        'P': [PLAYER_SPAWN],
        'E': [(ENTRY_DOOR[0], ENTRY_DOOR[1])],
        'M': [],
        'G': [],
        'B': [BOSS_SPAWN],
    }
    return rows, entities, scenery, []
