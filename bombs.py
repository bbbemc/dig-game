"""Bombs: pickups placed in a stage, thrown by the player, blasting dirt and stone.

Rules (tuning lives in config.py):
- Only stages listed in BOMB_STAGES place bomb pickups (stage 1 included). The
  authored opening map's spots are always used, plus a random subset of the
  generated world's candidate spots every time the stage starts.
- The player carries at most BOMB_MAX_CARRY bombs and throws one with the Q
  key toward the cursor. The fuse runs from the moment it is thrown.
- An explosion removes dirt and cooled stone (never rock, so locked doors stay
  shut), kills monsters (a boss loses one of its ``hp`` per blast), and hurts
  the player.
- A bomb that lands in water fizzles out without exploding.

Art: assets/bomb_sheet.png (the bomb, its fuse burning down and the spark)
and assets/explosion_sheet.png (flash, fireball, smoke), both drawn by
tools/make_bomb_art.py. Without them the old bomb.png / circles are used.
"""
import math
import random
from pathlib import Path

import pygame

from config import (CELL, MACRO, GRAVITY, BOMB_STAGES, BOMB_SPAWN_COUNT,
                    BOMB_MAX_CARRY, BOMB_THROW_SPEED, BOMB_FUSE, BOMB_SIZE, BOMB_RADIUS,
                    BOMB_PLAYER_DAMAGE)
from level import DIRT, STONE, EMPTY, WATER

BLASTABLE = (DIRT, STONE)
PICKUP_SIZE = 24
ASSET = Path(__file__).with_name('assets') / 'bomb.png'
SHEET = Path(__file__).with_name('assets') / 'bomb_sheet.png'
EXPLOSION = Path(__file__).with_name('assets') / 'explosion_sheet.png'
BOMB_FRAME = 24          # bomb sheet cell
FUSE_ROWS = 5            # fuse lengths, full to stub
SPARK_FPS = 16
EXPLOSION_FRAMES = 10
EXPLOSION_SIZE = 120     # covers the blast radius (BOMB_RADIUS cells)
EXPLOSION_FPS = 20
_images = {}
_sheets = {}


def _load_sheet(path, cell_w, cell_h):
    """Frames of a sheet as rows of surfaces, or None if it is missing."""
    if path not in _sheets:
        try:
            sheet = pygame.image.load(str(path))
            if pygame.display.get_surface() is not None:
                sheet = sheet.convert_alpha()
            rows = sheet.get_height() // cell_h
            cols = sheet.get_width() // cell_w
            _sheets[path] = [[sheet.subsurface((c * cell_w, r * cell_h, cell_w, cell_h)).copy()
                              for c in range(cols)] for r in range(rows)]
        except (pygame.error, FileNotFoundError):
            _sheets[path] = None
    return _sheets[path]


def bomb_frame(fuse_left=1.0, lit=False, time=0.0):
    """The bomb with a fuse ``fuse_left`` (1 full .. 0 gone), sparking if lit."""
    frames = _load_sheet(SHEET, BOMB_FRAME, BOMB_FRAME)
    if frames is None:
        return None
    row = min(FUSE_ROWS - 1, int((1 - max(0.0, min(1.0, fuse_left))) * FUSE_ROWS))
    col = 1 + int(time * SPARK_FPS) % 3 if lit else 0
    return frames[row][col]


def explosion_frame(age):
    """Explosion art ``age`` seconds after the blast, or None once it is over."""
    frames = _load_sheet(EXPLOSION, EXPLOSION_SIZE, EXPLOSION_SIZE)
    index = int(age * EXPLOSION_FPS)
    if frames is None or index >= EXPLOSION_FRAMES:
        return None
    return frames[0][index]


def bomb_image(size):
    """The supplied bomb sprite at a given size, loaded once per size."""
    if size not in _images:
        try:
            image = pygame.image.load(str(ASSET))
            if pygame.display.get_surface() is not None:
                image = image.convert_alpha()
            _images[size] = pygame.transform.scale(image, (size, size))
        except (pygame.error, FileNotFoundError):
            _images[size] = None  # fall back to drawn circles
    return _images[size]


class ThrownBomb:
    def __init__(self, position, velocity):
        self.pos = pygame.Vector2(position)
        self.velocity = pygame.Vector2(velocity)
        self.fuse = BOMB_FUSE

    @property
    def rect(self):
        rect = pygame.Rect(0, 0, BOMB_SIZE, BOMB_SIZE)
        rect.center = (round(self.pos.x), round(self.pos.y))
        return rect


class BombSystem:
    def __init__(self, game, spawn_spots, stage_number, force=False, rng=None,
                 count=None, fixed=()):
        self.game = game
        self.carried = 0
        self.thrown = []
        self.blasts = []        # (world centre, age) of explosions still playing
        self.aim = None  # world point while the throw button is held
        self.enabled = force or stage_number in BOMB_STAGES
        self.pickups = []
        if self.enabled and (spawn_spots or fixed):
            rng = rng or random.Random()
            count = min(count or BOMB_SPAWN_COUNT, len(spawn_spots))
            # ``fixed`` spots (an authored chamber's) are always used; a random
            # subset of the generated world's candidate spots is added.
            for mx, my in list(fixed) + rng.sample(list(spawn_spots), count):
                rect = pygame.Rect(0, 0, PICKUP_SIZE, PICKUP_SIZE)
                # Sit on the floor of the authored macro cell.
                rect.midbottom = (mx * MACRO + MACRO // 2, (my + 1) * MACRO)
                self.pickups.append(rect)

    # ---- input -------------------------------------------------------
    def launch_velocity(self, start, target):
        direction = pygame.Vector2(target) - start
        if direction.length_squared() == 0:
            direction = pygame.Vector2(1, 0)
        direction.scale_to_length(BOMB_THROW_SPEED)
        direction.y -= BOMB_THROW_SPEED * 0.25  # a little lift so it arcs
        return direction

    def throw(self, target):
        """Throw one carried bomb toward a world-pixel target."""
        self.aim = None
        if not self.enabled or self.carried <= 0:
            return False
        start = pygame.Vector2(self.game.player.rect.center)
        self.thrown.append(ThrownBomb(start, self.launch_velocity(start, target)))
        self.carried -= 1
        return True

    def predict(self, target, step=1 / 60):
        """Where a bomb thrown now would travel: (points, explodes_at or None).

        Uses the same movement as a real bomb for the whole fuse, so the end
        of the line is where it will explode. Stops early if it would land in
        water, where it fizzles (explodes_at is then None).
        """
        start = pygame.Vector2(self.game.player.rect.center)
        bomb = ThrownBomb(start, self.launch_velocity(start, target))
        points = [pygame.Vector2(bomb.pos)]
        time = 0.0
        while time < BOMB_FUSE:
            self._move(bomb, step)
            time += step
            points.append(pygame.Vector2(bomb.pos))
            if self.game.touches(bomb.rect, WATER):
                return points, None
        return points, bomb.pos

    # ---- simulation --------------------------------------------------
    def update(self, dt):
        if not self.enabled:
            return
        game = self.game
        player = game.player.rect
        for rect in self.pickups[:]:
            if self.carried < BOMB_MAX_CARRY and player.colliderect(rect):
                self.pickups.remove(rect)
                self.carried += 1
        self.blasts = [(c, age + dt) for c, age in self.blasts
                       if age + dt < EXPLOSION_FRAMES / EXPLOSION_FPS]
        remaining = []
        for bomb in self.thrown:
            self._move(bomb, dt)
            if game.touches(bomb.rect, WATER):
                game.particles.splash(bomb.pos.x, bomb.pos.y, 0.5)
                continue  # fizzled
            bomb.fuse -= dt
            if bomb.fuse <= 0:
                self.explode(bomb.pos)
            else:
                remaining.append(bomb)
        self.thrown = remaining

    def _solid_at(self, x, y):
        return self.game.world.solid(math.floor(x / CELL), math.floor(y / CELL))

    def _move(self, bomb, dt):
        bomb.velocity.y += GRAVITY * dt
        steps = max(1, math.ceil(bomb.velocity.length() * dt / (CELL / 2)))
        for _ in range(steps):
            step = bomb.velocity * (dt / steps)
            nx = bomb.pos.x + step.x
            if self._solid_at(nx, bomb.pos.y):
                bomb.velocity.x *= -0.3
            else:
                bomb.pos.x = nx
            ny = bomb.pos.y + step.y
            if self._solid_at(bomb.pos.x, ny + BOMB_SIZE / 2 * (1 if step.y > 0 else -1)):
                if step.y > 0:  # landed: lose most energy, roll to a stop
                    bomb.velocity.x *= 0.55
                bomb.velocity.y *= -0.25
                if abs(bomb.velocity.y) < 30:
                    bomb.velocity.y = 0
            else:
                bomb.pos.y = ny

    def explode(self, center):
        game = self.game
        world = game.world
        cx, cy = int(center.x // CELL), int(center.y // CELL)
        removed = []
        for y in range(max(1, cy - BOMB_RADIUS), min(world.height - 1, cy + BOMB_RADIUS + 1)):
            for x in range(max(1, cx - BOMB_RADIUS), min(world.width - 1, cx + BOMB_RADIUS + 1)):
                i = world.index(x, y)
                if (x - cx) ** 2 + (y - cy) ** 2 <= BOMB_RADIUS ** 2 and world.foreground[i] in BLASTABLE:
                    world.set_terrain(i, EMPTY)
                    removed.append(i)
        game.particles.dirt(world, removed, game.renderer.debris_colors)
        game.gold_system.dug(removed)
        game.particles.dust(center.x, center.y, 1.0)
        self.blasts.append((pygame.Vector2(center), 0.0))
        game.shake = min(1.0, game.shake + 0.6)
        reach = (BOMB_RADIUS + 1) * CELL
        blast = pygame.Rect(0, 0, reach * 2, reach * 2)
        blast.center = (round(center.x), round(center.y))
        # A Forge room makes bombs hit harder: a wider reach on enemies (the
        # dirt it digs and the player's own danger zone stay the same).
        rooms = getattr(game, 'rooms', None)
        power = 1.0 + (rooms.damage_bonus() if rooms is not None else 0.0)
        strike = blast.inflate(round(reach * 2 * (power - 1)), round(reach * 2 * (power - 1)))
        survivors = []
        for monster in game.monsters:
            if not strike.colliderect(monster.rect):
                survivors.append(monster)
            elif getattr(monster, 'is_boss', False):
                monster.hurt_timer = 0.5
                monster.hurt_time = game.world_time     # flinch animation
                posture = getattr(monster, 'posture', None)
                if posture is not None and not monster.broken:
                    side = 1 if monster.rect.centerx >= center.x else -1
                    if posture.add(rooms.posture_points(4) if rooms is not None else 4):
                        game.enemy_guard_break(monster, side)
                survivors.append(monster)
        game.monsters = survivors
        if blast.colliderect(game.player.rect):
            game.hp -= BOMB_PLAYER_DAMAGE
            game.hurt_timer = 0.8
            if game.hp <= 0:
                game.state = 'lose'
        return removed

    # ---- drawing -----------------------------------------------------
    def draw(self, screen, camera, time):
        if not self.enabled:
            return
        if self.aim is not None and self.carried:
            self.draw_aim(screen, camera)
        for rect in self.pickups:
            bob = round(math.sin(time * 3 + rect.x) * 2)
            draw_bomb(screen, rect.move(-camera[0], -camera[1] + bob), PICKUP_SIZE)
        for bomb in self.thrown:
            box = bomb.rect.move(-camera[0], -camera[1])
            left = bomb.fuse / BOMB_FUSE
            # The last moments: it blinks hot, faster and faster.
            hot = bomb.fuse < 0.8 and int(time * (8 if bomb.fuse > 0.35 else 18)) % 2 == 0
            image = bomb_frame(left, lit=True, time=time + id(bomb) % 7 * 0.05)
            if image is None:
                draw_bomb(screen, box, BOMB_SIZE)
                if int(time * (6 if bomb.fuse > 0.7 else 16)) % 2 == 0:
                    pygame.draw.circle(screen, (255, 214, 92), (box.centerx + 4, box.top - 2), 3)
                continue
            if hot:
                image = image.copy()
                image.fill((120, 26, 10, 0), special_flags=pygame.BLEND_RGBA_ADD)
            # Squash a little on the final beat before it goes off.
            if bomb.fuse < 0.15:
                w, h = image.get_size()
                image = pygame.transform.scale(image, (w + 4, h - 2))
            screen.blit(image, image.get_rect(center=(box.centerx, box.centery - 2)))

    def draw_emissive(self, screen, camera, time):
        """Explosions, drawn after the light map so the fireball glows."""
        for center, age in self.blasts:
            image = explosion_frame(age)
            if image is not None:
                screen.blit(image, image.get_rect(center=(round(center.x - camera[0]),
                                                         round(center.y - camera[1]))))

    def lights(self):
        """Lighting sources: fuse sparks and the blast's flash."""
        for bomb in self.thrown:
            yield ('flash', bomb.pos.x + 6, bomb.pos.y - 8, 48, (255, 170, 70), 0)
        for center, age in self.blasts:
            fade = 1 - age / (EXPLOSION_FRAMES / EXPLOSION_FPS)
            if fade > 0.15:
                yield ('flash', center.x, center.y, max(64, round(260 * fade / 32) * 32),
                       (255, 150, 60), 0)

    def draw_aim(self, screen, camera):
        """Dotted throw arc, with the blast area where the fuse runs out."""
        points, explodes_at = self.predict(self.aim)
        for n in range(3, len(points), 4):
            p = points[n]
            fade = 1 - n / len(points)
            pygame.draw.circle(screen, (255, 236, 170) if fade > .5 else (238, 196, 120),
                               (round(p.x - camera[0]), round(p.y - camera[1])), 2 if fade > .3 else 1)
        end = points[-1]
        center = (round(end.x - camera[0]), round(end.y - camera[1]))
        if explodes_at is None:  # lands in water: a small blue ring, no blast
            pygame.draw.circle(screen, (110, 180, 255), center, 7, 2)
            return
        radius = BOMB_RADIUS * CELL
        area = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(area, (255, 120, 60, 50), (radius + 1, radius + 1), radius)
        pygame.draw.circle(area, (255, 170, 90, 200), (radius + 1, radius + 1), radius, 2)
        screen.blit(area, (center[0] - radius - 1, center[1] - radius - 1))

    def draw_carried(self, screen, camera, player_rect):
        """Show the bomb in the miner's hand while carrying any."""
        if self.enabled and self.carried:
            box = pygame.Rect(0, 0, BOMB_SIZE, BOMB_SIZE)
            box.center = (player_rect.right - 2 - camera[0], player_rect.centery + 4 - camera[1])
            draw_bomb(screen, box, BOMB_SIZE)


def draw_bomb(screen, box, size):
    """An unlit bomb (pickups, the HUD, the bomb in hand) centred in ``box``."""
    frame = bomb_frame(1.0, lit=False)
    if frame is not None:
        if size != BOMB_FRAME:
            frame = pygame.transform.scale(frame, (size, size))
        screen.blit(frame, frame.get_rect(center=box.center))
        return
    image = bomb_image(size)
    if image is not None:
        screen.blit(image, box.topleft)
    else:
        pygame.draw.circle(screen, (24, 22, 28), box.center, size // 2)
        pygame.draw.circle(screen, (90, 90, 104), (box.centerx - size // 6, box.centery - size // 6), size // 6)
