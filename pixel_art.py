"""Small hand-authored pixel sprites for things the supplied sheet lacks.

Each sprite is a character grid plus a palette, so it stays crisp at 1:1.
Mine rails, tools, a rope coil, a warning sign and a bomb sprite complete the
mine scenes; the miner's animation frames live here as well.
"""

import pygame

TOOL_COLORS = {
    'K': (30, 22, 20), 'H': (150, 98, 54), 'h': (104, 66, 36), 'L': (196, 138, 80),
    'M': (176, 182, 196), 'm': (112, 118, 134), 'W': (232, 236, 244),
    'R': (170, 128, 70), 'r': (118, 84, 44), 'Y': (226, 196, 120),
    'B': (156, 104, 58), 'b': (110, 70, 38), 'S': (238, 210, 140), 's': (196, 64, 44),
    'D': (40, 35, 47), 'd': (68, 59, 75), 'P': (105, 91, 108),
    'C': (177, 62, 45), 'c': (129, 43, 39), 'O': (245, 153, 55),
    'o': (255, 211, 101),
}

PICKAXE = (
    "..KKKK.......",
    ".KmMMMKKK....",
    "KmMWWMMMMKK..",
    "KmK.KHKmMMMK.",
    ".K..KHK.KmmK.",
    "....KHK..KK..",
    "....KHK......",
    "....KhK......",
    "....KHK......",
    "....KHK......",
    "....KhK......",
    "....KHK......",
    "....KHK......",
    "....KhK......",
    "....KHK......",
    "....KHK......",
    "....KhK......",
    "....KKK......",
)

SHOVEL = (
    "..KKK..",
    ".KHHHK.",
    "..KhK..",
    "..KHK..",
    "..KHK..",
    "..KhK..",
    "..KHK..",
    "..KHK..",
    "..KhK..",
    "..KHK..",
    ".KKKKK.",
    "KmMMMmK",
    "KmMWMmK",
    "KmMMMmK",
    "KmMMMmK",
    ".KmMmK.",
    "..KKK..",
)

ROPE = (
    "....KKKKKK....",
    "..KKRRYRRRKK..",
    ".KRRrKKKKrRRK.",
    "KRrK......KrRK",
    "KRK..KKKK..KRK",
    "KRrKKRRYRKKrRK",
    ".KRRRrKKrRRRK.",
    "..KKRRRRRRKK..",
    "....KKKKKKr...",
    "..........rK..",
)

SIGN = (
    "KKKKKKKKKKKKKKKK",
    "KBBBBBBBBBBBBBBK",
    "KBbBBBBKKBBBBbBK",
    "KBBBBBBKSKBBBBBK",
    "KBBBBBBKSKBBBBBK",
    "KbbbbbbKSKbbbbbK",
    "KBBBBBBKSKBBBBBK",
    "KBBBBBBBKBBBBBBK",
    "KBBBBBBKSKBBBBBK",
    "KBbBBBBBKBBBBbBK",
    "KKKKKKKKKKKKKKKK",
    "......KHHK......",
    "......KHhK......",
    "......KHHK......",
    "......KhHK......",
    "......KHHK......",
    "......KHHK......",
)

BOMB = (
    "...............KK......",
    "..............KYoK.....",
    ".............KYYoK.....",
    "............KYYoK......",
    "...........KYYoK.......",
    "..........KYYoK........",
    ".........KYYoK.........",
    "........KYYoK..........",
    ".......KKKKK...........",
    ".....KKDDDDDK..........",
    "...KKDDPPDDDDK.........",
    "..KDPPDDDDDDDK.........",
    ".KDDDDCCCCDDDDK........",
    ".KDDDDCCCCDDDDK........",
    "KDDPPDDDDDDDDDK........",
    "KDDDDDDDDPPDDDK........",
    ".KDDDDDDDDDDDDK........",
    ".KDDDDDDDDDDDDK........",
    "..KDDDDDDDDDDK.........",
    "...KKDDDDDDKK...........",
    ".....KKKKKK.............",
    "......................",
)

KEY = (
    "........................",
    ".....KKKKKK.............",
    "...KKYooYYKK............",
    "..KYooYYYYYKK...........",
    ".KYooYYYYYYYK............",
    ".KYooYYYYYYYK............",
    "..KYooYYYYYKK............",
    "...KKYooYYKK.............",
    ".....KKKKKK..............",
    ".........K................",
    ".........K................",
    ".........K................",
    ".........K................",
    ".........K................",
    ".........KKKKKKKKKKKKKKK..",
    ".........KYYooYYKKYYooYK..",
    ".........KKKKKKKKKKKKKKK..",
    ".................K.........",
    ".................K.........",
    ".................KKKKKK....",
    ".................KYYooK....",
    ".................KKKKKK....",
    "........................",
)

SPRITES = {'pickaxe': PICKAXE, 'shovel': SHOVEL, 'rope': ROPE, 'sign': SIGN,
           'bomb': BOMB, 'key': KEY}


def grid_surface(rows, colors):
    surface = pygame.Surface((max(len(r) for r in rows), len(rows)), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, key in enumerate(row):
            if key in colors:
                surface.set_at((x, y), (*colors[key], 255))
    return surface


def sprite(name):
    return grid_surface(SPRITES[name], TOOL_COLORS)


def rail(length):
    """Side view of a short track: rail head on sleepers, 7 pixels tall."""
    surface = pygame.Surface((length, 7), pygame.SRCALPHA)
    for x in range(2, length - 4, 10):
        surface.fill((40, 26, 18), (x, 3, 7, 4))
        surface.fill((104, 68, 40), (x + 1, 3, 5, 3))
        surface.fill((136, 92, 56), (x + 1, 3, 5, 1))
    surface.fill((34, 34, 42), (0, 0, length, 3))
    surface.fill((150, 156, 170), (0, 0, length, 1))
    surface.fill((96, 100, 116), (0, 1, length, 1))
    for x in range(6, length, 23):
        surface.set_at((x, 2), (190, 196, 210))
    return surface


# --------------------------------------------------------------------------
# The miner: 32 x 32, facing right, feet on the bottom row of the collision
# box. Frames are assembled from a head, a torso, arm overlays and legs.
# --------------------------------------------------------------------------

MINER_COLORS = {
    'K': (26, 19, 21), 'Y': (238, 180, 52), 'y': (186, 124, 36), 'W': (255, 230, 150),
    'L': (255, 248, 206), 'S': (238, 184, 138), 's': (198, 132, 96), 'E': (34, 24, 30),
    'B': (132, 80, 44), 'b': (92, 54, 30), 'C': (72, 116, 172), 'c': (50, 80, 126),
    'O': (156, 102, 58), 'o': (110, 70, 40), 'G': (66, 46, 34), 'g': (230, 198, 98),
    'T': (80, 52, 36), 't': (52, 34, 26), 'H': (156, 104, 58), 'h': (112, 72, 40),
    'M': (178, 184, 198), 'm': (112, 118, 134),
}

MINER_HEAD = (
    "......KKKKKKK.......",
    "....KKWWYYYYYKK.....",
    "...KWWYYYYYYYYYK....",
    "..KWYYYYYYYYYYYYKKK.",
    "..KWYYYYYYYYYYYYKLLK",
    "..KYYYYYYYYYYYYYKLLK",
    "..KyYYYYYYYYYYYyKKK.",
    ".KyyyyyyyyyyyyyyyyK.",
    ".KKKKKKKKKKKKKKKKKK.",
    "...KsSSSSSSSSSSSK...",
    "...KsSSSSSSSSESSK...",
    "...KsSSSSSSSSESSSK..",
    "...KbBSSSSSSSSSssK..",
    "...KbBBBBBBBBBBBBK..",
    "...KbBBBBBBBBBBBK...",
    "....KbBBBBBBBBBK....",
)

MINER_BODY = (
    "...KKKbBBBBBBKKK..",
    "..KCCCKKbBBBKKCCK.",
    "..KCCCCCKKKKKCCCCK",
    "..KcCCOOOOOOOOCCCK",
    "..KcCOOOOOOOOOCSSK",
    "..KcCOoOOOOOOOKSSK",
    "...KKGGGGgGGGGKKK.",
)

# The front arm reaching up (ladders, jumps): drawn over the body.
MINER_REACH = (
    ".KSSK",
    ".KSSK",
    "KCCCK",
    "KCCCK",
    "KCCK.",
    "KcCK.",
    "KcCK.",
)

# Pickaxe held out in front: raised (wind-up) and striking.
MINER_SWING = {
    'raise': (
        "......KKK...",
        ".....KmMMK..",
        "....KmMKKMK.",
        "...KHK...KK.",
        "..KHK.......",
        ".KHK........",
        "KSSK........",
        "KSSK........",
    ),
    'strike': (
        "............",
        "............",
        "............",
        "KSSKKHHHHKK.",
        "KSSKKhhhKmMK",
        "...........K",
        "..........KM",
        "...........K",
    ),
}

MINER_PICK = (
    "KKK.....",
    "KmMKK...",
    ".KmMMKK.",
    "..KKmMMK",
    "....KHKK",
    "...KHK..",
    "..KHK...",
    ".KhK....",
    "KHK.....",
)

MINER_LEGS = {
    'stand': (
        "....KOOOOOOOOK....",
        "....KOOOoKoOOK....",
        "....KOOoK.KoOK....",
        "....KOOoK.KoOK....",
        "...KTTTTK.KTTTTK..",
        "...KTTTTTKKTTTTTK.",
        "...KKKKKKKKKKKKKK.",
    ),
    'stride': (
        "....KOOOOOOOOK....",
        "...KOOOoKKoOOOK...",
        "..KOOoK...KoOOK...",
        "..KOoK.....KoOOK..",
        ".KTTTK.....KTTTTK.",
        "KtTTTK.....KTTTTTK",
        "KKKKK.......KKKKKK",
    ),
    'pass': (
        "....KOOOOOOOOK....",
        "....KOOOoKoOOK....",
        "....KOOoKKoOK.....",
        ".....KOoKoOOK.....",
        "....KTTTKTTTTK....",
        "...KTTTTKTTTTTK...",
        "...KKKKKKKKKKKK...",
    ),
    'tuck': (
        "....KOOOOOOOOK....",
        "...KOOOOoKoOOOK...",
        "..KTTTOoK.KoOTTTK.",
        "..KTTTTKK.KKTTTTK.",
        "...KKKKK...KKKKK..",
        "..................",
        "..................",
    ),
    'dangle': (
        "....KOOOOOOOOK....",
        "....KOOOoKoOOK....",
        "...KOOoK..KoOOK...",
        "...KOoK....KoOK...",
        "..KTTTK....KTTTK..",
        "..KTTTTK...KTTTTK.",
        "..KKKKKK...KKKKKK.",
    ),
    'step': (
        "....KOOOOOOOOK....",
        "....KOOOoKoOOK....",
        "....KOOoK.KoOOTK..",
        "....KOOoK.KTTTTTK.",
        "...KTTTTK.KKKKKK..",
        "...KTTTTTK........",
        "...KKKKKKK........",
    ),
}


def _miner_frame(legs, bob=0, reach=False, swing=None, pick=True):
    frame = pygame.Surface((32, 32), pygame.SRCALPHA)
    parts = lambda rows: grid_surface(rows, MINER_COLORS)
    # Boots occupy row 31, the bottom row of the collision box.
    if pick and swing is None:
        frame.blit(parts(MINER_PICK), (4, 12 + bob))
    frame.blit(parts(MINER_HEAD), (7, 3 + bob))
    frame.blit(parts(MINER_BODY), (7, 18 + bob))
    frame.blit(parts(MINER_LEGS[legs]), (7, 25 + (1 if legs == 'tuck' else 0)))
    if reach:
        frame.blit(parts(MINER_REACH), (21, 13 + bob))
    if swing:
        frame.blit(parts(MINER_SWING[swing]), (20, 15 + bob))
    return frame


def miner_frames():
    """Animation name -> frames facing right."""
    return {
        'idle': [_miner_frame('stand'), _miner_frame('stand', bob=1)],
        'walk': [_miner_frame('stride'), _miner_frame('pass', bob=-1),
                 _miner_frame('stride'), _miner_frame('pass', bob=-1)],
        'jump': [_miner_frame('tuck', reach=True)],
        'fall': [_miner_frame('dangle', reach=True)],
        'climb': [_miner_frame('step', reach=True), _miner_frame('stand', bob=1)],
        'dig': [_miner_frame('stand', swing='raise'), _miner_frame('stand', bob=1, swing='strike')],
    }
