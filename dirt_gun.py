"""The dirt pistol: the miner shoots clods of dirt paid for from the dig meter.

Rules (tuning in config.py, DIRT_GUN_*):
- Right mouse button (or F) shoots toward the cursor; held, one clod every
  DIRT_GUN_COOLDOWN seconds. F is read by its key position, so a Thai layout
  works too. Bombs are on Q alone.
- Each clod costs DIRT_GUN_COST of the dig meter's capacity. With too little
  left the gun clicks empty ("NO DIRT").
- A clod flies in a shallow arc. Hitting an enemy knocks it back, makes it
  flinch and adds one posture point, so three hits break its guard for a
  deathblow (E). Hitting rock or dirt it just bursts; the map is unchanged.
  A clod falling into water or lava washes away.

Art comes from three sheets built by tools/make_dirt_gun_art.py: the
revolver (the team's art; idle 8 fps with the bell's lining glowing, fire
16 fps), the tumbling clod (12 fps) and the splat (18 fps).
"""
import math
from pathlib import Path

import pygame

from config import (CELL, GRAVITY, DIRT_GUN_COST, DIRT_GUN_COOLDOWN, DIRT_GUN_SPEED,
                    DIRT_GUN_GRAVITY, DIRT_GUN_STUN, DIRT_GUN_KNOCKBACK,
                    WALKER_SIZE)
from level import EMPTY

ASSETS = Path(__file__).with_name('assets')
GUN_WIDTH = 13              # the revolver's width in game pixels (about a third
                            # of the miner's height), before its 1 px outline
GUN_ART = (GUN_WIDTH + 2, round(GUN_WIDTH * 303 / 413) + 2)   # outlined, source aspect
GUN_FRAME = (GUN_ART[0] + 9, GUN_ART[1] + 2)   # room on the right for the muzzle burst
# Where the hand holds it (under the hammer) and the mouth of the bell, as
# shares of the art, so both follow GUN_WIDTH.
GRIP = (1 + round(GUN_ART[0] * 0.25), 1 + round(GUN_ART[1] * 0.55))
MUZZLE = (GUN_ART[0], 1 + round(GUN_ART[1] * 0.3))
CLOD_FRAME = (8, 8)
SPLAT_FRAME = (28, 16)
IDLE_FRAMES, IDLE_FPS = 4, 8
FIRE_FRAMES, FIRE_FPS = 5, 16
CLOD_FRAMES, CLOD_FPS = 4, 12
SPLAT_FRAMES, SPLAT_FPS = 6, 18
SHOW_TIME = 0.9             # the gun stays out this long after the last shot
CLOD_LIFE = 2.5
_sheets = {}


def _frames(name, cell):
    """Rows of frames from an asset sheet, or None if it is missing."""
    if name not in _sheets:
        try:
            sheet = pygame.image.load(str(ASSETS / name))
            if pygame.display.get_surface() is not None:
                sheet = sheet.convert_alpha()
            w, h = cell
            _sheets[name] = [[sheet.subsurface((c * w, r * h, w, h)).copy()
                              for c in range(sheet.get_width() // w)]
                             for r in range(sheet.get_height() // h)]
        except (pygame.error, FileNotFoundError):
            _sheets[name] = None
    return _sheets[name]


class Clod:
    def __init__(self, pos, velocity):
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(velocity)
        self.age = 0.0


class DirtGun:
    def __init__(self, game):
        self.game = game
        self.held = False           # F is down
        self.aim = None             # world point under the cursor
        self.cooldown = 0.0
        self.shown = 0.0            # seconds the gun stays drawn
        self.fired_at = -9.0        # world time of the last shot (fire animation)
        self.clods = []
        self.splats = []            # [world point, age]

    # ---- shooting --------------------------------------------------------
    @property
    def cost(self):
        meter = self.game.dig_meter
        return max(1, round(meter.capacity * DIRT_GUN_COST))

    def hand(self):
        """World point the gun pivots on: the miner's front hand."""
        rect = self.game.player.rect
        right = self.facing_right()
        return pygame.Vector2(rect.centerx + (5 if right else -5), rect.y + 19)

    def facing_right(self):
        if self.aim is None:
            return self.game.miner.facing_right
        return self.aim[0] >= self.game.player.rect.centerx

    def angle(self):
        """Aim angle in radians (0 = right, positive = down)."""
        if self.aim is None:
            return 0.0 if self.facing_right() else math.pi
        d = pygame.Vector2(self.aim) - self.hand()
        if d.length_squared() < 1:
            return 0.0 if self.facing_right() else math.pi
        return math.atan2(d.y, d.x)

    def muzzle(self):
        a = self.angle()
        dx, dy = MUZZLE[0] - GRIP[0], MUZZLE[1] - GRIP[1]
        if not self.facing_right():
            dy = -dy                    # the gun is flipped upside down to aim left
        hand = self.hand()
        return pygame.Vector2(hand.x + dx * math.cos(a) - dy * math.sin(a),
                              hand.y + dx * math.sin(a) + dy * math.cos(a))

    def fire(self):
        """One shot toward the aim; False if it cannot fire right now."""
        game = self.game
        if self.cooldown > 0 or not game.can_act():
            return False
        self.shown = SHOW_TIME
        meter = game.dig_meter
        if meter.remaining < self.cost:
            self.cooldown = DIRT_GUN_COOLDOWN
            rect = game.player.rect
            game.fx.popup('NO DIRT', rect.centerx, rect.top - 6, (240, 120, 80), 0.6)
            return False
        meter.spend(self.cost)
        a = self.angle()
        start = self.muzzle()
        # Fire from the hand if the barrel pokes into rock, so no clod starts inside a wall.
        if self._solid(start):
            start = self.hand()
        self.clods.append(Clod(start, (math.cos(a) * DIRT_GUN_SPEED, math.sin(a) * DIRT_GUN_SPEED)))
        self.cooldown = DIRT_GUN_COOLDOWN
        self.fired_at = game.world_time
        game.shake = min(1.0, game.shake + 0.08)
        return True

    # ---- simulation ------------------------------------------------------
    def update(self, dt):
        self.cooldown = max(0.0, self.cooldown - dt)
        self.shown = max(0.0, self.shown - dt)
        if self.held:
            self.shown = SHOW_TIME
            self.fire()
        alive = []
        for clod in self.clods:
            if self._move(clod, dt):
                alive.append(clod)
        self.clods = alive
        self.splats = [[p, age + dt] for p, age in self.splats if age + dt < SPLAT_FRAMES / SPLAT_FPS]

    def _cell(self, point):
        return math.floor(point.x / CELL), math.floor(point.y / CELL)

    def _solid(self, point):
        x, y = self._cell(point)
        return self.game.world.solid(x, y)

    def _move(self, clod, dt):
        """Advance one clod; False once it has burst or washed away."""
        game = self.game
        clod.age += dt
        clod.velocity.y += GRAVITY * DIRT_GUN_GRAVITY * dt
        steps = max(1, math.ceil(clod.velocity.length() * dt / (CELL / 2)))
        for _ in range(steps):
            previous = pygame.Vector2(clod.pos)
            clod.pos += clod.velocity * (dt / steps)
            if self._solid(clod.pos):
                self.burst(previous)
                return False
            x, y = self._cell(clod.pos)
            if game.liquids.type_at(x, y) != EMPTY:
                game.particles.splash(clod.pos.x, clod.pos.y, 0.35)
                return False
            box = pygame.Rect(0, 0, 6, 6)
            box.center = (round(clod.pos.x), round(clod.pos.y))
            for enemy in game.monsters:
                if box.colliderect(enemy.rect):
                    self.hit(enemy, clod)
                    self.burst(clod.pos)
                    return False
        if clod.age > CLOD_LIFE:
            self.burst(clod.pos)
            return False
        return True

    def burst(self, point):
        """The clod breaks apart (a splat animation); nothing is built."""
        self.splats.append([pygame.Vector2(point), 0.0])

    def hit(self, enemy, clod):
        """Knock an enemy back, make it flinch and chip its posture."""
        game = self.game
        side = 1 if clod.velocity.x >= 0 else -1
        enemy.hurt_time = game.world_time
        if getattr(enemy, 'broken', False):
            return                       # a broken guard waits for the deathblow
        enemy.stun_timer = max(getattr(enemy, 'stun_timer', 0.0), DIRT_GUN_STUN)
        weight = min(1.0, WALKER_SIZE / getattr(enemy, 'size', WALKER_SIZE))
        enemy.knockback = side * DIRT_GUN_KNOCKBACK * weight
        posture = getattr(enemy, 'posture', None)
        if posture is not None and posture.add(1):
            game.enemy_guard_break(enemy, side)
        game.last_combat = game.world_time

    # ---- drawing ---------------------------------------------------------
    def draw(self, screen, camera, time):
        """Clods in flight and their splats (world layer, before lighting)."""
        clods = _frames('dirt_clod_sheet.png', CLOD_FRAME)
        for clod in self.clods:
            x, y = round(clod.pos.x - camera[0]), round(clod.pos.y - camera[1])
            if clods:
                image = clods[0][int(clod.age * CLOD_FPS) % CLOD_FRAMES]
                screen.blit(image, image.get_rect(center=(x, y)))
            else:
                pygame.draw.circle(screen, (128, 84, 48), (x, y), 4)
            # a short dust trail
            back = clod.velocity.normalize() * -6 if clod.velocity.length_squared() else (0, 0)
            screen.fill((150, 118, 84), (x + round(back[0]), y + round(back[1]), 2, 2))
        splats = _frames('dirt_splat_sheet.png', SPLAT_FRAME)
        for point, age in self.splats:
            if splats:
                image = splats[0][min(SPLAT_FRAMES - 1, int(age * SPLAT_FPS))]
                screen.blit(image, image.get_rect(midbottom=(round(point.x - camera[0]),
                                                             round(point.y - camera[1]) + 4)))

    def draw_gun(self, screen, camera, time):
        """The pistol in the miner's hand while F is held or just after a shot."""
        if self.shown <= 0 or not self.game.can_act():
            return
        sheet = _frames('dirt_gun_sheet.png', GUN_FRAME)
        if sheet is None:
            return
        since = time - self.fired_at
        if 0 <= since < FIRE_FRAMES / FIRE_FPS:
            image = sheet[1][int(since * FIRE_FPS)]
        else:
            image = sheet[0][int(time * IDLE_FPS) % IDLE_FRAMES]
        right = self.facing_right()
        pivot = pygame.Vector2(GRIP)
        if not right:
            image = pygame.transform.flip(image, False, True)
            pivot.y = GUN_FRAME[1] - 1 - pivot.y
        degrees = -math.degrees(self.angle())
        rotated = pygame.transform.rotate(image, degrees)
        # Keep the grip on the hand: rotate the grip's offset from the centre.
        center = pygame.Vector2(GUN_FRAME[0] / 2, GUN_FRAME[1] / 2)
        offset = (pivot - center).rotate(-degrees)
        hand = self.hand()
        target = (hand.x - camera[0] - offset.x, hand.y - camera[1] - offset.y)
        screen.blit(rotated, rotated.get_rect(center=(round(target[0]), round(target[1]))))

    def face(self, miner):
        """While the gun is out, the miner faces where it points."""
        if self.shown > 0 and self.aim is not None:
            miner.facing_right = self.facing_right()
