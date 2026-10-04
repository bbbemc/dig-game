"""All source rectangles and rendering helpers for the supplied contact sheet."""
from pathlib import Path
import pygame
from level import DIRT, ROCK, WATER, LAVA, STONE

ATLAS = Path(__file__).parent / 'assets' / 'underground_tiles.png'

# Coordinates refer to the original 1536 x 1024 image. No replacement art.
# Categories deliberately mirror the 21 panels printed on the sheet.
SPRITE_GROUPS = {
    1: {
        'surface_grass': (16, 58, 43, 48),
        'surface_flowers': (69, 58, 43, 48),
    },
    2: {
        'dirt_1': (402, 52, 43, 49), 'dirt_2': (457, 52, 45, 49),
        'dirt_3': (512, 52, 44, 49), 'dirt_4': (566, 52, 38, 49),
    },
    3: {
        'deep_1': (785, 52, 45, 49), 'deep_2': (841, 52, 45, 49),
        'deep_3': (900, 52, 45, 49),
    },
    4: {
        'ancient_dirt_1': (1163, 52, 44, 49),
        'ancient_dirt_2': (1217, 52, 44, 49),
        'ancient_dirt_3': (1274, 52, 48, 49),
    },
    5: {
        'stone_1': (18, 287, 43, 48), 'stone_2': (71, 287, 42, 48),
        'stone_3': (126, 287, 43, 48),
    },
    6: {
        'dark_1': (403, 287, 45, 48), 'dark_2': (462, 287, 43, 48),
        'dark_3': (519, 287, 44, 48),
    },
    7: {
        'volcanic_1': (783, 287, 44, 48),
        'volcanic_2': (840, 287, 43, 48),
        'volcanic_3': (895, 287, 42, 48),
    },
    8: {
        'ancient_stone_1': (1163, 287, 44, 48),
        'ancient_stone_2': (1217, 287, 44, 48),
    },
    9: {
        'water_top': (20, 500, 45, 59),
        'water_body': (22, 521, 42, 32),
        'water_fall': (229, 500, 36, 73),
    },
    10: {
        'lava_top': (404, 501, 43, 58),
        'lava_body': (406, 523, 40, 31),
        'lava_fall': (558, 500, 37, 69),
    },
    11: {
        'mixed_1': (784, 503, 43, 49), 'mixed_2': (840, 503, 44, 49),
        'ash_1': (784, 566, 43, 50), 'ash_2': (840, 566, 43, 50),
    },
    12: {
        'sand': (1084, 503, 44, 48), 'gravel': (1137, 565, 43, 50),
    },
    13: {
        'mud_1': (1316, 503, 46, 48), 'mud_2': (1375, 503, 44, 48),
        'mud_ore': (1429, 503, 43, 48), 'moss_dirt': (1375, 565, 44, 50),
    },
    14: {
        'dirt_stalactite': (18, 669, 63, 67),
        'thin_stalactite': (90, 669, 30, 63),
        'stone_stalactite': (255, 669, 60, 67),
        'small_stalactite': (319, 669, 24, 59),
        'dirt_stalagmite': (18, 738, 58, 62),
        'stone_stalagmite': (255, 736, 47, 64),
        'small_stalagmite': (314, 744, 32, 56),
    },
    15: {
        'ore_blue': (448, 669, 44, 55), 'ore_gold': (506, 669, 46, 55),
        'ore_silver': (564, 669, 45, 55), 'ore_deep_blue': (623, 669, 45, 55),
        'ore_red': (682, 669, 45, 55), 'ore_ember': (741, 669, 45, 55),
        'blue_crystal': (446, 733, 57, 67),
        'purple_crystal': (511, 733, 61, 67),
        'red_crystal': (579, 734, 60, 66),
        'ember_rocks': (642, 740, 59, 59),
        'small_red_crystal': (711, 744, 24, 29),
    },
    16: {
        'vines': (816, 674, 90, 78), 'short_vines': (916, 675, 57, 73),
        'moss_vines': (983, 676, 56, 73),
        'cave_flowers': (1051, 676, 46, 36), 'fern': (1114, 674, 47, 39),
        'yellow_flower': (813, 738, 40, 64),
        'red_flower': (875, 744, 46, 57),
        'small_plants': (920, 746, 42, 55),
        'red_mushroom': (965, 734, 32, 41),
        'purple_mushroom': (1021, 721, 54, 56),
        'blue_mushroom': (1063, 767, 38, 34),
        'large_mushroom': (1095, 720, 68, 80),
    },
    17: {
        'bones': (1188, 675, 69, 52), 'ribs': (1267, 680, 41, 48),
        'skull': (1321, 674, 42, 52), 'small_skull': (1371, 674, 29, 52),
        'ruin_pillar': (1410, 671, 36, 54),
        'ruin_rubble': (1449, 676, 38, 52),
        'broken_pot': (1185, 731, 49, 69),
        'ruin_arch': (1274, 731, 106, 69),
        'ruin_wall': (1387, 732, 61, 68),
        'broken_pillar': (1478, 732, 43, 68),
    },
    18: {
        'mine_frame': (137, 850, 82, 94),
        'mine_tall_frame': (20, 850, 104, 156),
        'mine_rail': (294, 850, 143, 28),
        'ladder': (233, 850, 37, 156),
        'broken_support': (287, 906, 105, 71),
        'cart': (318, 958, 64, 49),
        'broken_cart': (392, 958, 51, 49),
        'hanging_lantern': (410, 899, 29, 56),
        'chain': (419, 890, 9, 27),
    },
    19: {
        'brick_1': (465, 852, 43, 45), 'brick_2': (519, 852, 44, 45),
        'brick_3': (574, 852, 44, 45), 'brick_4': (630, 852, 43, 45),
        'prison_window': (685, 850, 63, 48),
        'dungeon_column': (464, 908, 37, 99),
        'dungeon_arch': (591, 906, 82, 101),
        'broken_bricks': (699, 912, 50, 55),
    },
    20: {
        'barrel': (779, 850, 41, 51), 'crate': (830, 850, 43, 51),
        'wood_crate': (881, 850, 43, 51), 'sack': (930, 872, 23, 30),
        'toolbox': (1003, 850, 44, 35), 'banner': (1059, 850, 49, 76),
        'stone_column': (1119, 853, 39, 66),
        'torch': (781, 911, 29, 96), 'lantern': (830, 908, 26, 47),
        'cobweb': (930, 909, 58, 65), 'small_crate': (1004, 901, 45, 55),
        'large_sack': (860, 952, 41, 55),
        'rock_pile': (931, 969, 54, 38),
        'gold_chest': (1001, 963, 68, 44),
        'old_chest': (1081, 961, 77, 47),
    },
    21: {
        'small_rocks': (1188, 859, 32, 32),
        'gray_rubble': (1228, 859, 50, 34),
        'dry_roots': (1309, 849, 25, 43),
        'small_purple_crystal': (1379, 852, 22, 35),
        'tiny_purple_cluster': (1407, 857, 28, 33),
        'small_flower': (1445, 849, 38, 45),
        'dead_vines': (1259, 906, 49, 49),
        'volcanic_rubble': (1328, 906, 34, 33),
        'hanging_bones': (1458, 903, 59, 55),
    },
}
SPRITES = {name: {'rect': rect, 'category': category}
           for category, entries in SPRITE_GROUPS.items() for name, rect in entries.items()}

# Neighboring props overlap the rectangular extents of a few specimens on
# this contact sheet. These local cutouts remove only that neighboring art.
CROP_EXCLUSIONS = {
    'vines': ((0, 64, 32, 14), (59, 64, 31, 14)),
    'short_vines': ((0, 63, 49, 10), (49, 59, 8, 14)),
    'moss_vines': ((0, 58, 15, 15), (38, 45, 18, 28)),
    'purple_mushroom': ((42, 46, 12, 10),),
    'broken_support': ((31, 52, 65, 19),),
}

MATERIALS = {
    'surface': ('surface_grass', 'surface_flowers'),
    'dirt': ('dirt_1', 'dirt_2', 'dirt_3', 'dirt_4'),
    'deep': ('deep_1', 'deep_2', 'deep_3'),
    'ancient_dirt': ('ancient_dirt_1', 'ancient_dirt_2', 'ancient_dirt_3'),
    'stone': ('stone_1', 'stone_2', 'stone_3'),
    'dark': ('dark_1', 'dark_2', 'dark_3'),
    'volcanic': ('volcanic_1', 'volcanic_2', 'volcanic_3'),
    'ancient': ('ancient_stone_1', 'ancient_stone_2'),
    'ash': ('ancient_dirt_2', 'ash_1', 'ash_2', 'mixed_1'),
    'mixed': ('mixed_1', 'mixed_2', 'ash_1'),
    'sand': ('sand', 'gravel'),
    'mud': ('mud_1', 'mud_2', 'mud_ore'),
    'moss': ('moss_dirt',),
    'dungeon': ('brick_1', 'brick_2', 'brick_3', 'brick_4'),
    'ore_blue': ('ore_deep_blue',),
    'ore_gold': ('ore_gold', 'ore_silver'),
    'ore_red': ('ore_red', 'ore_ember'),
}
TILE_NAMES = {name for variants in MATERIALS.values() for name in variants}
TILE_NAMES.update(('water_top', 'water_body', 'lava_top', 'lava_body'))


def coordinate_hash(x, y):
    return (x * 73856093 ^ y * 19349663 ^ 42) & 0xffffffff


def blend_material(x, y, boundary, shallow, deep):
    # A six-row deterministic blend rather than a horizontal palette seam.
    return deep if coordinate_hash(x, y) % 6 < y - boundary + 3 else shallow


class TileArt:
    def __init__(self, cell_size, macro_size):
        self.cell_size, self.macro_size = cell_size, macro_size
        self.samples, self.macro, self.scaled, self.glows = {}, {}, {}, {}
        sheet = pygame.image.load(str(ATLAS)).convert_alpha()
        for name, definition in SPRITES.items():
            rect = pygame.Rect(definition['rect'])
            assert sheet.get_rect().contains(rect), name
            sample = sheet.subsurface(rect).copy()
            for excluded in CROP_EXCLUSIONS.get(name, ()):
                sample.fill((0, 0, 0, 0), excluded)
            if name not in TILE_NAMES:
                # Remove the contact sheet's blue-black panel background.
                # Warm wood/bone shading is preserved by the colour comparison.
                for y in range(sample.get_height()):
                    for x in range(sample.get_width()):
                        r, g, b, a = sample.get_at((x, y))
                        if r < 47 and g < 45 and b < 60 and b >= r - 4:
                            sample.set_at((x, y), (r, g, b, 0))
                bounds = sample.get_bounding_rect(min_alpha=10)
                assert bounds.w and bounds.h, name
                sample = sample.subsurface(bounds).copy()
            self.samples[name] = sample
            self.macro[name] = pygame.transform.scale(sample, (macro_size, macro_size))
        self.backgrounds = {}
        for group in ('dirt', 'deep', 'ancient_dirt', 'dark', 'volcanic', 'dungeon'):
            background = self.macro[MATERIALS[group][0]].copy()
            background.fill((38, 38, 48, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.backgrounds[group] = background

    @staticmethod
    def depth_material(kind, x, y):
        if kind == DIRT:
            if y < 47:
                return 'dirt'
            if y < 53:
                return blend_material(x, y, 50, 'dirt', 'deep')
            if y < 63:
                return 'deep'
            if y < 69:
                return blend_material(x, y, 66, 'deep', 'ancient_dirt')
            if y < 74:
                return 'ancient_dirt'
            if y < 80:
                return blend_material(x, y, 77, 'ancient_dirt', 'ash')
            return 'ash'
        if kind == ROCK:
            if y < 43:
                return 'stone'
            if y < 49:
                return blend_material(x, y, 46, 'stone', 'dark')
            if y < 72:
                return 'dark'
            if y < 78:
                return blend_material(x, y, 75, 'dark', 'volcanic')
            return 'volcanic'
        return 'stone'

    def tile(self, kind, x, y, material=None, above=None):
        if kind == WATER:
            name = 'water_body' if above == WATER else 'water_top'
        elif kind == LAVA:
            name = 'lava_body' if above == LAVA else 'lava_top'
        else:
            group = material or self.depth_material(kind, x, y)
            variants = MATERIALS[group]
            name = variants[coordinate_hash(x, y) % len(variants)]
        return self.macro[name]

    def sprite(self, name, width, height, opacity=255, flip=False):
        key = (name, width, height, opacity, flip)
        if key not in self.scaled:
            surface = pygame.transform.scale(self.samples[name], (width, height))
            if flip:
                surface = pygame.transform.flip(surface, True, False)
            if opacity != 255:
                surface.set_alpha(opacity)
            self.scaled[key] = surface
        return self.scaled[key]

    def glow(self, radius, color):
        key = (radius, color)
        if key not in self.glows:
            surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            for r in range(radius, 0, -3):
                alpha = int(66 * (1 - r / radius) ** 2)
                pygame.draw.circle(surface, (*color, alpha), (radius, radius), r)
            self.glows[key] = surface
        return self.glows[key]
