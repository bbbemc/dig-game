"""Pixel-art sprites and animations for the enemies and the boss.

The source art (assets/enemies/enemy_<kind>.png) faces left, has a transparent
background and is already scaled to its in-game size. Each sprite is drawn
with its feet on the bottom of the enemy's collision box, so the art can be
taller and wider than the box without changing how enemies collide.

Animations (idle, walk, attack, hurt, stun, death, and for the gunner a
charge and a fire) come from enemy_<kind>_sheet.png, built from the single sprites by
tools/make_enemy_animations.py: one row per animation in ANIMATIONS order, one
column per frame, each frame PAD_X wider on both sides and PAD_TOP taller than
the sprite, feet on the bottom edge. Which animation plays is read from the
enemy's state every frame (see animation()); nothing in the game logic
changes, apart from two time stamps the game sets on an enemy: hurt_time
(parried or blasted) and attack_time (a contact hit landed). Death plays
after an enemy is gone, from a Death object the game keeps for half a second.

If a sheet is missing the single sprite is drawn; if that is missing too,
draw() returns False and the caller falls back to the placeholder shapes.
"""
from pathlib import Path

import pygame

from config import ENEMY_FIRE_INTERVAL

FOLDER = Path(__file__).with_name('assets') / 'enemies'
FILES = {'gunner': 'enemy_gunner.png', 'walker': 'enemy_walker.png', 'boss': 'enemy_boss.png'}
BOSS_DIRECTIONAL_FILE = 'enemy_boss_directional.png'
BOSS_DIRECTIONAL_CELL = (160, 160)
BOSS_DIRECTIONAL_ANIMATIONS = (
    ('idle_down', 3),
    ('idle_side', 3),
    ('idle_up', 3),
    ('run_down', 4),
    ('run_side', 4),
    ('run_up', 4),
)
PAD_X, PAD_TOP = 8, 6       # margin around walker and gunner frames
# Per-kind frame margins: the boss needs room for its greatsword overhead
# and swung out in front.
PADS = {'walker': (PAD_X, PAD_TOP), 'gunner': (PAD_X, PAD_TOP), 'boss': (126, 130)}


def pad(kind):
    return PADS.get(kind, (PAD_X, PAD_TOP))

# (animation, frame count) per enemy, in sheet row order.
ANIMATIONS = {
    'walker': (('idle', 8), ('walk', 8), ('attack', 6), ('hurt', 2), ('stun', 4), ('death', 6)),
    'gunner': (('idle', 8), ('charge', 4), ('fire', 4), ('hurt', 2), ('stun', 4), ('death', 6)),
    'boss': (('idle', 8), ('walk', 8), ('attack', 6), ('hurt', 2), ('stun', 4), ('death', 8)),
}
# Frame rates, all within 8-20 fps. Walking advances with the ground covered
# instead (STRIDE pixels per frame), so the feet never slide.
IDLE_FPS, ATTACK_FPS, STUN_FPS, CHARGE_FPS, DEATH_FPS = 8, 14, 8, 12, 12
STRIDE = {'walker': 4, 'boss': 6}      # walker ~12 fps, boss ~10 fps at full speed
REACH = {'walker': 30, 'boss': 40}     # how close the player is when the swing is readied
FIRE_TIME = 0.28                       # recoil after a shot
CHARGE_TIME = 0.45                     # glow before the next shot
HURT_TIME = 0.2                        # flinch after a parry or a blast
SWING_TIME = 5 / ATTACK_FPS            # the swing after a hit lands (attack frames 1-5)
MUZZLE = (1, 23)                       # cannon tip in the still gunner sprite (facing left)

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
            px, pt = pad(kind)
            fw, fh = base.get_width() + 2 * px, base.get_height() + pt
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


def directional_frames(kind='boss'):
    """6-row directional sprite sheet frames for the Stage 6 Final Boss."""
    key = f'{kind}_directional'
    if key not in _sheets:
        if kind != 'boss':
            _sheets[key] = None
        else:
            sheet = _load(FOLDER / BOSS_DIRECTIONAL_FILE)
            anims = None
            if sheet is not None:
                cw, ch = BOSS_DIRECTIONAL_CELL
                anims = {}
                for row, (name, count) in enumerate(BOSS_DIRECTIONAL_ANIMATIONS):
                    anims[name] = [sheet.subsurface((col * cw, row * ch, cw, ch)).copy()
                                   for col in range(count)]
            _sheets[key] = anims
    return _sheets[key]


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
    """(animation name, frame index) for what the enemy is doing right now.

    ``time`` is the game clock; enemies carry ``hurt_time`` (last parried or
    blasted) and ``attack_time`` (last contact hit landed) on that clock.
    """
    kind = kind_of(actor)
    tx, ty = _target(target)
    since_hurt = time - getattr(actor, 'hurt_time', -99.0)
    if 0 <= since_hurt < HURT_TIME:
        return 'hurt', min(1, int(since_hurt / HURT_TIME * 2))
    if getattr(actor, 'broken', False) or getattr(actor, 'stun_timer', 0) > 0:
        return 'stun', int(time * STUN_FPS) % 4
    if kind == 'gunner':
        cooldown = getattr(actor, 'shot_cooldown', 0.0)
        since_shot = ENEMY_FIRE_INTERVAL - cooldown
        if since_shot < FIRE_TIME:
            return 'fire', min(3, int(since_shot / FIRE_TIME * 4))
        if 0 < cooldown <= CHARGE_TIME:
            return 'charge', min(3, int((CHARGE_TIME - cooldown) / CHARGE_TIME * 4))
        return 'idle', int(time * IDLE_FPS) % 8
    melee = getattr(actor, 'melee_state', None)
    if melee:
        # A real swing: ready, wind up (the warning), strike, recover.
        progress = 1 - max(0.0, actor.melee_timer) / max(1e-6, getattr(actor, 'melee_length', 1.0))
        if melee == 'windup':
            return 'attack', 0 if progress < 0.55 else 1
        if melee == 'strike':
            return 'attack', 2 if progress < 0.5 else 3
        return 'attack', 4 if progress < 0.5 else 5
    since_hit = time - getattr(actor, 'attack_time', -99.0)
    if 0 <= since_hit < SWING_TIME:           # the blow that just landed
        return 'attack', 1 + min(4, int(since_hit * ATTACK_FPS))
    rect = actor.rect
    if (tx is not None and abs(tx - rect.centerx) <= rect.w / 2 + REACH[kind]
            and (ty is None or abs(ty - rect.centery) <= rect.h)):
        return 'attack', 0                    # weapon readied, waiting to strike
    vx = getattr(getattr(actor, 'velocity', None), 'x', 0)
    if abs(vx) > 1:
        x = getattr(getattr(actor, 'pos', None), 'x', rect.x)
        return 'walk', int(x // STRIDE[kind]) % 8
    return 'idle', int(time * IDLE_FPS) % 8


def muzzle(actor, facing_right):
    """World point of a gunner's cannon tip (its centre if the art is missing)."""
    art = sprite('gunner')
    if art is None:
        return actor.rect.center
    w, h = art.get_size()
    left, top = actor.rect.centerx - w // 2, actor.rect.bottom - h
    x = left + (w - 1 - MUZZLE[0] if facing_right else MUZZLE[0])
    return x, top + MUZZLE[1]


def facing_right(actor, target=None, name=None):
    """Walkers face the way they move; gunners, idle and attacking enemies face the player."""
    if getattr(actor, 'melee_state', None):
        return getattr(actor, 'melee_side', -1) > 0      # a swing keeps its side
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
    elif name in ('stun', 'hurt'):
        offset = (0, 0)     # these frames already slump, sway or flinch
    box = actor.rect.move(-camera[0], -camera[1])
    rect = image.get_rect(midbottom=(box.centerx + offset[0], box.bottom + offset[1]))
    if rect.colliderect(screen.get_rect()):
        screen.blit(image, rect)
        draw_tell(screen, actor, rect, right, time)
    return True


def draw_tell(screen, actor, art, right, time):
    """The warning before a swing lands: a red '!' over the head that
    flashes faster as the strike nears, and a glint on the weapon."""
    if getattr(actor, 'melee_state', None) != 'windup':
        return
    from config import MELEE_TELL
    left = actor.melee_timer
    if left > MELEE_TELL:
        # Early wind-up: a steady, dim mark so the player sees it coming.
        color, glint = (200, 70, 50), False
    else:
        blink = int(time * (14 if left > MELEE_TELL / 2 else 24)) % 2
        color, glint = ((255, 236, 200) if blink else (240, 60, 40)), True
    # Over the head (the still sprite's top, not the padded frame's), and for
    # the boss above its HP pips.
    still = sprite(kind_of(actor))
    head = art.bottom - (still.get_height() if still is not None else art.height)
    x, y = art.centerx, head - (26 if getattr(actor, 'is_boss', False) else 10)
    pygame.draw.rect(screen, (30, 10, 10), (x - 3, y - 9, 6, 13))
    pygame.draw.rect(screen, color, (x - 2, y - 8, 4, 7))
    pygame.draw.rect(screen, color, (x - 2, y + 1, 4, 2))
    if glint:
        # The raised weapon is behind the body: on the side it faces away from.
        gx = art.centerx + (-art.width // 6 if right else art.width // 6)
        gy = head + 6
        screen.fill((255, 255, 255), (gx - 3, gy, 7, 1))
        screen.fill((255, 255, 255), (gx, gy - 3, 1, 7))


class Death:
    """A defeated enemy's death animation, left where it fell."""

    def __init__(self, actor, target, time):
        self.kind = kind_of(actor)
        self.facing_right = facing_right(actor, target, 'death')
        self.midbottom = actor.rect.midbottom
        self.start = time
        count = dict(ANIMATIONS[self.kind])['death']
        self.duration = count / DEATH_FPS

    def done(self, time):
        return time - self.start >= self.duration

    def draw(self, screen, camera, time):
        count = dict(ANIMATIONS[self.kind])['death']
        index = min(count - 1, max(0, int((time - self.start) * DEATH_FPS)))
        image = frame(self.kind, 'death', index, self.facing_right)
        if image is None:
            return
        x, y = self.midbottom
        rect = image.get_rect(midbottom=(x - camera[0], y - camera[1]))
        if rect.colliderect(screen.get_rect()):
            screen.blit(image, rect)
