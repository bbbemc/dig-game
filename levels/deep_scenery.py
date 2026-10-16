"""Biome decoration for The Deep Descent, using the existing sprite sheet.

Each layer has its own floor and ceiling palettes plus staged scenes
(mine galleries with timber, mushroom grottos, crystal clusters, ruins and
the boss arena). Scatter placement keeps the same sprite several macros
apart, so no stretch of cave repeats one pattern. Props stay visual only:
the _Placement rules keep every one in open cave with solid anchors.
"""

import copy
import math

from caves import sculpt_caves
from config import DEEP_BOMB_PICKUPS
from levels.deep_world import LAYER_COUNT, LAYER_NAMES
from level import DIRT, ROCK
from scenery import _Placement, _piece

WARM = (3.2, (255, 172, 70))
BLUE = (2.6, (64, 147, 255))
PURPLE = (2.6, (178, 86, 247))
RED = (2.4, (255, 91, 38))

# (name, width, height, weight, glow, layer) in macros.
FLOOR = {
    0: (('crate', 0.85, 1.0, 3, None, 'front'), ('small_crate', 0.7, 0.86, 3, None, 'front'),
        ('barrel', 0.7, 0.88, 3, None, 'front'), ('sack', 0.36, 0.47, 2, None, 'front'),
        ('large_sack', 0.6, 0.8, 2, None, 'front'), ('toolbox', 0.8, 0.64, 2, None, 'front'),
        ('rock_pile', 0.9, 0.65, 3, None, 'front'), ('gray_rubble', 0.8, 0.55, 3, None, 'back'),
        ('small_rocks', 0.5, 0.5, 4, None, 'back'), ('broken_cart', 1.25, 1.2, 1, None, 'front'),
        ('dirt_mound', 0.75, 0.93, 2, None, 'back'), ('gold_ore', 0.4, 0.48, 2, None, 'front'),
        ('torch', 0.4, 1.2, 1, WARM, 'front')),
    1: (('dirt_stalagmite', 1.2, 1.4, 3, None, 'back'), ('small_rocks', 0.5, 0.5, 3, None, 'back'),
        ('red_mushroom', 0.6, 0.75, 3, None, 'front'), ('purple_mushroom', 0.8, 0.85, 2, None, 'front'),
        ('blue_mushroom', 0.55, 0.65, 2, None, 'front'), ('fern', 0.9, 0.8, 3, None, 'front'),
        ('small_plants', 0.65, 0.8, 3, None, 'front'), ('cave_flowers', 0.8, 0.6, 2, None, 'front'),
        ('yellow_flower', 0.4, 0.65, 1, None, 'front'), ('red_flower', 0.45, 0.6, 1, None, 'front'),
        ('dirt_mound', 0.75, 0.93, 2, None, 'back'), ('gray_rubble', 0.8, 0.55, 2, None, 'back'),
        ('small_flower', 0.5, 0.6, 2, None, 'front')),
    2: (('blue_crystal', 1.1, 1.3, 2, BLUE, 'back'), ('purple_crystal', 1.1, 1.3, 2, PURPLE, 'back'),
        ('small_purple_crystal', 0.55, 0.85, 3, None, 'front'),
        ('tiny_purple_cluster', 0.6, 0.65, 3, None, 'front'),
        ('stone_stalagmite', 1.0, 1.35, 3, None, 'back'), ('small_stalagmite', 0.6, 0.95, 3, None, 'back'),
        ('blue_mushroom', 0.55, 0.65, 2, None, 'front'), ('stone_mound', 1.0, 0.9, 2, None, 'back'),
        ('small_rocks', 0.5, 0.5, 2, None, 'back')),
    3: (('red_crystal', 1.1, 1.4, 1, RED, 'back'), ('small_red_crystal', 0.6, 0.75, 3, None, 'front'),
        ('ember_rocks', 1.0, 1.0, 2, RED, 'front'), ('volcanic_rubble', 0.9, 0.7, 4, None, 'back'),
        ('ribs', 0.7, 0.7, 2, None, 'front'), ('bones', 1.0, 0.65, 2, None, 'front'),
        ('skull', 0.55, 0.7, 1, None, 'front'), ('small_skull', 0.45, 0.7, 2, None, 'front'),
        ('broken_pillar', 0.8, 1.6, 2, None, 'back'), ('ruin_rubble', 0.8, 1.0, 2, None, 'back'),
        ('broken_pot', 0.6, 0.85, 2, None, 'front'), ('stone_stalagmite', 1.0, 1.35, 2, None, 'back'),
        ('ruin_pillar', 0.7, 1.05, 2, None, 'back')),
}
CEILING = {
    0: (('cobweb', 0.9, 1.0, 3, None, 'back'), ('dry_roots', 0.4, 0.7, 3, None, 'front'),
        ('dead_vines', 0.9, 0.9, 2, None, 'front'), ('hanging_lantern', 0.62, 1.2, 1, WARM, 'front'),
        ('chain', 0.3, 1.2, 1, None, 'back')),
    1: (('dirt_stalactite', 1.3, 1.5, 3, None, 'back'), ('thin_stalactite', 0.45, 1.1, 3, None, 'back'),
        ('dry_roots', 0.4, 0.7, 3, None, 'front'), ('vines', 1.5, 1.4, 2, None, 'front'),
        ('moss_vines', 1.3, 1.6, 2, None, 'front'), ('short_vines', 1.0, 1.2, 2, None, 'front')),
    2: (('stone_stalactite', 1.3, 1.6, 3, None, 'back'), ('small_stalactite', 0.6, 1.3, 3, None, 'back'),
        ('thin_stalactite', 0.45, 1.1, 2, None, 'back'), ('short_vines', 1.0, 1.2, 1, None, 'front')),
    3: (('stone_stalactite', 1.3, 1.6, 2, None, 'back'), ('small_stalactite', 0.6, 1.3, 3, None, 'back'),
        ('dead_vines', 0.9, 0.9, 2, None, 'front'), ('hanging_bones', 0.8, 0.75, 1, None, 'front'),
        ('chain', 0.3, 1.4, 2, None, 'back')),
}
FLOOR_DENSITY = (0.2, 0.3, 0.26, 0.22)
CEILING_DENSITY = (0.12, 0.2, 0.18, 0.12)
SAME_SPRITE_GAP = 6       # macros between two copies of one sprite
MAX_GLOWS = (5, 4, 12, 9)  # scatter lights per layer (scenes add their own)
ORES = ('ore_gold', 'ore_gold', 'ore_blue', 'ore_red')


def depth_zones(tops):
    """Strata boundaries (macro rows) for ground, rock and the rear wall."""
    t1, t2, t3 = tops[1], tops[2], tops[3]
    return {DIRT: ((t1, 'dirt', 'deep'), (t2, 'deep', 'ancient_dirt'), (t3, 'ancient_dirt', 'ash')),
            ROCK: ((t2, 'stone', 'dark'), (t3, 'dark', 'volcanic')),
            'wall': ((t1, 'dirt', 'deep'), (t2, 'deep', 'dark'), (t3, 'dark', 'volcanic'))}


class _Decorator:
    def __init__(self, gen, rows, sprites):
        self.gen, self.rows = gen, rows
        self.rng = gen.rng
        self.layout = _Placement(rows, sprites)
        if gen.chamber:
            # The authored map keeps its own props; they also reserve space.
            authored = gen.chamber['scenery']
            self.layout.props.extend(copy.deepcopy(authored['props']))
            self.layout.structures.extend(copy.deepcopy(authored.get('structures', ())))
            for item in self.layout.props + self.layout.structures:
                self.layout.occupied[item['layer']].extend(item.get('occupancy_rects', ()))
        self.copies = {}       # sprite name -> [(x, y)] placed so far
        self.glows = [0] * LAYER_COUNT

    def far_from_copies(self, name, x, y):
        return all(abs(x - px) + abs(y - py) >= SAME_SPRITE_GAP
                   for px, py in self.copies.get(name, ()))

    def note(self, prop, name):
        if prop:
            self.copies.setdefault(name, []).append((prop['x'], prop['y']))
        return prop

    def floor(self, name, x, y, w, h, glow=None, layer='front', **extra):
        return self.note(self.layout.floor(name, x, y, w, h, glow, layer=layer, **extra), name)

    def ceiling(self, name, x, y, w, h, glow=None, layer='front', **extra):
        return self.note(self.layout.ceiling(name, x, y, w, h, glow, layer=layer, **extra), name)

    # ------------------------------------------------------------------
    def ladders(self):
        for shaft in self.gen.shafts:
            self.layout.ladder(shaft['x'], shaft['bottom'], width=0.8, top=shaft['top'] - 1)

    def scenes(self):
        for room in self.gen.rooms:
            getattr(self, 'scene_' + room['kind'])(room)
        self.scene_arena()
        for x0, y0, x1, y1 in self.gen.pockets:
            # A forgotten stash: someone hid this before the mine fell in.
            chest = 'gold_chest' if self.gen.layer_of(y0) >= 2 else 'old_chest'
            self.floor(chest, (x0 + x1) / 2 - 0.2, y1, 1.0, 0.65, search=1.0)
            self.ceiling('cobweb', x0 + 0.2, y0, 0.7, 0.8, layer='back', search=0.5)

    def scene_spawn(self, room):
        floor = room['floor']
        self.layout.mine_set(room['x0'] + 2.2, room['x0'] + 5.2, floor, lamp=room['x0'] + 3.7,
                             braces=False)
        self.layout.group([('crate', room['x0'] + 5.6, 0.85, 1.0, 0),
                           ('small_crate', room['x0'] + 6.5, 0.7, 0.86, 0)], floor)
        self.floor('toolbox', room['x0'] + 0.4, floor, 0.8, 0.64, search=0.5)
        level = self.layout.floor_level(room['x0'] + 1.6, room['x0'] + 2.0, floor)
        if level:
            bottom = level[1]
            self.layout.structure([_piece('art', room['x0'] + 1.6, bottom - 0.45, 0.325, 0.45,
                                          name='pickaxe')],
                                  [(math.floor(room['x0'] + 1.7), bottom, 'floor')])

    def scene_gallery(self, room):
        """An abandoned working: timber sets, track, a cart and stores."""
        x0, x1, floor = room['x0'], room['x1'], room['floor']
        for left in range(x0 + 1, x1 - 2, 4):
            self.layout.mine_set(left + 0.15, left + 3.0, floor,
                                 lamp=left + 1.6 if self.rng.random() < 0.5 else None,
                                 braces=self.rng.random() < 0.6, low_beam=self.rng.random() < 0.3)
        if self.layout.rails(x0 + 0.6, x1 - 0.4, floor):
            self.floor('cart' if self.rng.random() < 0.6 else 'broken_cart',
                       x0 + self.rng.randint(1, max(1, x1 - x0 - 2)), floor, 1.4, 1.1,
                       search=1.5, lift=0.1)
        self.layout.group([('barrel', x1 - 1.6, 0.7, 0.88, 0), ('crate', x1 - 0.9, 0.8, 0.95, 0)],
                          floor)
        self.ceiling('cobweb', x0 + 0.3, floor, 0.9, 1.0, layer='back', search=1.0)

    def scene_excavation(self, room):
        """A large worked chamber: tall frames, a scaffold, spoil heaps, track."""
        x0, x1, floor = room['x0'], room['x1'], room['floor']
        self.floor('mine_tall_frame', x0 + 1, floor, 2.4, 3.6, layer='back', search=1)
        self.layout.mine_set(x0 + 4.1, x0 + 7.2, floor, lamp=x0 + 5.6, platform=1.9)
        self.floor('mine_frame', x1 - 2, floor, 1.9, 2.2, layer='back', search=1)
        self.layout.rails(x0 + 3.4, x1 - 0.6, floor)
        self.floor('cart', x0 + 8, floor, 1.4, 1.1, search=1.5, lift=0.1)
        for name, x, w, h in (('rock_pile', x1 - 3.5, 1.1, 0.8), ('dirt_mound', x0 + 3, 0.8, 1.0),
                              ('gray_rubble', x1 - 1, 0.9, 0.6), ('gold_ore', x0 + 9.5, 0.4, 0.48)):
            self.floor(name, x, floor, w, h, search=1)
        self.ceiling('hanging_lantern', x1 - 4, floor, 0.62, 1.2, WARM, search=1.5)

    def scene_enemy(self, room):
        k, floor = room['layer'], room['floor']
        middle = (room['x0'] + room['x1']) / 2
        if k == 0:
            self.floor('broken_support', middle - 1, floor, 1.9, 1.28, layer='back', search=2)
            self.floor('rock_pile', middle + 1.5, floor, 1.1, 0.8, search=1.5)
        elif k == 1:
            self.floor('bones', middle - 1.5, floor, 1.0, 0.65, search=1.5)
            self.floor('large_mushroom', room['x0'] + 0.6, floor, 1.4, 1.7, search=1)
        elif k == 2:
            self.floor('blue_crystal', middle, floor, 1.6, 1.9, BLUE, layer='back', search=2)
            self.floor('stone_stalagmite', room['x0'] + 0.5, floor, 1.0, 1.35, layer='back')
        else:
            self.floor('ribs', middle - 1, floor, 0.7, 0.7, search=1.5)
            self.floor('skull', middle + 1, floor, 0.55, 0.7, search=1.5)
            self.layout.wall('torch', room['x0'], floor - 1, 0.45, 1.5, side='left', glow=WARM)

    def scene_grotto(self, room):
        """Mushroom grotto: one large cap with smaller growth around it."""
        floor = room['floor']
        x = room['x0'] + self.rng.randint(1, max(1, room['x1'] - room['x0'] - 3))
        self.floor('large_mushroom', x, floor, 1.4, 1.7, search=1.5)
        for name, dx, w, h in (('purple_mushroom', 1.6, 0.8, 0.85), ('blue_mushroom', -1.2, 0.55, 0.65),
                               ('red_mushroom', 2.6, 0.6, 0.75), ('fern', -2.3, 0.9, 0.8)):
            self.floor(name, x + dx, floor, w, h, search=0.5)
        self.ceiling('moss_vines', x + 1, floor, 1.3, 1.6, search=1.5)
        self.ceiling('short_vines', x - 2, floor, 1.0, 1.25, layer='fore', shade=112, search=1)

    def scene_cavern(self, room):
        floor = room['floor']
        for n, x in enumerate(range(room['x0'] + 1, room['x1'], 3)):
            if n % 2 == 0:
                self.floor('dirt_stalagmite', x, floor, 1.3, 1.5, layer='back', search=1)
            else:
                self.ceiling('dirt_stalactite', x, floor, 1.4, 1.7, layer='back', search=1)
        self.ceiling('vines', room['x0'] + 2, floor, 1.6, 1.6, search=1.5)

    def scene_crystal(self, room):
        """A crystal cluster: one focal facet, shards, pale formations."""
        floor = room['floor']
        x = room['x0'] + self.rng.randint(1, max(1, room['x1'] - room['x0'] - 2))
        focal, light = (('blue_crystal', BLUE) if self.rng.random() < 0.5
                        else ('purple_crystal', PURPLE))
        self.floor(focal, x, floor, 1.85, 2.2, light, layer='back', search=1.5)
        self.floor('small_purple_crystal', x + 1.8, floor, 0.7, 1.0, PURPLE, search=0.5)
        self.floor('tiny_purple_cluster', x - 1.4, floor, 0.65, 0.7, search=0.5)
        self.floor('small_stalagmite', x + 3, floor, 0.65, 1.0, layer='back', search=1)
        self.ceiling('stone_stalactite', x, floor, 1.6, 2.0, layer='back', search=1.5)

    def scene_ruin(self, room):
        """Weathered masonry: an arch, broken pillars and rubble."""
        floor = room['floor']
        middle = (room['x0'] + room['x1']) / 2
        self.floor('ruin_arch', middle - 1.5, floor, 3.0, 2.1, layer='back', opacity=150, search=2)
        self.floor('broken_pillar', room['x0'] + 0.5, floor, 0.85, 1.8, layer='back', opacity=185)
        self.floor('ruin_wall', room['x1'] - 1.5, floor, 1.2, 1.35, layer='back', opacity=190)
        self.floor('ruin_rubble', middle + 2, floor, 0.8, 1.0, search=1)
        self.floor('red_crystal', middle, floor, 1.2, 1.5, RED, layer='front', search=2)

    def scene_arena(self):
        x0, top, x1, bottom = self.gen.arena
        floor = bottom
        self.floor('dungeon_arch', x0 + 3, floor, 3.2, 3.9, layer='back', opacity=120, search=1)
        self.floor('dungeon_column', x1 - 3, floor, 1.2, 3.4, layer='back', opacity=140, search=1)
        self.floor('stone_column', (x0 + x1) / 2 - 3, floor, 1.0, 2.0, layer='back', opacity=150)
        for x in (x0 + 6, x1 - 1):
            self.floor('torch', x, floor, 0.55, 1.9, WARM, search=0.5)
        self.ceiling('banner', x0 + 8, top, 1.0, 1.8, search=1)
        self.ceiling('banner', x1 - 5, top, 1.0, 1.8, search=1)
        for x in (x0 + 10, x1 - 8):
            self.ceiling('chain', x, top, 0.35, 1.6, layer='back', search=1)
        self.floor('bones', x0 + 12, floor, 1.0, 0.65, search=1)
        self.floor('small_skull', x1 - 6, floor, 0.45, 0.7, search=1)

    # ------------------------------------------------------------------
    def scatter(self):
        """Biome props on open floors and roofs, never one sprite too often."""
        gen, rows = self.gen, self.rows
        floors, ceilings = [], []
        for y in range(1, gen.h - 1):
            for x in range(1, gen.w - 1):
                if rows[y][x] != ' ' or gen.in_chamber(x, y) or gen.in_chamber(x + 1, y) \
                        or gen.in_chamber(x - 1, y):
                    continue
                if rows[y + 1][x] in '#RS':
                    floors.append((x, y))
                if rows[y - 1][x] in '#RS':
                    ceilings.append((x, y))
        self.rng.shuffle(floors)
        self.rng.shuffle(ceilings)
        for spots, table, density, method in ((floors, FLOOR, FLOOR_DENSITY, self.floor),
                                              (ceilings, CEILING, CEILING_DENSITY, self.ceiling)):
            for x, y in spots:
                k = gen.layer_of(y)
                if self.rng.random() > density[k]:
                    continue
                options = [entry for entry in table[k] if self.far_from_copies(entry[0], x, y)]
                if not options:
                    continue
                name, w, h, _, glow, layer = self.rng.choices(options, [e[3] for e in options])[0]
                if glow and self.glows[k] >= MAX_GLOWS[k]:
                    glow = None
                scale = self.rng.uniform(0.85, 1.12)
                prop = method(name, x + self.rng.uniform(-0.3, 0.3) - 0.5, y, w * scale, h * scale,
                              glow, layer=layer, flip=self.rng.random() < 0.5, search=0)
                if prop and glow:
                    self.glows[k] += 1

    def materials(self):
        """Wet and scorched rims, biome ores and ancient masonry."""
        gen, rows = self.gen, self.rows
        materials = dict(gen.chamber['scenery']['materials']) if gen.chamber else {}

        def near(x, y, chars, reach=2):
            return any(rows[yy][xx] in chars
                       for yy in range(max(0, y - reach), min(gen.h, y + reach + 1))
                       for xx in range(max(0, x - reach), min(gen.w, x + reach + 1)))

        x0, top, x1, bottom = gen.arena
        ruin_rooms = [r for r in gen.rooms if r['kind'] == 'ruin']
        for y in range(1, gen.h - 1):
            for x in range(1, gen.w - 1):
                char = rows[y][x]
                if char not in '#R' or gen.in_chamber(x, y):
                    continue
                exposed = any(rows[ny][nx] in ' WL' for nx, ny in
                              ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
                if not exposed and not near(x, y, 'WL', 1):
                    continue
                k = gen.layer_of(y)
                if near(x, y, 'L'):
                    materials[x, y] = 'ash' if char == '#' else 'volcanic'
                elif near(x, y, 'W') and char == '#':
                    if any(rows[yy][x] == 'W' for yy in range(y + 1, min(gen.h, y + 3))):
                        materials[x, y] = 'moss'
                    elif any(rows[yy][x] == 'W' for yy in range(max(0, y - 2), y)):
                        materials[x, y] = 'sand'
                    else:
                        materials[x, y] = 'mud'
                elif char == 'R' and (x0 - 1 <= x <= x1 + 1 and top - 1 <= y <= bottom + 1
                                      or any(r['x0'] - 1 <= x <= r['x1'] + 1
                                             and r['top'] - 1 <= y <= r['floor'] + 1
                                             for r in ruin_rooms)):
                    materials[x, y] = 'ancient'
                elif exposed and (x * 11 + y * 7 + gen.seed) % 19 == 3:
                    materials[x, y] = ORES[k]
        for x in range(x0 - 1, x1 + 2):
            if rows[bottom + 1][x] == 'R':
                materials[x, bottom + 1] = 'ancient'
        return materials


def decorate(gen, rows):
    from tiles import SPRITES

    decorator = _Decorator(gen, rows, SPRITES)
    decorator.ladders()        # climbable props reserve their space first
    decorator.scenes()
    decorator.scatter()
    layout = decorator.layout
    x0, top, x1, bottom = gen.arena
    scenery = {
        'props': layout.props,
        'structures': layout.structures,
        'materials': decorator.materials(),
        'lights': [],
        'exit_door': gen.door,
        'bomb_spawns': list(gen.bomb_spots),
        # Authored pickups of the opening chamber are always placed.
        'bomb_fixed': list(gen.chamber['scenery'].get('bomb_spawns', ())) if gen.chamber else [],
        'chamber': gen.chamber_box,
        'chamber_gate': gen.chamber['scenery']['exit_door'] if gen.chamber else None,
        'bomb_count': DEEP_BOMB_PICKUPS,
        'depth_zones': depth_zones(gen.tops),
        'layers': {'tops': list(gen.tops), 'rows': gen.L, 'names': LAYER_NAMES},
        'boss_arena': gen.arena,
        'seed': gen.seed,
        'route': list(gen.route),
    }
    pools = [(x, y, w, h) for x, y, w, h, _ in gen.pools]
    protected = dict(gen.entities)
    protected['bombs'] = list(gen.bomb_spots)
    # Wall bumps at a step or drop could leave a gap narrower than the miner,
    # so the cell sculpting skips the route wherever its floor changes height.
    route = gen.route
    protected['route_steps'] = [
        route[n + d] for n in range(1, len(route))
        if route[n][1] != route[n - 1][1] for d in (-2, -1, 0, 1)
        if 0 <= n + d < len(route)]
    protected['shafts'] = [(column, y) for shaft in gen.shafts
                           for column in (shaft['x'], shaft['outer'])
                           for y in range(shaft['top'] - 1, shaft['bottom'] + 1)]
    if gen.chamber:
        for key, value in gen.chamber['scenery'].items():
            if key == 'enemy_spawn_offsets':
                scenery[key] = copy.deepcopy(value)
    areas = [gen.chamber_box] if gen.chamber_box else []
    scenery['sculpt'] = sculpt_caves(rows, scenery, protected, pools,
                                     boss_area=(x0 - 1, top - 1, x1 + 2, bottom + 1),
                                     areas=areas)
    return scenery

