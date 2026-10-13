def stage_scenery(rows, exit_door, bomb_spawns=()):
    materials = {}
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            if char in "#RS":
                materials[x, y] = ('stone' if char == 'S' else
                                   ('deep' if y > 10 else 'dirt'))
    return {
        'props': [],
        'structures': [],
        'materials': materials,
        'lights': [],
        'exit_door': exit_door,
        'bomb_spawns': bomb_spawns,
    }


def build_empty_stage(exit_door):
    from level import HEIGHT, WIDTH

    rows = [['#'] * WIDTH for _ in range(HEIGHT)]
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            rows[y][x] = ' '
    for x in range(1, WIDTH - 1):
        rows[HEIGHT - 2][x] = '#'

    rows = [''.join(row) for row in rows]
    entities = {
        'P': [(2, HEIGHT - 4)],
        'E': [(exit_door[0], exit_door[1])],
        'M': [],
        'G': [],
    }
    return rows, entities, stage_scenery(rows, exit_door), []
