"""Attached scenery made entirely from the supplied underground contact sheet.

All positions are in macro tiles. Decorations never change terrain or fluids.
The placement pass reserves the visible bodies of props, including the beams
of open frames, and records terrain anchors for the renderer after digging.
"""

from math import ceil, floor


_EPSILON = 1e-7


def _cells_in_box(box):
    x, y, w, h = box
    return [(xx, yy)
            for yy in range(floor(y + _EPSILON), ceil(y + h - _EPSILON))
            for xx in range(floor(x + _EPSILON), ceil(x + w - _EPSILON))]


def _overlap(a, b, margin=0.06):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (ax < bx + bw + margin and ax + aw + margin > bx and
            ay < by + bh + margin and ay + ah + margin > by)


class _Placement:
    def __init__(self, rows, sprites):
        self.rows, self.sprites = rows, sprites
        self.width, self.height = len(rows[0]), len(rows)
        self.props = []
        self.occupied = {'back': [], 'front': []}

    def solid(self, x, y):
        return (0 <= x < self.width and 0 <= y < self.height and
                self.rows[y][x] in '#R')

    def empty(self, x, y):
        return (0 <= x < self.width and 0 <= y < self.height and
                self.rows[y][x] == ' ')

    def open_column(self, x, cy):
        x, cy = floor(x), floor(cy)
        if not self.empty(x, cy):
            return None
        top = bottom = cy
        while self.empty(x, top - 1):
            top -= 1
        while self.empty(x, bottom + 1):
            bottom += 1
        return top, bottom + 1

    def size(self, name, w, h):
        """Fit the original aspect ratio inside a requested size."""
        _, _, source_w, source_h = self.sprites[name]['rect']
        scale = min(w / source_w, h / source_h)
        return source_w * scale, source_h * scale

    @staticmethod
    def bodies(name, box):
        x, y, w, h = box
        if name in ('mine_frame', 'mine_tall_frame'):
            post, beam = w * 0.15, h * 0.09
            parts = [(x, y, post, h), (x + w - post, y, post, h),
                     (x, y, w, beam), (x, y + h * 0.54, w, beam)]
            if name == 'mine_tall_frame':
                parts.append((x, y + h * 0.82, w, beam))
            return parts
        if name in ('ruin_arch', 'dungeon_arch'):
            return [(x, y, w * 0.22, h), (x + w * 0.78, y, w * 0.22, h),
                    (x + w * 0.22, y, w * 0.56, h * 0.38)]
        return [box]

    def place(self, name, box, support_cells, attachment, layer='front',
              opacity=255, glow=None, flip=False, **metadata):
        # A transparent sprite still needs its entire drawing area in the cave.
        if not all(self.empty(x, y) for x, y in _cells_in_box(box)):
            return None
        if not support_cells or not all(self.solid(x, y) for x, y in support_cells):
            return None
        bodies = self.bodies(name, box)
        if any(_overlap(body, other) for body in bodies
               for other in self.occupied[layer]):
            return None
        x, y, w, h = box
        prop = dict(name=name, x=x, y=y, w=w, h=h, layer=layer,
                    opacity=opacity, flip=flip, attachment=attachment,
                    support=support_cells[0], support_cells=support_cells,
                    support_mode='all', occupancy_rects=bodies, **metadata)
        if glow:
            prop['glow'] = glow
        self.props.append(prop)
        self.occupied[layer].extend(bodies)
        return prop

    def floor(self, name, x, cy, w=1, h=1, glow=None, flip=False,
              layer='front', opacity=255, search=1.5):
        w, h = self.size(name, w, h)
        for offset in self.offsets(search):
            center = x + 0.5 + offset
            span = self.open_column(center, cy)
            if not span:
                continue
            top, bottom = span
            if h > bottom - top:
                continue
            left = center - w / 2
            anchors = [(xx, bottom) for xx in
                       range(floor(left + _EPSILON), ceil(left + w - _EPSILON))]
            prop = self.place(name, (left, bottom - h, w, h), anchors, 'floor',
                              layer, opacity, glow, flip)
            if prop:
                return prop
        return None

    def ceiling(self, name, x, cy, w=1, h=1, glow=None, flip=False,
                layer='front', opacity=255, search=1.5):
        w, h = self.size(name, w, h)
        for offset in self.offsets(search):
            center = x + 0.5 + offset
            span = self.open_column(center, cy)
            if not span:
                continue
            top, bottom = span
            if h > bottom - top:
                continue
            left = center - w / 2
            anchors = [(xx, top - 1) for xx in
                       range(floor(left + _EPSILON), ceil(left + w - _EPSILON))]
            prop = self.place(name, (left, top, w, h), anchors, 'ceiling',
                              layer, opacity, glow, flip)
            if prop:
                return prop
        return None

    def wall(self, name, x, cy, w=1, h=1, side='left', glow=None,
             layer='front', opacity=255, search=1.0):
        w, h = self.size(name, w, h)
        direction = -1 if side == 'left' else 1
        for offset in self.offsets(search):
            middle = cy + 0.5 + offset
            tx, ty = floor(x), floor(middle)
            if not self.empty(tx, ty):
                continue
            while self.empty(tx + direction, ty):
                tx += direction
            wall_x = tx + direction
            left = wall_x + 1 if side == 'left' else wall_x - w
            top = middle - h / 2
            anchors = [(wall_x, yy) for yy in
                       range(floor(top + _EPSILON), ceil(top + h - _EPSILON))]
            prop = self.place(name, (left, top, w, h), anchors,
                              'wall_' + side, layer, opacity, glow,
                              flip=side == 'right')
            if prop:
                return prop
        return None

    def ladder(self, x, cy, width=0.85):
        """A floor anchored climb area; repeat the original ladder vertically."""
        span = self.open_column(x + 0.5, cy)
        if not span:
            return None
        top, bottom = span
        left = x + 0.5 - width / 2
        anchors = [(xx, bottom) for xx in
                   range(floor(left + _EPSILON), ceil(left + width - _EPSILON))]
        _, _, source_w, source_h = self.sprites['ladder']['rect']
        return self.place('ladder', (left, top, width, bottom - top), anchors,
                          'floor', layer='back', opacity=220, repeat_y=True,
                          segment_h=width * source_h / source_w)

    @staticmethod
    def offsets(distance):
        yield 0
        for step in range(1, floor(distance * 2) + 1):
            yield step * 0.5
            yield -step * 0.5


def build_scenery(rows, water_pools, lava_pools):
    # Lazy import avoids the level -> scenery -> tiles -> level import cycle.
    from tiles import SPRITES

    layout = _Placement(rows, SPRITES)
    materials, lights = {}, []
    width, height = layout.width, layout.height
    floor_prop, ceiling, wall = layout.floor, layout.ceiling, layout.wall

    def paint(x, y, material):
        if layout.solid(x, y):
            materials[x, y] = material

    def rim(cx, cy, rx, ry, material):
        for y in range(max(1, cy - ry), min(height - 1, cy + ry + 1)):
            for x in range(max(1, cx - rx), min(width - 1, cx + rx + 1)):
                if layout.solid(x, y) and any(layout.empty(nx, ny) for nx, ny in
                        ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
                    paint(x, y, material)

    def ores(cx, cy, rx, ry, material):
        for y in range(max(1, cy - ry), min(height - 1, cy + ry + 1)):
            for x in range(max(1, cx - rx), min(width - 1, cx + rx + 1)):
                if (x * 11 + y * 7) % 17 == 3 and layout.solid(x, y) and any(
                        layout.empty(nx, ny) for nx, ny in
                        ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
                    paint(x, y, material)

    warm = (2.6, (255, 169, 65))
    blue = (2.8, (64, 147, 255))
    purple = (2.8, (178, 86, 247))
    red = (2.6, (255, 91, 38))

    # Place climbable structures before ornamental architecture reserves space.
    # The arena ladder reaches the diggable roof below the overhead reservoir.
    layout.ladder(98, 85, width=0.85)
    layout.ladder(5, 7, width=0.75)
    layout.ladder(101, 18, width=0.7)

    # B1: old human mine and storage pockets. Wooden support bays are in the
    # distance, while crates, tools and stones sit against the actual ground.
    mine_rooms = [(10, 7), (40, 12), (77, 9), (103, 18)]
    for index, (cx, cy) in enumerate(mine_rooms):
        rim(cx, cy, 10, 6, 'dirt')
        ores(cx, cy, 11, 6, 'ore_gold')
        frame = 'mine_tall_frame' if index == 0 else 'mine_frame'
        floor_prop(frame, cx - 3, cy, 3.8, 6 if index == 0 else 3.9,
                   layer='back', opacity=205)
        if index == 0:
            floor_prop('mine_frame', cx + 4, cy, 2.4, 3.0,
                       layer='back', opacity=185, search=0.5)
        floor_prop('cart' if index != 3 else 'broken_cart',
                   cx + 1 if index == 0 else cx - 2, cy, 1.7, 1.3)
        floor_prop('crate', cx + 3, cy, 1.0, 1.2)
        floor_prop('barrel', cx + 5, cy, 0.85, 1.15)
        floor_prop('sack', cx + 1.5, cy, 0.65, 0.8)
        floor_prop('toolbox', cx - 5, cy, 1.0, 0.7)
        floor_prop('rock_pile', cx + 6, cy, 1.1, 0.65)
        ceiling('hanging_lantern', cx - 1, cy, 0.65, 1.3, warm)
        ceiling('cobweb', cx + 4, cy, 1.25, 1.3)
        wall('lantern', cx, cy, 0.6, 1.2, side='right', glow=warm)
        # Rail pieces belong behind the cart and do not hide its wheels.
        for offset in (-4, -1, 2):
            floor_prop('mine_rail', cx + offset, cy, 2.5, 0.5,
                       layer='back', opacity=225, search=0.5)
        if index == 0:
            floor_prop('mine_rail', cx + 1, cy, 2.5, 0.5,
                       layer='back', opacity=225, search=0.5)
    for cx, cy in [(28, 5), (69, 20)]:
        floor_prop('small_crate', cx - 1, cy, 0.8, 1.0)
        floor_prop('old_chest', cx + 1, cy, 1.2, 0.8)
        floor_prop('small_rocks', cx + 2, cy, 0.6, 0.5)
        ceiling('lantern', cx, cy, 0.55, 1.0, warm)
        ceiling('cobweb', cx + 1, cy, 0.9, 1.0)
        ores(cx, cy, 5, 3, 'ore_gold')

    # B2: earthen caves reclaim the abandoned excavation. No rail galleries;
    # vegetation hangs from roofs and mineral formations emerge from floors.
    natural_rooms = [(101, 30), (66, 37), (30, 43), (12, 32), (102, 44),
                     (110, 36), (66, 29), (36, 33), (10, 46), (53, 47)]
    for index, (cx, cy) in enumerate(natural_rooms):
        rim(cx, cy, 12 if index < 5 else 7, 5, 'dirt')
        floor_prop('dirt_stalagmite', cx - 3, cy, 1.3, 1.5)
        ceiling('dirt_stalactite', cx + 3, cy, 1.4, 1.6)
        ceiling('thin_stalactite', cx - 4, cy, 0.45, 1.15)
        ceiling('vines' if index % 3 == 0 else 'moss_vines', cx + 1, cy, 1.5, 1.6)
        floor_prop('purple_mushroom' if index % 3 == 1 else 'red_mushroom',
                   cx - 1, cy, 0.8, 0.85)
        floor_prop('blue_mushroom', cx + 2, cy, 0.55, 0.65)
        floor_prop('fern', cx + 4, cy, 0.9, 0.8)
        floor_prop('gray_rubble', cx - 5, cy, 1.0, 0.55)
        floor_prop('small_plants', cx + 5, cy, 0.65, 0.8)
        ores(cx, cy, 10, 5, 'ore_gold')
    # Small wall-attached roots give the plain gallery ends a cave silhouette.
    for cx, cy in [(101, 30), (66, 37), (30, 43), (12, 32), (102, 44)]:
        wall('dry_roots', cx, cy, 0.5, 0.9, side='left')
        wall('short_vines', cx, cy - 1, 1.0, 1.2, side='right')

    # B3: crystal grottos. Large facets are deliberate landmarks, with smaller
    # shards and pale stone formations nearby; ancient buildings start in B4.
    crystal_rooms = [(22, 57), (59, 60), (99, 56), (92, 70),
                     (36, 55), (78, 68), (10, 69), (46, 69)]
    for index, (cx, cy) in enumerate(crystal_rooms):
        focal = 'blue_crystal' if index % 2 == 0 else 'purple_crystal'
        light = blue if index % 2 == 0 else purple
        rim(cx, cy, 15 if index < 4 else 7, 8, 'deep')
        ores(cx, cy, 14 if index < 4 else 7, 7, 'ore_blue')
        floor_prop(focal, cx, cy, 1.85, 2.2, light)
        floor_prop('small_purple_crystal', cx + 3, cy, 0.7, 1.0, purple)
        floor_prop('tiny_purple_cluster', cx - 2, cy, 0.65, 0.7)
        floor_prop('stone_stalagmite', cx - 4, cy, 1.1, 1.4)
        floor_prop('small_stalagmite', cx + 5, cy, 0.65, 1.0)
        # Main chamber formations hang well into the room, remaining visible
        # when the camera follows a player down to the lowest crystal ledge.
        ceiling('stone_stalactite', cx, cy,
                3.7 if index < 3 else 1.35,
                4.4 if index < 3 else 1.6)
        if index < 3:
            ceiling('thin_stalactite', cx - 4, cy, 0.65, 2.2)
            ceiling('moss_vines', cx - 6, cy, 2.0, 2.7)
        ceiling('small_stalactite', cx + 4, cy, 0.65, 1.4)
        ceiling('short_vines', cx + 1, cy, 1.15, 1.3)
        floor_prop('gray_rubble', cx - 5, cy, 0.8, 0.55)
        floor_prop('blue_mushroom', cx + 2, cy, 0.6, 0.65)
    floor_prop('large_mushroom', 10, 69, 1.4, 1.7)
    floor_prop('gold_chest', 48, 69, 1.0, 0.7)

    # B4: scorched chambers and weathered ruins. The source's red crystals,
    # embers, bones and dead roots replace green growth in these pockets.
    for index, (cx, cy) in enumerate([(21, 82), (47, 84), (62, 78), (54, 95)]):
        rim(cx, cy, 12, 7, 'volcanic')
        ores(cx, cy, 12, 7, 'ore_red')
        if index < 2:
            floor_prop('ruin_arch', cx, cy, 3.0, 2.1,
                       layer='back', opacity=135, search=2.5)
            floor_prop('broken_pillar', cx - 5, cy, 0.85, 1.8,
                       layer='back', opacity=175)
        floor_prop('red_crystal', cx, cy, 1.4, 1.7, red)
        floor_prop('ember_rocks', cx + 2, cy, 1.0, 1.0, red)
        floor_prop('small_red_crystal', cx + 3, cy, 0.65, 0.8, red)
        floor_prop('volcanic_rubble', cx - 2, cy, 0.9, 0.7)
        floor_prop('ribs', cx - 3, cy, 0.7, 0.7)
        floor_prop('stone_stalagmite', cx - 4, cy, 1.25, 1.65)
        ceiling('stone_stalactite', cx - 1, cy, 1.35, 1.7)
        ceiling('small_stalactite', cx + 3, cy, 0.6, 1.3)
        ceiling('dead_vines', cx + 2, cy, 1.0, 1.1)
        wall('torch', cx, cy, 0.45, 1.6, side='left', glow=warm)

    # A restrained entrance, then the arena's side monuments and platform
    # braziers. The central combat area and the roof ladder remain readable.
    rim(67, 87, 7, 4, 'ancient')
    floor_prop('dungeon_arch', 69, 87, 2.8, 3.4,
               layer='back', opacity=160)
    floor_prop('torch', 63, 87, 0.5, 1.8, warm)
    floor_prop('torch', 71, 87, 0.5, 1.8, warm)
    floor_prop('skull', 65, 87, 0.6, 0.75)
    floor_prop('bones', 67, 87, 1.0, 0.65)
    ceiling('chain', 64, 87, 0.35, 1.6)
    ceiling('banner', 70, 87, 0.9, 1.55)
    wall('hanging_bones', 67, 87, 0.8, 0.9, side='right')

    for y in range(77, min(height, 98)):
        paint(76, y, 'ancient')
        paint(118, y, 'ancient')
    for x in range(77, min(width, 118)):
        paint(x, 97, 'ancient' if 91 <= x <= 104 else 'volcanic')
    for x in range(82, 92):
        paint(x, 92, 'ancient')
    for x in range(101, 112):
        paint(x, 87, 'ancient')
    floor_prop('dungeon_arch', 85, 90, 5.0, 6.1,
               layer='back', opacity=105)
    floor_prop('dungeon_column', 79, 94, 1.4, 3.8,
               layer='back', opacity=135)
    floor_prop('stone_column', 114, 94, 1.2, 2.2,
               layer='back', opacity=145)
    for x in (80, 90, 113):
        ceiling('chain', x, 82, 0.35, 2.4)
    ceiling('banner', 82, 82, 1.1, 2.0)
    ceiling('banner', 115, 82, 1.1, 2.0)
    ceiling('stone_stalactite', 105, 82, 1.8, 2.1)
    ceiling('small_stalactite', 111, 82, 0.75, 1.9)
    floor_prop('torch', 83, 90, 0.65, 2.2, warm)
    floor_prop('torch', 90, 90, 0.65, 2.2, warm)
    floor_prop('torch', 103, 85, 0.65, 2.2, warm)
    floor_prop('red_crystal', 79, 94, 1.5, 1.9, red)
    floor_prop('bones', 81, 95, 1.0, 0.65)
    floor_prop('broken_pillar', 106, 91, 0.9, 1.6,
               layer='back', opacity=155)
    floor_prop('small_skull', 116, 94, 0.6, 0.8)
    floor_prop('volcanic_rubble', 105, 95, 1.0, 0.8)
    wall('torch', 98, 84, 0.6, 2.0, side='left', glow=warm)

    # Wet/scorched rims are overlays on solid geology. Pool coordinates and
    # tile kinds remain untouched, so simulation and contacts are preserved.
    for pools, wet in ((water_pools, True), (lava_pools, False)):
        for x, y, w, h in pools:
            for yy in range(y - 2, y + h + 2):
                for xx in range(x - 2, x + w + 2):
                    if layout.solid(xx, yy):
                        if wet:
                            style = 'moss' if yy < y else ('sand' if yy >= y + h else 'mud')
                        else:
                            style = 'mixed' if (xx + yy) % 3 else 'volcanic'
                        materials.setdefault((xx, yy), style)
            lights.append(dict(x=x + w / 2, y=y + h / 2,
                               radius=2.4 if wet else 4.5,
                               color=(38, 98, 164) if wet else (255, 93, 30),
                               fluid='W' if wet else 'L'))

    return dict(props=layout.props, materials=materials, lights=lights)
