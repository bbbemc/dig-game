"""Shared level constants, validation, and stage loading."""

from collections import Counter, deque
from config import SCALE

WIDTH, HEIGHT = 24, 16
EMPTY, DIRT, ROCK, WATER, LAVA, STONE = range(6)
DIGGABLE = {DIRT}
FLUIDS = {WATER, LAVA}


FINAL_STAGE = 6
DEEP_STAGE = 6  # The Deep Descent: the procedurally generated large world


def build_level(stage=1, seed=None):
    """Build the selected stage as a large generated four-layer world.

    Stages 1-5 embed their original authored map as the opening chamber
    (see levels/expanded.py). ``seed`` overrides the stage's STAGE_SEEDS entry.
    """
    from levels.expanded import build_stage
    return build_stage(stage, seed)


def build_authored_level(stage=1):
    """The original single-screen 24 x 16 map of stages 1-5."""
    from levels.expanded import authored_level
    return authored_level(stage)


def validate_level(rows, entities, allow_lava_route=False, size=(WIDTH, HEIGHT)):
    """Check borders, spawns, liquid contacts and a route; return the mix.

    ``size`` is the expected (width, height); None accepts any size.
    """
    height, width = len(rows), len(rows[0])
    if size is not None:
        assert (width, height) == tuple(size)
    assert all(len(row) == width for row in rows)
    assert len(entities["P"]) == len(entities["E"]) == 1
    assert all(ch in "#RS" for ch in rows[0] + rows[-1])
    assert all(row[0] in "#RS" and row[-1] in "#RS" for row in rows)
    for kind in ("P", "E", "M", "G", "B"):
        for x, y in entities.get(kind, ()):
            assert 0 < x < width - 1 and 0 < y < height - 1
            assert rows[y][x] == " ", (kind, x, y)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in "WL":
                assert not any(0 <= nx < width and 0 <= ny < height and
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

    # Some stages deliberately require water to cool lava before the exit path
    # becomes safe. For those stages, validate the route after that reaction.
    assert reachable("# SL" if allow_lava_route else "# S")
    counts = Counter("".join(rows))
    return {k: counts[k] / (width * height) for k in "#RS WL"}


def expand_level(rows, entities):
    mapping = {"#": DIRT, "R": ROCK, "S": STONE, "W": WATER,
               "L": LAVA, " ": EMPTY}
    grid = []
    for row in rows:
        expanded = [mapping[ch] for ch in row for _ in range(SCALE)]
        for _ in range(SCALE):
            grid.append(expanded.copy())
    return grid, {kind: [(x * SCALE, y * SCALE) for x, y in points]
                  for kind, points in entities.items()}
