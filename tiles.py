"""Runtime sprite crops from the supplied labelled tile contact sheet."""

from pathlib import Path
import pygame

from level import DIRT, ROCK, WATER, LAVA, STONE

ATLAS = Path(__file__).parent / "assets" / "underground_tiles.png"

# Source rectangles are centralized because the supplied image is a contact
# sheet, not a grid-aligned atlas. Crops avoid headings and neighboring art.
SOURCE = {
    "upper_dirt": (401, 60, 43, 43),
    "upper_top": (457, 60, 44, 43),
    "mine_dirt": (401, 117, 43, 43),
    "mine_top": (515, 117, 43, 43),
    "deep_dirt": (782, 60, 43, 43),
    "deep_top": (839, 60, 43, 43),
    "ancient_dirt": (1163, 60, 43, 43),
    "ancient_top": (1220, 60, 43, 43),
    "gray_stone": (19, 285, 43, 43),
    "dark_stone": (400, 285, 43, 43),
    "volcanic_stone": (782, 285, 43, 43),
    "ancient_stone": (1163, 285, 43, 43),
    "water": (19, 508, 45, 47),
    "lava": (400, 508, 45, 47),
    "crate": (852, 913, 42, 42),
    "torch": (782, 976, 27, 38),
    "bones": (1187, 691, 49, 35),
    "support": (19, 855, 106, 73),
    "cart": (322, 981, 60, 33),
    "ladder": (234, 855, 40, 72),
    "lantern": (415, 889, 41, 46),
    "mushroom": (1059, 752, 47, 51),
    "crystal": (470, 751, 65, 55),
    "ruins": (1259, 743, 55, 60),
}


class TileArt:
    def __init__(self, cell_size, macro_size):
        sheet = pygame.image.load(str(ATLAS)).convert_alpha()
        self.macro = {}
        self.micro = {}
        for name, rect in SOURCE.items():
            sample = sheet.subsurface(pygame.Rect(rect)).copy()
            if name in {"crate", "torch", "bones", "support", "cart", "ladder",
                        "lantern", "mushroom", "crystal", "ruins"}:
                # The supplied contact sheet has an opaque dark panel behind
                # its props, so remove only those near-black panel pixels.
                for y in range(sample.get_height()):
                    for x in range(sample.get_width()):
                        r, g, b, a = sample.get_at((x, y))
                        if r < 37 and g < 35 and b < 49:
                            sample.set_at((x, y), (r, g, b, 0))
            self.macro[name] = pygame.transform.smoothscale(sample, (macro_size, macro_size))
            self.micro[name] = pygame.transform.smoothscale(sample, (cell_size, cell_size))

    @staticmethod
    def terrain_name(kind, macro_y, exposed_above=False):
        if kind == DIRT:
            if macro_y < 25:
                return "upper_top" if exposed_above else "upper_dirt"
            if macro_y < 50:
                return "mine_top" if exposed_above else "mine_dirt"
            if macro_y < 75:
                return "deep_top" if exposed_above else "deep_dirt"
            return "ancient_top" if exposed_above else "ancient_dirt"
        if kind == ROCK:
            if macro_y < 35:
                return "gray_stone"
            if macro_y < 67:
                return "dark_stone"
            return "volcanic_stone"
        if kind == STONE:
            return "ancient_stone"
        if kind == WATER:
            return "water"
        if kind == LAVA:
            return "lava"
        return None
