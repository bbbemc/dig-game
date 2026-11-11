"""Rooms the miner builds inside dug-out space: a Forge, a Herald and a Kitchen.

Rules (prices and buffs in ROOM_TYPES / SIZES below):
- Up to MAX_ROOMS rooms per stage, one of each type. Gold pays for them.
- B toggles Build Mode; 1/2/3 pick size S/M/L. A blueprint follows the mouse
  and settles on the floor below it: green when the space is fully dug out
  (no dirt, rock, water or lava inside), stands on solid ground and touches no
  other room or door; red with the reason otherwise.
- Left click or Enter on a green blueprint opens the room menu (Forge, Herald,
  Kitchen with the price for that size; types already built show BUILT).
- A built S or M room can be expanded one size (pay the price difference)
  when the bigger footprint is dug out too: press B while standing in it, or
  click it in Build Mode.
- Buffs last for the stage (bonus rooms keep them):
    Forge   refills bombs and adds damage (gun, parry and bomb posture hits,
            and the bomb's reach on enemies)
    Herald  shortens the dirt gun and parry cooldowns and refills dig energy
    Kitchen heals at once and raises max O2
- Rooms are background: the miner walks through them.

Art: assets/rooms/<kind>_<size>.png, baked from the team's pictures in
assets/rooms/source/ by tools/make_room_art.py. The name sign, lamp and fire
glow, sparks and steam are drawn live on top (LIVE below).
"""

import math
import random
from pathlib import Path

import pygame

from config import CELL, PLAYER_MAX_HP, BOMB_MAX_CARRY
from level import EMPTY

MAX_ROOMS = 3
ORDER = ('forge', 'herald', 'kitchen')
SIZE_NAMES = ('S', 'M', 'L')
# Footprints in cells (8 px): the miner is 4 cells (32 px) tall.
SIZES = {'S': (12, 8), 'M': (16, 10), 'L': (20, 12)}
FLOOR_SHARE = 0.75        # of the cells under a room that must be solid
FLOOR_SEARCH = 12         # cells below the cursor searched for a floor

ROOM_TYPES = {
    'forge': {
        'name': 'FORGE', 'price': {'S': 25, 'M': 40, 'L': 55},
        'power': {'S': 0.15, 'M': 0.30, 'L': 0.50},
        'accent': (238, 120, 46),
    },
    'herald': {
        'name': 'HERALD', 'price': {'S': 30, 'M': 45, 'L': 60},
        'cooldown': {'S': 0.20, 'M': 0.35, 'L': 0.50},
        'dig': {'S': 0.25, 'M': 0.40, 'L': 0.60},
        'accent': (96, 150, 236),
    },
    'kitchen': {
        'name': 'KITCHEN', 'price': {'S': 20, 'M': 30, 'L': 40},
        'heal': {'S': 30, 'M': 60, 'L': 100},
        'oxygen': {'S': 0.20, 'M': 0.40, 'L': 0.60},
        'accent': (120, 200, 96),
    },
}

GREEN = (96, 232, 120)
RED = (240, 72, 60)


def effects(kind, size):
    """The lines a menu shows for a room of this kind and size."""
    info = ROOM_TYPES[kind]
    if kind == 'forge':
        return ['REFILL BOMBS', f'+{round(info["power"][size] * 100)}% DAMAGE']
    if kind == 'herald':
        return [f'-{round(info["cooldown"][size] * 100)}% COOLDOWN',
                f'+{round(info["dig"][size] * 100)}% DIG']
    return [f'+{info["heal"][size]} HP', f'+{round(info["oxygen"][size] * 100)}% MAX O2']


def bigger(size):
    index = SIZE_NAMES.index(size)
    return SIZE_NAMES[index + 1] if index + 1 < len(SIZE_NAMES) else None


class Room:
    def __init__(self, kind, size, rect):
        self.kind, self.size = kind, size
        self.rect = pygame.Rect(rect)          # in cells
        self.built_at = 0.0
        self.art = None

    @property
    def pixels(self):
        r = self.rect
        return pygame.Rect(r.x * CELL, r.y * CELL, r.w * CELL, r.h * CELL)

    @property
    def name(self):
        return f'{ROOM_TYPES[self.kind]["name"]} [{self.size}]'


class RoomSystem:
    def __init__(self, game):
        self.game = game
        self.rooms = []
        self.parent = None          # a bonus room keeps its stage's buffs
        self.build_mode = False
        self.size = 'S'
        self.menu = None            # None, ('build', rect) or ('expand', room)
        self.buttons = []           # (screen rect, action) of the open menu
        self.hover = None           # menu action under the mouse
        self.blueprint = None       # (cell rect, reason or None, room to expand)
        self.mouse_latch = False    # swallow the held left button after a click
        self.carry = 0.0            # Forge damage carried between hits
        self.message = None         # (text, seconds left) under the build banner
        self.random = random.Random(7)

    # ---- buffs -------------------------------------------------------
    def all_rooms(self):
        rooms = list(self.rooms)
        if self.parent is not None:
            rooms += [r for r in self.parent.rooms
                      if all(r.kind != mine.kind for mine in self.rooms)]
        return rooms

    def level(self, kind):
        return next((r.size for r in self.all_rooms() if r.kind == kind), None)

    def damage_bonus(self):
        size = self.level('forge')
        return ROOM_TYPES['forge']['power'][size] if size else 0.0

    def cooldown_scale(self):
        size = self.level('herald')
        return 1.0 - ROOM_TYPES['herald']['cooldown'][size] if size else 1.0

    def oxygen_bonus(self):
        size = self.level('kitchen')
        return ROOM_TYPES['kitchen']['oxygen'][size] if size else 0.0

    def posture_points(self, points):
        """Posture points a hit deals with the Forge's bonus. Whole points
        only: the fraction carries to the next hit (+50% = every other hit
        lands one more)."""
        total = points * (1.0 + self.damage_bonus()) + self.carry
        whole = int(total + 1e-9)
        self.carry = total - whole
        return whole

    def sync(self):
        """Push the cooldown buff into the parry timer."""
        combat = getattr(self.game, 'combat', None)
        if combat is not None:
            combat.parry.cooldown_scale = self.cooldown_scale()

    def _apply(self, kind, size, before=None):
        """A room's one-off effects on build (or on expanding from ``before``)."""
        game = self.game
        info = ROOM_TYPES[kind]
        if kind == 'forge':
            if game.bombs.enabled:
                game.bombs.carried = BOMB_MAX_CARRY
        elif kind == 'herald':
            share = info['dig'][size] - (info['dig'][before] if before else 0.0)
            game.dig_meter.refill(share)
        else:
            heal = info['heal'][size] - (info['heal'][before] if before else 0)
            game.hp = min(PLAYER_MAX_HP, game.hp + heal)
            extra = 100 * (info['oxygen'][size] - (info['oxygen'][before] if before else 0.0))
            game.oxygen = min(game.max_oxygen, game.oxygen + extra)
        self.sync()

    # ---- placement ---------------------------------------------------
    def can_build_here(self):
        return not self.game.bonus_room

    def footprint(self, world_point, size):
        """The cell rect a blueprint of ``size`` takes at a world point,
        settled onto the first floor below it."""
        world = self.game.world
        w, h = SIZES[size]
        cx, cy = int(world_point[0] // CELL), int(world_point[1] // CELL)
        floor = None
        for row in range(cy, cy + FLOOR_SEARCH + h):
            if world.solid(cx, row):
                floor = row
                break
        if floor is None or floor - h < 0:
            floor = cy + h
        return pygame.Rect(cx - w // 2, floor - h, w, h)

    def _doors(self):
        game = self.game
        for door in (game.exit_door, game.bonus_door, game.chamber_gate):
            if door is not None:
                yield pygame.Rect(door.x // CELL, door.y // CELL,
                                  math.ceil(door.w / CELL), math.ceil(door.h / CELL))

    def check(self, rect, ignore=None):
        """None when a room fits the cell rect, else the reason it does not."""
        game, world = self.game, self.game.world
        if (rect.x < 1 or rect.y < 1 or rect.right >= world.width - 1
                or rect.bottom >= world.height - 1):
            return 'OUT OF BOUNDS'
        liquids = game.liquids.types
        dirt = wet = False
        for y in range(rect.y, rect.bottom):
            base = y * world.width
            for x in range(rect.x, rect.right):
                i = base + x
                if world.foreground[i] != EMPTY:
                    dirt = True
                elif i in liquids:
                    wet = True
        if dirt:
            return 'DIG MORE SPACE'
        if wet:
            return 'NO WATER OR LAVA'
        solid = sum(world.solid(x, rect.bottom) for x in range(rect.x, rect.right))
        if (solid < FLOOR_SHARE * rect.w or not world.solid(rect.x, rect.bottom)
                or not world.solid(rect.right - 1, rect.bottom)):
            return 'NEED SOLID FLOOR'
        for room in self.rooms:
            if room is not ignore and room.rect.colliderect(rect):
                return 'OVERLAPS A ROOM'
        if any(door.colliderect(rect) for door in self._doors()):
            return 'BLOCKS A DOOR'
        return None

    def expansion(self, room):
        """(cell rect, reason) for growing a room one size, trying the
        footprint centred, then grown to the right, then to the left."""
        size = bigger(room.size)
        if size is None:
            return None, 'MAX SIZE'
        w, h = SIZES[size]
        bottom = room.rect.bottom
        first = None
        for x in (room.rect.centerx - w // 2, room.rect.x, room.rect.right - w):
            rect = pygame.Rect(x, bottom - h, w, h)
            reason = self.check(rect, ignore=room)
            if reason is None:
                return rect, None
            first = first or (rect, reason)
        return first

    def room_at(self, world_point):
        cell = (int(world_point[0] // CELL), int(world_point[1] // CELL))
        return next((r for r in self.rooms if r.rect.collidepoint(cell)), None)

    def update_blueprint(self, world_point):
        """Recompute the blueprint under the cursor (Build Mode only)."""
        if not self.build_mode or self.menu is not None:
            return
        room = self.room_at(world_point)
        if room is not None:
            rect, reason = self.expansion(room)
            self.blueprint = (rect if rect is not None else room.rect, reason, room)
            return
        rect = self.footprint(world_point, self.size)
        reason = ('ROOM LIMIT 3/3' if len(self.rooms) >= MAX_ROOMS
                  else self.check(rect))
        self.blueprint = (rect, reason, None)

    # ---- actions -----------------------------------------------------
    @property
    def busy(self):
        """Build Mode or a menu owns the left button (no digging)."""
        return self.build_mode or self.menu is not None or self.mouse_latch

    def say(self, text, seconds=1.6):
        self.message = (text, seconds)

    def press_b(self):
        """B: open the expand menu when standing in a room that can grow,
        else toggle Build Mode."""
        if self.menu is not None:
            self.close()
            return
        if not self.can_build_here():
            self.say("CAN'T BUILD IN A BONUS ROOM")
            return
        if not self.build_mode:
            room = self.room_at(self.game.player.rect.center)
            if room is not None and bigger(room.size):
                self.open_expand(room)
                return
        self.build_mode = not self.build_mode
        self.blueprint = None

    def pick_size(self, number):
        if self.menu is not None:
            self.choose(number)
        elif self.build_mode and 1 <= number <= 3:
            self.size = SIZE_NAMES[number - 1]

    def confirm(self):
        """Left click / Enter on the blueprint: open the matching menu."""
        if self.menu is not None or not self.build_mode or self.blueprint is None:
            return False
        rect, reason, room = self.blueprint
        if room is not None:
            self.open_expand(room)
            return True
        if reason is not None:
            self.say(reason)
            return True
        self.menu = ('build', pygame.Rect(rect))
        return True

    def open_expand(self, room):
        self.menu = ('expand', room)

    def close(self):
        self.menu = None
        self.buttons = []

    def cancel(self):
        """Esc: close the menu, then leave Build Mode. False if neither was open."""
        if self.menu is not None:
            self.close()
            return True
        if self.build_mode:
            self.build_mode = False
            self.blueprint = None
            return True
        return False

    def build(self, kind):
        """Buy the open blueprint as ``kind``; the reason it failed, or None."""
        if self.menu is None or self.menu[0] != 'build':
            return 'NO SPACE CHOSEN'
        rect = self.menu[1]
        size = next(s for s, (w, h) in SIZES.items() if (w, h) == rect.size)
        if any(r.kind == kind for r in self.rooms):
            return 'BUILT'
        if len(self.rooms) >= MAX_ROOMS:
            return 'ROOM LIMIT 3/3'
        reason = self.check(rect)
        if reason is not None:
            return reason
        price = ROOM_TYPES[kind]['price'][size]
        if self.game.gold < price:
            return f'NEED {price} G'
        self.game.gold -= price
        room = Room(kind, size, rect)
        room.built_at = self.game.world_time
        self.rooms.append(room)
        self._apply(kind, size)
        self._celebrate(room, f'{room.name} BUILT!')
        self.close()
        self.build_mode = False
        self.blueprint = None
        return None

    def expand(self, room):
        """Grow ``room`` one size; the reason it failed, or None."""
        size = bigger(room.size)
        if size is None:
            return 'MAX SIZE'
        rect, reason = self.expansion(room)
        if reason is not None:
            return reason
        info = ROOM_TYPES[room.kind]
        price = info['price'][size] - info['price'][room.size]
        if self.game.gold < price:
            return f'NEED {price} G'
        self.game.gold -= price
        before, room.size, room.rect, room.art = room.size, size, rect, None
        room.built_at = self.game.world_time
        self._apply(room.kind, size, before)
        self._celebrate(room, f'{room.name} UPGRADED!')
        self.close()
        self.build_mode = False
        self.blueprint = None
        return None

    def choose(self, action):
        """A menu choice by number (1-3) or action name."""
        if self.menu is None:
            return None
        if self.menu[0] == 'build':
            if isinstance(action, int):
                if not 1 <= action <= 3:
                    return None
                action = ORDER[action - 1]
            if action in ROOM_TYPES:
                reason = self.build(action)
                if reason:
                    self.say(reason)
                return reason
        else:
            if action in (1, 'expand'):
                reason = self.expand(self.menu[1])
                if reason:
                    self.say(reason)
                return reason
        if action == 'close':
            self.close()
        return None

    def click(self, screen_pos, camera):
        """A left click in the game; True when the rooms used it."""
        if self.menu is not None:
            self.mouse_latch = True
            action = next((a for r, a in self.buttons if r.collidepoint(screen_pos)), None)
            if action is not None:
                self.choose(action)
            return True
        if self.build_mode:
            self.mouse_latch = True
            self.update_blueprint((screen_pos[0] + camera[0], screen_pos[1] + camera[1]))
            self.confirm()
            return True
        return False

    def _celebrate(self, room, text):
        game = self.game
        px = room.pixels
        game.fx.popup(text, px.centerx, px.y - 10, ROOM_TYPES[room.kind]['accent'], 1.6)
        for n in range(5):
            game.particles.dust(px.x + px.w * (n + 0.5) / 5, px.bottom - 2, 0.7)
        game.shake = min(1.0, game.shake + 0.15)

    def update(self, dt, mouse_down=False):
        if not mouse_down:
            self.mouse_latch = False
        if self.message is not None:
            text, left = self.message
            self.message = (text, left - dt) if left - dt > 0 else None

    # ---- world drawing -------------------------------------------------
    def lights(self):
        for room in self.rooms:
            px = room.pixels
            for n, (fx, fy, color, radius, _) in enumerate(LIVE[room.kind]['glow']):
                scale = SIZES[room.size][0] / SIZES['M'][0]
                yield ('torch', px.x + fx * px.w, px.y + fy * px.h,
                       round(radius * scale), color, n % 6)

    def draw(self, screen, camera, time):
        """Rooms behind everything that moves (after the terrain)."""
        view = screen.get_rect()
        for room in self.rooms:
            px = room.pixels.move(-camera[0], -camera[1])
            if not px.colliderect(view):
                continue
            if room.art is None:
                room.art = room_image(room.kind, room.size)
            screen.blit(room.art, px)
            draw_live(screen, room, px, time)
            board = sign(room.kind, room.size)     # nailed onto the top beam
            screen.blit(board, board.get_rect(center=(px.centerx, px.y + 5)))

    def draw_overlay(self, screen, camera, time):
        """Blueprint (after the light map, so it reads in the dark)."""
        if not self.build_mode or self.blueprint is None or self.menu is not None:
            return
        rect, reason, room = self.blueprint
        px = pygame.Rect(rect.x * CELL - camera[0], rect.y * CELL - camera[1],
                         rect.w * CELL, rect.h * CELL)
        color = GREEN if reason is None else RED
        pulse = 0.5 + 0.5 * math.sin(time * 6)
        shade = pygame.Surface(px.size, pygame.SRCALPHA)
        shade.fill((*color, 38 + round(26 * pulse)))
        # blueprint grid every cell
        for x in range(0, px.w, CELL):
            shade.fill((*color, 40), (x, 0, 1, px.h))
        for y in range(0, px.h, CELL):
            shade.fill((*color, 40), (0, y, px.w, 1))
        screen.blit(shade, px)
        pygame.draw.rect(screen, color, px, 2)
        # corner brackets
        for cx, cy, dx, dy in ((px.left, px.top, 1, 1), (px.right - 1, px.top, -1, 1),
                               (px.left, px.bottom - 1, 1, -1), (px.right - 1, px.bottom - 1, -1, -1)):
            screen.fill((255, 255, 255), (min(cx, cx + 7 * dx), cy, 8, 1))
            screen.fill((255, 255, 255), (cx, min(cy, cy + 7 * dy), 1, 8))
        # the floor it stands on
        screen.fill(color, (px.x, px.bottom, px.w, 2))
        font = _font(16)
        if room is not None:
            label = (f'{room.name}  ->  EXPAND {bigger(room.size)}'
                     if bigger(room.size) else f'{room.name}  MAX SIZE')
        else:
            label = f'ROOM {self.size}'
        _label(screen, font, label, (px.centerx, px.y - 10), color)
        if reason is not None and not (room is not None and reason == 'MAX SIZE'):
            _label(screen, _font(20), reason, (px.centerx, px.bottom + 14), RED)
        elif room is None:
            _label(screen, font, 'CLICK / ENTER TO BUILD', (px.centerx, px.bottom + 12), GREEN)
        else:
            _label(screen, font, 'CLICK TO EXPAND', (px.centerx, px.bottom + 12), GREEN)

    # ---- HUD and menus -------------------------------------------------
    def draw_hud(self, surface, ui, mouse):
        """ROOMS: X/3, active buffs, the Build Mode banner and the menus."""
        from ui import CREAM, MUTED, ORANGE
        if not self.game.bonus_room:
            # ROOMS X/3 with a [B] BUILD key; it glows once a room is affordable.
            cheapest = min(info['price']['S'] for kind, info in ROOM_TYPES.items()
                           if all(r.kind != kind for r in self.rooms)) \
                if len(self.rooms) < MAX_ROOMS else None
            ready = cheapest is not None and self.game.gold >= cheapest
            glow = ready and int(self.game.world_time * 2) % 2 == 0
            rect = pygame.Rect(16, 142, 226, 34)
            ui.frame(surface, rect, ORANGE if self.build_mode or glow else (150, 118, 84))
            ui.text(surface, f'ROOMS {len(self.rooms)}/{MAX_ROOMS}', 18, CREAM,
                    topleft=(rect.x + 12, rect.y + 10))
            ui.keycap(surface, 'B', rect.x + 104, rect.y + 3)
            if self.build_mode:
                label, color = 'BUILDING', ORANGE
            elif cheapest is None:
                label, color = 'ALL BUILT', MUTED
            elif ready:
                label, color = 'BUILD', CREAM
            else:
                label, color = f'{cheapest} G', MUTED      # gold needed for a room
            ui.text(surface, label, 18, color, topleft=(rect.x + 140, rect.y + 10))
        y = 184
        for room in sorted(self.all_rooms(), key=lambda r: ORDER.index(r.kind)):
            accent = ROOM_TYPES[room.kind]['accent']
            surface.fill(accent, (18, y + 3, 8, 8))
            buff = effects(room.kind, room.size)[0 if room.kind == 'herald' else 1]
            ui.text(surface, f'{room.name}  {buff}', 16, CREAM, topleft=(32, y))
            y += 18
        if self.build_mode and self.menu is None:
            self._banner(surface, ui)
        if self.message is not None and self.menu is None:
            ui.text(surface, self.message[0], 22, RED,
                    center=(surface.get_width() // 2, surface.get_height() - 92))
        self.buttons = []
        if self.menu is not None:
            if self.menu[0] == 'build':
                self._build_menu(surface, ui, mouse)
            else:
                self._expand_menu(surface, ui, mouse)

    def _banner(self, surface, ui):
        from ui import CREAM, MUTED, ORANGE
        width = 520
        rect = pygame.Rect((surface.get_width() - width) // 2, surface.get_height() - 70, width, 46)
        ui.frame(surface, rect, ORANGE)
        ui.text(surface, 'BUILD MODE', 20, ORANGE, topleft=(rect.x + 16, rect.y + 15))
        x = rect.x + 140
        for n, size in enumerate(SIZE_NAMES, 1):
            chosen = size == self.size
            box = pygame.Rect(x, rect.y + 10, 58, 26)
            pygame.draw.rect(surface, (90, 62, 30) if chosen else (40, 30, 24), box)
            pygame.draw.rect(surface, ORANGE if chosen else (96, 76, 58), box, 2)
            ui.text(surface, f'{n} = {size}', 18, CREAM if chosen else MUTED, center=box.center)
            x += 66
        ui.text(surface, 'B / ESC: EXIT', 16, MUTED, topleft=(rect.right - 112, rect.y + 17))

    def _panel(self, surface, ui, width, height, title):
        from ui import ORANGE
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (surface.get_width() // 2, surface.get_height() // 2 - 20)
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((10, 8, 6, 120))
        surface.blit(shade, (0, 0))
        ui.frame(surface, rect, ORANGE)
        ui.text(surface, title, 26, ORANGE, center=(rect.centerx, rect.y + 26))
        return rect

    def _close_button(self, surface, ui, rect, mouse):
        from ui import CREAM, MUTED
        close = pygame.Rect(rect.right - 40, rect.y + 10, 28, 28)
        hot = close.collidepoint(mouse)
        pygame.draw.rect(surface, (90, 40, 30) if hot else (50, 34, 26), close)
        ui.text(surface, 'X', 20, CREAM if hot else MUTED, center=close.center)
        self.buttons.append((close, 'close'))

    def _build_menu(self, surface, ui, mouse):
        from ui import CREAM, MUTED
        rect = self.menu[1]
        size = next(s for s, (w, h) in SIZES.items() if (w, h) == rect.size)
        panel = self._panel(surface, ui, 600, 300, f'BUILD A ROOM  -  SIZE {size}')
        self._close_button(surface, ui, panel, mouse)
        gold = self.game.gold
        for n, kind in enumerate(ORDER):
            info = ROOM_TYPES[kind]
            price = info['price'][size]
            card = pygame.Rect(panel.x + 18 + n * 192, panel.y + 52, 180, 214)
            built = any(r.kind == kind for r in self.rooms)
            poor = gold < price
            hot = card.collidepoint(mouse) and not built and not poor
            pygame.draw.rect(surface, (64, 44, 28) if hot else (40, 30, 24), card)
            pygame.draw.rect(surface, info['accent'] if hot else (96, 76, 58), card, 2)
            preview = _preview(kind, size, (card.w - 16, 90))
            if built:
                preview.set_alpha(90)
            surface.blit(preview, preview.get_rect(midtop=(card.centerx, card.y + 8)))
            ui.text(surface, f'{n + 1}  {info["name"]}', 22,
                    info['accent'] if not built else MUTED, center=(card.centerx, card.y + 108))
            for k, line in enumerate(effects(kind, size)):
                ui.text(surface, line, 16, CREAM if not built else MUTED,
                        center=(card.centerx, card.y + 132 + k * 18))
            if built:
                status, color = 'BUILT', MUTED
            elif poor:
                status, color = f'{price} G  (NEED {price - gold})', RED
            else:
                status, color = f'{price} G', (255, 207, 72)
            tag = pygame.Rect(card.x + 10, card.bottom - 40, card.w - 20, 30)
            pygame.draw.rect(surface, (24, 18, 14), tag)
            ui.text(surface, status, 20, color, center=tag.center)
            if not built:
                self.buttons.append((card, kind))
        ui.text(surface, f'YOUR GOLD: {gold} G      1/2/3 OR CLICK TO BUILD      ESC: CLOSE', 16,
                MUTED, center=(panel.centerx, panel.bottom - 16))

    def _expand_menu(self, surface, ui, mouse):
        from ui import CREAM, MUTED
        room = self.menu[1]
        info = ROOM_TYPES[room.kind]
        size = bigger(room.size)
        panel = self._panel(surface, ui, 440, 300, room.name)
        self._close_button(surface, ui, panel, mouse)
        preview = _preview(room.kind, size or room.size, (210, 90))
        surface.blit(preview, preview.get_rect(midtop=(panel.centerx, panel.y + 50)))
        if size is None:
            ui.text(surface, 'THIS ROOM IS AT MAX SIZE', 20, MUTED,
                    center=(panel.centerx, panel.y + 170))
            return
        now, then = effects(room.kind, room.size), effects(room.kind, size)
        changes = [(a, b) for a, b in zip(now, then) if a != b]
        if room.kind == 'forge':
            changes.append(('', 'REFILL BOMBS'))
        for k, (a, b) in enumerate(changes):
            ui.text(surface, f'{a}  ->  {b}' if a else b, 18, CREAM,
                    center=(panel.centerx, panel.y + 150 + k * 20))
        price = info['price'][size] - info['price'][room.size]
        _, reason = self.expansion(room)
        if reason is None and self.game.gold < price:
            reason = f'NEED {price} G'
        button = pygame.Rect(0, 0, 300, 44)
        button.center = (panel.centerx, panel.bottom - 64)
        hot = button.collidepoint(mouse) and reason is None
        pygame.draw.rect(surface, (70, 52, 26) if hot else (44, 34, 24), button)
        pygame.draw.rect(surface, info['accent'] if reason is None else (96, 76, 58), button, 2)
        ui.text(surface, f'EXPAND ROOM ({room.size} -> {size})  {price} G', 20,
                CREAM if reason is None else MUTED, center=button.center)
        self.buttons.append((button, 'expand'))
        ui.text(surface, reason or 'CLICK OR PRESS 1      ESC: CLOSE', 18,
                RED if reason else MUTED, center=(panel.centerx, panel.bottom - 22))


# ---------------------------------------------------------------------------
# Art and live effects.
ART = Path(__file__).parent / 'assets' / 'rooms'

# Where each picture's lamps and fires are, as fractions of the room:
# glow = (x, y, light colour, light radius at size M, glow size in px).
LIVE = {
    'forge': {
        'glow': ((0.235, 0.56, (255, 120, 40), 120, 10),     # furnace mouth
                 (0.49, 0.27, (255, 190, 100), 100, 5)),     # hanging lantern
        'sparks': (0.235, 0.50),
    },
    'herald': {
        'glow': ((0.12, 0.45, (200, 110, 255), 80, 5),       # violet crystals
                 (0.205, 0.40, (200, 110, 255), 64, 4),
                 (0.79, 0.40, (200, 110, 255), 64, 4),
                 (0.885, 0.43, (90, 230, 240), 80, 5),       # cyan crystal
                 (0.48, 0.55, (150, 210, 255), 70, 5)),      # the open book
        'motes': (0.49, 0.50),
    },
    'kitchen': {
        'glow': ((0.548, 0.32, (255, 180, 90), 90, 4),       # wall torch
                 (0.765, 0.73, (255, 130, 50), 120, 8)),     # hearth fire
        'steam': (0.77, 0.56),
        'sparks': (0.765, 0.66),
    },
}

_images = {}


def room_image(kind, size):
    """The baked picture for a room, or a plain wooden box without the art."""
    key = (kind, size)
    if key not in _images:
        w, h = SIZES[size]
        try:
            image = pygame.image.load(str(ART / f'{kind}_{size}.png')).convert_alpha()
            if image.get_size() != (w * CELL, h * CELL):
                image = pygame.transform.smoothscale(image, (w * CELL, h * CELL))
        except (pygame.error, FileNotFoundError):
            image = pygame.Surface((w * CELL, h * CELL), pygame.SRCALPHA)
            image.fill((70, 46, 28))
            pygame.draw.rect(image, (120, 80, 44), image.get_rect(), 4)
        _images[key] = image
    return _images[key]


_signs = {}


def sign(kind, size):
    """A small wooden board with the room's name and size."""
    key = (kind, size)
    if key not in _signs:
        font = _font(14)
        text = font.render(f'{ROOM_TYPES[kind]["name"]} [{size}]', False, (52, 30, 14))
        image = pygame.Surface((text.get_width() + 12, 14), pygame.SRCALPHA)
        board = image.get_rect()
        image.fill((44, 26, 14))
        image.fill((186, 136, 78), board.inflate(-2, -2))
        image.fill((156, 106, 58), (1, board.h - 4, board.w - 2, 3))
        for x in (2, board.w - 3):                       # nails
            image.fill((70, 70, 76), (x, 6, 1, 2))
        image.blit(text, text.get_rect(center=(board.centerx, board.centery)))
        _signs[key] = image
    return _signs[key]


_fonts = {}


def _font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def _label(screen, font, text, center, color):
    image = font.render(text, False, color)
    shadow = font.render(text, False, (12, 10, 8))
    rect = image.get_rect(center=center)
    screen.blit(shadow, rect.move(1, 1))
    screen.blit(image, rect)


_glows = {}


def _glow(radius, color):
    key = (radius, color)
    if key not in _glows:
        surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for r in range(radius, 0, -1):
            a = round(42 * (1 - r / radius) ** 1.5)
            pygame.draw.circle(surface, (*color, a), (radius, radius), r)
        _glows[key] = surface
    return _glows[key]


def draw_live(screen, room, px, time):
    """Flickering glow on the picture's lamps and fires, sparks and steam."""
    live = LIVE[room.kind]
    scale = px.w / (SIZES['M'][0] * CELL)
    for n, (fx, fy, color, _, size) in enumerate(live['glow']):
        flick = 0.85 + 0.15 * math.sin(time * 11 + n * 1.7) * math.sin(time * 4.3 + n)
        radius = max(3, round(size * scale * flick))
        glow = _glow(radius, color)
        screen.blit(glow, glow.get_rect(center=(px.x + fx * px.w, px.y + fy * px.h)),
                    special_flags=pygame.BLEND_RGBA_ADD)
    if 'sparks' in live:
        sx, sy = px.x + live['sparks'][0] * px.w, px.y + live['sparks'][1] * px.h
        for k in range(4):
            t = (time * 0.9 + k / 4) % 1
            x = sx + math.sin(k * 2.4 + time) * 6 * scale + (k - 1.5) * 3
            y = sy - t * 26 * scale
            if t < 0.8:
                screen.fill((255, 190 - round(110 * t), 70), (round(x), round(y), 2, 2))
    if 'steam' in live:
        bx, by = px.x + live['steam'][0] * px.w, px.y + live['steam'][1] * px.h
        for k in range(3):
            t = (time * 0.5 + k / 3) % 1
            puff = _glow(3 + round(3 * t), (200, 200, 195))
            puff.set_alpha(round(255 * (1 - t)))
            screen.blit(puff, puff.get_rect(center=(bx + math.sin(time * 1.8 + k) * 4,
                                                     by - t * 24 * scale)))
            puff.set_alpha(None)
    if 'motes' in live:
        mx, my = px.x + live['motes'][0] * px.w, px.y + live['motes'][1] * px.h
        for k in range(5):
            t = (time * 0.4 + k / 5) % 1
            x = mx + math.sin(time * 1.3 + k * 1.9) * 10 * scale
            y = my - t * 22 * scale
            if int(time * 6 + k) % 3:
                screen.fill((170, 230, 255), (round(x), round(y), 1 + (k % 2), 1 + (k % 2)))


_preview_cache = {}


def _preview(kind, size, box):
    """The room's picture fitted into ``box`` for the menus."""
    key = (kind, size, box)
    if key not in _preview_cache:
        image = room_image(kind, size)
        scale = min(box[0] / image.get_width(), box[1] / image.get_height())
        _preview_cache[key] = pygame.transform.smoothscale(
            image, (round(image.get_width() * scale), round(image.get_height() * scale)))
    return _preview_cache[key].copy()
