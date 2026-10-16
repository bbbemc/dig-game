"""The Deep Descent: a procedurally generated four-layer underground world.

Everything is generated on the macro grid (one character = SCALE x SCALE
simulation cells), the same format as the authored stages, so the existing
World, liquids, renderer, scenery placement and cave sculpting all apply.

Generation order
----------------
1. Cellular automata seed organic caves in every layer. Rows near a layer
   boundary start mostly solid, so the layers read as separate strata.
2. A zig-zag main route is carved as a stair-stepped tunnel:
   layer 1 left -> right, layer 2 right -> left, layer 3 left -> right and
   layer 4 right -> left into the boss arena. Floors rise at most one macro
   per column (a jump is ~1.3 macros) and sit on dirt, so the player can
   always dig a shortcut down. Landmark rooms are strung along the route and
   2-wide drop shafts with ladders join the layers.
3. Sealed reservoirs are placed off the route: water tanks, lava pockets
   and water-over-lava pairs separated by a two-macro dirt plug, plus
   hidden pockets with a bomb pickup. Nothing touches at start-up.
4. Noise-based rock formations are added (more with depth and near layer
   boundaries, never on forced cells), then the open share of every layer is
   nudged into DEEP_OPEN_RANGE by carving or refilling unprotected caves.
5. Lakes and lava pools fill the bottoms of caves that are not joined to
   the route.
   Massive caverns (with floating ledges) are cut off the route in every
   layer; the isolated ones later hold underground lakes or lava lakes.
6. Validation: a platformer walk (gravity, one-macro steps, short gap jumps,
   ladders, swimming, no lava) must reach the exit from the spawn without
   digging; every enemy, pickup and reservoir must be reachable by digging;
   water and lava may not share an open region. A failed seed is retried.

Every stage uses this generator through a *profile* (levels/expanded.py) that
tunes cave density, rock, reservoirs and lakes. Stages 1-5 also pass their
original authored 24 x 16 map as a *chamber*: it is embedded unchanged at the
world's top-left (so its coordinates are the authored ones), its right wall
gets a gate, and the route continues from that gate into the large world.
Feature counts are authored per 64 columns and scale with the world width.
"""

import math
import random
from collections import deque

from config import DEEP_COLUMNS, DEEP_LAYER_ROWS, DEEP_OPEN_RANGE, DEEP_SEED
from tiles import coordinate_hash

LAYER_COUNT = 4
LAYER_NAMES = ('ABANDONED MINE', 'DIRT CAVE', 'CRYSTAL CAVE', 'VOLCANIC RUINS')
MIN_COLUMNS, MIN_LAYER_ROWS = 44, 16
SOLID = '#RS'
OPEN = ' W'
MAX_ATTEMPTS = 60
# Starting open probability of the cave automaton in each layer.
CAVE_FILL = (0.37, 0.41, 0.42, 0.40)
# fbm threshold above which solid ground becomes rock; lower = more rock.
ROCK_THRESHOLD = (0.76, 0.73, 0.70, 0.69)
ENEMIES = {'M': (1, 1, 1, 1), 'G': (1, 2, 1, 2)}  # per layer, per 64 columns
DEFAULT_PROFILE = {
    'cave_bias': 0.0,               # added to the automaton's open probability
    'rock_bias': 0.0,               # added to the rock threshold (< 0: more rock)
    'stone': 0.86,                  # stone-seam threshold in B4 (lower: more stone)
    'water_tanks': (2, 2, 2, 1),    # per layer, per 64 columns
    'pairs': (0, 1, 1, 2),          # water-over-lava tanks
    'lava_pockets': (0, 0, 2, 2),
    'pockets': (1, 2, 2, 1),        # hidden bomb pockets
    'caverns': (1, 1, 1, 2),        # massive off-route caverns
    'lakes': ((1, 'W', 1), (2, 'W', 2), (3, 'L', 2)),  # (layer, liquid, count)
}


def world_size(columns=None, layer_rows=None):
    """(width, height, layer rows) in macros for the configured world."""
    width = max(MIN_COLUMNS, columns or DEEP_COLUMNS)
    rows = max(MIN_LAYER_ROWS, layer_rows or DEEP_LAYER_ROWS)
    return width, LAYER_COUNT * rows + 2, rows


class GenerationError(RuntimeError):
    pass


class _Generator:
    def __init__(self, seed, columns=None, layer_rows=None, profile=None, chamber=None):
        self.seed = seed
        self.profile = dict(DEFAULT_PROFILE, **(profile or {}))
        self.chamber = chamber
        self.rng = random.Random(seed)
        self.salt = self.rng.randrange(1 << 20)
        self.w, self.h, self.L = world_size(columns, layer_rows)
        self.grid = [['#'] * self.w for _ in range(self.h)]
        self.tops = [1 + k * self.L for k in range(LAYER_COUNT)]
        self.force = {}          # (x, y) -> char; final say over every pass
        self.reserved = set()    # cells later features keep their distance from
        self.route = []          # (x, y) standing cells of the main path
        self.route_cells = set()
        self.rooms = []          # dict(kind, layer, x0, x1, floor, top)
        self.shafts = []         # dict(x, outer, top, bottom)
        self.pools = []          # (x, y, w, h, char) liquid rectangles
        self.pockets = []        # hidden pocket boxes (x0, y0, x1, y1)
        self.entities = {'P': [], 'E': [], 'M': [], 'G': [], 'B': []}
        self.bomb_spots = []
        self.arena = None
        self.door = None
        self.scale = (self.w - 2) / 62          # feature counts are per 64 columns
        self.chamber_box = None                 # (x0, y0, x1, y1) of the authored map
        self.gate = None                        # first world cell outside the chamber
        self.walk_start = None
        self.caverns = []

    def count(self, value):
        """A per-64-column count scaled to this world's width."""
        return int(value * self.scale + self.rng.random())

    # ------------------------------------------------------------------
    # Grid helpers
    # ------------------------------------------------------------------
    def inside(self, x, y):
        return 1 <= x < self.w - 1 and 1 <= y < self.h - 1

    def char(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.grid[y][x]
        return 'R'

    def put(self, x, y, char, force=False):
        if self.inside(x, y):
            self.grid[y][x] = char
            if force:
                self.force[x, y] = char

    def layer_of(self, y):
        return max(0, min(LAYER_COUNT - 1, (y - 1) // self.L))

    def band(self, k):
        """(top, bottom) rows of layer k, inclusive."""
        top = self.tops[k]
        return top, top + self.L - 1

    def noise(self, x, y, scale, salt=0):
        """Smooth value noise in [0, 1]."""
        fx, fy = x / scale, y / scale
        x0, y0 = math.floor(fx), math.floor(fy)
        tx, ty = fx - x0, fy - y0
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)

        def value(ix, iy):
            return coordinate_hash(ix * 92821 + self.salt + salt * 7919, iy) % 1024 / 1023

        top = value(x0, y0) + (value(x0 + 1, y0) - value(x0, y0)) * tx
        bottom = value(x0, y0 + 1) + (value(x0 + 1, y0 + 1) - value(x0, y0 + 1)) * tx
        return top + (bottom - top) * ty

    def fbm(self, x, y, scale, salt=0):
        return (0.65 * self.noise(x, y, scale, salt)
                + 0.35 * self.noise(x, y, scale / 2.3, salt + 17))

    def reserve(self, x0, y0, x1, y1, margin=0):
        for y in range(y0 - margin, y1 + margin + 1):
            for x in range(x0 - margin, x1 + margin + 1):
                self.reserved.add((x, y))

    def free(self, x0, y0, x1, y1, margin=0):
        """Whether a box (plus margin) avoids reserved cells and the border."""
        if x0 - margin < 1 or y0 - margin < 1 or x1 + margin > self.w - 2 \
                or y1 + margin > self.h - 2:
            return False
        return not any((x, y) in self.reserved
                       for y in range(y0 - margin, y1 + margin + 1)
                       for x in range(x0 - margin, x1 + margin + 1))

    def carve(self, x, y):
        self.put(x, y, ' ', force=True)

    def blob(self, cx, cy, rx, ry, floor=None, force=True, salt=0):
        """Carve a noisy ellipse; never below ``floor`` when given."""
        cells = []
        for y in range(math.floor(cy - ry - 1), math.ceil(cy + ry + 2)):
            if floor is not None and y > floor:
                continue
            for x in range(math.floor(cx - rx - 1), math.ceil(cx + rx + 2)):
                if not self.inside(x, y) or self.force.get((x, y), ' ') in SOLID:
                    continue  # route floors and tank walls stay intact
                d = ((x - cx) / max(0.5, rx)) ** 2 + ((y - cy) / max(0.5, ry)) ** 2
                if d < 0.75 + 0.45 * self.noise(x, y, 2.7, 40 + salt):
                    cells.append((x, y))
                    self.put(x, y, ' ', force=force)
        return cells

    # ------------------------------------------------------------------
    # 1. Organic caves
    # ------------------------------------------------------------------
    def cellular_caves(self):
        w, h, rng = self.w, self.h, self.rng
        open_map = [[False] * w for _ in range(h)]
        for y in range(2, h - 2):
            k = self.layer_of(y)
            top, bottom = self.band(k)
            edge = min(y - top, bottom - y)
            for x in range(2, w - 2):
                p = (CAVE_FILL[k] + self.profile['cave_bias']
                     + (self.fbm(x, y, 9, 1) - 0.5) * 0.3)
                if edge <= 1:
                    p -= 0.22
                open_map[y][x] = rng.random() < p
        for _ in range(5):
            nxt = [row[:] for row in open_map]
            for y in range(2, h - 2):
                for x in range(2, w - 2):
                    walls = sum(not open_map[y + dy][x + dx]
                                for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                                if dx or dy)
                    if walls >= 5:
                        nxt[y][x] = False
                    elif walls <= 3:
                        nxt[y][x] = True
            open_map = nxt
        for y in range(h):
            for x in range(w):
                if open_map[y][x] and self.inside(x, y):
                    self.grid[y][x] = ' '
        # Specks of air read as noise; tiny regions return to dirt.
        for region in self.regions():
            if len(region) < 5:
                for x, y in region:
                    self.grid[y][x] = '#'

    def regions(self, chars=' '):
        """4-connected regions of the given characters (list of cell lists)."""
        seen, result = set(), []
        for y in range(1, self.h - 1):
            for x in range(1, self.w - 1):
                if (x, y) in seen or self.grid[y][x] not in chars:
                    continue
                queue, region = deque([(x, y)]), []
                seen.add((x, y))
                while queue:
                    cx, cy = queue.popleft()
                    region.append((cx, cy))
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if (nx, ny) not in seen and self.char(nx, ny) in chars:
                            seen.add((nx, ny))
                            queue.append((nx, ny))
                result.append(region)
        return result

    # ------------------------------------------------------------------
    # 2. Zig-zag route, rooms and shafts
    # ------------------------------------------------------------------
    def plan_rooms(self, k, x_from, x_to):
        """Landmark rooms strung along a layer's route, as x spans."""
        kinds = {0: ['gallery', 'enemy', 'gallery', 'excavation'],
                 1: ['grotto', 'enemy', 'cavern', 'grotto'],
                 2: ['crystal', 'enemy', 'crystal', 'cavern'],
                 3: ['ruin', 'enemy', 'ruin', 'cavern']}[k]
        lo, hi = sorted((x_from, x_to))
        lo, hi = lo + 3, hi - 3
        span = hi - lo
        count = max(1, span // 14)
        # Every landmark kind appears; longer layers repeat them in new orders.
        kinds = [kinds[n % len(kinds)] for n in range(count)]
        self.rng.shuffle(kinds)
        slot = span / count
        rooms = []
        for n in range(count):
            kind = kinds[n]
            width = {'cavern': 13, 'excavation': 12, 'gallery': 10, 'enemy': 10}.get(kind, 8)
            width = min(width, int(slot) - 3)
            start = lo + round(n * slot)
            x0 = start + self.rng.randint(1, max(1, int(slot) - width - 1))
            rooms.append((kind, x0, x0 + width - 1))
        return rooms

    def walk_layer(self, k, x_from, y_from, x_to, y_to, rooms):
        """Stair-stepped standing cells from (x_from, y_from) to (x_to, y_to)."""
        top, bottom = self.band(k)
        lo, hi = top + 3, bottom - 2
        step = 1 if x_to > x_from else -1
        flat = {x for _, x0, x1 in rooms for x in range(x0 - 1, x1 + 2)}
        xs = list(range(x_from, x_to + step, step))
        # Columns still free to change height after each index (rooms stay flat).
        free_after, count = [0] * len(xs), 0
        for n in reversed(range(len(xs))):
            free_after[n] = count
            count += xs[n] not in flat
        amplitude = (self.L - 6) / 2
        salt = 300 + k * 31
        path, y = [], y_from
        last_change = 0
        for n, x in enumerate(xs):
            if n and x not in flat:
                need = y_to - y
                capacity = free_after[n] + 1
                # Floors rise one macro per column but may drop up to three;
                # converge early enough that every layer ends where planned.
                if need < 0 and -need >= capacity - 1:
                    y -= 1
                    last_change = n
                elif need > 0 and need >= 2 * capacity - 2:
                    y += min(need, 3)
                    last_change = n
                elif n - last_change >= 2:
                    t = n / max(1, len(xs) - 1)
                    base = y_from + (y_to - y_from) * t
                    target = base + (self.noise(x, k, 6, salt) - 0.5) * 2 * amplitude
                    target = max(lo, min(hi, round(target)))
                    if target > y and self.rng.random() < 0.13:
                        y = min(target, y + self.rng.randint(2, 3))  # a short drop
                        last_change = n
                    elif target != y and self.rng.random() < 0.55:
                        y += 1 if target > y else -1
                        last_change = n
            y = max(lo, min(hi, y))
            path.append((x, y))
        return path

    def carve_route(self, path, k):
        heights = {}
        for n, (x, y) in enumerate(path):
            prev_y = path[n - 1][1] if n else y
            next_y = path[n + 1][1] if n + 1 < len(path) else y
            tall = prev_y != y or next_y != y or self.noise(x, y, 4, 70 + k) > 0.72
            height = 3 if tall else 2
            heights[x] = height
            for yy in range(min(prev_y, y) - height + 1, y + 1):
                self.carve(x, yy)
            self.route.append((x, y))
            self.route_cells.add((x, y))
            for depth in (1, 2):
                if (x, y + depth) not in self.force:
                    self.put(x, y + depth, '#', force=True)
            # Small and medium caves bulge off the tunnel roof.
            if self.rng.random() < 0.05:
                self.blob(x + self.rng.uniform(-1, 1), y - height - 0.5,
                          self.rng.uniform(1.4, 2.8), self.rng.uniform(0.9, 1.6),
                          floor=y, salt=x)
        for x, y in path:
            self.reserve(x, y - heights[x] - 1, x, y + 2, margin=1)

    def carve_room(self, kind, k, x0, x1, floor):
        """Carve a landmark room whose floor matches the route floor."""
        top_limit = self.band(k)[0] + 1
        rng = self.rng
        if kind in ('gallery', 'excavation'):
            # Abandoned mine galleries are dug square, with a flat roof.
            height = rng.randint(3, 4) if kind == 'gallery' else rng.randint(5, 7)
            for x in range(x0, x1 + 1):
                for y in range(max(top_limit, floor - height + 1), floor + 1):
                    self.carve(x, y)
            top = max(top_limit, floor - height + 1)
        else:
            height = {'cavern': rng.randint(5, 6), 'enemy': 4}.get(kind, rng.randint(3, 5))
            top = max(top_limit, floor - height + 1)
            width = x1 - x0 + 1
            for x in range(x0, x1 + 1):
                # A domed, noisy roof: lower towards the walls.
                t = (x - x0 + 0.5) / width
                dome = math.sin(math.pi * t) ** 0.6
                local = max(2, round(height * (0.45 + 0.55 * dome)
                                     + (self.noise(x, floor, 2.5, 90) - 0.5) * 2))
                for y in range(max(top_limit, floor - local + 1), floor + 1):
                    self.carve(x, y)
        for x in range(x0, x1 + 1):
            for depth in (1, 2):
                self.put(x, floor + depth, '#', force=True)
        room = dict(kind=kind, layer=k, x0=x0, x1=x1, floor=floor, top=top)
        self.rooms.append(room)
        self.reserve(x0, top, x1, floor + 2, margin=2)
        return room

    def carve_shaft(self, x, outer, top, bottom):
        """A 2-wide drop between layers; the inner column carries a ladder."""
        for y in range(top - 1, bottom + 1):
            self.carve(x, y)
            self.carve(outer, y)
        for column in (x, outer):
            self.put(column, bottom + 1, '#', force=True)
            self.put(column, bottom + 2, '#', force=True)
        self.shafts.append(dict(x=x, outer=outer, top=top, bottom=bottom))
        self.reserve(min(x, outer), top - 2, max(x, outer), bottom + 2, margin=1)

    def build_route(self):
        w = self.w
        arena_w = max(18, min(24, w // 3))
        x_left, x_right = 3, w - 4
        top0 = self.band(0)[0]
        y = top0 + 4
        x_start = x_left
        if self.gate:
            x_start, y = self.gate             # the route leaves the authored map
        # Spawn: a small worked chamber at the top-left of the mine.
        spawn_floor = y
        for k in range(LAYER_COUNT):
            top, bottom = self.band(k)
            direction = 1 if k % 2 == 0 else -1
            x_end = x_right if direction > 0 else x_left
            if k == LAYER_COUNT - 1:
                x_end = 2 + arena_w            # the arena's entry ledge
                y_end = bottom - 3
            else:
                y_end = bottom - self.rng.randint(3, 4)
            rooms = self.plan_rooms(k, x_start + direction * (9 if k == 0 else 3), x_end)
            spawn_span = [('spawn', 2, 9)] if k == 0 and not self.gate else []
            path = self.walk_layer(k, x_start, y, x_end, y_end, rooms + spawn_span)
            floors = dict(path)
            self.carve_route(path, k)
            for kind, x0, x1 in rooms:
                self.carve_room(kind, k, x0, x1, floors[x0])
            if k == 0 and not self.gate:
                self.carve_room('spawn', 0, 2, 9, spawn_floor)
                self.entities['P'].append((4, spawn_floor))
                self.walk_start = (4, spawn_floor)
            if k < LAYER_COUNT - 1:
                next_top = self.band(k + 1)[0]
                entry = next_top + self.rng.randint(3, 5)
                outer = x_end + direction
                self.carve_shaft(x_end, outer, path[-1][1], entry)
                x_start, y = x_end, entry
            else:
                self.build_arena(arena_w, path[-1])

    def build_arena(self, arena_w, entry):
        """Boss arena at the bottom-left, with a lava and a water tank above."""
        x0, x1 = 2, 2 + arena_w - 1
        floor = self.h - 2                        # solid rock floor row
        top = floor - 6
        for x in range(x0 - 1, x1 + 2):
            self.put(x, floor, 'R', force=True)
        for x in range(x0, x1 + 1):
            roof = top + (1 if self.noise(x, floor, 3, 120) > 0.62 else 0)
            for y in range(roof, floor):
                self.carve(x, y)
        ex, ey = entry
        for y in (ey + 1, ey + 2):                # two-high ledge: the boss stays in
            self.put(ex, y, 'R', force=True)
            self.put(ex + 1, y, 'R', force=True)
        for x in (x0, x0 + 1):                    # one-step door ledge
            self.put(x, floor - 1, 'R', force=True)
        self.door = (x0, floor - 3, 1, 2)
        self.entities['E'].append((x0, floor - 2))
        self.entities['B'].append((x0 + arena_w // 2 + 1, floor - 2))
        self.arena = (x0, top, x1, floor - 1)
        # Two sealed tanks over the arena; two-row dirt plugs hold them.
        lava_x0 = x0 + arena_w // 2 - 1
        lava_x1 = min(x1 - 2, lava_x0 + 5)
        self.tank(lava_x0, top - 5, lava_x1, top - 3, 'L', ring='R', plug_rows=2, air=1)
        self.tank(x0 + 1, top - 5, x0 + 4, top - 3, 'W', ring='R', plug_rows=2, air=1)
        self.reserve(x0, top - 7, x1 + 1, floor, margin=1)
        # Bombs wait on the approach to the arena.
        for n in range(1, 4):
            x, y = self.route[-1 - n * 3]
            self.bomb_spots.append((x, y))

    # ------------------------------------------------------------------
    # 3. Reservoirs and hidden pockets
    # ------------------------------------------------------------------
    def tank(self, x0, y0, x1, y1, liquid, ring='#', plug_rows=1, air=1):
        """Sealed reservoir: inner box (x0..x1, y0..y1) with ``air`` dry rows."""
        for y in range(y0 - 1, y1 + plug_rows + 1):
            for x in range(x0 - 1, x1 + 2):
                if x0 <= x <= x1 and y0 <= y <= y1:
                    self.put(x, y, ' ' if y < y0 + air else liquid, force=True)
                elif y > y1:
                    self.put(x, y, '#', force=True)       # diggable plug
                else:
                    self.put(x, y, ring, force=True)
        self.pools.append((x0, y0 + air, x1 - x0 + 1, y1 - y0 + 1 - air, liquid))
        self.reserve(x0, y0, x1, y1 + plug_rows, margin=2)

    def find_box(self, k, width, height, margin=2, tries=260, rows=None):
        top, bottom = self.band(k)
        lo, hi = rows or (top + 1, bottom - 1)
        for _ in range(tries):
            x0 = self.rng.randint(2, self.w - 3 - width)
            y0 = self.rng.randint(lo, max(lo, hi - height + 1))
            if self.free(x0, y0, x0 + width - 1, y0 + height - 1, margin):
                return x0, y0
        return None

    def above_route(self, x0, x1, y1, depth=4):
        return any((x, y) in self.route_cells for x in range(x0 - 1, x1 + 2)
                   for y in range(y1 + 1, y1 + depth + 1))

    def place_features(self):
        rng, profile = self.rng, self.profile
        for k in range(LAYER_COUNT):
            # Water tanks, often above the route so digging floods the way.
            for _ in range(self.count(profile['water_tanks'][k])):
                width, height = rng.randint(4, 7), rng.randint(2, 3)
                spot = self.find_box(k, width + 2, height + 3, margin=1)
                if spot:
                    x, y = spot
                    self.tank(x + 1, y + 1, x + width, y + height + 1, 'W',
                              ring='R' if rng.random() < 0.4 else '#')
            # Water over lava, two dirt rows apart: a reaction to set off.
            for _ in range(self.count(profile['pairs'][k])):
                width = rng.randint(4, 6)
                spot = self.find_box(k, width + 2, 10, margin=1)
                if not spot:
                    continue
                x, y = spot
                if self.above_route(x, x + width + 1, y + 9, 3):
                    continue
                self.tank(x + 1, y + 1, x + width, y + 3, 'W', plug_rows=2)
                self.tank(x + 1, y + 6, x + width, y + 7, 'L', plug_rows=2, air=0)
            # Lone lava pockets in the deeper layers, never just above the route.
            for _ in range(self.count(profile['lava_pockets'][k])):
                width = rng.randint(3, 5)
                spot = self.find_box(k, width + 2, 5, margin=1)
                if spot and not self.above_route(spot[0], spot[0] + width + 1, spot[1] + 4, 5):
                    x, y = spot
                    self.tank(x + 1, y + 1, x + width, y + 2, 'L', ring='R', plug_rows=2, air=0)
            # A hidden pocket per layer: sealed in dirt, holding a bomb.
            for _ in range(self.count(profile['pockets'][k])):
                width, height = rng.randint(3, 5), 2
                spot = self.find_box(k, width + 4, height + 4, margin=1)
                if not spot:
                    continue
                x, y = spot
                for yy in range(y, y + height + 4):
                    for xx in range(x, x + width + 4):
                        self.put(xx, yy, '#', force=True)
                for yy in range(y + 2, y + 2 + height):
                    for xx in range(x + 2, x + 2 + width):
                        self.carve(xx, yy)
                self.pockets.append((x + 2, y + 2, x + 1 + width, y + 1 + height))
                self.bomb_spots.append((x + 2 + width // 2, y + 1 + height))
                self.reserve(x, y, x + width + 3, y + height + 3, margin=1)

    def place_caverns(self):
        """Massive caverns off the route, with a few floating dirt ledges."""
        for k in range(LAYER_COUNT):
            top, bottom = self.band(k)
            for _ in range(self.count(self.profile['caverns'][k])):
                rx = self.rng.uniform(6.0, 9.5)
                ry = min(self.rng.uniform(3.2, 4.6), (self.L - 6) / 2)
                spot = self.find_box(k, math.ceil(rx * 2) + 2, math.ceil(ry * 2) + 2,
                                     margin=1, tries=200)
                if not spot:
                    continue
                cx, cy = spot[0] + rx + 1, spot[1] + ry + 1
                cells = self.blob(cx, cy, rx, ry, salt=len(self.caverns) * 13)
                floor = max(y for _, y in cells)
                for n in range(self.rng.randint(1, 3)):
                    lx = round(cx + self.rng.uniform(-rx * 0.6, rx * 0.6))
                    ly = round(cy + self.rng.uniform(-ry * 0.2, ry * 0.4))
                    if ly < floor - 1:
                        for x in range(lx - 1, lx + self.rng.randint(1, 3)):
                            if (x, ly) in cells:
                                self.put(x, ly, '#', force=True)
                xs, ys = [x for x, _ in cells], [y for _, y in cells]
                self.caverns.append(set(cells))
                self.reserve(min(xs), min(ys), max(xs), max(ys), margin=1)

    # ------------------------------------------------------------------
    # 4. Rock formations and density
    # ------------------------------------------------------------------
    def rock_formations(self):
        for y in range(1, self.h - 1):
            k = self.layer_of(y)
            top, bottom = self.band(k)
            edge = min(y - top, bottom - y)
            threshold = (ROCK_THRESHOLD[k] + self.profile['rock_bias']
                         - (0.06 if edge <= 1 else 0))
            for x in range(1, self.w - 1):
                if (x, y) in self.force or self.grid[y][x] != '#':
                    continue
                if self.fbm(x, y, 5.5, 200 + k) > threshold:
                    self.grid[y][x] = 'R'
        # Bombable stone seams streak the volcanic layer.
        top, bottom = self.band(3)
        for y in range(top, bottom + 1):
            for x in range(1, self.w - 1):
                if (x, y) not in self.force and self.grid[y][x] == '#' \
                        and self.noise(x, y * 3, 3, 260) > self.profile['stone']:
                    self.grid[y][x] = 'S'
        # A lone rock or stone macro reads as a placed tile, not geology.
        for _ in range(2):
            for y in range(1, self.h - 1):
                for x in range(1, self.w - 1):
                    char = self.grid[y][x]
                    if char in 'RS' and (x, y) not in self.force and sum(
                            self.grid[ny][nx] == char for nx, ny in
                            ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))) < 2:
                        self.grid[y][x] = '#'

    def open_share(self, k):
        top, bottom = self.band(k)
        cells = [self.grid[y][x] for y in range(top, bottom + 1) for x in range(1, self.w - 1)]
        return sum(c in ' WL' for c in cells) / len(cells)

    def loose_caves(self, top, bottom):
        """Regions of generated (unforced) open cells inside rows top..bottom."""
        seen, caves = set(), []
        for y in range(top, bottom + 1):
            for x in range(1, self.w - 1):
                if (x, y) in seen or self.grid[y][x] != ' ' or (x, y) in self.force:
                    continue
                queue, cave = deque([(x, y)]), []
                seen.add((x, y))
                while queue:
                    cx, cy = queue.popleft()
                    cave.append((cx, cy))
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if ((nx, ny) not in seen and top <= ny <= bottom
                                and self.char(nx, ny) == ' ' and (nx, ny) not in self.force):
                            seen.add((nx, ny))
                            queue.append((nx, ny))
                caves.append(cave)
        return caves

    def balance_density(self):
        lo, hi = DEEP_OPEN_RANGE
        for k in range(LAYER_COUNT):
            top, bottom = self.band(k)
            guard = 0
            while self.open_share(k) > hi - 0.01 and guard < 200:
                guard += 1
                # Generated caves only; carved route, rooms and tanks stay.
                # Caves hugging the route are refilled more often, so the
                # path does not merge into one long open band.
                candidates = self.loose_caves(top, bottom)
                if not candidates:
                    break
                weights = [3 if any((x + dx, y + dy) in self.force
                                    for x, y in cave for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                           else 1 for cave in candidates]
                for x, y in self.rng.choices(candidates, weights)[0]:
                    self.grid[y][x] = '#'
            guard = 0
            while self.open_share(k) < lo + 0.01 and guard < 300:
                guard += 1
                rx, ry = self.rng.uniform(1.5, 3.5), self.rng.uniform(1.0, 2.2)
                spot = self.find_box(k, math.ceil(rx * 2) + 1, math.ceil(ry * 2) + 1,
                                     margin=0, tries=80)
                if not spot:
                    continue
                cx, cy = spot[0] + rx, spot[1] + ry
                for x, y in self.blob(cx, cy, rx, ry, force=False, salt=guard):
                    if (x, y) in self.force:
                        self.grid[y][x] = self.force[x, y]

    # ------------------------------------------------------------------
    # 5. Lakes and lava pools in side caves
    # ------------------------------------------------------------------
    def fill_side_caves(self):
        joined = self.connected_to_route()
        used = set()
        for k, liquid, count in self.profile['lakes']:
            top, bottom = self.band(k)
            caves = [r for r in self.regions()
                     if len(r) >= 10 and not (set(r) & joined) and not (set(r) & used)
                     and all(top <= y <= bottom for x, y in r)]
            # Isolated massive caverns become lakes first, then plain caves.
            options = [r for r in caves if any(set(r) & c for c in self.caverns)]
            self.rng.shuffle(options)
            plain = [r for r in caves if r not in options
                     and all((x, y) not in self.force and (x, y) not in self.reserved
                             for x, y in r)]
            self.rng.shuffle(plain)
            for region in (options + plain)[:self.count(count)]:
                used.update(region)
                low = max(y for _, y in region)
                depth = min(1 if liquid == 'L' else 3, low - min(y for _, y in region))
                cells = [(x, y) for x, y in region if y > low - max(1, depth)]
                for x, y in cells:
                    self.grid[y][x] = liquid
                xs, ys = [x for x, _ in cells], [y for _, y in cells]
                self.pools.append((min(xs), min(ys), max(xs) - min(xs) + 1,
                                   max(ys) - min(ys) + 1, liquid))

    def connected_to_route(self):
        start = self.route[0]
        seen, queue = {start}, deque([start])
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) not in seen and self.char(nx, ny) in ' W':
                    seen.add((nx, ny))
                    queue.append((nx, ny))
        return seen

    # ------------------------------------------------------------------
    # Enemies and pickups
    # ------------------------------------------------------------------
    def place_enemies(self):
        spawn = self.entities['P'][0]
        for k in range(LAYER_COUNT):
            rooms = [r for r in self.rooms if r['layer'] == k and r['kind'] != 'spawn']
            rooms.sort(key=lambda r: r['kind'] != 'enemy')
            shooters = self.count(ENEMIES['M'][k])
            walkers = self.count(ENEMIES['G'][k])
            used = []

            def far(x, y):
                # Out of a shooter's sight (450 px) from the spawn and the gate.
                starts = [spawn] + ([self.gate] if self.gate else [])
                return (all(math.hypot(x - sx, y - sy) > 16 for sx, sy in starts)
                        and not self.in_chamber(x, y)
                        and all(abs(x - ux) > 3 for ux, uy in used if uy == y))

            for room in rooms:
                width = room['x1'] - room['x0'] + 1
                if shooters and width >= 6:
                    # Shooters hold the far wall of a room.
                    x = room['x1'] - 1 if room['x0'] % 2 else room['x0'] + 1
                    if far(x, room['floor']):
                        self.entities['M'].append((x, room['floor']))
                        used.append((x, room['floor']))
                        shooters -= 1
                if walkers and width >= 7:
                    x = (room['x0'] + room['x1']) // 2
                    if far(x, room['floor']):
                        self.entities['G'].append((x, room['floor']))
                        used.append((x, room['floor']))
                        walkers -= 1
            # Any left over patrol flat stretches of the route.
            runs = [p for n, p in enumerate(self.route[2:-2], 2)
                    if self.layer_of(p[1]) == k
                    and self.route[n - 2][1] == p[1] == self.route[n + 2][1]]
            self.rng.shuffle(runs)
            for x, y in runs:
                if not (shooters or walkers):
                    break
                if not far(x, y) or self.char(x, y - 1) != ' ':
                    continue
                kind = 'G' if walkers else 'M'
                self.entities[kind].append((x, y))
                used.append((x, y))
                if kind == 'G':
                    walkers -= 1
                else:
                    shooters -= 1

    def place_pickups(self):
        for room in self.rooms:
            if room['kind'] in ('gallery', 'grotto', 'crystal', 'ruin', 'cavern'):
                x = room['x0'] + self.rng.randint(0, room['x1'] - room['x0'])
                self.bomb_spots.append((x, room['floor']))
        taken = {p for kind in 'MGBP' for p in self.entities[kind]}
        spots = []
        for x, y in self.bomb_spots:
            if (x, y) not in taken and self.grid[y][x] == ' ' and self.char(x, y + 1) in SOLID \
                    and (x, y) not in spots:
                spots.append((x, y))
        self.bomb_spots = spots

    # ------------------------------------------------------------------
    # 6. Validation
    # ------------------------------------------------------------------
    def ladder_cells(self):
        cells = set()
        for shaft in self.shafts:
            for y in range(shaft['top'] - 1, shaft['bottom'] + 1):
                cells.add((shaft['x'], y))
        return cells

    def walk_reachable(self, start):
        """Standing cells reachable by walking, jumping, climbing and swimming."""
        ladders = self.ladder_cells()
        char = self.char

        def passable(x, y):
            return char(x, y) in OPEN

        def held(x, y):
            return char(x, y + 1) in SOLID or (x, y) in ladders or char(x, y) == 'W'

        def settle(x, y):
            while passable(x, y) and not held(x, y):
                y += 1
            return (x, y) if passable(x, y) else None

        first = settle(*start)
        seen, queue = {first}, deque([first])
        while queue:
            x, y = queue.popleft()
            moves = []
            for d in (-1, 1):
                if passable(x + d, y):
                    moves.append(settle(x + d, y))
                    # Running jumps over one- and two-wide gaps.
                    for gap in (2, 3):
                        if all(passable(x + d * n, y) and passable(x + d * n, y - 1)
                               for n in range(gap + 1)) and held(x + d * gap, y):
                            moves.append((x + d * gap, y))
                if passable(x, y - 1) and passable(x + d, y - 1) and char(x + d, y) in SOLID:
                    moves.append(settle(x + d, y - 1))
            climbing = (x, y) in ladders or char(x, y) == 'W'
            if climbing and passable(x, y - 1):
                moves.append((x, y - 1) if held(x, y - 1) else None)
                for d in (-1, 1):               # jump off the top rung
                    if passable(x + d, y - 1):
                        moves.append(settle(x + d, y - 1))
            if climbing and passable(x, y + 1):
                moves.append(settle(x, y + 1))
            for move in moves:
                if move and move not in seen:
                    seen.add(move)
                    queue.append(move)
        return seen

    def dig_reachable(self, start):
        """Cells reachable when dirt can be dug (rock, stone and lava block)."""
        seen, queue = {start}, deque([start])
        while queue:
            x, y = queue.popleft()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if (nx, ny) not in seen and self.char(nx, ny) in ' #W':
                    seen.add((nx, ny))
                    queue.append((nx, ny))
        return seen

    def validate(self):
        grid = self.grid
        # Water and lava never share an open region at start-up.
        for region in self.regions(' WL'):
            kinds = {grid[y][x] for x, y in region}
            if all(self.in_chamber(x, y) for x, y in region):
                continue  # the authored map is checked by level.validate_level
            if 'W' in kinds and 'L' in kinds:
                raise GenerationError('water and lava share a cave')
        spawn = self.entities['P'][0]
        walked = self.walk_reachable(self.walk_start)
        exit_cell = self.entities['E'][0]
        if exit_cell not in walked:
            raise GenerationError('exit cannot be walked to')
        for x, y in self.route[::4]:
            if (x, y) not in walked and not any((x, yy) in walked for yy in range(y - 1, y + 3)):
                raise GenerationError(f'route breaks at {(x, y)}')
        dug = self.dig_reachable(spawn)
        targets = [p for kind in 'MGB' for p in self.entities[kind]
                   if not self.in_chamber(*p)] + self.bomb_spots
        for x, y in targets:
            if (x, y) not in dug:
                raise GenerationError(f'unreachable target {(x, y)}')
        for x, y, w, h, _ in self.pools:
            ring = [(xx, yy) for yy in range(y - 2, y + h + 2) for xx in range(x - 2, x + w + 2)]
            if not any(cell in dug for cell in ring):
                raise GenerationError(f'sealed reservoir {(x, y)}')
        lo, hi = DEEP_OPEN_RANGE
        for k in range(LAYER_COUNT):
            share = self.open_share(k)
            if not lo - 0.03 <= share <= hi + 0.03:
                raise GenerationError(f'layer {k} open share {share:.2f}')

    # ------------------------------------------------------------------
    # The authored stage map
    # ------------------------------------------------------------------
    def in_chamber(self, x, y):
        box = self.chamber_box
        return bool(box) and box[0] <= x <= box[2] and box[1] <= y <= box[3]

    def embed_chamber(self):
        """Place the authored map at the top-left and open a gate to the world."""
        rows, entities = self.chamber['rows'], self.chamber['entities']
        width, height = len(rows[0]), len(rows)
        self.chamber_box = (0, 0, width - 1, height - 1)
        for y, row in enumerate(rows):
            for x, char in enumerate(row):
                if x == width - 1 or y == height - 1:
                    char = '#'          # inner walls become diggable earth
                self.grid[y][x] = char
                if self.inside(x, y):
                    self.force[x, y] = char
        gate_x, gate_y = width - 1, self.chamber['gate_row']
        for y in (gate_y - 1, gate_y):
            self.carve(gate_x, y)
        self.put(gate_x, gate_y + 1, '#', force=True)
        self.gate = (width, gate_y)
        self.walk_start = self.gate
        self.reserve(0, 0, width - 1, height - 1, margin=1)
        for kind in 'PMG':
            self.entities[kind].extend(entities.get(kind, ()))

    def generate(self):
        for x in range(self.w):
            self.grid[0][x] = self.grid[-1][x] = 'R'
        for row in self.grid:
            row[0] = row[-1] = 'R'
        self.cellular_caves()
        if self.chamber:
            self.embed_chamber()
        self.build_route()
        self.place_features()
        self.place_caverns()
        for (x, y), char in self.force.items():
            self.grid[y][x] = char
        self.rock_formations()
        self.balance_density()
        for (x, y), char in self.force.items():
            self.grid[y][x] = char
        self.fill_side_caves()
        self.place_enemies()
        self.place_pickups()
        self.validate()
        return [''.join(row) for row in self.grid]


def generate_deep_world(seed=None, columns=None, layer_rows=None, profile=None, chamber=None):
    """Return (generator, rows) for the first valid seed at or after ``seed``."""
    if seed is None:
        seed = DEEP_SEED if DEEP_SEED is not None else random.randrange(1 << 30)
    errors = []
    for attempt in range(MAX_ATTEMPTS):
        generator = _Generator(seed + attempt, columns, layer_rows, profile, chamber)
        try:
            rows = generator.generate()
        except GenerationError as error:
            errors.append(str(error))
            continue
        return generator, rows
    raise GenerationError(f'no valid world from seed {seed}: {errors[-3:]}')


def build_deep_world(seed=None, columns=None, layer_rows=None):
    """The Deep Descent at a custom size: (rows, entities, scenery, optional_rooms)."""
    from levels.deep_scenery import decorate

    generator, rows = generate_deep_world(seed, columns, layer_rows)
    scenery = decorate(generator, rows)
    entities = {kind: list(points) for kind, points in generator.entities.items()}
    return rows, entities, scenery, []
