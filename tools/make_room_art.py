"""Bake the room pictures (assets/rooms/source/*.png) to the in-game sizes.

Each source is the full room drawn large; it is fitted to every footprint in
rooms.SIZES (S, M, L) with a Lanczos filter and a light sharpen so the
pixel-art edges survive the shrink. Run from the repo root:

    python tools/make_room_art.py
"""
import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import CELL          # noqa: E402
from rooms import SIZES, ORDER   # noqa: E402

SOURCE = ROOT / 'assets' / 'rooms' / 'source'
OUT = ROOT / 'assets' / 'rooms'


def bake(kind, size):
    w, h = SIZES[size]
    image = Image.open(SOURCE / f'{kind}.png').convert('RGBA')
    # Premultiply so the see-through corners do not bleed dark fringes.
    small = image.resize((w * CELL, h * CELL), Image.LANCZOS, reducing_gap=3.0)
    small = small.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=2))
    alpha = small.getchannel('A').point(lambda a: 255 if a >= 128 else 0)
    small.putalpha(alpha)
    small.save(OUT / f'{kind}_{size}.png')
    return small


if __name__ == '__main__':
    for kind in ORDER:
        for size in SIZES:
            print(kind, size, bake(kind, size).size)
