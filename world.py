"""Permanent rear walls and mutable collision terrain, independent of liquids."""
from config import CELL, SCALE, CHUNK_CELLS
from level import EMPTY, DIRT, ROCK, WATER, LAVA, STONE

SOLIDS = (DIRT, ROCK, STONE)


class World:
    def __init__(self, rows, scale=SCALE):
        self.scale = scale
        self.width, self.height = len(rows[0]) * scale, len(rows) * scale
        self.pixel_width, self.pixel_height = self.width * CELL, self.height * CELL
        self.foreground = bytearray(self.width * self.height)
        self.background = bytearray(self.width * self.height)
        self.initial_liquids = {}
        self.listeners = []
        self.dirty_chunks = set()
        mapping = {' ': EMPTY, '#': DIRT, 'R': ROCK, 'S': STONE,
                   'W': WATER, 'L': LAVA}
        # Built a macro row at a time: large worlds have ~250k cells.
        width = self.width
        for my, row in enumerate(rows):
            values = [mapping[c] for c in row] if isinstance(row, str) else list(row)
            cells = bytes(EMPTY if v in (WATER, LAVA) else v for v in values for _ in range(scale))
            liquids = [(x, v) for x, v in enumerate(values) if v in (WATER, LAVA)]
            # Background IDs survive all digging and reaction changes.
            back = bytes((min(3, my * 4 // len(rows)) + 1,)) * width
            for y in range(my * scale, my * scale + scale):
                start = y * width
                self.foreground[start:start + width] = cells
                self.background[start:start + width] = back
                for mx, value in liquids:
                    for x in range(mx * scale, mx * scale + scale):
                        self.initial_liquids[start + x] = value

    def sculpt(self, plan):
        """Apply authored cell-level cave shaping before any simulation starts."""
        for x, y, kind in plan.get('fill', ()):
            self.foreground[y * self.width + x] = kind
        for x, y in plan.get('carve', ()):
            self.foreground[y * self.width + x] = EMPTY

    def index(self, x, y):
        return y * self.width + x

    def coords(self, index):
        return index % self.width, index // self.width

    def solid(self, x, y):
        return (not (0 <= x < self.width and 0 <= y < self.height)
                or self.foreground[y * self.width + x] in SOLIDS)

    def neighbors(self, i):
        x, y = self.coords(i)
        if x: yield i - 1
        if x + 1 < self.width: yield i + 1
        if y: yield i - self.width
        if y + 1 < self.height: yield i + self.width

    def set_terrain(self, i, kind):
        if self.foreground[i] == kind:
            return
        self.foreground[i] = kind
        x, y = self.coords(i)
        # Edge shadows and attached props can cross chunk boundaries.
        for nx, ny in ((x, y), (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < self.width and 0 <= ny < self.height:
                self.dirty_chunks.add((nx // CHUNK_CELLS, ny // CHUNK_CELLS))
        for listener in self.listeners:
            listener(i)

    def dig(self, cx, cy, radius=3):
        removed = []
        for y in range(max(1, cy - radius), min(self.height - 1, cy + radius + 1)):
            for x in range(max(1, cx - radius), min(self.width - 1, cx + radius + 1)):
                i = y * self.width + x
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2 and self.foreground[i] == DIRT:
                    self.set_terrain(i, EMPTY)
                    removed.append(i)
        return removed

    def dig_line(self, start, end, radius=3):
        removed = []
        steps = max(abs(end[0] - start[0]), abs(end[1] - start[1]), 1)
        for n in range(steps + 1):
            removed.extend(self.dig(start[0] + (end[0] - start[0]) * n // steps,
                                    start[1] + (end[1] - start[1]) * n // steps, radius))
        return removed
