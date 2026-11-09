"""Pixel-art sprites for the enemies and the boss.

The source art (assets/enemies/*.png) faces left, has a transparent
background and is already scaled to its in-game size. Each sprite is drawn
with its feet on the bottom of the enemy's collision box, so the art can be
taller and wider than the box without changing how enemies collide.

If an image is missing, draw() returns False and the caller falls back to the
old placeholder shapes.
"""
from pathlib import Path

import pygame

FOLDER = Path(__file__).with_name('assets') / 'enemies'
FILES = {'gunner': 'enemy_gunner.png', 'walker': 'enemy_walker.png', 'boss': 'enemy_boss.png'}
_cache = {}


def sprite(kind, facing_right=False, flash=False):
    """The sprite for an enemy kind, mirrored and white-flashed as asked."""
    key = (kind, facing_right, flash)
    if key not in _cache:
        if (kind, False, False) not in _cache:
            try:
                image = pygame.image.load(str(FOLDER / FILES[kind]))
                if pygame.display.get_surface() is not None:
                    image = image.convert_alpha()
            except (pygame.error, FileNotFoundError, KeyError):
                image = None
            _cache[(kind, False, False)] = image
        base = _cache[(kind, False, False)]
        image = base
        if base is not None and facing_right:
            image = pygame.transform.flip(base, True, False)
        if image is not None and flash:
            image = image.copy()
            image.fill((150, 150, 150, 0), special_flags=pygame.BLEND_RGBA_ADD)
        _cache[key] = image
    return _cache[key]


def kind_of(actor):
    if getattr(actor, 'is_boss', False):
        return 'boss'
    return 'gunner' if getattr(actor, 'shoots_projectiles', False) else 'walker'


def facing_right(actor, target_x):
    """Walkers face the way they move; gunners and idle enemies face the player."""
    vx = getattr(getattr(actor, 'velocity', None), 'x', 0)
    if not getattr(actor, 'shoots_projectiles', False) and abs(vx) > 1:
        return vx > 0
    return target_x is not None and target_x > actor.rect.centerx


def draw(screen, actor, camera, target_x=None, flash=False, offset=(0, 0)):
    """Draw an enemy's sprite; returns False if its art is unavailable."""
    image = sprite(kind_of(actor), facing_right(actor, target_x), flash)
    if image is None:
        return False
    box = actor.rect.move(-camera[0], -camera[1])
    rect = image.get_rect(midbottom=(box.centerx + offset[0], box.bottom + offset[1]))
    if rect.colliderect(screen.get_rect()):
        screen.blit(image, rect)
    return True
