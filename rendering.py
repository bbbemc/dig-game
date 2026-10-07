"""Visible chunk caches, layered cave art and mass-interpolated liquids.

Each 320-pixel chunk caches two layers that rebuild only after terrain edits:

* rear (opaque): mine wall, distant timber, soft occlusion near rock faces,
  contact shadows under grounded props, then rear props such as ladders;
* front (transparent): seamless ground with sparse per-macro details, exposed
  soil lips, shaded undersides, side rims, rounded corners and fillets, then
  front props.

Edge protrusions and fillets are visual only; collision stays on the grid.
Cobwebs and foreground pieces are drawn per frame so they can move or sit in
front of actors.
"""
import math
import time

import pygame

from config import CELL, SCALE, MACRO, CHUNK_CELLS
from level import WATER, LAVA, EMPTY, STONE, DIRT
from terrain_art import box_blur
from tiles import coordinate_hash
from world import SOLIDS

CHUNK_PIXELS = CHUNK_CELLS * CELL
MACROS_PER_CHUNK = CHUNK_CELLS // SCALE
SOLID_TABLE = bytes(1 if kind in SOLIDS else 0 for kind in range(256))
OPEN_TABLE = bytes(0 if kind in SOLIDS else 255 for kind in range(256))
GRAY = [(v, v, v) for v in range(256)]
ANIMATED = {'cobweb'}
NO_SHADOW = {'ladder', 'mine_rail', 'debris'}
# Height of a lamp's flame within its sprite, and how each light behaves.
LIGHT_ANCHOR = {'hanging_lantern': 0.7, 'lantern': 0.62, 'torch': 0.13}
LIGHT_KIND = {'hanging_lantern': 'lamp', 'lantern': 'lamp', 'torch': 'torch'}
OCCLUSION_MARGIN = 4      # cells read beyond a chunk so shading is continuous
OCCLUSION_FLOOR = 104     # rear-wall multiplier deep inside narrow tunnels


def prop_anchors(prop):
    anchors = prop.get('anchors')
    if anchors is None:
        attachment = prop.get('attachment', 'floor')
        cells = prop.get('support_cells') or ([prop['support']] if prop.get('support') else [])
        anchors = [(mx, my, attachment) for mx, my in cells]
    return anchors


def prop_supported(world, prop):
    for mx, my, attachment in prop_anchors(prop):
        gx, gy = mx * SCALE + SCALE // 2, my * SCALE
        if attachment == 'ceiling':
            gy += SCALE - 1
        elif attachment == 'wall_left':
            gx = mx * SCALE + SCALE - 1
            gy += SCALE // 2
        elif attachment == 'wall_right':
            gx = mx * SCALE
            gy += SCALE // 2
        if not world.solid(gx, gy):
            return False
    return True


def macro_rect(x, y, w, h):
    return pygame.Rect(round(x * MACRO), round(y * MACRO),
                       max(1, round(w * MACRO)), max(1, round(h * MACRO)))


class WorldRenderer:
    def __init__(self, world, art, scenery):
        self.world, self.art, self.scenery = world, art, scenery
        self.cache = {}
        self.items = []
        self.item_chunks, self.anchor_items = {}, {}
        self.visible_chunks = 0
        self.rebuilt_chunks = 0
        self.visible_liquids = 0
        self.visible_tiles = 0
        self.draw_calls = 0
        self.rebuild_ms = 0.0
        self.ladders = []
        self.lights = []
        self.animated_items, self.fore_items = [], []
        self.visible_lava, self.visible_water = set(), set()
        self.lava_surfaces, self.visible_lamps = [], []
        self._groups = {}
        for prop in scenery['props']:
            self._add(prop, self._prop_image(prop))
        for structure in scenery.get('structures', ()):
            self._add(structure, self._structure_image(structure))
        world.listeners.append(self.terrain_changed)
        # Cooling stone darkens progressively before the solid tile appears.
        self.cooling_stones = []
        for stage in range(8):
            stone = art.tile(STONE, 0, 80).copy()
            stone.fill((125, 125, 153), special_flags=pygame.BLEND_RGB_MULT)
            stone.set_alpha(55 + stage * 27)
            self.cooling_stones.append(stone)

    # ------------------------------------------------------------------
    # Scenery items
    # ------------------------------------------------------------------
    def _prop_image(self, prop):
        art = self.art
        box = macro_rect(prop['x'], prop['y'], prop['w'], prop['h'])
        shade = prop.get('shade', 255)
        if prop.get('repeat_y'):
            image = pygame.Surface(box.size, pygame.SRCALPHA)
            height = max(1, round(prop['segment_h'] * MACRO))
            segment = art.sprite(prop['name'], box.w, height, 255, prop['flip'], shade)
            for y in range(0, box.h, height):
                image.blit(segment, (0, y))
            if prop['opacity'] != 255:
                image.set_alpha(prop['opacity'])
            return image
        return art.sprite(prop['name'], box.w, box.h, prop['opacity'], prop['flip'], shade)

    def _structure_image(self, structure):
        """Compose timber pieces; beams overlap uprights as on the sheet."""
        art = self.art
        box = macro_rect(structure['x'], structure['y'], structure['w'], structure['h'])
        image = pygame.Surface(box.size, pygame.SRCALPHA)
        order = {'rail': 0, 'brace': 0, 'post': 1, 'stub': 1, 'chain': 1, 'foot': 2, 'beam': 3,
                 'thin_beam': 3, 'sprite': 4, 'art': 4}
        for piece in sorted(structure['pieces'], key=lambda p: order[p['kind']]):
            rect = macro_rect(piece['x'], piece['y'], piece['w'], piece['h']).move(-box.x, -box.y)
            kind = piece['kind']
            if kind in ('beam', 'thin_beam'):
                surface = art.beam(rect.w, rect.h, kind)
            elif kind in ('post', 'chain'):
                surface = art.post(rect.h, rect.w, kind)
            elif kind == 'brace':
                surface = art.brace(rect.w, rect.h, piece.get('thickness', 8), piece.get('rising', True))
            elif kind == 'foot':
                surface = art.sprite('post_foot', rect.w, rect.h)
            elif kind == 'stub':
                surface = art.sprite('post_stub', rect.w, rect.h, flip=piece.get('flip', False))
            elif kind == 'rail':
                surface = art.rail(rect.w)
                rect.top = rect.bottom - surface.get_height()
            elif kind == 'art':
                surface = art.pixel(piece['name'], rect.w, rect.h, piece.get('flip', False))
            else:
                surface = art.sprite(piece['name'], rect.w, rect.h, 255, piece.get('flip', False))
            image.blit(surface, rect.topleft)
        shade = structure.get('shade', 255)
        if shade != 255:
            image.fill((shade, shade, shade), special_flags=pygame.BLEND_RGB_MULT)
        if structure.get('opacity', 255) != 255:
            image.set_alpha(structure['opacity'])
        return image

    def _add(self, prop, image):
        number = len(self.items)
        box = macro_rect(prop['x'], prop['y'], prop['w'], prop['h'])
        item = {'prop': prop, 'box': box, 'image': image, 'layer': prop['layer'],
                'animated': prop.get('name') in ANIMATED, 'phase': coordinate_hash(box.x, box.y) % 628 / 100,
                'shadows': self._contact_shadows(prop, box)}
        self.items.append(item)
        if item['animated']:
            self.animated_items.append(number)
        elif item['layer'] == 'fore':
            self.fore_items.append(number)
        if prop.get('name') == 'ladder':
            self.ladders.append((box, prop))
        if 'glow' in prop:
            radius, color = prop['glow']
            name = prop.get('name')
            kind = LIGHT_KIND.get(name, 'crystal')
            if kind == 'crystal':
                # Mineral glow tints the rock; it must not outshine lanterns.
                color = tuple(round(c * 0.6) for c in color)
            self.lights.append({'item': number, 'x': box.centerx,
                                'y': round(box.y + box.h * LIGHT_ANCHOR.get(name, 0.5)),
                                'radius': radius * MACRO, 'color': color, 'kind': kind,
                                'phase': item['phase']})
        for lamp in prop.get('lamps', ()):
            # Lanterns hung from a structure's beam on a short chain.
            self.lights.append({'item': number, 'x': round(lamp['x'] * MACRO),
                                'y': round(lamp['y'] * MACRO), 'radius': 3.4 * MACRO,
                                'color': (255, 172, 70), 'kind': 'lamp',
                                'phase': coordinate_hash(round(lamp['x'] * 8), 3) % 628 / 100})
        if not (item['animated'] or item['layer'] == 'fore'):
            for cy in range(box.top // CHUNK_PIXELS, (box.bottom - 1) // CHUNK_PIXELS + 1):
                for cx in range(box.left // CHUNK_PIXELS, (box.right - 1) // CHUNK_PIXELS + 1):
                    self.item_chunks.setdefault((cx, cy), []).append(number)
        for mx, my, _ in prop_anchors(prop):
            self.anchor_items.setdefault((mx, my), []).append(number)

    @staticmethod
    def _contact_shadows(prop, box):
        """(left, width) pixel spans darkened where a grounded object stands."""
        if prop['layer'] not in ('back', 'front'):
            return ()
        if 'contact_shadow' in prop:
            return [(round(left * MACRO), max(8, round(width * MACRO)))
                    for left, width in prop['contact_shadow']]
        if prop.get('attachment') == 'floor' and prop.get('name') not in NO_SHADOW:
            width = box.w + 6
            return [(box.centerx - width // 2, width)]
        return ()

    def debris_colors(self, x, y):
        """Dark, body and light tones of the ground dug at cell (x, y)."""
        mx, my = x // SCALE, y // SCALE
        group = self.art.ground(DIRT, mx, my, self.scenery['materials'].get((mx, my)))[3]
        palette = self.art.palettes[group]
        return palette['dark'], palette['body'], palette['light']

    def supported(self, number):
        return prop_supported(self.world, self.items[number]['prop'])

    def terrain_changed(self, index):
        x, y = self.world.coords(index)
        for number in self.anchor_items.get((x // SCALE, y // SCALE), ()):
            box = self.items[number]['box'].inflate(16, 16)
            for cy in range(box.top // CHUNK_PIXELS, (box.bottom - 1) // CHUNK_PIXELS + 1):
                for cx in range(box.left // CHUNK_PIXELS, (box.right - 1) // CHUNK_PIXELS + 1):
                    self.world.dirty_chunks.add((cx, cy))

    def ladder_at(self, rect):
        return any(box.colliderect(rect) and prop_supported(self.world, prop)
                   for box, prop in self.ladders)

    # ------------------------------------------------------------------
    # Chunk construction
    # ------------------------------------------------------------------
    def _rows(self, x0, y0, w, h, table, outside):
        """Translated cell rows for a window; cells outside the world use ``outside``."""
        world = self.world
        width, height, ground = world.width, world.height, world.foreground
        pad = bytes((outside,))
        rows = []
        for y in range(y0, y0 + h):
            if 0 <= y < height:
                lo, hi = max(0, x0), min(width, x0 + w)
                row = ground[y * width + lo:y * width + hi].translate(table)
                rows.append(pad * (lo - x0) + bytes(row) + pad * (x0 + w - hi))
            else:
                rows.append(pad * w)
        return rows

    def _group(self, x, y):
        """Edge palette for the material at cell (x, y)."""
        mx, my = x // SCALE, y // SCALE
        kind = self.world.foreground[y * self.world.width + x]
        key = (mx, my, kind)
        if key not in self._groups:
            material = self.scenery['materials'].get((mx, my))
            self._groups[key] = self.art.ground(kind, mx, my, material)[3]
        return self._groups[key]

    def _occlusion(self, back, cx, cy):
        """Darken the rear wall near rock faces; deep inside tunnels most."""
        margin = OCCLUSION_MARGIN
        span = CHUNK_CELLS + 2 * margin
        rows = self._rows(cx * CHUNK_CELLS - margin, cy * CHUNK_CELLS - margin, span, span, OPEN_TABLE, 0)
        cells = pygame.image.frombytes(b''.join(rows), (span, span), 'P')
        cells.set_palette(GRAY)
        field = pygame.Surface((span, span), 0, 32)
        field.blit(cells, (0, 0))
        field = box_blur(field, 2)
        field = pygame.transform.smoothscale(field, (span * CELL, span * CELL))
        shade = field.subsurface((margin * CELL, margin * CELL, CHUNK_PIXELS, CHUNK_PIXELS))
        keep = 255 - OCCLUSION_FLOOR
        shade.fill((keep, keep, keep), special_flags=pygame.BLEND_RGB_MULT)
        shade.fill((OCCLUSION_FLOOR,) * 3, special_flags=pygame.BLEND_RGB_ADD)
        back.blit(shade, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    @staticmethod
    def _crossfade(target, blend, px, py, wx, wy, columns=None):
        """Lay the next stratum over a macro one 8-pixel row at a time."""
        texture, shares = blend
        for row, share in enumerate(shares):
            if share < 0.01 or (columns is not None and not columns[row]):
                continue
            texture.set_alpha(round(share * 255))
            if columns is None:
                target.blit(texture, (px, py + row * CELL), (wx, wy + row * CELL, MACRO, CELL))
            else:
                for dx in columns[row]:
                    target.blit(texture, (px + dx * CELL, py + row * CELL),
                                (wx + dx * CELL, wy + row * CELL, CELL, CELL))
        texture.set_alpha(None)

    def _ground(self, front, cx, cy):
        world, art = self.world, self.art
        width, ground = world.width, world.foreground
        materials = self.scenery['materials']
        mx0, my0 = cx * MACROS_PER_CHUNK, cy * MACROS_PER_CHUNK
        origin_x, origin_y = cx * CHUNK_PIXELS, cy * CHUNK_PIXELS
        base, fades, details, seams = [], [], [], []
        for my in range(my0, min(world.height // SCALE, my0 + MACROS_PER_CHUNK)):
            for mx in range(mx0, min(world.width // SCALE, mx0 + MACROS_PER_CHUNK)):
                gx, gy = mx * SCALE, my * SCALE
                rows = [ground[(gy + dy) * width + gx:(gy + dy) * width + gx + SCALE] for dy in range(SCALE)]
                first = rows[0][0]
                uniform = all(row.count(first) == SCALE for row in rows)
                if uniform and first == EMPTY:
                    continue
                px, py = mx * MACRO - origin_x, my * MACRO - origin_y
                material = materials.get((mx, my))
                if uniform:
                    texture, wx, wy, group, detail, blend = art.ground(first, mx, my, material)
                    base.append((texture, (px, py), (wx, wy, MACRO, MACRO)))
                    if blend:
                        fades.append((blend, px, py, wx, wy, None))
                    if material:
                        seams.extend(self._seams(first, mx, my, group, px, py, wx, wy))
                    if detail:
                        sprite, dx, dy = detail
                        details.append((sprite, (px + dx, py + dy)))
                    continue
                # Partly excavated macro: every remaining cell keeps the
                # texture coordinates (and detail pixels) it had when whole.
                by_kind = {}
                for dy, row in enumerate(rows):
                    for dx, kind in enumerate(row):
                        if kind in SOLIDS:
                            by_kind.setdefault(kind, [[] for _ in range(SCALE)])[dy].append(dx)
                for kind, columns in by_kind.items():
                    texture, wx, wy, _, detail, blend = art.ground(kind, mx, my, material)
                    for dy, xs in enumerate(columns):
                        for dx in xs:
                            cell = (dx * CELL, dy * CELL)
                            base.append((texture, (px + cell[0], py + cell[1]),
                                         (wx + cell[0], wy + cell[1], CELL, CELL)))
                            if detail:
                                sprite, sx, sy = detail
                                area = pygame.Rect(*cell, CELL, CELL).clip(pygame.Rect(sx, sy, *sprite.get_size()))
                                if area.w and area.h:
                                    details.append((sprite, (px + area.x, py + area.y), area.move(-sx, -sy)))
                    if blend:
                        fades.append((blend, px, py, wx, wy, columns))
        front.blits(base, doreturn=False)
        for blend, px, py, wx, wy, columns in fades:
            self._crossfade(front, blend, px, py, wx, wy, columns)
        if seams:
            scratch = pygame.Surface((MACRO, MACRO), pygame.SRCALPHA)
            for texture, area, mask, position in seams:
                scratch.blit(texture, (0, 0), area)
                scratch.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                front.blit(scratch, position)
        front.blits(details, doreturn=False)

    def _seams(self, kind, mx, my, group, px, py, wx, wy):
        """Feather neighbouring ground of the same kind into a painted macro.

        Scenery paints rims (wet, scorched, worked) per macro; without this
        their 40-pixel squares would read as tiles. Rock never blends into
        dirt, so diggable and unbreakable ground stay distinct.
        """
        world, art = self.world, self.art
        materials = self.scenery['materials']
        sides = (('top', 0, -1), ('bottom', 0, 1), ('left', -1, 0), ('right', 1, 0))
        for side, dx, dy in sides:
            nx, ny = mx + dx, my + dy
            if not (0 <= nx < world.width // SCALE and 0 <= ny < world.height // SCALE):
                continue
            if world.foreground[world.index(nx * SCALE + 2, ny * SCALE + 2)] != kind:
                continue
            texture, nwx, nwy, other, *_ = art.ground(kind, nx, ny, materials.get((nx, ny)))
            if other == group:
                continue
            # The neighbour's canvas at this macro's own window continues it.
            ww, wh = texture.get_size()
            area = ((mx * MACRO) % ww, (my * MACRO) % wh, MACRO, MACRO)
            masks = art.borders[side]
            yield texture, area, masks[coordinate_hash(mx, my * 7 + dx) % len(masks)], (px, py)

    def _edges(self, front, cx, cy):
        """Lips, undersides, side rims, rounded corners and fillets."""
        art = self.art
        x0, y0 = cx * CHUNK_CELLS, cy * CHUNK_CELLS
        span = CHUNK_CELLS + 4
        rows = self._rows(x0 - 2, y0 - 2, span, span, SOLID_TABLE, 1)
        erasers = art.erasers
        multiply = pygame.BLEND_RGBA_MULT
        shading, corners, fillets = [], [], []
        last = CHUNK_CELLS
        for ly in range(-1, last + 1):
            above, row, below = rows[ly + 1], rows[ly + 2], rows[ly + 3]
            py = ly * CELL
            for lx in range(-1, last + 1):
                g = lx + 2
                px = lx * CELL
                if row[g]:
                    up, down = not above[g], not below[g]
                    left, right = not row[g - 1], not row[g + 1]
                    if not (up or down or left or right):
                        continue
                    x, y = x0 + lx, y0 + ly
                    pieces = art.edges[self._group(min(max(x, 0), self.world.width - 1),
                                                   min(max(y, 0), self.world.height - 1))]
                    h = coordinate_hash(x, y)
                    if up:
                        options = pieces['top']
                        shading.append((options[h % len(options)], (px, py - 1)))
                    if down:
                        options = pieces['bottom']
                        shading.append((options[(h >> 5) % len(options)], (px, py + 5)))
                    if left:
                        options = pieces['left']
                        shading.append((options[(h >> 9) % len(options)], (px - 2, py)))
                    if right:
                        options = pieces['right']
                        shading.append((options[(h >> 13) % len(options)], (px + 6, py)))
                    if up and left and not above[g - 1]:
                        corners.append((erasers['tl'], (px, py), None, multiply))
                    if up and right and not above[g + 1]:
                        corners.append((erasers['tr'], (px, py), None, multiply))
                    if down and left and not below[g - 1]:
                        corners.append((erasers['bl'], (px, py), None, multiply))
                    if down and right and not below[g + 1]:
                        corners.append((erasers['br'], (px, py), None, multiply))
                elif 0 <= lx < last and 0 <= ly < last:
                    left, right = row[g - 1], row[g + 1]
                    if not (left or right):
                        continue
                    up, down = above[g], below[g]
                    if down and left and below[g - 1]:
                        fillets.append(('bl', lx, ly, x0 + lx - 1, y0 + ly))
                    if down and right and below[g + 1]:
                        fillets.append(('br', lx, ly, x0 + lx + 1, y0 + ly))
                    if up and left and above[g - 1]:
                        fillets.append(('tl', lx, ly, x0 + lx - 1, y0 + ly))
                    if up and right and above[g + 1]:
                        fillets.append(('tr', lx, ly, x0 + lx + 1, y0 + ly))
        front.blits(shading, doreturn=False)
        front.blits(corners, doreturn=False)
        last_x, last_y = self.world.width - 1, self.world.height - 1
        front.blits([(art.edges[self._group(min(max(sx, 0), last_x), min(max(sy, 0), last_y))]
                      ['fillet'][corner], (lx * CELL, ly * CELL))
                     for corner, lx, ly, sx, sy in fillets], doreturn=False)

    def _build(self, cx, cy):
        world, art = self.world, self.art
        origin_x, origin_y = cx * CHUNK_PIXELS, cy * CHUNK_PIXELS
        # Opaque layers never carry an alpha channel (see terrain_art).
        back = pygame.Surface((CHUNK_PIXELS, CHUNK_PIXELS), 0, 32)
        front = pygame.Surface((CHUNK_PIXELS, CHUNK_PIXELS), pygame.SRCALPHA)
        back.fill((24, 20, 18))
        mx0, my0 = cx * MACROS_PER_CHUNK, cy * MACROS_PER_CHUNK
        walls, fades = [], []
        for my in range(my0, min(world.height // SCALE, my0 + MACROS_PER_CHUNK)):
            for mx in range(mx0, min(world.width // SCALE, mx0 + MACROS_PER_CHUNK)):
                texture, wx, wy, blend = art.wall(mx, my)
                px, py = mx * MACRO - origin_x, my * MACRO - origin_y
                walls.append((texture, (px, py), (wx, wy, MACRO, MACRO)))
                if blend:
                    fades.append((blend, px, py, wx, wy))
        back.blits(walls, doreturn=False)
        for blend, px, py, wx, wy in fades:
            self._crossfade(back, blend, px, py, wx, wy)
        visible = [n for n in self.item_chunks.get((cx, cy), ()) if self.supported(n)]
        for number in visible:
            item = self.items[number]
            if item['layer'] == 'far':
                back.blit(item['image'], (item['box'].x - origin_x, item['box'].y - origin_y))
        self._occlusion(back, cx, cy)
        for number in visible:
            item = self.items[number]
            for left, width in item['shadows']:
                back.blit(art.shadow(width), (left - origin_x, item['box'].bottom - 6 - origin_y))
        for number in visible:
            item = self.items[number]
            if item['layer'] == 'back':
                back.blit(item['image'], (item['box'].x - origin_x, item['box'].y - origin_y))
        self._ground(front, cx, cy)
        self._edges(front, cx, cy)
        for number in visible:
            item = self.items[number]
            if item['layer'] == 'front':
                front.blit(item['image'], (item['box'].x - origin_x, item['box'].y - origin_y))
        self.cache[cx, cy] = back.convert(), front.convert_alpha()
        world.dirty_chunks.discard((cx, cy))

    def draw_static(self, screen, camera):
        start = time.perf_counter()
        cx, cy = camera
        self.rebuilt_chunks = 0
        self.draw_calls = 0
        x0, y0 = max(0, cx // CHUNK_PIXELS), max(0, cy // CHUNK_PIXELS)
        x1 = min(math.ceil(self.world.pixel_width / CHUNK_PIXELS), (cx + screen.get_width() - 1) // CHUNK_PIXELS + 1)
        y1 = min(math.ceil(self.world.pixel_height / CHUNK_PIXELS), (cy + screen.get_height() - 1) // CHUNK_PIXELS + 1)
        visible = [(x, y) for y in range(y0, y1) for x in range(x0, x1)]
        for key in visible:
            if key not in self.cache or key in self.world.dirty_chunks:
                self._build(*key)
                self.rebuilt_chunks += 1
        self.rebuild_ms = (time.perf_counter() - start) * 1000
        self.visible_chunks = len(visible)
        self.visible_tiles = (((cx + screen.get_width() - 1) // MACRO - cx // MACRO + 1) *
                              ((cy + screen.get_height() - 1) // MACRO - cy // MACRO + 1))
        layers = []
        for x, y in visible:
            back, front = self.cache[x, y]
            position = (x * CHUNK_PIXELS - cx, y * CHUNK_PIXELS - cy)
            layers.append((back, position))
            layers.append((front, position))
        screen.blits(layers, doreturn=False)
        self.draw_calls += len(layers)
        view = screen.get_rect().move(camera)
        self.visible_lamps = [(light['x'], light['y']) for light in self.lights
                              if light['kind'] in ('lamp', 'torch') and view.collidepoint(light['x'], light['y'])
                              and self.supported(light['item'])]

    def _visible_items(self, screen, camera, numbers):
        view = screen.get_rect().move(camera)
        for number in numbers:
            item = self.items[number]
            if item['box'].colliderect(view) and self.supported(number):
                yield item

    def draw_animated(self, screen, camera, world_time):
        """Cobwebs stir by a single pixel now and then; never distracting."""
        cx, cy = camera
        for item in self._visible_items(screen, camera, self.animated_items):
            sway = math.sin(world_time * 0.7 + item['phase'])
            offset = 1 if sway > 0.82 else (-1 if sway < -0.9 else 0)
            screen.blit(item['image'], (item['box'].x - cx + offset, item['box'].y - cy))
            self.draw_calls += 1

    def draw_foreground(self, screen, camera):
        cx, cy = camera
        for item in self._visible_items(screen, camera, self.fore_items):
            screen.blit(item['image'], (item['box'].x - cx, item['box'].y - cy))
            self.draw_calls += 1

    def draw_liquids(self, screen, liquids, camera, alpha, world_time):
        cx, cy = camera
        x0, y0 = max(0, cx // CELL - 1), max(0, cy // CELL - 1)
        x1 = min(self.world.width, (cx + screen.get_width()) // CELL + 2)
        y1 = min(self.world.height, (cy + screen.get_height()) // CELL + 2)
        if hasattr(liquids, 'visible_indices'):
            indices = liquids.visible_indices(x0, y0, x1, y1)
        else:
            indices = (y * self.world.width + x for y in range(y0, y1) for x in range(x0, x1))
        cells = {}
        self.visible_lava, self.visible_water = set(), set()
        self.lava_surfaces = []
        for i in indices:
            mass = liquids.render_mass(i, alpha)
            if mass <= .005 or self.world.foreground[i] != EMPTY:
                continue
            kind = liquids.types.get(i) or getattr(liquids, 'previous_types', {}).get(i)
            if kind not in (WATER, LAVA):
                continue
            x, y = self.world.coords(i)
            cells[x, y] = (i, kind, mass)
            (self.visible_lava if kind == LAVA else self.visible_water).add((x // SCALE, y // SCALE))
        self.visible_liquids = len(cells)
        # Blit the original texture clipped to bottom-aligned pool geometry.
        # Falling cells use connected full-height ribbons instead of tiny bars.
        patches, surfaces, streaks, cooling, vapor = [], [], [], [], []
        textures = self.art.liquid_textures
        drift = {WATER: int(world_time * 6), LAVA: int(world_time * 2)}
        for (x, y), (i, kind, mass) in cells.items():
            above, below = cells.get((x, y - 1)), cells.get((x, y + 1))
            left, right = cells.get((x - 1, y)), cells.get((x + 1, y))
            below_solid = self.world.solid(x, y + 1)
            falling = (not below_solid and (mass < .98 or below is None or below[2] < .98)
                       and above is not None and above[1] == kind)
            sx, sy = x * CELL - cx, y * CELL - cy
            if falling:
                # Neighboring flowing cells meet without dark gaps. Width
                # ranges from half a grid cell to a full cell according to flow.
                width = CELL if (left and left[1] == kind) or (right and right[1] == kind) else max(CELL // 2, round(CELL * min(1, mass * 2)))
                offset = (CELL - width) // 2
                rect = pygame.Rect(sx + offset, sy, width, CELL)
                if (x + y) % 3 == int(world_time * 12) % 3:
                    streaks.append((kind, rect.x + width // 2, rect.y, rect.bottom))
            else:
                height = max(1, min(CELL, round(CELL * mass)))
                rect = pygame.Rect(sx, sy + CELL - height, CELL, height)
            # Bodies drift slowly; the window follows world coordinates, so
            # neighbouring cells always continue one seamless texture.
            texture = textures[kind]
            span = texture.get_width() // 2
            area = pygame.Rect((x * CELL + drift[kind]) % span + (rect.x - sx),
                               (y * CELL) % texture.get_height() + CELL - rect.h, rect.w, rect.h)
            patches.append((texture, rect.topleft, area))
            if (above is None or above[1] != kind) and not falling:
                surfaces.append((kind, x, rect.left, rect.top, rect.right - 1))
                if kind == LAVA:
                    self.lava_surfaces.append((rect.left + cx, rect.top + cy))
            if i in liquids.reactions:
                progress = liquids.reaction_progress(i)
                if kind == WATER:
                    vapor.append((rect, progress, x, y))
                else:
                    cooling.append((rect, progress, x, y))
        screen.blits(patches, doreturn=False)
        self.draw_calls += len(patches)
        # Surfaces: a light rim with slow travelling glints on water and a
        # gently pulsing crust on lava.
        pulse = 0.5 + 0.5 * math.sin(world_time * 1.7)
        lava_rim = (255, round(150 + 50 * pulse), round(40 + 20 * pulse))
        tick = int(world_time * 6)
        for kind, x, left, top, right in surfaces:
            if kind == WATER:
                pygame.draw.line(screen, (91, 194, 255), (left, top), (right, top))
                glint = (x * 5 + tick) % 11
                if glint < CELL:
                    screen.fill((205, 238, 255), (left + glint, top, 2, 1))
            else:
                pygame.draw.line(screen, lava_rim, (left, top), (right, top))
                if (x * 7 + tick // 2) % 13 < 2:
                    screen.fill((255, 236, 150), (left + (x * 3) % CELL, top, 1, 1))
        for kind, x, top, bottom in streaks:
            color = (47, 147, 220) if kind == WATER else (230, 112, 31)
            pygame.draw.line(screen, color, (x, top), (x, bottom - 1))
        for rect, progress, x, y in vapor:
            for puff in range(3):
                phase = (world_time * 13 + x * 2.3 + y * 3.7 + puff / 3) % 1
                rise = round(2 + phase * 12)
                size = 4 + puff * 2
                shade = round(145 + 55 * (1 - phase))
                pygame.draw.ellipse(
                    screen, (shade, shade, min(220, shade + 12)),
                    (rect.centerx - size // 2 + puff * 2 - 2,
                     rect.top - rise, size, size + 2))
        for rect, progress, x, y in cooling:
            # Darkening happens locally before solidity; a few restrained steam
            # pixels move upward without allocating particle emitters per tile.
            stone = self.cooling_stones[min(7, int(progress * 8))]
            screen.blit(stone, rect.topleft, ((x % SCALE) * CELL, (y % SCALE) * CELL, rect.w, rect.h))
            if (rect.x + rect.y) // CELL % 7 == int(world_time * 8) % 7:
                rise = int(world_time * 20) % 9
                pygame.draw.rect(screen, (192, 191, 199), (rect.centerx, rect.top - rise, 2, 3))
