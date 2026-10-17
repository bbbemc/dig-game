"""Dig energy: how much dirt a stage needs, and the meter that limits digging.

The minimum is measured on the real map. Each macro tile (5 x 5 cells) costs
the dirt cells inside it; rock, stone and lava tiles cannot be crossed. A
cheapest route is found from the spawn to the boss and on to the exit, then
dug on a copy of the map with the player's own dig brush, so the minimum is
what a careful player really spends. The meter adds a margin for mistakes.

Players also like to dig straight down. A second route that weighs distance
as much as dirt (so it tunnels through instead of following caves, and only
bends around rock) measures that shortcut; the meter is always big enough
for it with a small margin, so digging down is a tight but fair choice.
"""
import heapq
import math

from config import (SCALE, DIG_RADIUS, DIG_BUDGET_MARGIN, DIG_BUDGET_EXTRA,
                    DIG_SHORTCUT_MARGIN)
from level import DIRT, ROCK, STONE, LAVA

BLOCKED = -1


def tile_costs(world):
    """Dirt cells per macro tile, or BLOCKED for rock, stone or lava."""
    cols, rows = world.width // SCALE, world.height // SCALE
    dirt = [0] * (cols * rows)
    hard = [0] * (cols * rows)
    fg, width = world.foreground, world.width
    for y in range(rows * SCALE):
        my = y // SCALE
        row = y * width
        for x in range(cols * SCALE):
            kind = fg[row + x]
            if kind == DIRT:
                dirt[my * cols + x // SCALE] += 1
            elif kind == ROCK or kind == STONE:
                hard[my * cols + x // SCALE] += 1
    for i, kind in world.initial_liquids.items():
        if kind == LAVA:
            x, y = i % width, i // width
            hard[(y // SCALE) * cols + x // SCALE] = SCALE * SCALE
    # A tile that is mostly hard rock has no room for the 32 px player.
    limit = SCALE * SCALE // 2
    costs = [BLOCKED if hard[i] > limit else dirt[i] for i in range(cols * rows)]
    return costs, cols, rows


def cheapest_route(costs, cols, rows, start, goal, step_cost=1):
    """Macro tiles of the cheapest route (Dijkstra): dirt plus step_cost per tile."""
    start_i, goal_i = start[1] * cols + start[0], goal[1] * cols + goal[0]
    best = {start_i: 0}
    came = {}
    queue = [(0, start_i)]
    while queue:
        cost, i = heapq.heappop(queue)
        if i == goal_i:
            break
        if cost > best.get(i, math.inf):
            continue
        x, y = i % cols, i // cols
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < cols and 0 <= ny < rows:
                n = ny * cols + nx
                step = costs[n]
                if step == BLOCKED and n != goal_i:
                    continue
                total = cost + max(step, 0) + step_cost
                if total < best.get(n, math.inf):
                    best[n] = total
                    came[n] = i
                    heapq.heappush(queue, (total, n))
    if goal_i not in best:
        return None
    path, i = [goal_i], goal_i
    while i != start_i:
        i = came[i]
        path.append(i)
    return [(i % cols, i // cols) for i in reversed(path)]


def dig_route(world, route):
    """Dirt cells a careful player removes digging along the route."""
    fg = bytearray(world.foreground)
    width, height = world.width, world.height
    r2 = DIG_RADIUS * DIG_RADIUS
    removed = 0

    def dig(cx, cy):
        nonlocal removed
        for y in range(max(1, cy - DIG_RADIUS), min(height - 1, cy + DIG_RADIUS + 1)):
            for x in range(max(1, cx - DIG_RADIUS), min(width - 1, cx + DIG_RADIUS + 1)):
                i = y * width + x
                if fg[i] == DIRT and (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                    fg[i] = 0
                    removed += 1

    centers = [(x * SCALE + SCALE // 2, y * SCALE + SCALE // 2) for x, y in route]
    for (x0, y0), (x1, y1) in zip(centers, centers[1:]):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for n in range(steps + 1):
            dig(x0 + (x1 - x0) * n // steps, y0 + (y1 - y0) * n // steps)
    return removed


def plan_stage(world, start, goals, step_cost=1):
    """Dirt cells to reach every goal in order, and the route used.

    step_cost=1 follows open caves wherever it can (the minimum); a step cost
    of a whole tile of dirt tunnels the short way, like digging straight down.
    """
    costs, cols, rows = tile_costs(world)
    route, here = [], start
    for goal in goals:
        leg = cheapest_route(costs, cols, rows, here, goal, step_cost)
        if leg is None:
            continue  # unreachable goal: leave it to the margin
        for x, y in leg:
            costs[y * cols + x] = 0  # dug already; reusing it is free
        route += leg if not route else leg[1:]
        here = goal
    return dig_route(world, route), route


SHORTCUT_STEP = SCALE * SCALE  # one full tile of dirt per tile travelled


def plan_shortcut(world, start, goals):
    """Dirt cells for the direct route, tunnelling instead of following caves."""
    return plan_stage(world, start, goals, SHORTCUT_STEP)


def budget_for(minimum, shortcut=0):
    return max(math.ceil(minimum * DIG_BUDGET_MARGIN) + DIG_BUDGET_EXTRA,
               math.ceil(shortcut * DIG_SHORTCUT_MARGIN))


class DigMeter:
    """Remaining dig energy, in dirt cells."""

    def __init__(self, minimum, shortcut=0):
        self.minimum = minimum
        self.shortcut = shortcut
        self.capacity = budget_for(minimum, shortcut)
        self.remaining = self.capacity

    @property
    def empty(self):
        return self.remaining <= 0

    @property
    def fraction(self):
        return self.remaining / self.capacity if self.capacity else 0.0

    def spend(self, cells):
        self.remaining = max(0, self.remaining - cells)
