"""Shrink the miner's portrait art to its true pixel grid.

    python tools/make_miner_portrait.py

assets/miner_portrait.png   the stage intro portrait (dialog.py), from the
                            team's miner art (assets/miner_portrait_source.png).

The source is pixel art blown up about ten times: GRID x GRID art pixels on a
1004 px canvas. Reading the middle of every art pixel gives the drawing back
at one screen pixel per art pixel, with no blending, and the empty margin is
trimmed. Needs only pygame.
"""
import os
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
import pygame  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'assets' / 'miner_portrait_source.png'
TARGET = ROOT / 'assets' / 'miner_portrait.png'
GRID = 98


def portrait():
    pygame.init()
    pygame.display.set_mode((1, 1))
    source = pygame.image.load(SOURCE).convert_alpha()
    width, height = source.get_size()
    small = pygame.Surface((GRID, GRID), pygame.SRCALPHA)
    for gy in range(GRID):
        for gx in range(GRID):
            x = int((gx + 0.5) * width / GRID)
            y = int((gy + 0.5) * height / GRID)
            r, g, b, a = source.get_at((x, y))
            small.set_at((gx, gy), (r, g, b, 255) if a >= 128 else (0, 0, 0, 0))
    return small.subsurface(small.get_bounding_rect()).copy()


if __name__ == '__main__':
    image = portrait()
    pygame.image.save(image, TARGET)
    print(f'{TARGET.relative_to(ROOT)}: {image.get_width()} x {image.get_height()}')
