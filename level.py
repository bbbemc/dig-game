"""Shared level constants, validation, and stage loading."""

from collections import Counter, deque
from config import SCALE

WIDTH, HEIGHT = 24, 16
EMPTY, DIRT, ROCK, WATER, LAVA, STONE = range(6)
DIGGABLE = {DIRT}
FLUIDS = {WATER, LAVA}


def build_level(stage=1):
    """Build the selected stage from its own layout module."""
    if stage == 2:
        from levels.stage_two import build_stage_two
        return build_stage_two()
    if stage == 3:
        from levels.stage_three import build_stage_three
        return build_stage_three()
    if stage != 1:
        raise ValueError(f"Unknown stage: {stage}")
    from levels.stage_one import build_stage_one
    return build_stage_one()


def validate_level(rows, entities):
    height, width = len(rows), len(rows[0])
    assert height == HEIGHT and width == WIDTH and all(len(row) == width for row in rows)
    assert len(entities["P"]) == len(entities["E"]) == 1
    assert all(ch in "#RS" for ch in rows[0] + rows[-1])
    assert all(row[0] in "#RS" and row[-1] in "#RS" for row in rows)
    for kind in ("P", "E", "M", "G"):
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
    assert reachable("# S")
    counts = Counter("".join(rows))
    return {k: counts[k] / (width * height) for k in "#RS WL"}


def expand_level(rows, entities):
    mapping = {"#": DIRT, "R": ROCK, "S": ROCK, "W": WATER,
               "L": LAVA, " ": EMPTY}
    grid = []
    for row in rows:
        expanded = [mapping[ch] for ch in row for _ in range(SCALE)]
        for _ in range(SCALE):
            grid.append(expanded.copy())
    return grid, {kind: [(x * SCALE, y * SCALE) for x, y in points]
                  for kind, points in entities.items()}
