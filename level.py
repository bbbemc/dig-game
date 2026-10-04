"""Hand-placed underground world. One map character is five simulation cells."""

from collections import Counter, deque

WIDTH, HEIGHT = 124, 100
SCALE = 5
EMPTY, DIRT, ROCK, WATER, LAVA, STONE = range(6)
DIGGABLE = {DIRT}
FLUIDS = {WATER, LAVA}


def build_level():
    rows = [["#"] * WIDTH for _ in range(HEIGHT)]

    def put(x, y, char):
        if 1 <= x < WIDTH - 1 and 1 <= y < HEIGHT - 1:
            rows[y][x] = char

    def ellipse(cx, cy, rx, ry, char=" "):
        for y in range(max(1, cy - ry), min(HEIGHT - 1, cy + ry + 1)):
            for x in range(max(1, cx - rx), min(WIDTH - 1, cx + rx + 1)):
                # Small fixed unevenness keeps caves organic without changing each run.
                edge = ((x * 17 + y * 11) % 9 - 4) * 0.025
                limit = 0.45 if char == " " else 1.0
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 < limit + edge:
                    put(x, y, char)

    def room(x1, y1, x2, y2):
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                put(x, y, " ")

    # Bedrock pockets and seams; they never make a full-width barrier.
    rocks = [
        (61, 6, 8, 3), (78, 18, 9, 3), (109, 23, 8, 3),
        (77, 27, 9, 4), (113, 42, 8, 4),
        (43, 56, 10, 4), (77, 53, 9, 4), (112, 63, 9, 4),
        (13, 84, 9, 4), (43, 75, 10, 4), (63, 92, 8, 3), (120, 84, 6, 5),
    ]
    for shape in rocks:
        ellipse(*shape, "R")
    # Small stone strata are solid too, but do not seal an entire layer.
    for x1, y, length in [(3, 25, 23), (57, 24, 21), (96, 49, 23),
                          (2, 50, 22), (49, 73, 23), (3, 75, 20)]:
        for yy in range(y, y + 2):
            for xx in range(x1, x1 + length):
                put(xx, yy, "R")

    # B1: a small prison start and isolated dirt-wrapped cave pockets.
    room(5, 4, 16, 10)
    for shape in [(40, 12, 10, 4), (77, 9, 8, 4), (103, 18, 10, 5),
                  (28, 5, 5, 3), (69, 20, 6, 3)]:
        ellipse(*shape)
    # B2: disconnected mine galleries, shafts, and several dead ends.
    for x1, y1, x2, y2 in [(88, 29, 115, 32), (54, 36, 79, 39),
                           (18, 42, 43, 45), (5, 31, 20, 33),
                           (97, 43, 107, 46)]:
        room(x1, y1, x2, y2)
    for shape in [(110, 36, 6, 4), (66, 29, 6, 3), (36, 33, 7, 4),
                  (10, 46, 6, 3), (53, 47, 5, 3)]:
        ellipse(*shape)
    # B3: natural caverns and enclosed ancient rooms.
    for shape in [(22, 57, 13, 6), (59, 60, 14, 7), (99, 56, 12, 6),
                  (92, 70, 10, 4), (10, 69, 7, 4), (46, 69, 6, 4)]:
        ellipse(*shape)
    room(33, 53, 40, 58)
    room(74, 66, 82, 71)
    # B4: broken volcanic caves lead to a quiet boss approach.
    for shape in [(21, 82, 12, 6), (47, 84, 10, 5), (62, 78, 6, 3),
                  (54, 95, 5, 2)]:
        ellipse(*shape)
    room(62, 86, 72, 89)  # boss entrance, no ordinary monsters
    room(77, 78, 117, 96)  # 41 x 19 boss arena
    # Ancient/volcanic rim with one breakable main entrance on the west.
    for y in range(77, 98):
        for x in (76, 118):
            put(x, y, "R")
    for x in range(76, 119):
        put(x, 77, "R")
        put(x, 97, "R")
    for x in range(95, 102):
        put(x, 77, "#")  # diggable roof beneath the boss lava reservoir
    for y in range(86, 90):
        put(76, y, "#")
    # Ground/platforms inside the arena; boss and player have room to move.
    for x in range(82, 92):
        put(x, 92, "R")
    for x in range(101, 112):
        put(x, 87, "R")
    # The visible side pool stays in its own stone basin until the player digs.
    for y in range(89, 97):
        put(108, y, "R")
    for x in range(108, 118):
        put(x, 95, "R")

    # Enclosed fluid reservoirs. Pairs have 2-5 tiles of intact terrain.
    water_pools = [
        (25, 15, 5, 3), (59, 17, 7, 3), (102, 7, 6, 3),
        (81, 30, 6, 3), (45, 49, 6, 3), (82, 59, 7, 3),
        (71, 81, 4, 3),
    ]
    lava_pools = [
        (82, 35, 6, 3), (46, 54, 6, 3), (83, 64, 7, 3),
        (36, 77, 6, 3), (68, 75, 4, 3), (109, 91, 7, 3),
        (95, 72, 7, 3),
    ]
    for pools, char in ((water_pools, "W"), (lava_pools, "L")):
        for x, y, w, h in pools:
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    put(xx, yy, char)

    for x in range(WIDTH):
        rows[0][x] = rows[-1][x] = "R"
    for row in rows:
        row[0] = row[-1] = "R"

    entities = {"P": [(10, 7)], "E": [(98, 96)],
                "M": [(43, 12), (100, 19), (100, 31), (70, 38),
                      (31, 44), (104, 45), (20, 58), (60, 62),
                      (97, 57), (91, 70), (20, 83), (46, 85)]}
    optional_rooms = [(28, 5), (69, 20), (10, 46), (53, 47),
                      (10, 69), (46, 69), (54, 95), (104, 45)]
    decorations = [
        ("crate", 7, 8), ("torch", 14, 5), ("bones", 102, 19),
        ("support", 94, 29), ("cart", 106, 31), ("ladder", 61, 36),
        ("support", 29, 42), ("lantern", 37, 42), ("mushroom", 12, 46),
        ("crystal", 20, 57), ("ruins", 35, 54), ("bones", 98, 56),
        ("crystal", 61, 59), ("ruins", 76, 67), ("bones", 66, 86),
        ("torch", 71, 86), ("ruins", 80, 80), ("bones", 113, 94),
    ]
    return ["".join(row) for row in rows], entities, decorations, optional_rooms


def validate_level(rows, entities):
    assert len(rows) == HEIGHT and all(len(row) == WIDTH for row in rows)
    assert len(entities["P"]) == len(entities["E"]) == 1
    assert all(ch == "R" for ch in rows[0] + rows[-1])
    assert all(row[0] == row[-1] == "R" for row in rows)
    for kind in ("P", "E", "M"):
        for x, y in entities[kind]:
            assert 0 < x < WIDTH - 1 and 0 < y < HEIGHT - 1
            assert rows[y][x] == " ", (kind, x, y)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in "WL":
                assert not any(0 <= nx < WIDTH and 0 <= ny < HEIGHT and
                               rows[ny][nx] in ("L" if ch == "W" else "W")
                               for nx, ny in ((x - 1, y), (x + 1, y),
                                              (x, y - 1), (x, y + 1)))
    assert all(rows[y][x] == " " for y in range(79, 86) for x in range(79, 113))
    # A route may cross dirt, but cannot require breaking unbreakable rock.
    start, goal = entities["P"][0], entities["E"][0]
    queue, seen = deque([start]), {start}
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            break
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) not in seen and 0 <= nx < WIDTH and 0 <= ny < HEIGHT and rows[ny][nx] in "# ":
                seen.add((nx, ny))
                queue.append((nx, ny))
    else:
        raise AssertionError("No diggable path from spawn to boss")
    # Digging is mandatory: existing empty spaces must not form a full route.
    queue, seen = deque([start]), {start}
    while queue:
        x, y = queue.popleft()
        assert (x, y) != goal, "Boss is reachable without digging"
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) not in seen and 0 <= nx < WIDTH and 0 <= ny < HEIGHT and rows[ny][nx] == " ":
                seen.add((nx, ny))
                queue.append((nx, ny))
    counts = Counter("".join(rows))
    return {k: counts[k] / (WIDTH * HEIGHT) for k in "#R WL"}


def expand_level(rows, entities):
    mapping = {"#": DIRT, "R": ROCK, "W": WATER, "L": LAVA, " ": EMPTY}
    grid = []
    for row in rows:
        expanded = [mapping[ch] for ch in row for _ in range(SCALE)]
        for _ in range(SCALE):
            grid.append(expanded.copy())
    return grid, {kind: [(x * SCALE, y * SCALE) for x, y in points]
                  for kind, points in entities.items()}
