"""Seamless ground, rear-wall, detail and exposed-edge art from the supplied sheet.

Everything here is generated once while loading. Ground textures are
wrap-around mosaics of the original specimen pixels: every specimen is
equalised (its own bevel and lighting gradient removed), laid down once for
coverage and then stamped many times through feathered masks. Neighbouring
macro tiles therefore continue one another instead of repeating a framed
square, and macro (x, y) always maps to the same pixels.

Opaque layers never carry an alpha channel. On macOS the display format has
one without SRCALPHA, and pygame-ce blending onto such a surface clears the
destination alpha, which the window then presents as black.
"""

import math
import random

import pygame

TEXTURE_SIZE = (480, 400)  # 12 x 10 macro tiles; deliberately not a chunk size.

# Weighted per-macro ground details: (cumulative percent, category).
DETAIL_WEIGHTS = ((65, None), (80, 'alt'), (88, 'pebbles'), (94, 'crack'),
                  (98, 'dark'), (100, 'rare'))


def opaque(surface):
    """Copy into a 32-bit surface without an alpha channel."""
    result = pygame.Surface(surface.get_size(), 0, 32)
    result.blit(surface, (0, 0))
    return result


def box_blur(surface, radius):
    """pygame-ce's box blur, or an equivalent separable blur on classic pygame."""
    if hasattr(pygame.transform, 'box_blur'):
        return pygame.transform.box_blur(surface, radius)
    width, height = surface.get_size()
    taps = 2 * radius + 1
    weight = (255 // taps,) * 3
    result = surface
    for dx, dy in ((1, 0), (0, 1)):
        # Edge pixels repeat, matching pygame-ce's default.
        padded = pygame.Surface((width + 2 * radius * dx, height + 2 * radius * dy), 0, 32)
        padded.blit(pygame.transform.scale(result.subsurface((0, 0, 1, height) if dx else (0, 0, width, 1)),
                                           (radius, height) if dx else (width, radius)), (0, 0))
        padded.blit(pygame.transform.scale(result.subsurface((width - 1, 0, 1, height) if dx else (0, height - 1, width, 1)),
                                           (radius, height) if dx else (width, radius)),
                    (width + radius, 0) if dx else (0, height + radius))
        padded.blit(result, (radius * dx, radius * dy))
        part = padded.copy()
        part.fill(weight, special_flags=pygame.BLEND_RGB_MULT)
        out = pygame.Surface((width, height), 0, 32)
        out.fill((0, 0, 0))
        for k in range(taps):
            out.blit(part, (-k * dx, -k * dy), special_flags=pygame.BLEND_RGB_ADD)
        result = out
    return result


def luminance(color):
    return color[0] * 0.3 + color[1] * 0.59 + color[2] * 0.11


def mix(a, b, amount):
    return tuple(round(a[i] + (b[i] - a[i]) * amount) for i in range(3))


def shift_mean(surface, target):
    average = pygame.transform.average_color(surface)
    difference = [target[c] - average[c] for c in range(3)]
    surface.fill(tuple(max(0, -d) for d in difference), special_flags=pygame.BLEND_RGB_SUB)
    surface.fill(tuple(max(0, d) for d in difference), special_flags=pygame.BLEND_RGB_ADD)


def wrap_blit(canvas, piece, x, y, special_flags=0):
    """Blit so that anything leaving one edge re-enters at the opposite one."""
    width, height = canvas.get_size()
    w, h = piece.get_size()
    x, y = round(x) % width, round(y) % height
    for ox in ((0, -width) if x + w > width else (0,)):
        for oy in ((0, -height) if y + h > height else (0,)):
            canvas.blit(piece, (x + ox, y + oy), special_flags=special_flags)


def feather(size, hard=0.35, power=1.5):
    """Radial alpha mask with an opaque core and a smooth transparent rim."""
    mask = pygame.Surface((size, size), pygame.SRCALPHA)
    centre = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            distance = math.hypot(x - centre, y - centre) / (size / 2)
            fade = 1.0 if distance < hard else max(0.0, 1 - (distance - hard) / (1 - hard))
            mask.set_at((x, y), (255, 255, 255, round(255 * fade ** power)))
    return mask


def soft_blob(size, color, alpha, hard=0.2):
    blob = feather(size, hard, 1.8)
    blob.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
    blob.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    return blob


def equalize(sample, inset, contrast, keep=0.3):
    """Keep a specimen's clods but most of its framing light gradient goes."""
    inner = opaque(sample.subsurface(sample.get_rect().inflate(-2 * inset, -2 * inset)))
    size = inner.get_size()
    gradient = pygame.transform.smoothscale(pygame.transform.smoothscale(inner, (3, 3)), size)
    mean = pygame.transform.average_color(inner)[:3]
    flat = pygame.Surface(size, 0, 32)
    flat.fill(mean)
    parts = []
    for first, second, weight in ((inner, gradient, contrast), (gradient, flat, keep)):
        above = first.copy()
        above.blit(second, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        below = second.copy()
        below.blit(first, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
        k = (round(255 * min(weight, 1)),) * 3
        for part in (above, below):
            part.fill(k, special_flags=pygame.BLEND_RGB_MULT)
            if weight > 1:
                extra = part.copy()
                extra.fill((round(255 * (weight - 1)),) * 3, special_flags=pygame.BLEND_RGB_MULT)
                part.blit(extra, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        parts.append((above, below))
    result = flat
    for above, below in parts:
        result.blit(above, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        result.blit(below, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
    return result


def tone_field(size, cells, rng, low):
    """Seamless low-frequency multiplier in [low, 255]."""
    width, height = size
    gw, gh = cells
    grid = [[rng.randint(low, 255) for _ in range(gw)] for _ in range(gh)]
    small = pygame.Surface((gw + 2, gh + 2), 0, 32)
    for y in range(gh + 2):
        for x in range(gw + 2):
            value = grid[(y - 1) % gh][(x - 1) % gw]
            small.set_at((x, y), (value, value, value))
    cw, ch = width / gw, height / gh
    large = pygame.transform.smoothscale(small, (round((gw + 2) * cw), round((gh + 2) * ch)))
    return large.subsurface((round(cw), round(ch), width, height)).copy()


def ground_texture(samples, seed, contrast=1.15, inset=3, size=TEXTURE_SIZE):
    rng = random.Random(seed)
    width, height = size
    specimens = [equalize(sample, inset, contrast) for sample in samples]
    means = [pygame.transform.average_color(s)[:3] for s in specimens]
    target = tuple(round(sum(m[c] for m in means) / len(means)) for c in range(3))
    for specimen in specimens:
        shift_mean(specimen, target)
    canvas = pygame.Surface(size, 0, 32)
    # 1. Full coverage from opaque specimen squares; seams are hidden next.
    step = min(min(s.get_size()) for s in specimens) - 2
    for y in range(0, height, step):
        for x in range(0, width, step):
            source = rng.choice(specimens)
            sw, sh = source.get_size()
            area = (rng.randrange(sw - step + 1), rng.randrange(sh - step + 1), step, step)
            wrap_blit(canvas, source.subsurface(area), x, y)
    # 2. Many feathered stamps; no square boundary survives.
    patch = min(30, step)
    mask = feather(patch)
    for _ in range(round(width * height / patch ** 2 * 3.4)):
        source = rng.choice(specimens)
        sw, sh = source.get_size()
        piece = pygame.Surface((patch, patch), pygame.SRCALPHA)
        piece.blit(source, (0, 0), (rng.randrange(sw - patch + 1), rng.randrange(sh - patch + 1),
                                    patch, patch))
        if rng.random() < 0.5:
            piece = pygame.transform.flip(piece, True, False)
        piece.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        wrap_blit(canvas, piece, rng.randrange(width), rng.randrange(height))
    # 3. Gentle large-scale tone so the 480 x 400 period does not read.
    canvas.blit(tone_field(size, (8, 6), rng, 214), (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    shift_mean(canvas, target)
    return canvas


def palette(texture):
    """Shadow-to-highlight colours measured from a texture."""
    width, height = texture.get_size()
    pixels = sorted((tuple(texture.get_at((x, y)))[:3]
                     for y in range(1, height, 5) for x in range(2, width, 7)), key=luminance)

    def pick(q):
        lo = max(0, round((q - 0.03) * len(pixels)))
        hi = min(len(pixels), round((q + 0.03) * len(pixels)) + 1)
        window = pixels[lo:hi]
        return tuple(round(sum(c[i] for c in window) / len(window)) for i in range(3))

    return {'shadow': pick(0.05), 'dark': pick(0.22), 'body': pick(0.5),
            'light': pick(0.8), 'high': pick(0.96)}


# --------------------------------------------------------------------------
# Rear walls
# --------------------------------------------------------------------------

def _crack(surface, rng, start, color, light, steps, step_len=(3, 6)):
    x, y = start
    angle = rng.uniform(0, math.tau)
    points = [(x, y)]
    for _ in range(steps):
        angle += rng.uniform(-0.8, 0.8)
        length = rng.uniform(*step_len)
        x += math.cos(angle) * length
        y += math.sin(angle) * length
        points.append((x, y))
    if light:
        pygame.draw.lines(surface, light, False, [(px + 1, py + 1) for px, py in points])
    pygame.draw.lines(surface, color, False, points)
    return points


def rear_wall(texture, tint, seed, marks=False):
    """A darker, softer, monochrome copy of the ground with mining details."""
    rng = random.Random(seed)
    width, height = texture.get_size()
    margin = 6
    padded = pygame.Surface((width + 2 * margin, height + 2 * margin), 0, 32)
    for ox in (-width, 0, width):
        for oy in (-height, 0, height):
            padded.blit(texture, (margin + ox, margin + oy))
    padded = box_blur(padded, 1)
    wall = pygame.Surface(texture.get_size(), 0, 32)
    wall.blit(pygame.transform.grayscale(padded), (0, 0), (margin, margin, width, height))
    mean = pygame.transform.average_color(wall)[0]
    keep = 150  # Retain ~60% of the ground's local contrast.
    wall.fill((keep,) * 3, special_flags=pygame.BLEND_RGB_MULT)
    lift = round(mean * (1 - keep / 255))
    wall.fill((lift,) * 3, special_flags=pygame.BLEND_RGB_ADD)
    wall.fill(tint, special_flags=pygame.BLEND_RGB_MULT)
    base = pygame.transform.average_color(wall)[:3]
    dark = mix(base, (0, 0, 0), 0.5)
    pale = mix(base, (196, 184, 168), 0.22)
    # Broad shadowed hollows break up the period at room scale.
    for _ in range(9):
        size = rng.randrange(44, 96, 4)
        wrap_blit(wall, soft_blob(size, (0, 0, 0), rng.randrange(40, 70)),
                  rng.randrange(width), rng.randrange(height))
    # Rock faces in low relief: irregular slabs, lit along their upper
    # edges and shaded along the lower ones.
    for count, (small, large) in ((7, (44, 110)), (20, (14, 36))):
        for _ in range(count):
            w, h = rng.randrange(small, large), rng.randrange(round(small * 0.6), round(large * 0.6))
            piece = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
            points = []
            sides = rng.randrange(7, 11)
            for k in range(sides):
                angle = math.tau * (k + rng.uniform(-0.25, 0.25)) / sides
                radius = rng.uniform(0.78, 1.0)
                points.append((2 + w / 2 + math.cos(angle) * w / 2 * radius,
                               2 + h / 2 + math.sin(angle) * h / 2 * radius))
            pygame.draw.polygon(piece, (*pale, 15 if large > 50 else 24), points)
            for a, b in zip(points, points[1:] + points[:1]):
                upper = (a[1] + b[1]) / 2 < 2 + h / 2
                pygame.draw.line(piece, (*pale, 62) if upper else (*dark, 115), a, b,
                                 2 if large > 50 and not upper else 1)
            wrap_blit(wall, piece, rng.randrange(width), rng.randrange(height))
    # Hairline cracks.
    for _ in range(16):
        piece = pygame.Surface((64, 64), pygame.SRCALPHA)
        _crack(piece, rng, (32, 32), (*dark, 150), (*pale, 44), rng.randrange(4, 9))
        wrap_blit(wall, piece, rng.randrange(width), rng.randrange(height))
    # Small stone clusters.
    for _ in range(22):
        piece = pygame.Surface((14, 10), pygame.SRCALPHA)
        for _ in range(rng.randrange(2, 5)):
            sx, sy = rng.randrange(0, 10), rng.randrange(2, 7)
            sw, sh = rng.randrange(2, 5), rng.randrange(2, 4)
            pygame.draw.ellipse(piece, (*dark, 110), (sx, sy + 1, sw, sh))
            pygame.draw.ellipse(piece, (*pale, 80), (sx, sy, sw, sh))
        wrap_blit(wall, piece, rng.randrange(width), rng.randrange(height))
    if marks:
        # Pick scratches and the stains of supports removed long ago.
        for _ in range(12):
            piece = pygame.Surface((22, 18), pygame.SRCALPHA)
            slope = rng.choice((-1, 1))
            for n in range(rng.randrange(2, 5)):
                x0 = 4 + n * 4
                length = rng.randrange(6, 11)
                start, end = (x0, 3), (x0 + slope * length // 2, 3 + length)
                pygame.draw.line(piece, (*dark, 125), start, end)
                pygame.draw.line(piece, (*pale, 58), (start[0] + 1, start[1]), (end[0] + 1, end[1]))
            wrap_blit(wall, piece, rng.randrange(width), rng.randrange(height))
        for _ in range(4):
            vertical = rng.random() < 0.6
            w, h = (rng.randrange(4, 7), rng.randrange(28, 60)) if vertical else \
                   (rng.randrange(30, 64), rng.randrange(4, 6))
            piece = pygame.Surface((w, h), pygame.SRCALPHA)
            piece.fill((*mix(dark, (70, 40, 20), 0.35), 70))
            wrap_blit(wall, piece, rng.randrange(width), rng.randrange(height))
    return wall


# --------------------------------------------------------------------------
# Ground details (deterministic per-macro variants)
# --------------------------------------------------------------------------

def _pebble(surface, x, y, w, h, body, outline, light):
    pygame.draw.ellipse(surface, outline, (x, y, w + 1, h + 1))
    pygame.draw.ellipse(surface, body, (x, y, w, h))
    surface.set_at((x + max(1, w // 3), y + 1), light)


def ground_details(pal, stony, seed):
    """Small SRCALPHA sprites; each fits wholly inside one 40-pixel macro."""
    rng = random.Random(seed)
    shadow, dark, body, light, high = (pal[k] for k in ('shadow', 'dark', 'body', 'light', 'high'))
    stone_body = mix(body, (104, 102, 112), 0.55) if not stony else mix(body, (40, 42, 58), 0.35)
    stone_light = mix(light, (176, 174, 184), 0.55) if not stony else mix(high, (220, 225, 240), 0.2)
    stone_edge = mix(shadow, (16, 12, 14), 0.4)
    details = {'alt': [], 'pebbles': [], 'crack': [], 'dark': [], 'rare': []}
    for size in (26, 30, 34):
        tone = mix(light, high, 0.3) if not stony else mix(light, (150, 160, 190), 0.25)
        details['alt'].append(soft_blob(size, tone, 52))
    for size in (24, 30):
        details['dark'].append(soft_blob(size, mix(shadow, (0, 0, 0), 0.5), 70))
    for _ in range(4):
        piece = pygame.Surface((18, 14), pygame.SRCALPHA)
        for _ in range(rng.randrange(2, 4)):
            w, h = rng.randrange(4, 8), rng.randrange(3, 6)
            _pebble(piece, rng.randrange(0, 18 - w - 1), rng.randrange(0, 14 - h - 1), w, h,
                    stone_body, stone_edge, stone_light)
        details['pebbles'].append(piece)
    big = pygame.Surface((14, 11), pygame.SRCALPHA)
    _pebble(big, 1, 1, 11, 8, stone_body, stone_edge, stone_light)
    big.set_at((5, 2), stone_light)
    details['pebbles'].append(big)
    for _ in range(4):
        piece = pygame.Surface((30, 26), pygame.SRCALPHA)
        _crack(piece, rng, (rng.randrange(8, 22), rng.randrange(6, 20)),
               (*mix(shadow, (0, 0, 0), 0.4), 230), (*light, 110), rng.randrange(3, 6), (3, 5))
        details['crack'].append(piece)
    if stony:
        for color in ((120, 160, 230), (170, 110, 230)):
            piece = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.polygon(piece, stone_edge, ((5, 0), (9, 5), (5, 9), (1, 5)))
            pygame.draw.polygon(piece, color, ((5, 1), (8, 5), (5, 8), (2, 5)))
            piece.set_at((4, 3), (235, 240, 255))
            details['rare'].append(piece)
        vein = pygame.Surface((30, 20), pygame.SRCALPHA)
        _crack(vein, rng, (4, 10), (*mix(high, (230, 230, 240), 0.4), 150), None, 6, (3, 5))
        details['rare'].append(vein)
    else:
        root = pygame.Surface((30, 24), pygame.SRCALPHA)
        points = _crack(root, rng, (3, 4), (*mix(shadow, (60, 34, 18), 0.4), 220), None, 6, (3, 5))
        for px, py in points[2::2]:
            pygame.draw.line(root, (*mix(shadow, (60, 34, 18), 0.4), 200), (px, py),
                             (px + rng.randrange(-4, 5), py + rng.randrange(2, 5)))
        details['rare'].append(root)
        ore = pygame.Surface((14, 12), pygame.SRCALPHA)
        for x, y in ((2, 3), (7, 2), (5, 7), (10, 6)):
            pygame.draw.rect(ore, (70, 46, 18), (x, y, 3, 3))
            pygame.draw.rect(ore, (214, 168, 70), (x, y, 2, 2))
            ore.set_at((x, y), (246, 222, 150))
        details['rare'].append(ore)
    return details


# --------------------------------------------------------------------------
# Exposed edges: soil lips, shaded undersides, side rims, rounded corners
# --------------------------------------------------------------------------

def edge_pieces(pal, seed, cell=8):
    """Overlays drawn on boundary cells; protrusions are visual only."""
    rng = random.Random(seed)
    shadow, dark, body, light, high = (pal[k] for k in ('shadow', 'dark', 'body', 'light', 'high'))
    rim = mix(shadow, (8, 6, 10), 0.35)
    hang = mix(dark, shadow, 0.35)
    lip = mix(light, high, 0.45)
    pieces = {'top': [], 'bottom': [], 'left': [], 'right': [], 'fillet': {}}
    # Floor lips: 8 x 4 at (x, y - 1); row 0 is above the cell.
    for _ in range(5):
        piece = pygame.Surface((cell, 4), pygame.SRCALPHA)
        for x in range(cell):
            if rng.random() < 0.22:
                piece.set_at((x, 0), (*light, 230))
            piece.set_at((x, 1), (*(lip if rng.random() < 0.8 else light), 255))
            if rng.random() < 0.55:
                piece.set_at((x, 2), (*light, 150))
            if rng.random() < 0.12:
                piece.set_at((x, 3), (*shadow, 160))
        pieces['top'].append(piece)
    # Undersides: 8 x 10 at (x, y + 5); rows 3.. hang below the cell.
    for variant in range(8):
        piece = pygame.Surface((cell, 10), pygame.SRCALPHA)
        piece.fill((*shadow, 55), (0, 0, cell, 1))
        piece.fill((*shadow, 105), (0, 1, cell, 1))
        piece.fill((*rim, 215), (0, 2, cell, 1))
        style = variant % 4
        if style == 0:
            w, depth = rng.randrange(3, 6), rng.randrange(2, 4)
            x = rng.randrange(0, cell - w + 1)
            pygame.draw.ellipse(piece, (*rim, 235), (x, 1, w, depth * 2 + 1))
            pygame.draw.ellipse(piece, (*hang, 255), (x, 1, w - 1, depth * 2))
        elif style == 1:
            x = rng.randrange(1, cell - 1)
            length = rng.randrange(3, 7)
            pygame.draw.line(piece, (*mix(rim, (70, 40, 22), 0.3), 230), (x, 3), (x, 2 + length))
            piece.set_at((x + rng.choice((-1, 1)), 3 + length // 2), (*rim, 200))
        elif style == 2:
            for x in rng.sample(range(cell), 2):
                piece.fill((*hang, 255), (x, 3, 1, rng.randrange(1, 3)))
        pieces['bottom'].append(piece)
    # Side rims: 4 x 8 at (x - 2, y); columns 0-1 outside, 2-3 inside.
    for _ in range(5):
        piece = pygame.Surface((4, cell), pygame.SRCALPHA)
        piece.fill((*rim, 165), (2, 0, 1, cell))
        piece.fill((*shadow, 70), (3, 0, 1, cell))
        if rng.random() < 0.6:
            y = rng.randrange(1, cell - 3)
            h = rng.randrange(2, 4)
            piece.fill((*rim, 230), (0, y, 2, h))
            piece.fill((*dark, 255), (1, y, 1, h - 1))
        pieces['left'].append(piece)
        pieces['right'].append(pygame.transform.flip(piece, True, False))
    # Concave corners: a stepped fillet of loose soil or shaded overhang.
    floor = pygame.Surface((cell, cell), pygame.SRCALPHA)
    for step in range(4):
        floor.fill((*body, 255), (0, cell - 1 - step, 4 - step, 1))
        floor.set_at((3 - step, cell - 1 - step), (*lip, 255))
    pieces['fillet']['bl'] = floor
    pieces['fillet']['br'] = pygame.transform.flip(floor, True, False)
    ceiling = pygame.Surface((cell, cell), pygame.SRCALPHA)
    for step in range(4):
        ceiling.fill((*hang, 255), (0, step, 4 - step, 1))
        ceiling.set_at((3 - step, step), (*rim, 255))
    pieces['fillet']['tl'] = ceiling
    pieces['fillet']['tr'] = pygame.transform.flip(ceiling, True, False)
    return pieces


def border_masks(size=40, depth=18, variants=3, seed=7):
    """Alpha ramps for feathering a neighbouring material into a macro.

    Keyed by side ('top', 'bottom', 'left', 'right'); each has a few ragged
    variants so feathered borders do not repeat a straight line.
    """
    rng = random.Random(seed)
    masks = {side: [] for side in ('top', 'bottom', 'left', 'right')}
    for _ in range(variants):
        ramp = pygame.Surface((size, size), pygame.SRCALPHA)
        offsets = []
        wobble = 0.0
        for _ in range(size):
            wobble = max(-4.0, min(4.0, wobble + rng.uniform(-1.2, 1.2)))
            offsets.append(wobble)
        for x in range(size):
            for y in range(size):
                t = (y + offsets[x]) / depth
                alpha = 0 if t >= 1 else round(215 * (1 - max(0.0, t)) ** 1.4)
                ramp.set_at((x, y), (255, 255, 255, alpha))
        masks['top'].append(ramp)
        masks['bottom'].append(pygame.transform.flip(ramp, False, True))
        masks['left'].append(pygame.transform.rotate(ramp, 90))
        masks['right'].append(pygame.transform.rotate(ramp, -90))
    return masks


def corner_erasers(cell=8):
    """Multiply masks that round convex corners; keyed by corner name."""
    base = pygame.Surface((cell, cell), pygame.SRCALPHA)
    base.fill((255, 255, 255, 255))
    for x, y in ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (0, 2)):
        base.set_at((x, y), (255, 255, 255, 0))
    return {'tl': base, 'tr': pygame.transform.flip(base, True, False),
            'bl': pygame.transform.flip(base, False, True),
            'br': pygame.transform.flip(base, True, True)}


def detail_category(roll):
    for limit, category in DETAIL_WEIGHTS:
        if roll < limit:
            return category
    return None
