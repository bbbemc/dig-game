"""The Sinking Mine authored stage."""

def build_stage_one():
    from level import HEIGHT, WIDTH
    from scenery import build_first_stage_scenery

    rows = [["#"] * WIDTH for _ in range(HEIGHT)]

    def put(x, y, char):
        if 1 <= x < WIDTH - 1 and 1 <= y < HEIGHT - 1:
            rows[y][x] = char

    def room(x1, y1, x2, y2, char=" "):
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                put(x, y, char)

    # Main chamber and level enemy/exit walkway.
    room(1, 1, 22, 9)
    for x in range(1, 23):
        put(x, 10, "#")

    # Raised dirt shelf at the spawn; the open shaft beside it holds the ladder.
    for y in range(4, 10):
        for x in range(1, 8):
            put(x, y, "#")
    # Water basin high on the right, held above the main room.
    for y in range(2, 4):
        put(14, y, "#")
        put(19, y, "#")
    for x in range(14, 20):
        put(x, 4, "#")
    for y in range(2, 4):
        for x in range(15, 19):
            put(x, y, "W")

    # Dirt around a narrow shaft and lower lava pool.
    for y in range(11, 14):
        for x in range(13, 19):
            put(x, y, " ")
        put(12, y, "#")
        put(19, y, "#")
    for x in range(12, 20):
        put(x, 14, "#")
    for y in range(12, 14):
        for x in range(13, 19):
            put(x, y, "L")

    for x in range(WIDTH):
        rows[0][x] = rows[-1][x] = "#"
    for row in rows:
        row[0] = row[-1] = "#"

    entities = {
        "P": [(3, 3)],
        "E": [(16, 9)],
        "M": [(13, 9)],
        "G": [(19, 9)],
    }
    rows = ["".join(row) for row in rows]
    scenery = build_first_stage_scenery(rows)
    scenery["exit_door"] = (21, 8, 1, 2)
    scenery["bomb_spawns"] = [(5, 3)]
    return rows, entities, scenery, []
