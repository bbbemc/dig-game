"""All source rectangles and rendering helpers for the supplied contact sheet."""
from collections import deque
from functools import lru_cache
import math
from pathlib import Path
import pygame
from level import DIRT, ROCK, WATER, LAVA, STONE
from pixel_art import rail as rail_art, sprite as pixel_sprite
from terrain_art import (TEXTURE_SIZE, border_masks, corner_erasers, detail_category, edge_pieces,
                         ground_details, ground_texture, luminance, opaque, palette,
                         rear_wall)

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
        'gold_ore': (506, 669, 46, 55),
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
        # Modular timber cut from the frames above; structures tile them.
        'beam': (21, 851, 102, 15), 'post': (23, 926, 14, 44),
        'post_foot': (21, 989, 17, 16), 'thin_beam': (308, 853, 50, 11),
        'post_stub': (287, 968, 25, 37), 'debris': (40, 895, 70, 13),
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
        'iron_bar': (1112, 932, 44, 12),
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
        'dirt_mound': (1188, 940, 50, 62),
        'stone_mound': (1290, 948, 62, 56),
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
    'broken_support': ((31, 52, 65, 19), (0, 50, 31, 21)),
    'cart': ((0, 0, 8, 7),),
}
# Lamps carry a baked dark halo on the sheet. Dim pixels connected to the
# specimen border are cleared; the runtime lighting supplies the glow.
LIGHT_SPRITES = {'lantern', 'hanging_lantern', 'torch'}
HALO_LUMINANCE = 48

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
# Built blocks keep their per-tile masonry; every other ground is seamless.
MASONRY = {'surface', 'dungeon', 'ancient'}
STONY = {'stone', 'dark', 'volcanic', 'ancient', 'mixed', 'dungeon'}
# Ore veins are embedded chunks drawn over the surrounding ground.
ORES = {'ore_blue': ('ore_deep_blue', 'ore_blue'),
        'ore_gold': ('ore_gold', 'ore_silver'),
        'ore_red': ('ore_red', 'ore_ember')}
SOIL = ('dirt', 'deep', 'ancient_dirt', 'ash', 'surface', 'mud', 'sand', 'moss')
# Depth strata, top to bottom: (boundary macro row, upper group, lower group).
DEPTH_ZONES = {
    DIRT: ((50, 'dirt', 'deep'), (66, 'deep', 'ancient_dirt'), (77, 'ancient_dirt', 'ash')),
    ROCK: ((46, 'stone', 'dark'), (75, 'dark', 'volcanic')),
}
WALL_ZONES = ((25, 'dirt', 'deep'), (50, 'deep', 'ancient_dirt'),
              (74, 'ancient_dirt', 'dark'), (80, 'dark', 'volcanic'))
ZONE_DEPTH = 6.0
LIQUID_SIZE = (160, 160)
# Mean colour of each rear wall: dark charcoal-browns, never pure black.
WALL_COLORS = {'dirt': (38, 31, 25), 'deep': (38, 27, 23), 'ancient_dirt': (35, 28, 26),
               'dark': (29, 29, 36), 'volcanic': (39, 26, 21)}


def coordinate_hash(x, y):
    value = (x * 73856093 ^ y * 19349663 ^ 42) & 0xffffffff
    value ^= value >> 16
    value = (value * 0x45d9f3b) & 0xffffffff
    return value ^ (value >> 16)


def _wave(x, salt, period=5.0):
    """Smooth value noise in [0, 1) along macro columns."""
    knot, t = divmod(x / period, 1.0)
    a = coordinate_hash(int(knot), salt) % 1000 / 1000
    b = coordinate_hash(int(knot) + 1, salt) % 1000 / 1000
    t = t * t * (3 - 2 * t)
    return a + (b - a) * t


@lru_cache(maxsize=None)
def stratum(zones, x, y):
    """Macro (x, y): (base group, overlay group or None, share per cell row).

    Strata meet in a smooth crossfade about six macro rows deep whose height
    wanders along x, so layers blend in a soft wavy band instead of tiles.
    """
    group = zones[0][1]
    for boundary, upper, lower in zones:
        shift = (_wave(x, boundary) - 0.5) * 2.4
        t = (y + 0.5 - boundary - shift) / ZONE_DEPTH + 0.5
        if t <= 0:
            return upper, None, None
        if t < 1:
            shares = []
            for row in range(5):
                share = (y + (row + 0.5) / 5 - boundary - shift) / ZONE_DEPTH + 0.5
                share = min(1.0, max(0.0, share))
                shares.append(share * share * (3 - 2 * share))
            return upper, lower, tuple(shares)
        group = lower
    return group, None, None


def remove_halo(sample, limit=HALO_LUMINANCE):
    """Clear dim pixels reachable from the border through other dim pixels."""
    width, height = sample.get_size()
    queue = deque([(x, y) for x in range(width) for y in (0, height - 1)] +
                  [(x, y) for y in range(height) for x in (0, width - 1)])
    seen = set()
    while queue:
        x, y = queue.popleft()
        if (x, y) in seen or not (0 <= x < width and 0 <= y < height):
            continue
        seen.add((x, y))
        r, g, b, a = sample.get_at((x, y))
        if a and luminance((r, g, b)) >= limit:
            continue
        sample.set_at((x, y), (r, g, b, 0))
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))


class TileArt:
    def __init__(self, cell_size, macro_size):
        self.cell_size, self.macro_size = cell_size, macro_size
        self.samples, self.macro, self.scaled, self.glows = {}, {}, {}, {}
        self.cache = {}
        sheet = pygame.image.load(str(ATLAS)).convert_alpha()
        for name, definition in SPRITES.items():
            rect = pygame.Rect(definition['rect'])
            assert sheet.get_rect().contains(rect), name
            sample = sheet.subsurface(rect).copy()
            for excluded in CROP_EXCLUSIONS.get(name, ()):
                sample.fill((0, 0, 0, 0), excluded)
            if name not in TILE_NAMES:
                sample = self.cutout(sample, name in LIGHT_SPRITES)
            self.samples[name] = sample
            self.macro[name] = pygame.transform.scale(sample, (macro_size, macro_size))
        self.ore_chunks = {group: [self.cutout(sheet.subsurface(SPRITES[n]['rect']).copy())
                                   for n in names] for group, names in ORES.items()}
        self.ore_chunks = {group: [pygame.transform.smoothscale(c, (22, round(22 * c.get_height() / c.get_width())))
                                   for c in chunks] for group, chunks in self.ore_chunks.items()}
        self._build_ground()
        self.walls = {}
        for seed, (group, color) in enumerate(WALL_COLORS.items()):
            texture = self.textures[group]
            gray = pygame.transform.average_color(pygame.transform.grayscale(texture))[0]
            tint = tuple(min(255, round(color[c] * 255 / max(1, gray))) for c in range(3))
            self.walls[group] = rear_wall(texture, tint, 101 + seed, marks=group == 'dirt')
        # Liquid texture patches contain the original pixels, without the
        # atlas specimen's rectangular frame. No replacement fluid artwork.
        self.liquid_patches, self.liquid_textures = {}, {}
        for kind, name in ((WATER, 'water_body'), (LAVA, 'lava_body')):
            sample = self.samples[name]
            patch = sample.subsurface(sample.get_rect().inflate(-6, -6))
            self.liquid_patches[kind] = opaque(pygame.transform.scale(patch, (macro_size, macro_size)))
            # A seamless body, twice as wide so a drifting window never wraps.
            body = ground_texture([pygame.transform.scale(patch, (macro_size, macro_size))],
                                  211 + kind, contrast=1.0, inset=0, size=LIQUID_SIZE)
            wide = pygame.Surface((LIQUID_SIZE[0] * 2, LIQUID_SIZE[1]), 0, 32)
            wide.blit(body, (0, 0))
            wide.blit(body, (LIQUID_SIZE[0], 0))
            self.liquid_textures[kind] = wide

    @staticmethod
    def cutout(sample, halo=False):
        """Remove the sheet's blue-black panel and make solid pixels opaque."""
        # Warm wood/bone shading is preserved by the colour comparison.
        for y in range(sample.get_height()):
            for x in range(sample.get_width()):
                r, g, b, a = sample.get_at((x, y))
                if r < 47 and g < 45 and b < 60 and b >= r - 4:
                    sample.set_at((x, y), (r, g, b, 0))
                elif a >= 200:
                    sample.set_at((x, y), (r, g, b, 255))
        if halo:
            remove_halo(sample)
        bounds = sample.get_bounding_rect(min_alpha=10)
        assert bounds.w and bounds.h
        return sample.subsurface(bounds).copy()

    def _build_ground(self):
        size = self.macro_size
        self.textures, self.palettes, self.details, self.edges = {}, {}, {}, {}
        for seed, (group, names) in enumerate(MATERIALS.items()):
            if group in ORES:
                continue
            if group in MASONRY:
                canvas = pygame.Surface(TEXTURE_SIZE, 0, 32)
                tiles = [opaque(pygame.transform.scale(self.samples[n], (size, size))) for n in names]
                for y in range(0, TEXTURE_SIZE[1], size):
                    for x in range(0, TEXTURE_SIZE[0], size):
                        canvas.blit(tiles[coordinate_hash(x // size, y // size) % len(tiles)], (x, y))
            else:
                # Specimens keep their native pixels (about one sheet pixel per
                # world pixel), so clods match the props' level of detail.
                canvas = ground_texture([self.samples[n] for n in names], 31 + seed * 17)
            self.textures[group] = canvas
            self.palettes[group] = palette(canvas)
            self.details[group] = ground_details(self.palettes[group], group in STONY, seed)
            self.edges[group] = edge_pieces(self.palettes[group], seed)
        self.erasers = corner_erasers(self.cell_size)
        self.borders = border_masks(size)

    @staticmethod
    def depth_material(kind, x, y):
        """The dominant ground group of a macro (no scenery override)."""
        if kind not in DEPTH_ZONES:
            return 'stone'
        upper, lower, shares = stratum(DEPTH_ZONES[kind], x, y)
        return lower if lower and sum(shares) > 2.5 else upper

    def ground(self, kind, x, y, material=None):
        """(texture, window x, window y, edge group, detail, blend) for macro (x, y).

        The window continues the neighbouring macros' pixels. ``detail`` is
        ``(sprite, dx, dy)`` inside the macro or None; most macros stay plain.
        ``blend`` is ``(texture, share per cell row)`` crossfading into the
        next stratum, or None.
        """
        if kind not in (DIRT, ROCK) or (kind == ROCK and material in SOIL):
            # A cave's soil style must not disguise unbreakable rock as dirt,
            # and cooled stone always reads as stone.
            material = None
        ore = material if material in ORES else None
        blend = None
        if material and not ore:
            base = group = material
        elif kind in DEPTH_ZONES:
            base, lower, shares = stratum(DEPTH_ZONES[kind], x, y)
            group = base
            if lower:
                blend = (self.textures[lower], shares)
                if sum(shares) > 2.5:
                    group = lower
        else:
            base = group = 'stone'
        texture = self.textures[base]
        width, height = texture.get_size()
        size = self.macro_size
        detail = None
        roll = coordinate_hash(x * 3 + 11, y * 5 + 7)
        if ore:
            chunks = self.ore_chunks[ore]
            sprite = chunks[roll % len(chunks)]
        else:
            category = None if group in MASONRY else detail_category(roll % 100)
            sprite = None
            if category:
                options = self.details[group][category]
                sprite = options[(roll >> 8) % len(options)]
        if sprite:
            w, h = sprite.get_size()
            detail = (sprite, 2 + (roll >> 12) % max(1, size - w - 3),
                      2 + (roll >> 18) % max(1, size - h - 3))
        return texture, (x * size) % width, (y * size) % height, group, detail, blend

    def tile(self, kind, x, y, material=None, above=None):
        if kind == WATER:
            return self.macro['water_body' if above == WATER else 'water_top']
        if kind == LAVA:
            return self.macro['lava_body' if above == LAVA else 'lava_top']
        texture, wx, wy, group, *_ = self.ground(kind, x, y, material)
        key = ('tile', id(texture), wx, wy)
        if key not in self.cache:
            self.cache[key] = texture.subsurface((wx, wy, self.macro_size, self.macro_size))
        return self.cache[key]

    def wall(self, x, y):
        """(texture, window x, window y, blend) of the rear wall at macro (x, y)."""
        base, lower, shares = stratum(WALL_ZONES, x, y)
        texture = self.walls[base]
        size = self.macro_size
        blend = (self.walls[lower], shares) if lower else None
        return texture, (x * size) % texture.get_width(), (y * size) % texture.get_height(), blend

    def background(self, x, y, background_type=None):
        """The dominant rear-wall window of macro (x, y) as a cached surface."""
        base, lower, shares = stratum(WALL_ZONES, x, y)
        group = lower if lower and sum(shares) > 2.5 else base
        wall = self.walls[group]
        size = self.macro_size
        wx, wy = (x * size) % wall.get_width(), (y * size) % wall.get_height()
        key = ('wall', group, wx, wy)
        if key not in self.cache:
            self.cache[key] = wall.subsurface((wx, wy, size, size))
        return self.cache[key]

    def sprite(self, name, width, height, opacity=255, flip=False, shade=255):
        key = (name, width, height, opacity, flip, shade)
        if key not in self.scaled:
            surface = pygame.transform.scale(self.samples[name], (width, height))
            if flip:
                surface = pygame.transform.flip(surface, True, False)
            if shade != 255:
                surface.fill((shade, shade, shade), special_flags=pygame.BLEND_RGB_MULT)
            if opacity != 255:
                surface.set_alpha(opacity)
            self.scaled[key] = surface
        return self.scaled[key]

    # ------------------------------------------------------------------
    # Modular timber: structures are assembled from pieces of the frames.
    # ------------------------------------------------------------------
    def beam(self, length, thickness, name='beam'):
        """A horizontal beam of any length that keeps both bolted ends."""
        key = ('beam', name, length, thickness)
        if key not in self.cache:
            sample = self.samples[name]
            w, h = sample.get_size()
            scaled = pygame.transform.scale(sample, (max(1, round(w * thickness / h)), thickness))
            sw = scaled.get_width()
            surface = pygame.Surface((length, thickness), pygame.SRCALPHA)
            cap = min(sw // 4, length // 2)
            if length <= sw:
                surface.blit(scaled, (0, 0), (0, 0, length - cap, thickness))
                surface.blit(scaled, (length - cap, 0), (sw - cap, 0, cap, thickness))
            else:
                middle = scaled.subsurface((cap, 0, sw - 2 * cap, thickness))
                x = cap
                while x < length - cap:
                    surface.blit(middle, (x, 0), (0, 0, min(middle.get_width(), length - cap - x), thickness))
                    x += middle.get_width()
                surface.blit(scaled, (0, 0), (0, 0, cap, thickness))
                surface.blit(scaled, (length - cap, 0), (sw - cap, 0, cap, thickness))
            self.cache[key] = surface
        return self.cache[key]

    def post(self, height, width, name='post'):
        """A vertical post of any height, tiled from the frame's upright."""
        key = ('post', name, height, width)
        if key not in self.cache:
            sample = self.samples[name]
            w, h = sample.get_size()
            scaled = pygame.transform.scale(sample, (width, max(1, round(h * width / w))))
            surface = pygame.Surface((width, height), pygame.SRCALPHA)
            for y in range(0, height, scaled.get_height()):
                surface.blit(scaled, (0, y))
            self.cache[key] = surface
        return self.cache[key]

    def brace(self, width, height, thickness, rising=True):
        """A diagonal plank spanning a corner box, cut from the upright's grain."""
        key = ('brace', width, height, thickness, rising)
        if key not in self.cache:
            length = round(math.hypot(width, height)) + thickness
            plank = self.post(length, thickness)
            angle = math.degrees(math.atan2(height, width))
            rotated = pygame.transform.rotate(plank, -(90 - angle) if rising else (90 - angle))
            surface = pygame.Surface((width, height), pygame.SRCALPHA)
            surface.blit(rotated, rotated.get_rect(center=(width / 2, height / 2)))
            self.cache[key] = surface
        return self.cache[key]

    def pixel(self, name, width, height, flip=False):
        """A hand-authored sprite from pixel_art, scaled once and cached."""
        key = ('pixel', name, width, height, flip)
        if key not in self.cache:
            surface = pixel_sprite(name)
            if surface.get_size() != (width, height):
                surface = pygame.transform.scale(surface, (width, height))
            self.cache[key] = pygame.transform.flip(surface, True, False) if flip else surface
        return self.cache[key]

    def rail(self, length):
        key = ('rail', length)
        if key not in self.cache:
            self.cache[key] = rail_art(length)
        return self.cache[key]

    def shadow(self, width, height=10, alpha=120):
        """Soft contact shadow placed where a prop meets the floor."""
        key = ('shadow', width, height, alpha)
        if key not in self.cache:
            surface = pygame.Surface((width, height), pygame.SRCALPHA)
            for step in range(6):
                inset = step * width // 14
                rect = pygame.Rect(inset, step * height // 14, width - 2 * inset, height - 2 * (step * height // 14))
                if rect.w > 0 and rect.h > 0:
                    pygame.draw.ellipse(surface, (8, 6, 6, alpha // 6), rect)
            self.cache[key] = surface
        return self.cache[key]

    def glow(self, radius, color):
        key = (radius, color)
        if key not in self.glows:
            surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            for r in range(radius, 0, -3):
                alpha = int(66 * (1 - r / radius) ** 2)
                pygame.draw.circle(surface, (*color, alpha), (radius, radius), r)
            self.glows[key] = surface
        return self.glows[key]
