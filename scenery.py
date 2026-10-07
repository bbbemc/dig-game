"""Attached scenery from the supplied contact sheet, grouped into small scenes.

All positions are in macro tiles. Decorations never change terrain or fluids.
The placement pass reserves the visible bodies of props, including the beams
of open frames, and records terrain anchors for the renderer after digging.

Mine timber is assembled from pieces of the sheet's frames ("structures"):
uprights stand on the floor, cap beams sit under the ceiling, braces fill the
corners and lanterns hang from beams on chains, so supports read as built
rather than floating. B1 rooms are staged as scenes - a worked face at the
start, an abandoned workstation, a storage room, a collapsed tunnel and two
small stashes - so the mine looks as if people once worked in it.
"""

from math import ceil, floor


_EPSILON = 1e-7
BEAM, THIN, POST = 0.375, 0.275, 0.35
FOOT = (0.42, 0.4)
TIMBER = {'post', 'beam', 'thin_beam', 'foot', 'stub', 'chain'}


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


def _piece(kind, x, y, w, h, **extra):
    return dict(kind=kind, x=x, y=y, w=w, h=h, **extra)


def _uprights(left, right, top, bottom):
    """Two posts (outer edges ``left``/``right``) with feet on the floor."""
    pieces = []
    for x in (left, right - POST):
        pieces.append(_piece('post', x, top, POST, bottom - top))
        pieces.append(_piece('foot', x + POST / 2 - FOOT[0] / 2, bottom - FOOT[1], *FOOT))
    return pieces


def _beam(left, right, y, kind='beam', overhang=0.12):
    return _piece(kind, left - overhang, y, right - left + 2 * overhang,
                  BEAM if kind == 'beam' else THIN)


def _braces(left, right, y, size=0.7):
    """Corner braces from both uprights up to the beam whose underside is y."""
    size = min(size, (right - left - 2 * POST) / 2.4)
    return [_piece('brace', left + POST, y, size, size, rising=True),
            _piece('brace', right - POST - size, y, size, size, rising=False)]


def _hung_lamp(x, beam_bottom, chain=0.4):
    """Chain links and a lantern under a beam, plus the matching light."""
    w, h = 0.62, 1.2
    return ([_piece('chain', x - 0.11, beam_bottom, 0.22, chain),
             _piece('sprite', x - w / 2, beam_bottom + chain, w, h, name='hanging_lantern')],
            {'x': x, 'y': beam_bottom + chain + h * 0.7})


def _post_anchors(left, right, bottom):
    return [(floor(left + POST / 2), round(bottom), 'floor'),
            (floor(right - POST / 2), round(bottom), 'floor')]


def _feet_shadows(left, right):
    return [(left - 0.12, POST + 0.24), (right - POST - 0.12, POST + 0.24)]


class _Placement:
    def __init__(self, rows, sprites):
        self.rows, self.sprites = rows, sprites
        self.width, self.height = len(rows[0]), len(rows)
        self.props = []
        self.structures = []
        self.occupied = {'far': [], 'back': [], 'front': [], 'fore': []}

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
              layer='front', opacity=255, search=1.5, lift=0.0):
        """Stand a prop on the floor; ``lift`` raises it onto e.g. a rail."""
        w, h = self.size(name, w, h)
        for offset in self.offsets(search):
            center = x + 0.5 + offset
            span = self.open_column(center, cy)
            if not span:
                continue
            top, bottom = span
            if h + lift > bottom - top:
                continue
            left = center - w / 2
            anchors = [(xx, bottom) for xx in
                       range(floor(left + _EPSILON), ceil(left + w - _EPSILON))]
            prop = self.place(name, (left, bottom - h - lift, w, h), anchors, 'floor',
                              layer, opacity, glow, flip)
            if prop:
                return prop
        return None

    def ceiling(self, name, x, cy, w=1, h=1, glow=None, flip=False,
                layer='front', opacity=255, search=1.5, shade=255):
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
            extra = {'shade': shade} if shade != 255 else {}
            prop = self.place(name, (left, top, w, h), anchors, 'ceiling',
                              layer, opacity, glow, flip, **extra)
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

    def structure(self, pieces, anchors, layer='back', lamps=(), contact=(), shade=255):
        """Composite timber or a staged group of sprites drawn as one image.

        Every piece must lie in open cave and every ``(x, y, attachment)``
        anchor must be solid; the whole group disappears if one is dug away.
        Timber pieces reserve space against later items in the same layer.
        """
        boxes = [(p['x'], p['y'], p['w'], p['h']) for p in pieces]
        if not all(self.empty(x, y) for box in boxes for x, y in _cells_in_box(box)):
            return None
        if not anchors or not all(self.solid(mx, my) for mx, my, _ in anchors):
            return None
        bodies = [box for box, piece in zip(boxes, pieces)
                  if piece['kind'] in TIMBER or piece['kind'] == 'sprite']
        if any(_overlap(body, other) for body in bodies for other in self.occupied[layer]):
            return None
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes)
        y1 = max(b[1] + b[3] for b in boxes)
        item = dict(name='structure', x=x0, y=y0, w=x1 - x0, h=y1 - y0, layer=layer,
                    pieces=list(pieces), anchors=list(anchors), attachment=anchors[0][2],
                    lamps=list(lamps), contact_shadow=list(contact), shade=shade,
                    occupancy_rects=bodies)
        self.structures.append(item)
        self.occupied[layer].extend(bodies)
        return item

    def floor_level(self, left, right, cy):
        """(ceiling, floor) of an open span with a level floor, else None."""
        columns = [self.open_column(x + 0.5, cy) for x in range(floor(left), ceil(right))]
        if not columns or None in columns or len({c[1] for c in columns}) != 1:
            return None
        return max(c[0] for c in columns), columns[0][1]

    def mine_set(self, left, right, cy, layer='back', lamp=None, platform=None,
                 shade=255, braces=True, low_beam=False):
        """A timber set: uprights on the floor and a cap beam under the roof."""
        level = self.floor_level(left - 0.12, right + 0.12, cy)
        if not level or level[1] - level[0] < 2:
            return None
        top, bottom = level
        pieces = _uprights(left, right, top, bottom) + [_beam(left, right, top)]
        if braces:
            pieces += _braces(left, right, top + BEAM)
        if platform is not None:
            y = bottom - platform
            pieces += [_beam(left, right, y)] + _braces(left, right, y + BEAM, 0.55)
        if low_beam:
            pieces.append(_beam(left, right, bottom - 1.45, 'thin_beam', 0.05))
        lamps = []
        if lamp is not None:
            parts, light = _hung_lamp(lamp, top + BEAM, 0.35)
            pieces += parts
            lamps.append(light)
        return self.structure(pieces, _post_anchors(left, right, bottom), layer, lamps,
                              _feet_shadows(left, right) if layer != 'far' else (), shade)

    def rails(self, left, right, cy):
        """A short length of track lying on a level floor."""
        level = self.floor_level(left, right, cy)
        if not level:
            return None
        bottom = level[1]
        return self.structure([_piece('rail', left, bottom - 0.2, right - left, 0.2)],
                              [(floor(left + 0.3), bottom, 'floor'), (floor(right - 0.3), bottom, 'floor')],
                              layer='back')

    def group(self, entries, cy, layer='front', shadow=True):
        """Stand a staged group of sheet sprites (stacked crates and the like).

        ``entries`` hold (name, left, width, height, stack) where ``stack`` is
        the height in macros the sprite rests on above the floor.
        """
        lefts = [e[1] for e in entries]
        rights = [e[1] + e[2] for e in entries]
        level = self.floor_level(min(lefts), max(rights), cy)
        if not level:
            return None
        bottom = level[1]
        pieces = [_piece('sprite', left, bottom - stack - h, w, h, name=name, flip=flip)
                  for name, left, w, h, stack, flip in
                  ((*e, False) if len(e) == 5 else e for e in entries)]
        anchors = sorted({(floor(left + w / 2), bottom, 'floor')
                          for _, left, w, _, stack, *_ in entries if stack == 0})
        contact = [(min(lefts) - 0.05, max(rights) - min(lefts) + 0.1)] if shadow else ()
        return self.structure(pieces, anchors, layer, contact=contact)

    @staticmethod
    def offsets(distance):
        yield 0
        for step in range(1, floor(distance * 2) + 1):
            yield step * 0.5
            yield -step * 0.5


def _opening_room(layout, warm):
    """B1 start (level.py room 5..16 x 4..10): a worked face around the spawn.

    Left: a two-level scaffold from floor to roof with braces, a lantern on a
    chain, loose dirt on its platform and rubble below. Centre: the cart on a
    short track with spilled ore. Right: stacked stores, a barrel and a
    smaller support whose beam runs into the stepped east wall.
    """
    floor_y, top = 11.0, 4.0
    left, right = 6.15, 9.35
    pieces, light = _hung_lamp(7.95, top + BEAM, 0.45)
    pieces += (_uprights(left, right, top, floor_y)
               + [_beam(left, right, top), _beam(left, right, 7.35),
                  _beam(left, right, 9.6, 'thin_beam', 0.05)]
               + _braces(left, right, top + BEAM) + _braces(left, right, 7.35 + BEAM, 0.6)
               + [_piece('sprite', left + 0.55, 7.35 - 0.3, 1.6, 0.3, name='debris'),
                  _piece('art', right + 0.02, floor_y - 0.45, 0.325, 0.45, name='pickaxe')])
    layout.structure(pieces, _post_anchors(left, right, floor_y), lamps=[light],
                     contact=_feet_shadows(left, right))
    layout.rails(9.75, 12.9, 7)
    post, beam_y = 15.15, 6.0
    pieces, light = _hung_lamp(16.4, beam_y + BEAM, 0.3)
    pieces += [_piece('post', post, beam_y, POST, floor_y - beam_y),
               _piece('foot', post + POST / 2 - FOOT[0] / 2, floor_y - FOOT[1], *FOOT),
               _piece('beam', 14.3, beam_y, 17.0 - 14.3, BEAM),
               _piece('brace', post - 0.6, beam_y + BEAM, 0.6, 0.6, rising=False),
               _piece('brace', post + POST, beam_y + BEAM, 0.55, 0.55, rising=True)]
    layout.structure(pieces, [(15, 11, 'floor')], lamps=[light],
                     contact=[(post - 0.12, POST + 0.24)])
    layout.group([('crate', 13.0, 0.86, 1.02, 0), ('wood_crate', 13.1, 0.66, 0.78, 1.02),
                  ('small_crate', 13.95, 0.7, 0.86, 0), ('sack', 14.7, 0.36, 0.47, 0)], 7)
    layout.floor('cart', 11.2, 7, 1.4, 1.1, search=0, lift=0.1)
    layout.floor('gold_ore', 12.15, 7, 0.36, 0.43, search=0)
    layout.floor('barrel', 15.5, 7, 0.7, 0.88, search=0)
    layout.floor('small_rocks', 16.15, 7, 0.45, 0.45, search=0)
    layout.floor('toolbox', 6.55, 7, 0.8, 0.64, search=0)
    layout.floor('gray_rubble', 7.6, 7, 0.8, 0.55, search=0)
    layout.ceiling('dead_vines', 10.1, 3, 0.9, 0.9, search=0)
    layout.ceiling('dry_roots', 11.0, 3, 0.4, 0.7, search=0)
    layout.ceiling('dry_roots', 13.0, 4, 0.36, 0.62, search=0)
    layout.ceiling('cobweb', 14.95, 4, 0.95, 1.06, search=0)


def _mine_scenes(layout, warm, floor_prop, ceiling, wall):
    """The remaining B1 rooms, each staged as a small story."""
    # Abandoned workstation: the original tall frame, a cart left on its
    # track, ore and tools beside it, one lantern still hanging.
    floor_prop('mine_tall_frame', 36.5, 12, 2.6, 3.9, layer='back')
    layout.rails(38.6, 42.6, 12)
    floor_prop('cart', 39.6, 12, 1.6, 1.25, search=1.0, lift=0.1)
    floor_prop('rock_pile', 41.6, 12, 0.85, 0.6, search=0.5)
    floor_prop('gold_ore', 42.4, 12, 0.4, 0.48, search=0.5)
    layout.group([('crate', 44.1, 0.9, 1.07, 0), ('toolbox', 45.05, 0.8, 0.64, 0)], 12)
    ceiling('hanging_lantern', 40.6, 12, 0.62, 1.2, warm, search=1.0)
    ceiling('dry_roots', 43.5, 12, 0.36, 0.62)
    ceiling('cobweb', 35.5, 12, 0.85, 0.95, search=1.0)
    # Old storage room: barrels and crates under a support, sacks, webs.
    layout.mine_set(74.15, 77.45, 9, lamp=75.8)
    layout.group([('barrel', 74.6, 0.75, 0.93, 0), ('barrel', 75.4, 0.75, 0.93, 0),
                  ('barrel', 75.0, 0.75, 0.93, 0.93)], 9)
    layout.group([('wood_crate', 77.0, 0.9, 1.07, 0), ('crate', 77.95, 0.9, 1.07, 0),
                  ('small_crate', 77.45, 0.75, 0.92, 1.07), ('large_sack', 78.9, 0.6, 0.8, 0)], 9)
    floor_prop('sack', 80.3, 9, 0.45, 0.59, search=1.0)
    ceiling('cobweb', 72.6, 9, 1.0, 1.12, search=1.0)
    ceiling('cobweb', 80.4, 9, 0.8, 0.9, search=1.0)
    # Collapsed tunnel: a fallen support, the broken cart, piled rock and a
    # warning sign at the safe end; ore shows in the cracked rim.
    floor_prop('broken_support', 98.45, 18, 1.9, 1.28, layer='back', search=0)
    floor_prop('broken_cart', 104.2, 18, 1.25, 1.2, search=1.0)
    floor_prop('rock_pile', 102.6, 18, 1.2, 0.85, search=1.0)
    floor_prop('gray_rubble', 105.6, 18, 1.0, 0.68, search=1.0)
    floor_prop('stone_mound', 106.8, 18, 1.0, 0.9, search=1.0)
    floor_prop('dirt_mound', 97.3, 18, 0.75, 0.93, search=1.0)
    for x in (96.5, 108.2):
        level = layout.floor_level(x, x + 0.6, 18)
        if level:
            bottom = level[1]
            layout.structure([_piece('stub', x, bottom - 0.92, 0.62, 0.92)],
                             [(floor(x + 0.3), bottom, 'floor')], contact=[(x, 0.62)])
    level = layout.floor_level(109.3, 109.7, 18)
    if level:
        bottom = level[1]
        layout.structure([_piece('art', 109.1, bottom - 0.43, 0.4, 0.43, name='sign')],
                         [(109, bottom, 'floor')], contact=[(109.2, 0.2)])
    ceiling('dry_roots', 101.5, 18, 0.45, 0.78)
    ceiling('dead_vines', 106.0, 18, 0.9, 0.9)
    ceiling('dead_vines', 98.4, 18, 1.0, 1.0, layer='fore', shade=118)
    wall('lantern', 103, 18, 0.55, 1.0, side='right', glow=warm)
    # Two small stashes: a rope and lantern by an old chest, and a cache
    # tucked under a single cap beam.
    floor_prop('old_chest', 28.6, 5, 1.2, 0.73)
    floor_prop('small_crate', 26.7, 5, 0.7, 0.86)
    level = layout.floor_level(30.2, 30.6, 5)
    if level:
        bottom = level[1]
        layout.structure([_piece('art', 30.2, bottom - 0.25, 0.35, 0.25, name='rope')],
                         [(30, bottom, 'floor')], contact=[(30.2, 0.35)])
    ceiling('lantern', 27.6, 5, 0.5, 0.9, warm)
    ceiling('cobweb', 30.3, 5, 0.8, 0.9)
    layout.mine_set(66.6, 69.3, 20, lamp=68.0, braces=True)
    floor_prop('old_chest', 70.2, 20, 1.15, 0.7)
    floor_prop('small_rocks', 71.6, 20, 0.45, 0.45)
    ceiling('cobweb', 72.0, 20, 0.8, 0.9)


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

    warm = (3.4, (255, 172, 70))
    blue = (2.8, (64, 147, 255))
    purple = (2.8, (178, 86, 247))
    red = (2.6, (255, 91, 38))

    # Place climbable structures before ornamental architecture reserves space.
    # The arena ladder reaches the diggable roof below the overhead reservoir.
    layout.ladder(98, 85, width=0.85)
    layout.ladder(5, 7, width=0.75)
    layout.ladder(101, 18, width=0.7)

    # B1: the old human mine. Timber is built into the rooms and every prop
    # belongs to a small scene; ore glints in the worked rims.
    for cx, cy in [(10, 7), (40, 12), (77, 9), (103, 18)]:
        rim(cx, cy, 10, 6, 'dirt')
        ores(cx, cy, 11, 6, 'ore_gold')
    for cx, cy in [(28, 5), (69, 20)]:
        ores(cx, cy, 5, 3, 'ore_gold')
    _opening_room(layout, warm)
    _mine_scenes(layout, warm, floor_prop, ceiling, wall)

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
        if index % 3 == 2:
            # Sparse foreground growth: dark, at the roof, never over a path.
            ceiling('short_vines', cx - 2, cy, 1.0, 1.25, layer='fore', shade=112)
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

    return dict(props=layout.props, structures=layout.structures,
                materials=materials, lights=lights)
