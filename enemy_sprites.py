"""Pixel-art sprites and animations for the enemies and the boss.

The source art (assets/enemies/enemy_<kind>.png) faces left, has a transparent
background and is already scaled to its in-game size. Each sprite is drawn
with its feet on the bottom of the enemy's collision box, so the art can be
taller and wider than the box without changing how enemies collide.

Animations come from enemy_<kind>_sheet.png, built from the single sprites by
tools/make_enemy_animations.py: one row per animation in ANIMATIONS order, one
column per frame, each frame PAD_X wider on both sides and PAD_TOP taller than
the sprite, feet on the bottom edge. Which animation plays is read from the
enemy's state every frame (see animation()); nothing in the game logic
changes.

If a sheet is missing the single sprite is drawn; if that is missing too,
draw() returns False and the caller falls back to the placeholder shapes.
"""
from pathlib import Path

import pygame

from config import ENEMY_FIRE_INTERVAL

FOLDER = Path(__file__).with_name('assets') / 'enemies'
FILES = {'gunner': 'enemy_gunner.png', 'walker': 'enemy_walker.png', 'boss': 'enemy_boss.png'}
PAD_X, PAD_TOP = 8, 6

# (animation, frame count) per enemy, in sheet row order.
ANIMATIONS = {
    'walker': (('idle', 8), ('walk', 6), ('attack', 4), ('stun', 2)),
    'gunner': (('idle', 8), ('charge', 3), ('fire', 3), ('stun', 2)),
    'boss': (('idle', 8), ('walk', 6), ('attack', 4), ('stun', 2)),
}
IDLE_FPS, ATTACK_FPS, STUN_FPS, CHARGE_FPS = 8, 10, 8, 12   # all within 8-20 fps
STRIDE = {'walker': 5, 'boss': 7}      # pixels walked per walk frame (feet don't slide)
REACH = {'walker': 30, 'boss': 40}     # how close the player is when the attack plays
FIRE_TIME = 0.24                       # recoil after a shot
CHARGE_TIME = 0.45                     # glow before the next shot

_cache = {}
_sheets = {}


def sheet_name(kind):
    return FILES[kind].replace('.png', '_sheet.png')


def _load(path):
    try:
        image = pygame.image.load(str(path))
    except (pygame.error, FileNotFoundError):
        return None
    if pygame.display.get_surface() is not None:
        image = image.convert_alpha()
    return image


def sprite(kind, facing_right=False, flash=False):
    """The single still sprite for an enemy kind, mirrored and white-flashed as asked."""
    key = (kind, facing_right, flash)
    if key not in _cache:
        if (kind, False, False) not in _cache:
            _cache[(kind, False, False)] = _load(FOLDER / FILES[kind]) if kind in FILES else None
        _cache[key] = _variant(_cache[(kind, False, False)], facing_right, flash)
    return _cache[key]


def _variant(image, facing_right, flash):
    if image is not None and facing_right:
        image = pygame.transform.flip(image, True, False)
    if image is not None and flash:
        image = image.copy()
        image.fill((150, 150, 150, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return image


def frames(kind):
    """{animation: [frame surfaces]} cut from the sheet, or None without one."""
    if kind not in _sheets:
        sheet = _load(FOLDER / sheet_name(kind)) if kind in FILES else None
        base = sprite(kind)
        anims = None
        if sheet is not None and base is not None:
            fw, fh = base.get_width() + 2 * PAD_X, base.get_height() + PAD_TOP
            anims = {}
            for row, (name, count) in enumerate(ANIMATIONS[kind]):
                anims[name] = [sheet.subsurface((col * fw, row * fh, fw, fh)).copy()
                               for col in range(count)]
        _sheets[kind] = anims
    return _sheets[kind]


def frame(kind, name, index, facing_right=False, flash=False):
    key = (kind, name, index, facing_right, flash)
    if key not in _cache:
        anims = frames(kind)
        if anims is None:
            return None
        _cache[key] = _variant(anims[name][index], facing_right, flash)
    return _cache[key]


def kind_of(actor):
    if getattr(actor, 'is_boss', False):
        return 'boss'
    return 'gunner' if getattr(actor, 'shoots_projectiles', False) else 'walker'


def _target(target):
    """Accept a player x, a (x, y) point or nothing."""
    if target is None:
        return None, None
    if isinstance(target, (int, float)):
        return target, None
    return target[0], target[1]


def animation(actor, target=None, time=0.0):
    """(animation name, frame index) for what the enemy is doing right now."""
    kind = kind_of(actor)
    tx, ty = _target(target)
    if getattr(actor, 'broken', False) or getattr(actor, 'stun_timer', 0) > 0:
        return 'stun', int(time * STUN_FPS) % 2
    if kind == 'gunner':
        cooldown = getattr(actor, 'shot_cooldown', 0.0)
        since_shot = ENEMY_FIRE_INTERVAL - cooldown
        if since_shot < FIRE_TIME:
            return 'fire', min(2, int(since_shot / FIRE_TIME * 3))
        if 0 < cooldown <= CHARGE_TIME:
            return 'charge', int(time * CHARGE_FPS) % 3
        return 'idle', int(time * IDLE_FPS) % 8
    rect = actor.rect
    if (tx is not None and abs(tx - rect.centerx) <= rect.w / 2 + REACH[kind]
            and (ty is None or abs(ty - rect.centery) <= rect.h)):
        return 'attack', int(time * ATTACK_FPS) % 4
    vx = getattr(getattr(actor, 'velocity', None), 'x', 0)
    if abs(vx) > 1:
        x = getattr(getattr(actor, 'pos', None), 'x', rect.x)
        return 'walk', int(x // STRIDE[kind]) % 6
    return 'idle', int(time * IDLE_FPS) % 8


def facing_right(actor, target=None, name=None):
    """Walkers face the way they move; gunners, idle and attacking enemies face the player."""
    tx, _ = _target(target)
    vx = getattr(getattr(actor, 'velocity', None), 'x', 0)
    if name != 'attack' and not getattr(actor, 'shoots_projectiles', False) and abs(vx) > 1:
        return vx > 0
    return tx is not None and tx > actor.rect.centerx


def draw(screen, actor, camera, target=None, flash=False, offset=(0, 0), time=0.0):
    """Draw an enemy, animated when its sheet exists; False if it has no art at all.

    ``target`` is the player's x or (x, y) centre; ``time`` the game clock.
    """
    kind = kind_of(actor)
    name, index = animation(actor, target, time)
    right = facing_right(actor, target, name)
    image = frame(kind, name, index, right, flash)
    if image is None:
        image = sprite(kind, right, flash)
        if image is None:
            return False
    elif name == 'stun':
        offset = (0, 0)     # the stun frames already slump and sway
    box = actor.rect.move(-camera[0], -camera[1])
    rect = image.get_rect(midbottom=(box.centerx + offset[0], box.bottom + offset[1]))
    if rect.colliderect(screen.get_rect()):
        screen.blit(image, rect)
    return True
