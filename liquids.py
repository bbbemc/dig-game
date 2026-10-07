"""Sparse, conservative liquid cells and a timed water/lava reaction.

Mass uses integer units internally. Transfers read a phase snapshot and apply
their deltas together, so set/dictionary traversal order cannot move a liquid
twice or choose the direction in which a pool spreads.
"""

from collections import defaultdict
import heapq

from config import (FLUID_HZ, WATER_FLOW_RATE, LAVA_FLOW_RATE,
                    REACTION_DURATION, CHUNK_CELLS, MIN_FLOW_UNITS,
                    REACTION_STEP_LIMIT)
from level import EMPTY, WATER, LAVA, STONE


FULL = 1024
KINDS = (WATER, LAVA)


class LiquidSystem:
    """Only awake liquid cells and scheduled reaction events cost step work.

    Public ``mass`` values are normalized cell volumes, and ``types`` and
    ``occupied`` contain only positive-mass cells. On first water/lava contact,
    all liquid is frozen and scheduled to evaporate or harden.
    """

    def __init__(self, world):
        self.world = world
        self.types = dict(world.initial_liquids)
        self._units = {i: FULL for i in self.types}
        self.mass = {i: 1.0 for i in self.types}
        self.occupied = set(self.types)
        self._kind_counts = {kind: sum(value == kind for value in self.types.values())
                             for kind in KINDS}
        self.active = {i for i, kind in self.types.items()
                       if any(world.foreground[n] == EMPTY and self.types.get(n) != kind
                              for n in world.neighbors(i))}
        self._contact_checks = set(self.active)
        self.previous_mass = {}
        self.previous_types = {}
        self.chunks = {}
        self._previous_chunks = {}
        for i in self.occupied:
            self._chunk_add(self.chunks, i)
        self.reactions = {}
        self.frozen = set()
        self._events = []
        self._reaction_units = {}
        self._reaction_started = False
        self._awake = set()
        self._changed = set()
        self.time = 0.0
        self._reacted_units = 0
        self._evaporated_units = 0
        self._solidified_units = 0
        self.reaction_work = 0
        self.last_processed = 0
        self.initial_mass = len(self.types)
        world.listeners.append(self._terrain_changed)

    @property
    def active_count(self):
        return len(self.active)

    @property
    def reacted_mass(self):
        return self._reacted_units / FULL

    @property
    def evaporated_mass(self):
        return self._evaporated_units / FULL

    @property
    def solidified_mass(self):
        return self._solidified_units / FULL

    @property
    def total_mass(self):
        return sum(self._units.values()) / FULL

    def type_at(self, x, y):
        if 0 <= x < self.world.width and 0 <= y < self.world.height:
            return self.types.get(y * self.world.width + x, EMPTY)
        return EMPTY

    def mass_at(self, x, y):
        if 0 <= x < self.world.width and 0 <= y < self.world.height:
            return self.mass.get(y * self.world.width + x, 0.0)
        return 0.0

    def interpolated_mass(self, index, alpha):
        current = self.mass.get(index, 0.0)
        previous = self.previous_mass.get(index, current)
        return previous + (current - previous) * max(0.0, min(1.0, alpha))

    def render_mass(self, index, alpha):
        mass = self.interpolated_mass(index, alpha)
        if self.types.get(index) == WATER and index in self.reactions:
            mass = max(0.0, mass - self._reaction_units[index] / FULL
                       * self.reaction_progress(index))
        return mass

    def render_type(self, index):
        return self.types.get(index, self.previous_types.get(index, EMPTY))

    def _chunk_key(self, index):
        x, y = self.world.coords(index)
        return x // CHUNK_CELLS, y // CHUNK_CELLS

    def _chunk_add(self, chunks, index):
        chunks.setdefault(self._chunk_key(index), set()).add(index)

    def _chunk_remove(self, index):
        key = self._chunk_key(index)
        chunk = self.chunks[key]
        chunk.remove(index)
        if not chunk:
            del self.chunks[key]

    def visible_indices(self, x0, y0, x1, y1):
        """Yield current/fading liquid cells within exclusive cell bounds."""
        if x1 <= x0 or y1 <= y0:
            return
        width = self.world.width
        for cy in range(y0 // CHUNK_CELLS, (y1 - 1) // CHUNK_CELLS + 1):
            for cx in range(x0 // CHUNK_CELLS, (x1 - 1) // CHUNK_CELLS + 1):
                key = cx, cy
                cells = self.chunks.get(key, set()) | self._previous_chunks.get(key, set())
                for i in cells:
                    x, y = i % width, i // width
                    if x0 <= x < x1 and y0 <= y < y1:
                        yield i

    def _remember(self, index, old):
        if index in self.previous_mass:
            return
        self.previous_mass[index] = old / FULL
        self.previous_types[index] = self.types.get(index, EMPTY)
        if old:
            self._chunk_add(self._previous_chunks, index)

    def reaction_progress(self, index):
        start = self.reactions.get(index)
        if start is None:
            return 0.0
        return max(0.0, min(1.0, (self.time - start) / REACTION_DURATION))

    def _terrain_changed(self, index):
        self._awake.add(index)
        self._awake.update(self.world.neighbors(index))

    def _neighbors_of(self, cells):
        result = set(cells)
        width, last = self.world.width, self.world.width * self.world.height
        for i in cells:
            x = i % width
            if x:
                result.add(i - 1)
            if x + 1 < width:
                result.add(i + 1)
            if i >= width:
                result.add(i - width)
            if i + width < last:
                result.add(i + width)
        return result

    def _passable(self, index, kind):
        return (self.world.foreground[index] == EMPTY
                and index not in self.frozen
                and self.types.get(index, kind) == kind)

    def _transfer(self, proposals):
        """Apply one phase atomically; competing kinds choose by total inflow.

        An empty cell can receive one kind. The greater inflow wins, with the
        material ID resolving an exact tie, independently of iteration order.
        Rejected proposals retain all of their mass at their source.
        """
        incoming = defaultdict(lambda: defaultdict(int))
        delta = defaultdict(int)
        undecided = []
        for source, target, amount, kind in proposals:
            if target in self.types:
                delta[source] -= amount
                delta[target] += amount
            else:
                incoming[target][kind] += amount
                undecided.append((source, target, amount, kind))
        chosen = {}
        for target, amounts in incoming.items():
            chosen[target] = min(amounts, key=lambda kind: (-amounts[kind], kind))
        for source, target, amount, kind in undecided:
            if chosen[target] == kind:
                delta[source] -= amount
                delta[target] += amount
        for i, amount in delta.items():
            if not amount:
                continue
            old = self._units.get(i, 0)
            new = old + amount
            if new < 0:
                raise AssertionError("Liquid transfer spent more mass than its source")
            self._remember(i, old)
            self._changed.add(i)
            if new:
                self._units[i] = new
                self.mass[i] = new / FULL
                if i not in self.types:
                    self.types[i] = chosen[i]
                    self._kind_counts[chosen[i]] += 1
                    self.occupied.add(i)
                    self._chunk_add(self.chunks, i)
            else:
                self._units.pop(i, None)
                self.mass.pop(i, None)
                kind = self.types.pop(i, None)
                self._kind_counts[kind] -= 1
                self.occupied.discard(i)
                self._chunk_remove(i)

    def _gravity(self, candidates, dt):
        proposals = []
        width, height = self.world.width, self.world.height
        # A lower cell's planned outgoing mass creates capacity for the cell
        # above. Each source can spend its original mass once. This lets a full
        # column fall together, avoiding alternating occupied/empty bands and
        # expensive churn of every interior cell. Columns do not interact in
        # this phase, so this spatial order preserves reflection symmetry.
        pending = [-i for i in candidates]
        heapq.heapify(pending)
        queued = set(candidates)
        outgoing = {}
        while pending:
            i = -heapq.heappop(pending)
            kind = self.types.get(i)
            if kind is None or i in self.frozen or i // width + 1 >= height:
                continue
            below = i + width
            if not self._passable(below, kind):
                continue
            source = self._units[i]
            target = self._units.get(below, 0) - outgoing.get(below, 0)
            amount = min(source, self._rates[kind], max(0, FULL - target))
            if amount >= MIN_FLOW_UNITS:
                proposals.append((i, below, amount, kind))
                outgoing[i] = amount
                above = i - width
                if (above >= 0 and above not in queued
                        and self.types.get(above) == kind and above not in self.frozen):
                    queued.add(above)
                    heapq.heappush(pending, -above)
        self._transfer(proposals)

    def _lateral(self, candidates, dt):
        width = self.world.width
        edges = set()
        for i in candidates:
            x = i % width
            if x:
                edges.add(i - 1)
            if x + 1 < width:
                edges.add(i)
        proposals = []
        for left in edges:
            right = left + 1
            lmass, rmass = self._units.get(left, 0), self._units.get(right, 0)
            if lmass == rmass:
                continue
            source, target = (left, right) if lmass > rmass else (right, left)
            kind = self.types.get(source)
            if kind is None or source in self.frozen or not self._passable(target, kind):
                continue
            amount = min(abs(lmass - rmass) // 4, max(1, self._rates[kind] // 4))
            if amount >= MIN_FLOW_UNITS:
                proposals.append((source, target, amount, kind))
        self._transfer(proposals)

    def _contacts(self, candidates):
        if (self._reaction_started or not self._kind_counts[WATER]
                or not self._kind_counts[LAVA]):
            return
        for i in candidates:
            kind = self.types.get(i)
            if kind not in KINDS:
                continue
            for neighbor in self.world.neighbors(i):
                other = self.types.get(neighbor)
                if other in KINDS and other != kind:
                    self._start_reaction()
                    return

    def _start_reaction(self):
        self._reaction_started = True
        finish = self.time + REACTION_DURATION
        for index, kind in sorted(self.types.items()):
            units = self._units[index]
            self.reactions[index] = self.time
            self._reaction_units[index] = units
            self.frozen.add(index)
            heapq.heappush(self._events, (finish, index, kind, units))

    def _advance_reactions(self):
        # Completing cells is bounded per simulation step.
        while (self._events and self._events[0][0] <= self.time + 1e-9
               and self.reaction_work < REACTION_STEP_LIMIT):
            _, index, kind, amount = heapq.heappop(self._events)
            self.reaction_work += 1
            if self.types.get(index) != kind or index not in self.frozen:
                continue
            self._reacted_units += amount
            if kind == WATER:
                self._evaporated_units += amount
            else:
                self._solidified_units += amount
            self._finish_reaction_cell(index, kind)

    def _finish_reaction_cell(self, index, kind):
        self._remember(index, self._units[index])
        self.mass.pop(index)
        self._units.pop(index)
        self._kind_counts[self.types.pop(index)] -= 1
        self.occupied.discard(index)
        self._chunk_remove(index)
        self._changed.add(index)
        if kind == LAVA:
            self.world.set_terrain(index, STONE)
        self.reactions.pop(index, None)
        self._reaction_units.pop(index, None)
        self.frozen.discard(index)

    def step(self, dt=1 / FLUID_HZ):
        if dt < 0:
            raise ValueError("Liquid step duration cannot be negative")
        if not dt:
            return
        self.time += dt
        self.previous_mass.clear()
        self.previous_types.clear()
        self._previous_chunks.clear()
        self._changed.clear()
        self.reaction_work = 0
        self._rates = {WATER: max(1, round(FULL * WATER_FLOW_RATE * dt * FLUID_HZ)),
                       LAVA: max(1, round(FULL * LAVA_FLOW_RATE * dt * FLUID_HZ))}
        candidates = (self.active | self._awake) & self.occupied
        contacts = self._contact_checks | self._awake
        self._contact_checks.clear()
        self._awake.clear()
        self.last_processed = len(candidates)
        self._contacts(contacts)
        self._advance_reactions()
        if candidates:
            self._gravity(candidates, dt)
            candidates |= self._neighbors_of(self._changed) & self.occupied
            self._lateral(candidates, dt)
            self._contacts(self._changed)
        self._advance_reactions()
        # Intermediate gravity/lateral transfers can cancel within one tick.
        # Wake from the final mass difference, so invisible settling cannot
        # keep a pool awake merely by circulating quanta through its surface.
        significant = {i for i in self._changed
                       if abs(self._units.get(i, 0)
                              - round(self.previous_mass.get(i, 0.0) * FULL)) >= MIN_FLOW_UNITS}
        self.active = (self._neighbors_of(significant) | self._awake) & self.occupied
        self.active.difference_update(self.frozen)
        self._awake.clear()
