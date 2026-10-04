"""Player and monster movement in pixels, with collision on the cell grid."""

from collections import deque
import math

import pygame

from config import (CELL, GRAVITY, JUMP_SPEED, LADDER_JUMP_GRACE, MAX_FALL_SPEED,
                    MAX_FRAME_DT, MOVE_SPEED, PHYSICS_HZ, PLAYER_SIZE, SWIM_SPEED)


_EPSILON = 1e-7


class Actor:
    """A square actor whose float position is its top-left pixel coordinate.

    ``rect`` is an integer pixel rectangle for rendering and actor contacts.
    Terrain collision uses ``pos`` directly, retaining fractional movement.
    The caller verifies ``ladder_attached`` against a visible, supported ladder.
    """

    def __init__(self, world, x, y, size=PLAYER_SIZE, speed=MOVE_SPEED):
        self.world = world
        self.size = int(size)
        if self.size <= 0:
            raise ValueError("Actor size must be positive")
        self.speed = float(speed)
        self.pos = pygame.Vector2(x, y)
        self.velocity = pygame.Vector2()
        self.rect = pygame.Rect(round(x), round(y), self.size, self.size)
        self.grounded = False
        self.on_ladder = False
        self.ladder_detach_timer = 0.0
        self.hit_wall = False
        self.hit_ceiling = False
        self.landed = False

    def _sync_rect(self):
        self.rect.topleft = round(self.pos.x), round(self.pos.y)

    def _solid_cells(self, x, y):
        left, top = math.floor(x / CELL), math.floor(y / CELL)
        right = math.floor((x + self.size - _EPSILON) / CELL)
        bottom = math.floor((y + self.size - _EPSILON) / CELL)
        return [(tx, ty) for ty in range(top, bottom + 1)
                for tx in range(left, right + 1) if self.world.solid(tx, ty)]

    def overlaps_terrain(self):
        """Whether the actor's precise bounds intersect solid terrain."""
        return bool(self._solid_cells(self.pos.x, self.pos.y))

    def _supported(self):
        return bool(self._solid_cells(self.pos.x, self.pos.y + 0.001))

    def _move_axis(self, amount, axis):
        """Sweep in short pieces and stop exactly at the first solid face."""
        if not amount:
            return False
        pieces = max(1, math.ceil(abs(amount) / (CELL / 2)))
        piece = amount / pieces
        for _ in range(pieces):
            candidate = self.pos.copy()
            candidate[axis] += piece
            cells = self._solid_cells(candidate.x, candidate.y)
            if cells:
                if piece > 0:
                    self.pos[axis] = min(cell[axis] * CELL - self.size
                                         for cell in cells)
                else:
                    self.pos[axis] = max((cell[axis] + 1) * CELL
                                         for cell in cells)
                self.velocity[axis] = 0
                return True
            self.pos[axis] = candidate[axis]
        return False

    def _find_clear_position(self):
        """Recover an invalid authored spawn using a nearby open cell box."""
        if not self.overlaps_terrain():
            return True
        max_x = self.world.pixel_width - self.size
        max_y = self.world.pixel_height - self.size
        if max_x < 0 or max_y < 0:
            return False
        start = (math.floor(max(0, min(self.pos.x, max_x)) / CELL),
                 math.floor(max(0, min(self.pos.y, max_y)) / CELL))
        queue, seen = deque([start]), {start}
        while queue:
            x, y = queue.popleft()
            px, py = x * CELL, y * CELL
            if px <= max_x and py <= max_y and not self._solid_cells(px, py):
                self.pos.update(px, py)
                return True
            # Prefer a floor below the authored spawn over moving sideways.
            for nx, ny in ((x, y + 1), (x - 1, y), (x + 1, y), (x, y - 1)):
                if (nx, ny) not in seen and 0 <= nx < self.world.width and 0 <= ny < self.world.height:
                    seen.add((nx, ny))
                    queue.append((nx, ny))
        return False

    def drop_to_ground(self):
        """Place a spawn on the first floor beneath it; return success.

        An obstructed spawn first moves to the closest open position in cell
        steps. Liquids are separate from terrain, so they do not form a floor.
        """
        if not self._find_clear_position():
            return False
        left = math.floor(self.pos.x / CELL)
        right = math.floor((self.pos.x + self.size - _EPSILON) / CELL)
        first_row = math.floor((self.pos.y + self.size - _EPSILON) / CELL) + 1
        for y in range(first_row, self.world.height + 1):
            if any(self.world.solid(x, y) for x in range(left, right + 1)):
                self.pos.y = y * CELL - self.size
                self.velocity.update(0, 0)
                self.grounded = True
                self.on_ladder = False
                self.ladder_detach_timer = 0.0
                self._sync_rect()
                return True
        return False

    def update(self, dt, horizontal, jump=False, swimming=False, climb=0,
               ladder_attached=None):
        """Advance by seconds; horizontal/climb inputs are in [-1, 1].

        ``jump`` is a discrete request. Swimming lowers gravity and grants a
        buoyant jump. ``ladder_attached`` means the caller verified a ladder
        under the actor. Climbing attaches; neutral input then holds position.
        A jump briefly prevents attachment so held climb cannot cancel it.
        Omitting the keyword retains the old nonzero-climb attachment behavior.
        Large frame gaps are clamped and each physics step is at most 1/120 s.
        """
        dt = max(0.0, min(float(dt), MAX_FRAME_DT))
        horizontal = max(-1.0, min(float(horizontal), 1.0))
        climb = max(-1.0, min(float(climb), 1.0))
        was_grounded = self.grounded
        was_on_ladder = self.on_ladder
        self.ladder_detach_timer = max(0.0, self.ladder_detach_timer - dt)
        ladder_available = bool(climb) if ladder_attached is None else bool(ladder_attached)
        if self.overlaps_terrain() and self._find_clear_position():
            # A liquid reaction can create stone inside a moving actor.
            self.velocity.y = 0
        self.grounded = not self.overlaps_terrain() and self._supported()
        self.hit_wall = self.hit_ceiling = self.landed = False
        can_attach = ladder_available and self.ladder_detach_timer <= _EPSILON
        self.on_ladder = can_attach and (bool(climb) or was_on_ladder)
        self.velocity.x = horizontal * (SWIM_SPEED if swimming else self.speed)
        if jump and (self.grounded or swimming or can_attach):
            self.velocity.y = -JUMP_SPEED * (0.55 if swimming else 1.0)
            self.grounded = False
            self.on_ladder = False
            self.ladder_detach_timer = LADDER_JUMP_GRACE
        if not dt:
            self._sync_rect()
            return

        steps = max(1, math.ceil(dt * PHYSICS_HZ))
        step_dt = dt / steps
        gravity = GRAVITY * (0.25 if swimming else 1.0)
        fall_limit = MAX_FALL_SPEED * (0.4 if swimming else 1.0)
        for _ in range(steps):
            if self.on_ladder:
                self.velocity.y = climb * SWIM_SPEED
            else:
                self.velocity.y = min(fall_limit, self.velocity.y + gravity * step_dt)
            if self._move_axis(self.velocity.x * step_dt, 0):
                self.hit_wall = True
            downward = self.velocity.y >= 0
            hit_vertical = self._move_axis(self.velocity.y * step_dt, 1)
            if hit_vertical and not downward:
                self.hit_ceiling = True
            self.grounded = downward and self._supported()
        self.landed = self.grounded and not was_grounded
        self._sync_rect()


class Player(Actor):
    """Player defaults; monsters can use Actor with their own size and speed."""


def drop_to_ground(actor):
    """Convenience wrapper for ``actor.drop_to_ground()``."""
    return actor.drop_to_ground()
