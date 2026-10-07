"""Authored first stage. One map character is five simulation cells."""

from collections import Counter, deque
from scenery import build_first_stage_scenery
from config import SCALE

WIDTH, HEIGHT = 24, 16
EMPTY, DIRT, ROCK, WATER, LAVA, STONE = range(6)
DIGGABLE = {DIRT}
FLUIDS = {WATER, LAVA}


def build_level():
    """Build the ladder, exit and lower lava chamber shown in the stage sketch."""
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

    # The locked door is solid, undiggable terrain across the corridor.
    for y in range(8, 10):
        put(21, y, "R")

    for x in range(WIDTH):
        rows[0][x] = rows[-1][x] = "#"
    for row in rows:
        row[0] = row[-1] = "#"

    entities = {"P": [(3, 3)], "E": [(16, 9)], "M": [(13, 9)]}
    optional_rooms = []
    rows = ["".join(row) for row in rows]
    decorations = build_first_stage_scenery(rows)
    decorations["key_spawn"] = entities["P"][0]
    decorations["exit_door"] = (21, 8, 1, 2)
    # Candidate floor spots for bomb pickups (used only in stages with bombs).
    decorations["bomb_spawns"] = [(5, 3), (9, 9), (11, 9), (19, 9)]
    return rows, entities, decorations, optional_rooms


def validate_level(rows, entities):
    height, width = len(rows), len(rows[0])
    assert height == HEIGHT and width == WIDTH and all(len(row) == width for row in rows)
    assert len(entities["P"]) == len(entities["E"]) == 1
    assert all(ch in "#R" for ch in rows[0] + rows[-1])
    assert all(row[0] in "#R" and row[-1] in "#R" for row in rows)
    for kind in ("P", "E", "M"):
        for x, y in entities[kind]:
            assert 0 < x < width - 1 and 0 < y < height - 1
            assert rows[y][x] == " ", (kind, x, y)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in "WL":
                assert not any(0 <= nx < WIDTH and 0 <= ny < HEIGHT and
                               rows[ny][nx] in ("L" if ch == "W" else "W")
                               for nx, ny in ((x - 1, y), (x + 1, y),
                                              (x, y - 1), (x, y + 1)))
    start, goal = entities["P"][0], entities["E"][0]

    def reachable(allowed):
        queue, seen = deque([start]), {start}
        while queue:
            x, y = queue.popleft()
            if (x, y) == goal:
                return True
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if ((nx, ny) not in seen and 0 <= nx < width and 0 <= ny < height
                        and rows[ny][nx] in allowed):
                    seen.add((nx, ny))
                    queue.append((nx, ny))
        return False

    # The boss must remain reachable through the authored shelf and ladder.
    assert reachable("# ")
    counts = Counter("".join(rows))
    return {k: counts[k] / (width * height) for k in "#R WL"}


def expand_level(rows, entities):
    mapping = {"#": DIRT, "R": ROCK, "W": WATER, "L": LAVA, " ": EMPTY}
    grid = []
    for row in rows:
        expanded = [mapping[ch] for ch in row for _ in range(SCALE)]
        for _ in range(SCALE):
            grid.append(expanded.copy())
    return grid, {kind: [(x * SCALE, y * SCALE) for x, y in points]
                  for kind, points in entities.items()}
