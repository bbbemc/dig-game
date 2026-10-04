"""Hand-placed decoration clusters. These records never change the level grid."""

def build_scenery(rows, water_pools, lava_pools):
    props, materials, lights = [], {}, []
    width, height = len(rows[0]), len(rows)

    def solid(x, y):
        return 0 <= x < width and 0 <= y < height and rows[y][x] in '#R'

    def paint(x, y, material):
        if solid(x, y):
            materials[x, y] = material

    def open_column(x, cy):
        x, cy = int(x), int(cy)
        if not 0 < x < width - 1 or rows[cy][x] != ' ':
            return None
        top = bottom = cy
        while top > 0 and rows[top - 1][x] == ' ':
            top -= 1
        while bottom < height - 1 and rows[bottom + 1][x] == ' ':
            bottom += 1
        return top, bottom + 1

    def place(name, x, y, w, h, layer='front', opacity=255, support=None,
              attachment=None, glow=None, flip=False):
        if name in {'broken_pillar', 'ruin_pillar', 'ruin_wall'} and layer == 'front':
            layer, opacity = 'back', 140
        prop = dict(name=name, x=x, y=y, w=w, h=h, layer=layer,
                    opacity=opacity, support=support, attachment=attachment, flip=flip)
        props.append(prop)
        if glow:
            prop['glow'] = glow

    def floor(name, x, cy, w=1, h=1, glow=None, flip=False):
        span = open_column(x, cy)
        if not span:
            return
        top, bottom = span
        if not solid(int(x), bottom):
            return
        h = min(h, bottom - top - 0.15)
        if h > 0:
            place(name, x - w / 2 + 0.5, bottom - h, w, h,
                  support=(int(x), bottom), attachment='floor', glow=glow, flip=flip)

    def ceiling(name, x, cy, w=1, h=1, glow=None, flip=False):
        span = open_column(x, cy)
        if not span:
            return
        top, bottom = span
        if not solid(int(x), top - 1):
            return
        h = min(h, bottom - top - 0.15)
        if h > 0:
            place(name, x - w / 2 + 0.5, top, w, h,
                  support=(int(x), top - 1), attachment='ceiling', glow=glow, flip=flip)

    def rim(cx, cy, rx, ry, material):
        for y in range(max(1, cy - ry), min(height - 1, cy + ry + 1)):
            for x in range(max(1, cx - rx), min(width - 1, cx + rx + 1)):
                if solid(x, y) and any(rows[ny][nx] == ' ' for nx, ny in
                                       ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
                    paint(x, y, material)

    def ores(cx, cy, rx, ry, material):
        # Only small patches on the solid cave rim; positions are reproducible.
        for y in range(max(1, cy - ry), min(height - 1, cy + ry + 1)):
            for x in range(max(1, cx - rx), min(width - 1, cx + rx + 1)):
                if solid(x, y) and (x * 11 + y * 7) % 17 == 3 and any(
                        rows[ny][nx] == ' ' for nx, ny in
                        ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))):
                    paint(x, y, material)

    warm = (3, (255, 170, 65))
    blue = (3, (64, 147, 255))
    purple = (3, (178, 86, 247))
    red = (3, (255, 91, 38))

    # B1 prison: masonry surrounds the existing solid walls, with a faded
    # barred window on the distant wall and props grouped beside the exits.
    rim(10, 7, 8, 5, 'dungeon')
    place('prison_window', 13, 4.6, 2.6, 2.1, 'back', 115)
    place('dungeon_column', 5.1, 4.1, 1.2, 6.8, 'back', 115)
    place('dungeon_column', 15.3, 4.1, 1.2, 6.8, 'back', 115)
    place('brick_2', 6.5, 5.5, 2, 2, 'back', 48)
    place('broken_bricks', 12, 8.2, 1.4, 1.4, 'back', 95)
    floor('mine_frame', 8, 7, 3.4, 4.1)
    floor('crate', 6, 7, 1.15, 1.35)
    floor('barrel', 7.3, 7, 0.9, 1.2)
    floor('sack', 8.4, 7, 0.6, 0.8)
    floor('wood_crate', 15, 7, 1.1, 1.2)
    floor('rock_pile', 13.5, 7, 1.1, 0.65)
    floor('torch', 14.6, 7, 0.5, 1.8, warm)
    ceiling('hanging_lantern', 8, 7, 0.65, 1.3, warm)
    ceiling('cobweb', 15, 7, 1.6, 1.4)
    for cx, cy in [(40, 12), (77, 9)]:
        floor('small_rocks', cx - 4, cy, 1, 0.7)
        floor('fern', cx + 2, cy, 1.1, 0.8)
        floor('red_mushroom', cx - 1, cy, 0.65, 0.8)
        floor('rock_pile', cx + 4, cy, 1.1, 0.7)
        ceiling('short_vines', cx - 3, cy, 1.5, 1.5)
        ores(cx, cy, 11, 5, 'ore_gold')
    floor('dirt_stalagmite', 44, 12, 0.95, 1.15)
    floor('broken_support', 101, 18, 2.8, 2)
    floor('small_crate', 104, 18, 0.9, 1)
    floor('small_skull', 106, 18, 0.55, 0.6)
    floor('small_rocks', 99, 18, 1, 0.7)
    ceiling('lantern', 102, 18, 0.65, 1.2, warm)
    for cx, cy in [(28, 5), (69, 20)]:
        for offset in (-1, 0, 1):
            span = open_column(cx + offset, cy)
            if span:
                paint(cx + offset, span[1], 'surface')
        floor('small_flower', cx - 1, cy, 0.9, 1)
        floor('small_plants', cx + 1, cy, 0.9, 1)
        floor('small_rocks', cx + 2, cy, 0.7, 0.5)

    # B2: supports every 10-11 tiles, real rail segments, hanging lights,
    # ladders and workspaces. All frames are open, non-colliding decorations.
    galleries = [(88, 115, 30), (54, 79, 37), (18, 43, 43),
                 (5, 20, 32), (97, 107, 44)]
    for index, (left, right, cy) in enumerate(galleries):
        for x in range(left + 3, right - 1, 11):
            floor('mine_frame', x, cy, 3.4, 4)
            ceiling('hanging_lantern', x + 1, cy, 0.6, 1.25, warm)
        for x in range(left + 1, right, 3):
            floor('mine_rail', x, cy, 3, 0.5)
        workspace = left + 5
        floor('cart' if index != 3 else 'broken_cart', workspace, cy, 1.7, 1.3)
        floor('crate', workspace + 2, cy, 1, 1.2)
        floor('barrel', right - 3, cy, 0.85, 1.1)
        floor('large_sack', right - 4, cy, 0.65, 0.85)
        floor('gray_rubble', left + 1, cy, 1.2, 0.6)
        floor('red_mushroom', right - 1, cy, 0.65, 0.8)
        ceiling('cobweb', right - 2, cy, 1.2, 1.1)
        floor('ladder', left + 9, cy, 0.8, 3.8)
        ores((left + right) // 2, cy, (right - left) // 2 + 2, 4, 'ore_gold')
    for cx, cy in [(110, 36), (66, 29), (36, 33), (10, 46), (53, 47)]:
        floor('purple_mushroom', cx - 1, cy, 1.1, 1.2)
        floor('red_mushroom', cx + 2, cy, 0.7, 0.85)
        floor('blue_mushroom', cx + 1, cy, 0.65, 0.7)
        floor('gray_rubble', cx - 3, cy, 1.1, 0.55)
        ceiling('moss_vines', cx, cy, 1.6, 1.5)
        ceiling('thin_stalactite', cx + 2, cy, 0.55, 1.3)
        ores(cx, cy, 7, 4, 'ore_blue')
    floor('blue_crystal', 65, 29, 1, 1.3, blue)
    floor('blue_crystal', 111, 36, 0.95, 1.2, blue)
    floor('blue_crystal', 35, 33, 1, 1.3, blue)
    floor('ore_blue', 37, 33, 0.8, 0.9)
    floor('old_chest', 10, 46, 1.3, 0.85)
    floor('toolbox', 53, 47, 1, 0.75)

    # B3: natural chambers and rare, larger crystal landmarks.
    for index, (cx, cy) in enumerate([(22, 57), (59, 60), (99, 56), (92, 70)]):
        focal = 'red_crystal' if index == 3 else ('blue_crystal' if index % 2 == 0 else 'purple_crystal')
        light = red if index == 3 else (blue if index % 2 == 0 else purple)
        floor(focal, cx, cy, 1.8, 2.2, light)
        floor('small_purple_crystal', cx + 3, cy, 0.75, 1, purple)
        floor('tiny_purple_cluster', cx - 3, cy, 0.65, 0.65)
        ceiling('stone_stalactite', cx - 5, cy, 1.5, 1.9)
        ceiling('small_stalactite', cx + 4, cy, 0.65, 1.4)
        floor('stone_stalagmite', cx - 4, cy, 1.1, 1.3)
        floor('small_stalagmite', cx + 5, cy, 0.7, 1)
        floor('bones', cx + 2, cy, 1, 0.65)
        floor('purple_mushroom', cx - 6, cy, 0.8, 0.9)
        ceiling('short_vines', cx + 1, cy, 1.5, 1.6)
        floor('gray_rubble', cx + 6, cy, 1, 0.55)
        ores(cx, cy, 15, 8, 'ore_blue')
    # Architecture on the distant wall belongs to the cave backdrop and does
    # not imply an obstacle in the playable foreground.
    place('ruin_arch', 54, 56.4, 5, 3.8, 'back', 100)
    place('ruin_wall', 62, 57.5, 2, 2.6, 'back', 80)
    place('ruin_rubble', 20, 54.8, 1.6, 1.8, 'back', 70)
    for cx, cy in [(35, 55), (77, 68)]:
        rim(cx, cy, 7, 5, 'ancient')
        place('ruin_arch', cx - 2.5, cy - 2, 5, 3.8, 'back', 130)
        floor('broken_pillar', cx - 2, cy, 0.85, 2.3)
        floor('broken_pot', cx + 2, cy, 0.9, 1.2)
        floor('purple_crystal', cx, cy, 1.3, 1.6, purple)
        floor('ribs', cx + 1, cy, 0.8, 0.65)
        ceiling('banner', cx - 1, cy, 0.9, 1.65)
        ceiling('cobweb', cx + 2, cy, 1.3, 1.3)
        floor('torch', cx - 3, cy, 0.45, 1.7, warm)
    for cx, cy in [(10, 69), (46, 69)]:
        floor('large_mushroom', cx, cy, 1.5, 1.7)
        floor('small_purple_crystal', cx + 2, cy, 0.7, 0.9)
        floor('bones', cx - 2, cy, 0.8, 0.6)
        ceiling('vines', cx - 1, cy, 1.9, 2)
        ceiling('dirt_stalactite', cx + 1, cy, 1.1, 1.5)
    floor('gold_chest', 46, 69, 1, 0.7)

    # B4: volcanic formations, ember crystals and dry ruins; no green plants.
    for cx, cy in [(21, 82), (47, 84), (62, 78), (54, 95)]:
        floor('red_crystal', cx, cy, 1.3, 1.6, red)
        floor('ember_rocks', cx + 2, cy, 1.1, 1.1)
        floor('volcanic_rubble', cx - 2, cy, 0.9, 0.7)
        floor('small_red_crystal', cx + 3, cy, 0.65, 0.8, red)
        floor('ribs', cx - 3, cy, 0.8, 0.65)
        floor('stone_stalagmite', cx - 4, cy, 1.3, 1.7)
        ceiling('stone_stalactite', cx - 1, cy, 1.4, 1.8)
        ceiling('small_stalactite', cx + 3, cy, 0.6, 1.3)
        ceiling('dead_vines', cx + 2, cy, 1.1, 1.1)
        ores(cx, cy, 12, 7, 'ore_red')
    place('ruin_arch', 43, 81, 5, 4, 'back', 105)
    rim(47, 84, 11, 6, 'mixed')

    # Boss approach: quiet ceremonial masonry with two fires and hanging chains.
    rim(67, 87, 7, 4, 'dungeon')
    place('dungeon_arch', 68.5, 86, 2.9, 3.8, 'back', 105)
    floor('torch', 63, 87, 0.5, 2.2, warm)
    floor('torch', 71, 87, 0.5, 2.2, warm)
    floor('skull', 65, 87, 0.65, 0.8)
    floor('bones', 67, 87, 1, 0.65)
    ceiling('chain', 64, 87, 0.35, 1.9)
    ceiling('banner', 70, 87, 1, 2.2)
    ceiling('hanging_bones', 66, 87, 1.1, 1.3)

    # Boss arena: background monuments and edge props leave the central arena clear.
    for y in range(78, 97):
        paint(76, y, 'ancient')
        paint(118, y, 'ancient')
    for x in range(77, 118):
        paint(x, 97, 'ancient' if 91 <= x <= 104 else 'volcanic')
    for x in range(82, 92):
        paint(x, 92, 'ancient')
    for x in range(101, 112):
        paint(x, 87, 'ancient')
    place('dungeon_arch', 94.5, 84.5, 7, 11.5, 'back', 78)
    place('stone_column', 79, 80, 2.1, 10, 'back', 92)
    place('stone_column', 114, 80, 2.1, 10, 'back', 92)
    for x in (80, 90, 113):
        ceiling('chain', x, 82, 0.5, 4)
    ceiling('banner', 82, 82, 1.3, 3)
    ceiling('banner', 115, 82, 1.3, 3)
    ceiling('stone_stalactite', 105, 82, 2, 2.5)
    ceiling('small_stalactite', 111, 82, 0.85, 2)
    floor('torch', 83, 90, 0.65, 2.5, warm)
    floor('torch', 90, 90, 0.65, 2.5, warm)
    floor('torch', 103, 85, 0.65, 2.5, warm)
    floor('red_crystal', 79, 94, 1.7, 2.1, red)
    floor('bones', 81, 95, 1.2, 0.7)
    floor('broken_pillar', 106, 91, 1.1, 2.6)
    floor('small_skull', 116, 94, 0.7, 0.8)
    floor('volcanic_rubble', 105, 95, 1.2, 0.8)

    # Reservoir geology: wet dirt/moss/gravel, and scorched stone around lava.
    # This is a visual overlay on existing solid tiles, never a fluid/collision edit.
    for pools, wet in ((water_pools, True), (lava_pools, False)):
        for x, y, w, h in pools:
            for yy in range(y - 2, y + h + 2):
                for xx in range(x - 2, x + w + 2):
                    if solid(xx, yy):
                        if wet:
                            style = 'moss' if yy < y else ('sand' if yy >= y + h else 'mud')
                        else:
                            style = 'mixed' if (xx + yy) % 3 else 'volcanic'
                        # Preserve architectural borders and boss platforms.
                        materials.setdefault((xx, yy), style)
            if not wet:
                lights.append(dict(x=x + w / 2, y=y + h / 2, radius=4.5,
                                   color=(255, 93, 30), fluid='L'))
            else:
                lights.append(dict(x=x + w / 2, y=y + h / 2, radius=2.4,
                                   color=(38, 98, 164), fluid='W'))
    # A few selected red ore seams remain focal points even where scorched
    # materials or ruin facings cover the surrounding wall.
    for cx, cy in [(21, 82), (47, 84), (62, 78), (54, 95)]:
        for x in (cx - 3, cx + 3):
            span = open_column(x, cy)
            if span:
                paint(x, span[0] - 1, 'ore_red')
    return dict(props=props, materials=materials, lights=lights)
