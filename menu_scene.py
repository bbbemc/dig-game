"""Cinematic Main Menu Scene: 6-layer parallax underground diorama and ambient animations.

Separates the Main Menu environment, parallax camera, pixel-art diorama layers,
and continuous environmental animations from the menu UI state in ``ui.py``.

Layers (back to front):
1. Layer 1 (depth 0.12): Very distant cave background, deep arches, drifting cave shadows/fog.
2. Layer 2 (depth 0.28): Dark cave walls, arched ceiling, hanging roots/vines, stalactites.
3. Layer 3 (depth 0.48): Distant wooden mine frame, earth mound, timber doorway & glowing red eyes.
4. Layer 4 (depth 0.72): Main ground platform, cliff stone edging, tall ladder, dirt/rocks & lava pocket.
5. Layer 5 (depth 0.90): Animated miner (breathing, head motion, flickering lamp), crate, bomb & rocks.
6. Layer 6 (depth 1.15): Floating glowing particles, falling ceiling dust/pebbles & dynamic lighting.
"""

from array import array
import math
import random

import pygame

from config import SCREEN_H, SCREEN_W

# Base pixel-art grid: 240 x 160 scaled 4x -> 960 x 640 crisp pixel art.
PIXEL = 4
BASE_W = SCREEN_W // PIXEL
BASE_H = SCREEN_H // PIXEL
PAD_BASE = 8  # 32 px margin on each side so parallax shifts never expose edges
CANVAS_W = BASE_W + 2 * PAD_BASE
CANVAS_H = BASE_H + 2 * PAD_BASE
PAD_PX = PAD_BASE * PIXEL

VOID_COLOR = (11, 12, 18)


# ---------------------------------------------------------------------------
# Reusable animation & interpolation functions
# ---------------------------------------------------------------------------
def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def lerp(a, b, t):
    return a + (b - a) * clamp(t)


def lerp_color(c1, c2, t):
    t = clamp(t)
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))


def ease_out_cubic(t):
    t = clamp(t)
    return 1.0 - (1.0 - t) ** 3


def ease_out_back(t, overshoot=1.35):
    t = clamp(t) - 1.0
    return 1.0 + t * t * ((overshoot + 1.0) * t + overshoot)


def ease_in_out_quad(t):
    t = clamp(t)
    return 2.0 * t * t if t < 0.5 else 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0


def smooth_damp(current, target, speed, dt):
    if dt <= 0:
        return current
    return current + (target - current) * (1.0 - math.exp(-speed * dt))


def flicker_wave(time_s, speed=1.0, phase=0.0):
    """Smooth multi-harmonic lantern/lava flicker in [0, 1]."""
    w = (0.55 * math.sin(time_s * 6.7 * speed + phase)
         + 0.30 * math.sin(time_s * 13.3 * speed + phase * 1.9)
         + 0.15 * math.cos(time_s * 23.1 * speed + phase * 0.7))
    return clamp(0.5 + 0.5 * w)


# ---------------------------------------------------------------------------
# Lightweight procedural menu sound effects (respects global SFX volume)
# ---------------------------------------------------------------------------
class MenuAudio:
    """Synthesizes subtle pixel-art UI hover/select/confirm sounds and ambient loop."""

    def __init__(self):
        self._sounds = {}
        self._ambient = None
        self._ambient_channel = None
        self._ready = False
        self.music_volume = 0.70
        self.sfx_volume = 0.80

    def _ensure(self):
        if self._ready:
            return
        self._ready = True
        try:
            if not pygame.mixer.get_init():
                return
            rate, size, channels = pygame.mixer.get_init()
            if abs(size) != 16:
                return
            self._sounds['hover'] = self._make_tone(rate, channels, 520.0, 680.0, 0.038, 0.22)
            self._sounds['select'] = self._make_tone(rate, channels, 620.0, 920.0, 0.085, 0.34)
            self._sounds['back'] = self._make_tone(rate, channels, 580.0, 390.0, 0.075, 0.28)
            self._sounds['slider'] = self._make_tone(rate, channels, 460.0, 510.0, 0.028, 0.18)
            self._ambient = self._make_ambient_drone(rate, channels, 2.0, 0.06)
        except Exception:
            self._sounds.clear()
            self._ambient = None

    @staticmethod
    def _make_ambient_drone(rate, channels, duration, amp):
        """A seamless 2.0s warm subterranean harmonic drone loop."""
        frames = max(1, int(rate * duration))
        pcm = array('h')
        for n in range(frames):
            t = n / frames
            p1 = 2.0 * math.pi * 55.0 * t * duration
            p2 = 2.0 * math.pi * 82.5 * t * duration
            p3 = 2.0 * math.pi * 110.0 * t * duration
            lfo = 0.78 + 0.22 * math.sin(2.0 * math.pi * 1.0 * t)
            sample = (0.55 * math.sin(p1) + 0.30 * math.sin(p2) + 0.15 * math.sin(p3)) * amp * lfo
            val = max(-32767, min(32767, round(sample * 32767)))
            for _ in range(channels):
                pcm.append(val)
        return pygame.mixer.Sound(buffer=pcm.tobytes())

    @staticmethod
    def _make_tone(rate, channels, f0, f1, duration, amp):
        frames = max(1, int(rate * duration))
        pcm = array('h')
        phase = 0.0
        for n in range(frames):
            t = n / frames
            freq = f0 + (f1 - f0) * (t ** 0.7)
            phase += 2.0 * math.pi * freq / rate
            env = math.sin(math.pi * min(1.0, t / 0.15)) if t < 0.15 else (1.0 - t) ** 1.8
            sample = (0.75 * math.sin(phase) + 0.25 * math.sin(phase * 2.0)) * amp * env
            val = max(-32767, min(32767, round(sample * 32767)))
            for _ in range(channels):
                pcm.append(val)
        return pygame.mixer.Sound(buffer=pcm.tobytes())

    def set_music_volume(self, volume):
        self.music_volume = clamp(volume, 0.0, 1.0)
        try:
            if self._ambient is not None:
                self._ambient.set_volume(self.music_volume * 0.35)
        except Exception:
            pass

    def set_sfx_volume(self, volume):
        self.sfx_volume = clamp(volume, 0.0, 1.0)
        try:
            from audio import sounds
            sounds().set_volume(self.sfx_volume)
        except Exception:
            pass

    def update_ambient(self, active=True, fade=1.0):
        try:
            from audio import sounds
            if not sounds().enabled or not pygame.mixer.get_init():
                return
            self._ensure()
            if self._ambient is None:
                return
            vol = self.music_volume * clamp(fade, 0.0, 1.0) * 0.35
            if active and vol > 0.002:
                self._ambient.set_volume(vol)
                if self._ambient_channel is None or not self._ambient_channel.get_busy():
                    self._ambient_channel = self._ambient.play(loops=-1)
            else:
                if self._ambient_channel is not None and self._ambient_channel.get_busy():
                    self._ambient_channel.stop()
        except Exception:
            pass

    def play(self, kind):
        try:
            from audio import sounds
            bank = sounds()
            if not bank.enabled:
                return
            vol = min(bank.volume, self.sfx_volume)
            if vol <= 0.001:
                return
            self._ensure()
            snd = self._sounds.get(kind)
            if snd is not None:
                snd.set_volume(vol * 0.55)
                snd.play()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Parallax Camera Controller
# ---------------------------------------------------------------------------
class ParallaxCamera:
    """Combines subtle autonomous camera drift with smooth mouse parallax."""

    MAX_MOUSE_X = 14.0
    MAX_MOUSE_Y = 9.0
    DRIFT_X = 4.5
    DRIFT_Y = 3.0
    SMOOTH_SPEED = 6.5

    def __init__(self):
        self.time = 0.0
        self.mouse_norm_x = 0.0
        self.mouse_norm_y = 0.0
        self.smooth_x = 0.0
        self.smooth_y = 0.0

    def reset(self):
        self.time = 0.0
        self.mouse_norm_x = 0.0
        self.mouse_norm_y = 0.0
        self.smooth_x = 0.0
        self.smooth_y = 0.0

    def update(self, dt, mouse_pos=None):
        self.time += dt
        if mouse_pos is not None:
            mx, my = mouse_pos
            if 0 <= mx <= SCREEN_W and 0 <= my <= SCREEN_H:
                self.mouse_norm_x = clamp((mx - SCREEN_W * 0.5) / (SCREEN_W * 0.5), -1.0, 1.0)
                self.mouse_norm_y = clamp((my - SCREEN_H * 0.5) / (SCREEN_H * 0.5), -1.0, 1.0)
        target_x = self.mouse_norm_x * self.MAX_MOUSE_X
        target_y = self.mouse_norm_y * self.MAX_MOUSE_Y
        self.smooth_x = smooth_damp(self.smooth_x, target_x, self.SMOOTH_SPEED, dt)
        self.smooth_y = smooth_damp(self.smooth_y, target_y, self.SMOOTH_SPEED, dt)

    def offset_for(self, depth):
        """Return (dx, dy) pixel offset for a layer with the given depth factor."""
        drift_x = math.sin(self.time * 0.55) * self.DRIFT_X + math.cos(self.time * 0.27) * 1.8
        drift_y = math.cos(self.time * 0.43) * self.DRIFT_Y + math.sin(self.time * 0.31) * 1.2
        dx = (drift_x + self.smooth_x) * depth
        dy = (drift_y + self.smooth_y) * depth
        return round(dx), round(dy)


# ---------------------------------------------------------------------------
# Pixel-art helper routines on the base 240 x 160 grid (+ padding)
# ---------------------------------------------------------------------------
def _base_surface():
    return pygame.Surface((CANVAS_W, CANVAS_H), pygame.SRCALPHA)


def _upscale(surface):
    w, h = surface.get_size()
    return pygame.transform.scale(surface, (w * PIXEL, h * PIXEL))


def _hash2d(x, y, seed=0):
    """Deterministic integer hash in [0, 255] without directional striping."""
    n = (x * 374761393 + y * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFF)


def _cave_arch_top(bx):
    """Y coordinate (in base 240x160 coords) of the cave ceiling arch at column bx."""
    if bx < 95:
        return 165
    # Smooth arch profile matching the reference composition:
    # Steep left wall rising from x=95..128, high dome x=130..205, gentle slope to right edge.
    if bx < 108:
        t = (bx - 95) / 13.0
        return round(160 - 78 * (t ** 0.75))
    if bx < 135:
        t = (bx - 108) / 27.0
        return round(82 - 44 * ease_out_cubic(t))
    if bx < 185:
        t = (bx - 135) / 50.0
        return round(38 - 10 * math.sin(math.pi * t))
    t = clamp((bx - 185) / 60.0)
    return round(38 + 10 * (t ** 1.3))


def _draw_rock_cluster(surface, cx, cy, rx, ry, pal, rng):
    """Draw a chunky pixel-art boulder with highlight, body, shadow, and outline."""
    outline, shadow, body, light = pal
    for y in range(cy - ry - 1, cy + ry + 2):
        for x in range(cx - rx - 1, cx + rx + 2):
            if not (0 <= x < surface.get_width() and 0 <= y < surface.get_height()):
                continue
            nx = (x - cx) / max(1.0, rx)
            ny = (y - cy) / max(1.0, ry)
            d = nx * nx + ny * ny + (rng.random() - 0.5) * 0.18
            if d <= 1.05:
                if d > 0.78:
                    surface.set_at((x, y), outline)
                elif ny < -0.22 and nx < 0.35:
                    surface.set_at((x, y), light)
                elif ny > 0.28 or nx > 0.42:
                    surface.set_at((x, y), shadow)
                else:
                    surface.set_at((x, y), body)


# ---------------------------------------------------------------------------
# Main Menu 6-Layer Environment & Ambient Animation System
# ---------------------------------------------------------------------------
class MenuEnvironment:
    """Builds and animates the 6 parallax layers of the Main Menu underground scene."""

    LAYER_DEPTHS = {
        1: 0.12,  # Distant cave background & silhouettes
        2: 0.28,  # Dark cave walls, arch ceiling, roots & stalactites
        3: 0.48,  # Wooden mine frame, background mound & doorway with red eyes
        4: 0.72,  # Main platform, cliff stones, ladder & subterranean lava chamber
        5: 0.90,  # Miner, crate, bomb & foreground rocks
        6: 1.15,  # Floating particles, falling ceiling dust/rocks & dynamic lighting
    }

    def __init__(self, art=None):
        self.art = art
        self.camera = ParallaxCamera()
        self.time = 0.0
        self.rng = random.Random(107)

        # Build static pixel-art layer surfaces once
        self.layer1_distant = _upscale(self._build_layer1_distant())
        self.layer2_walls = _upscale(self._build_layer2_walls())
        self.layer3_structures = _upscale(self._build_layer3_structures())
        self.layer4_platform = _upscale(self._build_layer4_platform())
        self.layer5_static = _upscale(self._build_layer5_static_props())
        self.layer_fg_details = _upscale(self._build_fg_details())

        # Animated sprite caches (Miner frames, swaying roots, swaying chains, lights)
        self.miner_frames = self._build_miner_frames()
        self.root_frames = [
            _upscale(self._build_hanging_roots(sway=-1)),
            _upscale(self._build_hanging_roots(sway=0)),
            _upscale(self._build_hanging_roots(sway=1)),
        ]
        self.chain_frames = [
            _upscale(self._build_hanging_chains(sway=-1)),
            _upscale(self._build_hanging_chains(sway=0)),
            _upscale(self._build_hanging_chains(sway=1)),
        ]
        self.pulley_frames = [
            _upscale(self._build_hanging_pulley(sway=-1)),
            _upscale(self._build_hanging_pulley(sway=0)),
            _upscale(self._build_hanging_pulley(sway=1)),
        ]
        self.shadow_clouds = self._build_shadow_clouds()
        self.light_cache = {}
        self.dark_veil = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

        # Live ambient particle & animation pools
        self.fireflies = []
        self.ceiling_dust = []
        self.falling_rocks = []
        self.rock_splashes = []
        self.lava_bubbles = []
        self.lava_embers = []
        self.cavern_embers = []
        self.fuse_sparks = []
        self.water_drips = []
        self._rock_timer = 1.4
        self._drip_timer = 0.75
        self._eye_blink_timer = 3.8
        self._eye_blink_dur = 0.0
        self._miner_blink_timer = 2.9
        self._miner_blink_dur = 0.0
        self._init_ambient_particles()

    def reset(self):
        self.camera.reset()
        self.time = 0.0
        self._rock_timer = 1.4
        self._init_ambient_particles()

    # ------------------------------------------------------------------
    # Layer 1: Distant cave background & silhouettes
    # ------------------------------------------------------------------
    def _build_layer1_distant(self):
        surf = _base_surface()
        surf.fill(VOID_COLOR)
        rng = random.Random(11)
        ox, oy = PAD_BASE, PAD_BASE
        for by in range(20, BASE_H):
            for bx in range(90, BASE_W + PAD_BASE):
                x, y = ox + bx, oy + by
                if not (0 <= x < CANVAS_W and 0 <= y < CANVAS_H):
                    continue
                # Distant cavern wall gradient with cool slate-blue atmospheric depth
                wave = math.sin(bx * 0.09 + by * 0.05) * 2.5 + math.cos(bx * 0.21 - by * 0.14) * 1.5
                # Subtle deep cavern glow pocket around (158, 62) for background-foreground depth
                dist_glow = max(0.0, 1.0 - math.hypot((bx - 158) / 38.0, (by - 62) / 28.0))
                shade = 17 + int((by / BASE_H) * 5 + wave + dist_glow * 7.0)
                r = clamp(shade, 13, 28)
                g = clamp(shade + int(dist_glow * 3), 14, 30)
                b = clamp(shade + 6 + int(dist_glow * 6), 19, 42)
                surf.set_at((x, y), (r, g, b, 255))

        # Distant rock pillar silhouettes & deep cavern arches with subtle rim highlight
        for px, top_y, bot_y, width in ((132, 34, 98, 9), (166, 30, 96, 12), (208, 34, 96, 10)):
            for by in range(top_y, bot_y):
                spread = abs(by - (top_y + bot_y) // 2) // 10
                w = width + spread
                for bx in range(px - w // 2, px + w // 2 + 1):
                    x, y = ox + bx, oy + by
                    if 0 <= x < CANVAS_W and 0 <= y < CANVAS_H:
                        if bx == px - w // 2 and by % 2 == 0:
                            surf.set_at((x, y), (26, 29, 40, 255))
                        else:
                            surf.set_at((x, y), (15, 16, 24, 255))

        # Distant stalagmite silhouettes along the deep horizon
        for bx in range(105, BASE_W, 7):
            h = rng.randint(5, 14)
            for dy in range(h):
                w = max(1, (h - dy) // 3)
                for dx in range(-w, w + 1):
                    x, y = ox + bx + dx, oy + 92 - dy
                    if 0 <= x < CANVAS_W and 0 <= y < CANVAS_H:
                        surf.set_at((x, y), (22, 23, 33, 255))
        return surf

    def _build_shadow_clouds(self):
        """Soft drifting shadow/fog patches for Layer 1."""
        clouds = []
        for w, h, alpha in ((180, 56, 38), (220, 64, 30), (160, 48, 34)):
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            cx, cy = w / 2.0, h / 2.0
            for y in range(h):
                for x in range(w):
                    d = math.hypot((x - cx) / cx, (y - cy) / cy)
                    if d < 1.0:
                        a = round(alpha * (1.0 - d) ** 1.8)
                        surf.set_at((x, y), (8, 8, 14, a))
            clouds.append(surf)
        return clouds

    # ------------------------------------------------------------------
    # Layer 2: Dark cave walls, arch ceiling, stalactites & roots
    # ------------------------------------------------------------------
    def _build_layer2_walls(self):
        surf = _base_surface()
        rng = random.Random(22)
        ox, oy = PAD_BASE, PAD_BASE

        # Outer black cave mask with stepped rocky inner rim & ceiling rock clusters
        for by in range(-PAD_BASE, BASE_H + PAD_BASE):
            for bx in range(-PAD_BASE, BASE_W + PAD_BASE):
                x, y = ox + bx, oy + by
                arch_y = _cave_arch_top(bx)
                # Left of the cliff (bx < 118 below y=92) is also solid dark void
                in_left_void = bx < 118 and by >= 90 and bx < 102 + (by - 90) // 4
                if by < arch_y or bx < 95 or in_left_void:
                    surf.set_at((x, y), VOID_COLOR)
                elif by < arch_y + 4 or (bx < 103 and by < 105):
                    # Stepped rocky inner rim of the cave ceiling arch
                    surf.set_at((x, y), (25, 25, 35, 255))
                elif by < arch_y + 8:
                    h = _hash2d(bx // 2, by // 2, 41)
                    if h > 110:
                        surf.set_at((x, y), (31, 31, 42, 255))
                    elif h > 65:
                        surf.set_at((x, y), (22, 22, 31, 255))

        # Additional chiseled rock ledges along the left cave wall & ceiling arch
        wall_rock_pal = (
            (14, 14, 20, 255),
            (24, 24, 34, 255),
            (34, 35, 46, 255),
            (46, 48, 60, 255),
        )
        for rx_c, ry_c, rw, rh in (
            (108, 66, 5, 3), (114, 54, 6, 3), (122, 43, 6, 3),
            (146, 32, 6, 2), (168, 31, 7, 2), (222, 42, 6, 3), (232, 47, 6, 3),
        ):
            if ry_c >= _cave_arch_top(rx_c):
                _draw_rock_cluster(surf, ox + rx_c, oy + ry_c, rw, rh, wall_rock_pal, rng)

        # Upper-right cave ceiling stalactites + smaller secondary ceiling spikes
        stalactites = (
            (120, 3, 7),
            (148, 3, 8),
            (176, 3, 9),
            (184, 5, 16),
            (191, 4, 11),
            (196, 6, 19),
            (204, 4, 12),
            (211, 5, 14),
            (219, 3, 9),
        )
        for sx, sw, sh in stalactites:
            sy = _cave_arch_top(sx) + 1
            for dy in range(sh):
                t = dy / max(1, sh - 1)
                half = max(0, round((sw * 0.5) * (1.0 - t ** 1.15)))
                for dx in range(-half - 1, half + 2):
                    bx, by = sx + dx, sy + dy
                    if by < _cave_arch_top(bx):
                        continue
                    x, y = ox + bx, oy + by
                    if not (0 <= x < CANVAS_W and 0 <= y < CANVAS_H):
                        continue
                    if abs(dx) > half or dy == sh - 1:
                        surf.set_at((x, y), (14, 14, 20, 255))
                    elif dx < 0:
                        surf.set_at((x, y), (48, 49, 60, 255))
                    elif dx == 0:
                        surf.set_at((x, y), (37, 38, 48, 255))
                    else:
                        surf.set_at((x, y), (26, 27, 36, 255))
        return surf

    def _build_hanging_chains(self, sway=0):
        """Pixel-art iron chains hanging from the cave ceiling arch."""
        surf = _base_surface()
        ox, oy = PAD_BASE, PAD_BASE
        c_out = (14, 14, 18, 255)
        c_dark = (32, 34, 42, 255)
        c_mid = (50, 52, 62, 255)
        c_hi = (74, 78, 90, 255)
        c_warm = (96, 78, 60, 255)  # Subtle warm reflection on lower links

        chains = (
            (119, 52, 14),
            (163, 30, 14),
            (225, 39, 13),
        )
        for cx, start_y, length in chains:
            top_y = max(start_y, _cave_arch_top(cx) + 1)
            for dy in range(length):
                by = top_y + dy
                shift = round(sway * (dy / max(1, length - 1))) if dy > 4 else 0
                px = ox + cx + shift
                py = oy + by
                if not (2 <= px < CANVAS_W - 2 and 2 <= py < CANVAS_H - 2):
                    continue
                link_phase = dy % 3
                is_lower = dy > length * 0.65
                hi_col = c_warm if is_lower else c_hi
                if link_phase == 0:
                    # Narrow vertical link profile
                    surf.set_at((px, py), hi_col)
                    surf.set_at((px + 1, py), c_out)
                elif link_phase == 1:
                    # Open loop link profile
                    surf.set_at((px - 1, py), c_mid)
                    surf.set_at((px, py), c_out)
                    surf.set_at((px + 1, py), c_dark)
                else:
                    surf.set_at((px, py), c_mid)
                    surf.set_at((px + 1, py), c_out)
            # Bottom iron hook/ring
            end_x = ox + cx + sway
            end_y = oy + top_y + length
            surf.set_at((end_x - 1, end_y), c_mid)
            surf.set_at((end_x, end_y + 1), c_dark)
            surf.set_at((end_x + 1, end_y), c_out)
        return surf

    def _build_fg_details(self):
        """Foreground silhouettes (support beam, near-camera rocks & subtle edge shadow)."""
        surf = _base_surface()
        rng = random.Random(88)
        ox, oy = PAD_BASE, PAD_BASE

        # 1. Foreground silhouetted wooden support post & diagonal brace on far right (bx=238..246, by=40..91)
        b_out = (12, 10, 12, 255)
        b_dark = (28, 20, 18, 255)
        b_mid = (42, 30, 24, 255)
        b_rim = (76, 52, 36, 255)  # Warm rim from entrance/lava light
        for by in range(42, 90):
            for bx in range(241, 246):
                px, py = ox + bx, oy + by
                if 0 <= px < CANVAS_W and 0 <= py < CANVAS_H:
                    if bx == 241:
                        surf.set_at((px, py), b_rim if by % 3 else b_mid)
                    elif bx == 242:
                        surf.set_at((px, py), b_mid)
                    elif bx == 245:
                        surf.set_at((px, py), b_out)
                    else:
                        surf.set_at((px, py), b_dark)
        # Diagonal upper-right timber strut
        for step in range(10):
            for w in range(3):
                px = ox + 233 + step
                py = oy + 43 + step + w
                if 0 <= px < CANVAS_W and 0 <= py < CANVAS_H:
                    surf.set_at((px, py), b_rim if w == 0 else b_dark)

        # 2. Small foreground rock silhouettes near the bottom camera edge
        fg_dark_pal = (
            (10, 9, 12, 255),
            (20, 18, 22, 255),
            (32, 28, 32, 255),
            (84, 48, 34, 255),  # Subtle warm lava rim on top edge
        )
        _draw_rock_cluster(surf, ox + 238, oy + 160, 7, 4, fg_dark_pal, rng)
        _draw_rock_cluster(surf, ox + 229, oy + 162, 5, 3, fg_dark_pal, rng)
        _draw_rock_cluster(surf, ox + 118, oy + 161, 5, 3, (
            (10, 9, 12, 255), (18, 17, 22, 255), (26, 25, 32, 255), (42, 40, 48, 255)
        ), rng)
        return surf

    def _build_hanging_roots(self, sway=0):
        """Gnarled hanging roots and looped vine under the upper cave arch."""
        surf = _base_surface()
        ox, oy = PAD_BASE, PAD_BASE
        dark = (22, 18, 16, 255)
        body = (52, 41, 32, 255)
        light = (70, 55, 42, 255)

        def root_strand(points):
            for idx in range(len(points) - 1):
                x0, y0 = points[idx]
                x1, y1 = points[idx + 1]
                steps = max(abs(x1 - x0), abs(y1 - y0), 1)
                for s in range(steps + 1):
                    t = s / steps
                    bx = round(x0 + (x1 - x0) * t)
                    by = round(y0 + (y1 - y0) * t)
                    shift = sway if by > 42 else 0
                    px, py = ox + bx + shift, oy + by
                    if 0 <= px < CANVAS_W and 0 <= py < CANVAS_H:
                        surf.set_at((px - 1, py), dark)
                        surf.set_at((px, py), light if idx == 0 else body)
                        surf.set_at((px + 1, py), dark)

        # Left hanging tendrils (x ~ 125..146)
        root_strand([(125, 41), (124, 47), (126, 52)])
        root_strand([(133, 36), (132, 44), (130, 51), (132, 57)])
        root_strand([(139, 34), (138, 43), (141, 51), (139, 59)])
        root_strand([(138, 44), (135, 49), (134, 54)])
        # Center looped root on the ceiling arch (x ~ 150..162)
        root_strand([(150, 30), (152, 36), (156, 38), (160, 35), (162, 29)])
        root_strand([(156, 38), (155, 43)])
        # Small right root tendril (x ~ 171)
        root_strand([(171, 30), (172, 36), (170, 41)])
        return surf

    # ------------------------------------------------------------------
    # Layer 3: Wooden mine structures, background mound & doorway
    # ------------------------------------------------------------------
    def _build_layer3_structures(self):
        surf = _base_surface()
        ox, oy = PAD_BASE, PAD_BASE

        # 1. Distant silhouetted wooden mine support frame (x=140..176, y=47..92)
        frame_out = (20, 17, 18, 255)
        frame_dark = (34, 28, 26, 255)
        frame_mid = (45, 36, 32, 255)
        frame_hi = (56, 45, 39, 255)

        def draw_beam_box(x0, y0, x1, y1):
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    px, py = ox + x, oy + y
                    if y in (y0, y1) or x in (x0, x1):
                        surf.set_at((px, py), frame_out)
                    elif y == y0 + 1 or x == x0 + 1:
                        surf.set_at((px, py), frame_hi)
                    elif y == y1 - 1 or x == x1 - 1:
                        surf.set_at((px, py), frame_dark)
                    else:
                        surf.set_at((px, py), frame_mid)

        # Diagonal braces first, then posts, then top lintel
        for step in range(11):
            for w in range(3):
                surf.set_at((ox + 146 + step, oy + 60 - step + w), frame_mid)
                surf.set_at((ox + 170 - step, oy + 60 - step + w), frame_mid)
        draw_beam_box(143, 50, 146, 92)
        draw_beam_box(170, 50, 173, 92)
        draw_beam_box(139, 47, 177, 51)

        # 2. Background rocky/earth mound behind the mine entrance (x=162..238, y=43..92)
        mound_out = (24, 20, 19, 255)
        mound_dark = (38, 32, 29, 255)
        mound_mid = (50, 42, 37, 255)
        mound_hi = (64, 54, 46, 255)
        for by in range(42, 93):
            for bx in range(152, 239):
                # Sloping mound silhouette rising from left (x=152, y=90) to peak behind doorway (x=208, y=43)
                if bx < 182:
                    top = 90 - int(((bx - 152) / 30.0) ** 1.1 * 28)
                elif bx < 216:
                    top = 44 + int(abs(bx - 202) * 0.35)
                else:
                    top = 48 + int((bx - 216) * 1.4)
                top += int(math.sin(bx * 0.45) * 1.5)
                if by < top:
                    continue
                px, py = ox + bx, oy + by
                patch = _hash2d(bx // 2, by // 2, 31)
                speck = _hash2d(bx, by, 73)
                if by == top:
                    surf.set_at((px, py), mound_out)
                elif by == top + 1:
                    surf.set_at((px, py), mound_hi)
                elif by < top + 4 and patch > 110:
                    surf.set_at((px, py), mound_hi)
                elif patch < 75 or speck < 36:
                    surf.set_at((px, py), mound_dark)
                elif patch > 195 and by < 74:
                    surf.set_at((px, py), mound_hi)
                else:
                    surf.set_at((px, py), mound_mid)

        # 3. Heavy Wooden Mine Entrance Doorway (x=194..229, y=54..92)
        w_out = (20, 14, 12, 255)
        w_dark = (74, 44, 25, 255)
        w_mid = (108, 66, 36, 255)
        w_light = (138, 86, 48, 255)
        w_hi = (162, 106, 62, 255)

        # Pitch-black tunnel interior (x=201..221, y=61..92)
        for by in range(60, 93):
            for bx in range(200, 223):
                surf.set_at((ox + bx, oy + by), (8, 8, 12, 255))

        # Left and right vertical timber posts (x=195..201 and x=221..227, y=60..92)
        for post_x0, post_x1 in ((195, 201), (221, 227)):
            for by in range(60, 93):
                for bx in range(post_x0, post_x1 + 1):
                    px, py = ox + bx, oy + by
                    if bx in (post_x0, post_x1) or by == 92:
                        surf.set_at((px, py), w_out)
                    elif bx == post_x0 + 1:
                        surf.set_at((px, py), w_light)
                    elif bx == post_x1 - 1:
                        surf.set_at((px, py), w_dark)
                    elif bx == post_x0 + 3 and by % 6 != 0:
                        surf.set_at((px, py), w_dark)
                    else:
                        surf.set_at((px, py), w_mid)

        # Top horizontal timber lintel beam (x=193..229, y=54..60)
        for by in range(54, 61):
            for bx in range(193, 230):
                px, py = ox + bx, oy + by
                if by in (54, 60) or bx in (193, 229):
                    surf.set_at((px, py), w_out)
                elif by == 55:
                    surf.set_at((px, py), w_hi)
                elif by == 57:
                    surf.set_at((px, py), w_dark)
                elif by == 59:
                    surf.set_at((px, py), w_dark)
                else:
                    surf.set_at((px, py), w_light if (bx + by) % 5 else w_mid)

        # 4. Small iron wall-lantern bracket mounted on left doorway post (bx=191..195, by=62..67)
        iron_dark = (28, 26, 30, 255)
        iron_mid = (58, 54, 60, 255)
        surf.set_at((ox + 194, oy + 62), iron_dark)
        surf.set_at((ox + 193, oy + 62), iron_mid)
        surf.set_at((ox + 192, oy + 62), iron_dark)
        surf.set_at((ox + 192, oy + 63), iron_mid)
        for lx in range(191, 194):
            surf.set_at((ox + lx, oy + 64), iron_dark)
            surf.set_at((ox + lx, oy + 67), iron_dark)

        # 5. Pixel Cobwebs in upper corners of background support frame & doorway (Abandoned Mine vibe)
        web_main = (92, 88, 96, 175)
        web_dim = (66, 62, 70, 150)
        # Left frame upper corner (bx=147..152, by=52..57)
        for step in range(6):
            surf.set_at((ox + 147 + step, oy + 52), web_dim)
            surf.set_at((ox + 147, oy + 52 + step), web_dim)
            if step < 5:
                surf.set_at((ox + 147 + step, oy + 56 - step), web_main)
            if step < 3:
                surf.set_at((ox + 147 + step, oy + 54 - step), web_dim)
        # Right frame upper corner (bx=164..169, by=52..57)
        for step in range(6):
            surf.set_at((ox + 169 - step, oy + 52), web_dim)
            surf.set_at((ox + 169, oy + 52 + step), web_dim)
            if step < 5:
                surf.set_at((ox + 169 - step, oy + 56 - step), web_main)
        # Mine doorway upper-right interior corner cobweb (bx=216..220, by=61..65)
        for step in range(5):
            surf.set_at((ox + 220 - step, oy + 61 + step), web_main if step % 2 == 0 else web_dim)
            if step < 3:
                surf.set_at((ox + 220 - step, oy + 61), web_dim)
                surf.set_at((ox + 220, oy + 61 + step), web_dim)

        # 6. Old Minecart with Gold/Crystal Ore parked under background frame (bx=138..149, by=81..91)
        cart_out = (16, 14, 18, 255)
        cart_dark = (36, 38, 46, 255)
        cart_mid = (54, 58, 68, 255)
        cart_hi = (78, 82, 94, 255)
        # Heaped ore chunks peeking above cart rim (by=81..83)
        ore_pts = (
            (140, 82, (196, 146, 42, 255)),
            (141, 81, (242, 198, 68, 255)),
            (142, 82, (168, 118, 34, 255)),
            (143, 81, (72, 204, 242, 255)),
            (144, 82, (48, 152, 196, 255)),
            (145, 81, (236, 184, 58, 255)),
            (146, 82, (176, 98, 228, 255)),
            (147, 82, (196, 146, 42, 255)),
        )
        for ox_p, oy_p, ocol in ore_pts:
            surf.set_at((ox + ox_p, oy + oy_p), ocol)
        # Trapezoidal riveted iron tub (by=83..89)
        for by in range(83, 90):
            inset = 1 if by >= 87 else 0
            x_left = 138 + inset
            x_right = 149 - inset
            for bx in range(x_left, x_right + 1):
                px, py = ox + bx, oy + by
                if bx in (x_left, x_right) or by == 89:
                    surf.set_at((px, py), cart_out)
                elif by == 83:
                    surf.set_at((px, py), cart_hi)
                elif bx == x_left + 1 or (bx == 143 and by % 2 == 0):
                    surf.set_at((px, py), cart_hi)
                elif by >= 87:
                    surf.set_at((px, py), cart_dark)
                else:
                    surf.set_at((px, py), cart_mid)
        # Two iron flanged wheels (bx=140..142 & bx=145..147, by=89..91)
        for wx in (140, 145):
            for wy in range(89, 92):
                for dx_w in range(3):
                    wcol = cart_hi if (dx_w == 1 and wy == 90) else cart_out if wy == 91 else cart_dark
                    surf.set_at((ox + wx + dx_w, oy + wy), wcol)

        return surf

    def _build_hanging_pulley(self, sway=0):
        """Hanging iron pulley wheel, rope & wooden ore bucket under the background frame lintel."""
        surf = _base_surface()
        ox, oy = PAD_BASE, PAD_BASE
        px_c = 158
        iron_out = (16, 14, 18, 255)
        iron_mid = (58, 60, 70, 255)
        iron_hi = (88, 92, 104, 255)
        rope_col = (118, 92, 58, 255)
        rope_dark = (78, 58, 36, 255)

        # Pulley bracket & wheel under lintel (by=51..54)
        surf.set_at((ox + px_c, oy + 51), iron_out)
        for wy in range(52, 55):
            for wx in range(px_c - 1, px_c + 2):
                col = iron_hi if (wx == px_c and wy == 53) else iron_mid if wx == px_c else iron_out
                surf.set_at((ox + wx, oy + wy), col)

        # Rope descending from pulley to bucket (by=55..63)
        for by in range(55, 64):
            shift = sway if by >= 59 else 0
            rx = ox + px_c + shift
            surf.set_at((rx, oy + by), rope_col if by % 2 == 0 else rope_dark)

        # Banded wooden ore bucket (bx=155..161 + sway, by=64..70)
        bx0 = px_c - 3 + sway
        bx1 = px_c + 3 + sway
        # Handle arch (by=63)
        surf.set_at((ox + bx0 + 1, oy + 63), iron_mid)
        surf.set_at((ox + px_c + sway, oy + 62), iron_hi)
        surf.set_at((ox + bx1 - 1, oy + 63), iron_mid)
        # Glinting gold nuggets peeking out of bucket top (by=63..64)
        surf.set_at((ox + px_c - 1 + sway, oy + 64), (244, 198, 68, 255))
        surf.set_at((ox + px_c + sway, oy + 63), (255, 228, 110, 255))
        surf.set_at((ox + px_c + 1 + sway, oy + 64), (198, 142, 38, 255))

        b_out = (20, 14, 12, 255)
        b_wood = (116, 72, 38, 255)
        b_hi = (148, 94, 50, 255)
        b_dark = (78, 46, 24, 255)
        for by in range(64, 71):
            taper = 1 if by >= 69 else 0
            for bx in range(bx0 + taper, bx1 - taper + 1):
                px, py = ox + bx, oy + by
                if bx in (bx0 + taper, bx1 - taper) or by == 70:
                    surf.set_at((px, py), b_out)
                elif by in (65, 68):
                    # Iron hoop bands around the wooden bucket
                    surf.set_at((px, py), iron_hi if bx == bx0 + 1 else iron_mid)
                elif bx == bx0 + taper + 1:
                    surf.set_at((px, py), b_hi)
                elif bx == bx1 - taper - 1:
                    surf.set_at((px, py), b_dark)
                else:
                    surf.set_at((px, py), b_wood)
        return surf

    # ------------------------------------------------------------------
    # Layer 4: Main ground platform, cliff stones, ladder & lava chamber
    # ------------------------------------------------------------------
    def _build_layer4_platform(self):
        surf = _base_surface()
        rng = random.Random(44)
        ox, oy = PAD_BASE, PAD_BASE

        # Platform spans bx = 120..247, by = 92..167
        dirt_out = (24, 16, 13, 255)
        dirt_hi = (146, 96, 54, 255)
        dirt_light = (124, 79, 44, 255)
        dirt_mid = (98, 60, 34, 255)
        dirt_dark = (74, 44, 26, 255)
        dirt_deep = (54, 32, 20, 255)

        # 1. Fill earthen cross-section with organic pixel-art soil patches (no diagonal stripes)
        for by in range(94, BASE_H + PAD_BASE):
            for bx in range(121, BASE_W + PAD_BASE):
                px, py = ox + bx, oy + by
                depth = by - 94
                blob = (_hash2d(bx // 3, by // 3, 19) - 128) / 128.0
                fine = (_hash2d(bx // 2, by // 2, 53) - 128) / 128.0
                speck = _hash2d(bx, by, 97)
                n = blob * 0.7 + fine * 0.3
                if depth < 3:
                    col = dirt_hi if speck > 150 else dirt_light
                elif depth < 14 + int(n * 4):
                    col = dirt_light if n > 0.12 else dirt_mid
                elif depth < 38 + int(n * 6):
                    col = dirt_mid if n > -0.22 else dirt_dark
                else:
                    col = dirt_dark if n > -0.05 else dirt_deep
                if speck < 14:
                    col = dirt_deep
                elif speck > 242 and depth < 32:
                    col = dirt_hi if depth < 14 else dirt_light
                surf.set_at((px, py), col)

        # 2. Embedded gray/brown stones inside the earth cross-section
        stone_pal = (
            (24, 20, 18, 255),
            (62, 59, 56, 255),
            (90, 86, 82, 255),
            (116, 112, 106, 255),
        )
        embedded_rocks = (
            (172, 116, 5, 4), (168, 121, 3, 2), (186, 115, 2, 2),
            (164, 134, 5, 3), (171, 131, 4, 3), (178, 137, 3, 2),
            (158, 146, 2, 2), (163, 149, 4, 3), (171, 146, 5, 4),
            (180, 149, 4, 3), (165, 156, 5, 3), (175, 155, 3, 2),
            (188, 143, 3, 2), (153, 126, 2, 2), (235, 118, 3, 2),
        )
        for rx_c, ry_c, rx_w, ry_h in embedded_rocks:
            _draw_rock_cluster(surf, ox + rx_c, oy + ry_c, rx_w, ry_h, stone_pal, rng)

        # 3. Left vertical cliff cobblestone wall (bx ~ 120..126, by = 94..166)
        for cy in range(97, BASE_H + PAD_BASE, 6):
            _draw_rock_cluster(surf, ox + 123 + (cy % 2), oy + cy, 4, 3, stone_pal, rng)

        # 4. Top mossy/grassy surface lip (bx = 120..247, by = 91..96)
        moss_out = (20, 24, 16, 255)
        moss_dark = (52, 64, 42, 255)
        moss_mid = (78, 94, 58, 255)
        moss_hi = (104, 122, 76, 255)
        for bx in range(120, BASE_W + PAD_BASE):
            overhang = 95 + ((bx * 3) % 3 == 0)
            for by in range(91, overhang + 1):
                px, py = ox + bx, oy + by
                if by == 91:
                    surf.set_at((px, py), moss_out)
                elif by == 92:
                    surf.set_at((px, py), moss_hi if bx % 2 == 0 else moss_mid)
                elif by == 93:
                    surf.set_at((px, py), moss_mid)
                elif by == overhang:
                    surf.set_at((px, py), (64, 62, 60, 255))
                else:
                    surf.set_at((px, py), moss_dark)

        # Small grass blades poking up on the left cliff edge (bx = 127..131)
        for gx, gh in ((127, 2), (129, 3), (130, 2), (149, 2), (222, 2)):
            for dy in range(1, gh + 1):
                surf.set_at((ox + gx, oy + 91 - dy), moss_hi if dy == gh else moss_mid)

        # 5. Tall Wooden Ladder on the left cliff (bx = 135..145, by = 89..167)
        rail_out = (20, 14, 12, 255)
        rail_dark = (92, 56, 32, 255)
        rail_mid = (132, 82, 46, 255)
        rail_hi = (166, 108, 62, 255)

        # Dark recessed shaft behind ladder rungs
        for by in range(92, BASE_H + PAD_BASE):
            for bx in range(136, 145):
                surf.set_at((ox + bx, oy + by), (22, 16, 15, 255))

        # Horizontal rungs every 5 base pixels
        for ry in range(93, BASE_H + PAD_BASE, 5):
            for bx in range(137, 144):
                surf.set_at((ox + bx, oy + ry - 1), rail_out)
                surf.set_at((ox + bx, oy + ry), rail_hi if bx < 141 else rail_mid)
                surf.set_at((ox + bx, oy + ry + 1), rail_dark)
                surf.set_at((ox + bx, oy + ry + 2), rail_out)

        # Left and right ladder side rails (bx = 135..137 and bx = 143..145)
        for rx0 in (135, 143):
            for by in range(89, BASE_H + PAD_BASE):
                surf.set_at((ox + rx0, oy + by), rail_out)
                surf.set_at((ox + rx0 + 1, oy + by), rail_hi if by % 4 else rail_mid)
                surf.set_at((ox + rx0 + 2, oy + by), rail_dark)
                surf.set_at((ox + rx0 + 3, oy + by), rail_out)
            # Top caps of rails
            for dx in range(4):
                surf.set_at((ox + rx0 + dx, oy + 88), rail_out)

        # 6. Subterranean Lava Chamber Cavity (bx = 197..231, by = 125..149)
        cx, cy = 214.0, 137.0
        rx, ry = 17.5, 12.0
        for by in range(121, 154):
            for bx in range(193, 236):
                px, py = ox + bx, oy + by
                nx = (bx - cx) / rx
                ny = (by - cy) / ry
                # Rounded rectangular cavity metric
                dist = (abs(nx) ** 2.6 + abs(ny) ** 2.6) ** (1.0 / 2.6)
                if dist < 0.84:
                    # Inside the lava cavity: warm glowing rear wall
                    heat = clamp((by - 125) / 20.0)
                    wall_col = lerp_color((58, 28, 22), (176, 78, 28), heat ** 1.3)
                    surf.set_at((px, py), (*wall_col, 255))
                elif dist < 0.92:
                    surf.set_at((px, py), (22, 14, 12, 255))
                elif dist < 1.12:
                    # Scorched stone brick border around the lava pocket
                    brick = (bx // 3 + by // 2) % 3
                    if brick == 0:
                        surf.set_at((px, py), (88, 52, 34, 255))
                    elif brick == 1:
                        surf.set_at((px, py), (66, 38, 26, 255))
                    else:
                        surf.set_at((px, py), (46, 26, 20, 255))

        # 7. Small Underground Water Pocket (bx = 149..171, by = 133..150, opposite the lava pocket)
        wcx, wcy = 160.0, 142.0
        wrx, wry = 10.5, 8.0
        for by in range(132, 152):
            for bx in range(148, 173):
                px, py = ox + bx, oy + by
                nx = (bx - wcx) / wrx
                ny = (by - wcy) / wry
                dist = (abs(nx) ** 2.4 + abs(ny) ** 2.4) ** (1.0 / 2.4)
                if dist < 0.80:
                    depth_k = clamp((by - 134) / 14.0)
                    w_wall = lerp_color((18, 28, 38), (28, 56, 74), depth_k)
                    surf.set_at((px, py), (*w_wall, 255))
                elif dist < 0.92:
                    surf.set_at((px, py), (14, 18, 22, 255))
                elif dist < 1.15:
                    # Damp mossy stone border around water pocket
                    brick = (bx // 2 + by // 2) % 3
                    if brick == 0:
                        surf.set_at((px, py), (54, 72, 68, 255))
                    elif brick == 1:
                        surf.set_at((px, py), (42, 56, 58, 255))
                    else:
                        surf.set_at((px, py), (32, 42, 46, 255))

        # 8. Glowing Crystal Geode Cluster embedded in upper-left dirt (bx = 151..163, by = 106..117)
        gcx, gcy = 157.0, 112.0
        for by in range(105, 119):
            for bx in range(150, 165):
                d = math.hypot((bx - gcx) / 6.2, (by - gcy) / 5.2)
                px, py = ox + bx, oy + by
                if d < 0.78:
                    surf.set_at((px, py), (24, 18, 34, 255))
                elif d < 1.04:
                    surf.set_at((px, py), (46, 34, 58, 255) if (bx + by) % 2 == 0 else (34, 24, 44, 255))
        # Angled amethyst-violet & cyan crystal shards inside geode
        crystal_pixels = (
            # Tall center-left violet shard
            (155, 114, (132, 62, 196, 255)), (155, 113, (168, 88, 232, 255)),
            (155, 112, (198, 124, 252, 255)), (155, 111, (228, 176, 255, 255)),
            (156, 114, (108, 48, 168, 255)), (156, 113, (148, 74, 214, 255)),
            (156, 112, (182, 108, 244, 255)),
            # Angled cyan-ice shard on right
            (158, 114, (38, 138, 186, 255)), (158, 113, (64, 188, 236, 255)),
            (159, 113, (96, 218, 252, 255)), (159, 112, (168, 244, 255, 255)),
            (157, 114, (52, 164, 214, 255)),
            # Left small magenta shard
            (153, 114, (144, 68, 204, 255)), (153, 113, (192, 116, 246, 255)),
            (154, 114, (118, 52, 176, 255)),
            # Right small violet shard
            (160, 114, (138, 66, 198, 255)), (161, 113, (186, 112, 242, 255)),
        )
        for cpx, cpy, ccol in crystal_pixels:
            surf.set_at((ox + cpx, oy + cpy), ccol)

        # 9. Buried Ancient Miner Skull, Cracked Helmet & Old Pickaxe in dirt (bx = 180..192, by = 107..116)
        for by in range(107, 117):
            for bx in range(180, 193):
                d = math.hypot((bx - 186.0) / 5.8, (by - 112.0) / 4.5)
                if d < 0.92:
                    surf.set_at((ox + bx, oy + by), (38, 24, 18, 255) if d < 0.72 else (56, 34, 24, 255))
        # Cracked vintage yellow-ochre helmet on top of buried skull (bx=182..187, by=108..110)
        helm_old = (182, 132, 42, 255)
        helm_shd = (134, 92, 28, 255)
        for hx in range(183, 187):
            surf.set_at((ox + hx, oy + 108), helm_old if hx < 185 else helm_shd)
        for hx in range(182, 188):
            surf.set_at((ox + hx, oy + 109), (28, 20, 16, 255) if hx == 185 else helm_old)
            surf.set_at((ox + hx, oy + 110), helm_shd)
        # Pixel skull face (bx=182..187, by=111..114)
        bone_hi = (214, 198, 172, 255)
        bone_mid = (176, 158, 134, 255)
        bone_dark = (128, 112, 94, 255)
        eye_void = (22, 16, 14, 255)
        for sx_k in range(182, 187):
            surf.set_at((ox + sx_k, oy + 111), bone_hi if sx_k < 185 else bone_mid)
            surf.set_at((ox + sx_k, oy + 112), eye_void if sx_k in (183, 185) else bone_mid)
            surf.set_at((ox + sx_k, oy + 113), bone_mid if sx_k != 184 else eye_void)
        for sx_k in (183, 184, 185):
            surf.set_at((ox + sx_k, oy + 114), bone_dark if sx_k == 184 else bone_mid)
        # Buried old pickaxe head & handle stub beside the skull (bx=188..191, by=110..115)
        surf.set_at((ox + 189, oy + 114), (108, 72, 42, 255))
        surf.set_at((ox + 188, oy + 113), (124, 84, 48, 255))
        surf.set_at((ox + 189, oy + 112), (92, 96, 106, 255))
        surf.set_at((ox + 190, oy + 111), (124, 128, 138, 255))
        surf.set_at((ox + 188, oy + 111), (74, 78, 88, 255))

        return surf

    # ------------------------------------------------------------------
    # Layer 5: Crate, Bomb, Pickaxe, Speed Potion, Sign & Animated Miner
    # ------------------------------------------------------------------
    def _build_layer5_static_props(self):
        surf = _base_surface()
        rng = random.Random(55)
        ox, oy = PAD_BASE, PAD_BASE

        # Contact shadows on the mossy platform top (y = 92)
        for sx0, sx1 in ((124, 133), (150, 161), (163, 179), (180, 192), (225, 242)):
            for bx in range(sx0, sx1):
                surf.set_at((ox + bx, oy + 92), (24, 28, 18, 220))

        # 0. Wooden Warning Sign on the left cliff edge (bx = 123..132, by = 80..91)
        s_out = (20, 14, 11, 255)
        s_dark = (84, 50, 28, 255)
        s_mid = (118, 72, 38, 255)
        s_hi = (148, 94, 50, 255)
        # Signpost stake (bx=127..128, by=86..91)
        for by in range(86, 92):
            surf.set_at((ox + 126, oy + by), s_out)
            surf.set_at((ox + 127, oy + by), s_mid)
            surf.set_at((ox + 128, oy + by), s_dark)
            surf.set_at((ox + 129, oy + by), s_out)
        # Signboard (bx=123..132, by=80..86)
        for by in range(80, 87):
            for bx in range(123, 133):
                px, py = ox + bx, oy + by
                if bx in (123, 132) or by in (80, 86):
                    surf.set_at((px, py), s_out)
                elif by == 81:
                    surf.set_at((px, py), s_hi)
                elif by == 85 or bx == 131:
                    surf.set_at((px, py), s_dark)
                else:
                    surf.set_at((px, py), s_mid)
        # Red/amber hazard exclamation mark on the wooden sign
        surf.set_at((ox + 127, oy + 82), (224, 68, 48, 255))
        surf.set_at((ox + 128, oy + 82), (242, 168, 56, 255))
        surf.set_at((ox + 127, oy + 83), (224, 68, 48, 255))
        surf.set_at((ox + 128, oy + 83), (242, 168, 56, 255))
        surf.set_at((ox + 127, oy + 85), (224, 68, 48, 255))

        # 1. Round Black Bomb (bx = 150..160, by = 81..92)
        bcx, bcy, br = 155.0, 87.0, 5.2
        for by in range(81, 93):
            for bx in range(149, 162):
                d = math.hypot(bx - bcx, by - bcy)
                px, py = ox + bx, oy + by
                if d <= br:
                    if d > br - 1.05:
                        surf.set_at((px, py), (14, 15, 20, 255))
                    elif bx < bcx - 1 and by < bcy - 1:
                        surf.set_at((px, py), (92, 98, 114, 255))
                    elif bx < bcx and by < bcy:
                        surf.set_at((px, py), (58, 63, 76, 255))
                    elif bx > bcx + 1 or by > bcy + 1:
                        surf.set_at((px, py), (24, 26, 34, 255))
                    else:
                        surf.set_at((px, py), (38, 41, 52, 255))
        # Bomb fuse neck & cord
        surf.set_at((ox + 156, oy + 81), (68, 72, 84, 255))
        surf.set_at((ox + 157, oy + 80), (186, 142, 88, 255))
        surf.set_at((ox + 158, oy + 79), (218, 174, 110, 255))

        # 2. Wooden Crate (bx = 164..175, by = 81..92)
        c_out = (22, 14, 11, 255)
        c_dark = (88, 52, 28, 255)
        c_mid = (122, 74, 38, 255)
        c_light = (152, 96, 50, 255)
        c_hi = (178, 116, 62, 255)
        x0, y0, x1, y1 = 164, 81, 175, 92
        for by in range(y0, y1 + 1):
            for bx in range(x0, x1 + 1):
                px, py = ox + bx, oy + by
                if bx in (x0, x1) or by in (y0, y1):
                    surf.set_at((px, py), c_out)
                elif bx in (x0 + 1, x1 - 1) or by in (y0 + 1, y1 - 1):
                    # Outer wood frame of crate (warmer on right side facing miner's lamp)
                    surf.set_at((px, py), c_hi if (by == y0 + 1 or bx == x1 - 1) else c_light)
                elif bx in (x0 + 2, x1 - 2) or by in (y0 + 2, y1 - 2):
                    surf.set_at((px, py), c_dark)
                elif abs((bx - x0) - (by - y0)) <= 1:
                    # Diagonal cross plank
                    surf.set_at((px, py), c_light if (bx - x0) == (by - y0) else c_dark)
                else:
                    surf.set_at((px, py), c_mid if (bx - x0) % 2 else c_dark)

        # 2b. Glowing Blue Speed Potion Bottle sitting on top of the crate (bx = 167..171, by = 75..80)
        p_out = (18, 22, 28, 255)
        p_cork = (168, 112, 62, 255)
        p_glass = (148, 212, 236, 255)
        p_cyan = (43, 220, 255, 255)
        p_deep = (22, 138, 192, 255)
        p_spec = (220, 252, 255, 255)
        # Cork & neck (by=75..76)
        surf.set_at((ox + 169, oy + 75), p_cork)
        surf.set_at((ox + 168, oy + 76), p_out)
        surf.set_at((ox + 169, oy + 76), p_glass)
        surf.set_at((ox + 170, oy + 76), p_out)
        # Rounded potion flask body (bx=167..171, by=77..80)
        for by in range(77, 81):
            for bx in range(167, 172):
                px, py = ox + bx, oy + by
                if by == 80 and bx in (167, 171):
                    continue
                if bx in (167, 171) or by == 80:
                    surf.set_at((px, py), p_out)
                elif bx == 168 and by == 78:
                    surf.set_at((px, py), p_spec)
                elif by == 77:
                    surf.set_at((px, py), p_glass if bx == 168 else p_cyan)
                elif by == 79 and bx == 170:
                    surf.set_at((px, py), p_deep)
                else:
                    surf.set_at((px, py), p_cyan)

        # 2c. Miner's Pickaxe leaning against the right side of the wooden crate (bx = 173..179, by = 80..92)
        pk_out = (18, 14, 14, 255)
        pk_wood = (158, 102, 54, 255)
        pk_wood_dark = (108, 66, 34, 255)
        pk_steel = (142, 152, 168, 255)
        pk_steel_hi = (212, 222, 236, 255)
        pk_steel_dark = (88, 94, 108, 255)
        # Diagonal wooden shaft from bottom-right (178, 92) up-left to (175, 82)
        for step in range(10):
            hx = 178 - (step // 3)
            hy = 91 - step
            surf.set_at((ox + hx - 1, oy + hy), pk_out)
            surf.set_at((ox + hx, oy + hy), pk_wood if step % 2 == 0 else pk_wood_dark)
            surf.set_at((ox + hx + 1, oy + hy), pk_out)
        # Curved forged-steel double-pointed pickaxe head (bx=173..178, by=80..84)
        pick_head = (
            (173, 83, pk_steel_hi), (174, 82, pk_steel_hi), (175, 81, pk_steel),
            (176, 81, pk_steel_hi), (177, 82, pk_steel), (178, 83, pk_steel_dark),
            (174, 83, pk_steel_dark), (175, 82, pk_steel_hi), (176, 82, pk_steel_dark),
            (173, 84, pk_out), (178, 84, pk_out),
        )
        for px_h, py_h, pcol in pick_head:
            surf.set_at((ox + px_h, oy + py_h), pcol)

        # 3. Foreground Rock Pile on far right of platform (bx = 226..242, by = 84..92)
        fg_stone_pal = (
            (18, 16, 16, 255),
            (58, 56, 54, 255),
            (88, 85, 80, 255),
            (118, 114, 108, 255),
        )
        _draw_rock_cluster(surf, ox + 234, oy + 88, 6, 4, fg_stone_pal, rng)
        _draw_rock_cluster(surf, ox + 229, oy + 90, 4, 2, fg_stone_pal, rng)
        _draw_rock_cluster(surf, ox + 239, oy + 90, 4, 3, fg_stone_pal, rng)
        return surf

    def _build_miner_frames(self):
        """Build crisp pixel-art Miner frames for breathing, hat tilt, glance, blink & lamp flicker."""
        base_palette = {
            'K': (20, 15, 16, 255),     # Dark outline
            'Y': (242, 192, 68, 255),   # Helmet gold
            'y': (196, 142, 42, 255),   # Helmet shadow
            'd': (152, 104, 28, 255),   # Helmet band / deep ochre
            'W': (255, 232, 138, 255),  # Helmet highlight
            'L': (255, 252, 220, 255),  # Headlamp core bright
            'l': (184, 206, 220, 255),  # Headlamp metallic rim
            'S': (236, 182, 140, 255),  # Skin light
            's': (196, 138, 98, 255),   # Skin shadow
            'n': (224, 142, 114, 255),  # Nose / cheek warm tone
            'B': (116, 74, 44, 255),    # Vest/hair brown
            'b': (78, 48, 30, 255),     # Dark brown
            'C': (198, 186, 168, 255),  # Shirt cream
            'c': (150, 138, 122, 255),  # Shirt shadow
            'G': (58, 42, 32, 255),     # Belt/boots dark
            'g': (226, 184, 82, 255),   # Belt buckle gold
            'P': (88, 66, 48, 255),     # Pants
            'p': (62, 46, 36, 255),     # Pants shadow
        }

        # Miner facing left (toward crate/bomb/menu, matching reference image)
        helmet_rows = (
            "....KKKKKKK.....",
            "...KYYKKKWWK....",
            "..KYKllLLKYWK...",
            "..KYKlLLKYYYK...",
            ".KyyyyKKKdYYYYK.",
            ".KKKKKKKKKKKKKK.",
        )
        helmet_tilt_rows = (
            "....KKKKKKK.....",
            "...KYYKKKWWK....",
            "..KYKllLLKYWK...",
            ".KYYKlLLKYYYYK..",
            ".KyyyyKKKdYYYYK.",
            "..KKKKKKKKKKKKK.",
        )
        face_open = (
            "..KSSSSSSSSbBK..",
            "..KSKSSSSKSbBK..",
            "..KnKSSSSKSbBsK.",
            "..KssssssssbBK..",
            "...KKKKKKKKKK...",
        )
        face_blink = (
            "..KSSSSSSSSbBK..",
            "..KSSSSSSSSbBK..",
            "..KnKSSSSKSbBsK.",
            "..KssssssssbBK..",
            "...KKKKKKKKKK...",
        )
        torso_rows = (
            "..KBBCCCCCCBBK..",
            ".KBBBCCCCCCbBBK.",
            ".KSSKBBBBBBKSSK.",
            ".KssKGGGGgGKssK.",
            "..KKKPPPPPPKKK..",
        )
        legs_rows = (
            "...KPPPpKPPPpK..",
            "...KPPPpKPPPpK..",
            "...KGGGGKGGGGK..",
            "...KKKKKKKKKKK..",
        )

        def make_frame(breath_dy=0, head_dx=0, hat_tilt=False, blink=False, bright_lamp=True):
            surf = pygame.Surface((18, 22), pygame.SRCALPHA)
            pal = dict(base_palette)
            if not bright_lamp:
                pal['L'] = (255, 226, 152, 255)
                pal['l'] = (158, 174, 186, 255)

            def blit_rows(rows, ox, oy):
                for ry, row in enumerate(rows):
                    for rx, ch in enumerate(row):
                        if ch in pal:
                            px, py = ox + rx, oy + ry
                            if 0 <= px < 18 and 0 <= py < 22:
                                surf.set_at((px, py), pal[ch])

            blit_rows(legs_rows, 1, 18)
            blit_rows(torso_rows, 1, 13 + breath_dy)
            blit_rows(face_blink if blink else face_open, 1 + head_dx, 8 + breath_dy)
            blit_rows(helmet_tilt_rows if hat_tilt else helmet_rows, 1 + head_dx, 2 + breath_dy)
            return _upscale(surf)

        frames = {}
        for pose, b_dy, h_dx, tilt in (
            ('stand', 0, 0, False),
            ('breath', 1, 0, False),
            ('hat', 0, 0, True),
            ('glance', 0, 1, False),
        ):
            for blink in (False, True):
                for bright in (False, True):
                    frames[(pose, blink, bright)] = make_frame(b_dy, h_dx, tilt, blink, bright)
            # Backward-compatible tuple key (pose, glance_int, blink)
            g_int = 1 if pose == 'glance' else 0
            frames[(pose, g_int, False)] = frames[(pose, False, True)]
            frames[(pose, g_int, True)] = frames[(pose, True, True)]
        return frames

    # ------------------------------------------------------------------
    # Layer 6: Ambient Particles, Falling Rocks, Lava Bubbles & Lighting
    # ------------------------------------------------------------------
    def _init_ambient_particles(self):
        self.fireflies.clear()
        self.ceiling_dust.clear()
        self.falling_rocks.clear()
        self.rock_splashes.clear()
        self.lava_bubbles.clear()
        self.lava_embers.clear()
        self.cavern_embers.clear()
        self.fuse_sparks.clear()
        self.water_drips.clear()

        # 22 glowing cave fireflies / floating light specks with varying sizes & speeds
        for _ in range(22):
            self.fireflies.append({
                'x': self.rng.uniform(430, 915),
                'y': self.rng.uniform(135, 425),
                'vx': self.rng.uniform(-7.5, 7.5),
                'vy': self.rng.uniform(-12.0, -3.5),
                'phase': self.rng.uniform(0, math.tau),
                'size': self.rng.choice((3, 4, 4, 6)),
                'warmth': self.rng.uniform(0.0, 1.0),
            })

        # 20 ceiling & air dust motes across 3 depth/speed tiers
        for _ in range(20):
            self.ceiling_dust.append(self._spawn_dust(random_y=True))

        # 5 lava bubbles on the molten lava surface
        for i in range(5):
            self.lava_bubbles.append({
                'x': 806 + i * 23 + self.rng.uniform(-5, 5),
                'age': self.rng.uniform(0.0, 1.1),
                'life': self.rng.uniform(0.85, 1.45),
                'radius': self.rng.choice((4, 6, 8)),
            })

        # 12 rising embers inside the subterranean lava pocket
        for _ in range(12):
            self.lava_embers.append(self._spawn_lava_ember(random_age=True))

        # 10 rising warm embers drifting up in the main cavern air
        for _ in range(10):
            self.cavern_embers.append(self._spawn_cavern_ember(random_age=True))

    def _spawn_dust(self, random_y=False):
        bx = self.rng.randint(116, 232)
        arch_py = (_cave_arch_top(bx) + 2) * PIXEL
        size = self.rng.choice((2, 3, 4))
        speed_scale = 0.7 if size == 2 else (1.0 if size == 3 else 1.3)
        return {
            'x': bx * PIXEL + self.rng.uniform(-4, 4),
            'y': self.rng.uniform(arch_py, 360) if random_y else arch_py,
            'vx': self.rng.uniform(-4.5, 4.5) * speed_scale,
            'vy': self.rng.uniform(10.0, 24.0) * speed_scale,
            'alpha': self.rng.randint(65, 150),
            'phase': self.rng.uniform(0, math.tau),
            'size': size,
        }

    def _spawn_lava_ember(self, random_age=False):
        life = self.rng.uniform(0.65, 1.35)
        return {
            'x': self.rng.uniform(802, 910),
            'y': self.rng.uniform(518, 558) if random_age else 556.0,
            'vx': self.rng.uniform(-11.0, 11.0),
            'vy': self.rng.uniform(-36.0, -16.0),
            'age': self.rng.uniform(0.0, life) if random_age else 0.0,
            'life': life,
            'size': self.rng.choice((2, 3, 4)),
        }

    def _spawn_cavern_ember(self, random_age=False):
        life = self.rng.uniform(1.8, 3.4)
        return {
            'x': self.rng.uniform(460, 910),
            'y': self.rng.uniform(220, 480) if random_age else self.rng.uniform(355, 460),
            'vx': self.rng.uniform(-8.0, 8.0),
            'vy': self.rng.uniform(-22.0, -10.0),
            'age': self.rng.uniform(0.0, life) if random_age else 0.0,
            'life': life,
            'size': self.rng.choice((2, 3, 4)),
            'phase': self.rng.uniform(0, math.tau),
        }

    def _spawn_falling_rock(self):
        bx = self.rng.randint(130, 218)
        start_y = (_cave_arch_top(bx) + 3) * PIXEL
        return {
            'x': float(bx * PIXEL),
            'y': float(start_y),
            'vx': self.rng.uniform(-14.0, 14.0),
            'vy': self.rng.uniform(15.0, 40.0),
            'bounced': False,
            'life': 1.8,
            'size': self.rng.choice((4, 6)),
        }

    def update(self, dt, mouse_pos=None):
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt
        self.camera.update(dt, mouse_pos)

        # Blink timers for doorway monster eyes and the miner
        if self._eye_blink_dur > 0:
            self._eye_blink_dur = max(0.0, self._eye_blink_dur - dt)
        else:
            self._eye_blink_timer -= dt
            if self._eye_blink_timer <= 0:
                self._eye_blink_dur = 0.15
                self._eye_blink_timer = self.rng.uniform(3.2, 6.0)

        if self._miner_blink_dur > 0:
            self._miner_blink_dur = max(0.0, self._miner_blink_dur - dt)
        else:
            self._miner_blink_timer -= dt
            if self._miner_blink_timer <= 0:
                self._miner_blink_dur = 0.13
                self._miner_blink_timer = self.rng.uniform(2.5, 5.2)

        # Update floating fireflies
        for p in self.fireflies:
            p['x'] += (p['vx'] + math.sin(self.time * 1.4 + p['phase']) * 8.0) * dt
            p['y'] += (p['vy'] + math.cos(self.time * 1.1 + p['phase']) * 4.0) * dt
            if p['y'] < 125 or p['x'] < 405 or p['x'] > 940:
                p['x'] = self.rng.uniform(440, 900)
                p['y'] = self.rng.uniform(330, 430)

        # Update ceiling dust
        for d in self.ceiling_dust:
            d['x'] += (d['vx'] + math.sin(self.time * 1.8 + d['phase']) * 5.0) * dt
            d['y'] += d['vy'] * dt
            if d['y'] > 366:
                d.update(self._spawn_dust(random_y=False))

        # Occasional tiny falling rocks from cave ceiling
        self._rock_timer -= dt
        if self._rock_timer <= 0:
            self._rock_timer = self.rng.uniform(1.4, 3.0)
            if len(self.falling_rocks) < 3:
                self.falling_rocks.append(self._spawn_falling_rock())

        kept_rocks = []
        for r in self.falling_rocks:
            r['vy'] += 460.0 * dt
            r['x'] += r['vx'] * dt
            r['y'] += r['vy'] * dt
            if not r['bounced'] and r['x'] >= 485 and r['y'] >= 364:
                r['y'] = 364.0
                r['vy'] = -abs(r['vy']) * 0.35
                r['vx'] *= 0.6
                r['bounced'] = True
                # Spawn tiny dust puff on impact
                for side in (-1, 1):
                    self.rock_splashes.append([
                        r['x'], 364.0,
                        side * self.rng.uniform(12.0, 28.0),
                        self.rng.uniform(-38.0, -18.0),
                        0.0, 0.28,
                    ])
            if r['bounced']:
                r['life'] -= dt * 2.5
            if r['life'] > 0 and r['y'] < SCREEN_H + 16:
                kept_rocks.append(r)
        self.falling_rocks = kept_rocks

        kept_splashes = []
        for sp in self.rock_splashes:
            sp[4] += dt
            if sp[4] < sp[5]:
                sp[3] += 140.0 * dt
                sp[0] += sp[2] * dt
                sp[1] += sp[3] * dt
                kept_splashes.append(sp)
        self.rock_splashes = kept_splashes

        # Update lava bubbles
        for b in self.lava_bubbles:
            b['age'] += dt
            if b['age'] >= b['life']:
                b['age'] = 0.0
                b['life'] = self.rng.uniform(0.85, 1.45)
                b['x'] = self.rng.uniform(804, 906)
                b['radius'] = self.rng.choice((4, 6, 8))

        # Update lava pocket embers
        for e in self.lava_embers:
            e['age'] += dt
            e['x'] += (e['vx'] + math.sin(self.time * 5.0 + e['y'] * 0.1) * 8.0) * dt
            e['y'] += e['vy'] * dt
            if e['age'] >= e['life'] or e['y'] < 502:
                e.update(self._spawn_lava_ember(random_age=False))

        # Update cavern rising embers
        for ce in self.cavern_embers:
            ce['age'] += dt
            ce['x'] += (ce['vx'] + math.sin(self.time * 2.8 + ce['phase']) * 10.0) * dt
            ce['y'] += ce['vy'] * dt
            if ce['age'] >= ce['life'] or ce['y'] < 135:
                ce.update(self._spawn_cavern_ember(random_age=False))

        # Update bomb fuse sparks
        if self.rng.random() < 0.45 and len(self.fuse_sparks) < 10:
            angle = self.rng.uniform(-math.pi * 0.9, -math.pi * 0.1)
            spd = self.rng.uniform(25.0, 68.0)
            self.fuse_sparks.append([
                634.0, 314.0,
                math.cos(angle) * spd, math.sin(angle) * spd,
                0.0, self.rng.uniform(0.16, 0.34),
            ])
        kept_sparks = []
        for s in self.fuse_sparks:
            s[4] += dt
            if s[4] < s[5]:
                s[3] += 180.0 * dt
                s[0] += s[2] * dt
                s[1] += s[3] * dt
                kept_sparks.append(s)
        self.fuse_sparks = kept_sparks

        # Update underground water pocket ceiling drips & splashes
        self._drip_timer -= dt
        if self._drip_timer <= 0:
            self._drip_timer = self.rng.uniform(0.9, 1.9)
            if len(self.water_drips) < 3:
                self.water_drips.append({
                    'x': self.rng.uniform(612.0, 666.0),
                    'y': 544.0,
                    'vy': 18.0,
                    'splashed': False,
                    'splash_age': 0.0,
                })
        kept_drips = []
        for wd in self.water_drips:
            if not wd['splashed']:
                wd['vy'] += 320.0 * dt
                wd['y'] += wd['vy'] * dt
                if wd['y'] >= 574.0:
                    wd['y'] = 574.0
                    wd['splashed'] = True
                kept_drips.append(wd)
            else:
                wd['splash_age'] += dt
                if wd['splash_age'] < 0.25:
                    kept_drips.append(wd)
        self.water_drips = kept_drips

    # ------------------------------------------------------------------
    # Pixel-Quantized Stepped Radial Light Cache (preserves pixel-art clarity)
    # ------------------------------------------------------------------
    def _radial_light(self, radius, color, peak_alpha):
        q_alpha = (peak_alpha // 4) * 4
        key = (radius, color, q_alpha)
        if key not in self.light_cache:
            if len(self.light_cache) > 160:
                self.light_cache.clear()
            base_r = max(2, radius // PIXEL)
            bw = base_r * 2
            base = pygame.Surface((bw, bw), 0, 32)
            base.fill((0, 0, 0))
            # Stepped pixel rings so light feels crisp and native to pixel art
            bands = min(6, max(3, base_r // 2))
            for b in range(bands, 0, -1):
                t = b / bands
                r = max(1, round(base_r * t))
                k = ((1.0 - (b - 1) / bands) ** 1.75) * (q_alpha / 255.0)
                col = tuple(min(255, round(c * k)) for c in color)
                pygame.draw.circle(base, col, (base_r, base_r), r)
            self.light_cache[key] = pygame.transform.scale(base, (radius * 2, radius * 2))
        return self.light_cache[key]

    # ------------------------------------------------------------------
    # Dynamic Sub-Renderers for Animated Environmental Elements & Reflections
    # ------------------------------------------------------------------
    def _draw_doorway_eyes(self, screen, dx, dy, light_alpha):
        """Flickering mine entrance lantern, warm doorway timber reflections & glowing red eyes."""
        # 1. Flickering wall lantern on left timber post of the mine entrance (bx=192, by=65)
        flick = 0.76 + 0.24 * flicker_wave(self.time, 1.85, 0.9)
        lan_x = 192 * PIXEL + dx
        lan_y = 65 * PIXEL + dy
        glass_col = lerp_color((214, 118, 34), (255, 224, 118), flick * light_alpha)
        core_col = lerp_color((245, 168, 54), (255, 248, 186), flick * light_alpha)
        pygame.draw.rect(screen, glass_col, (lan_x - 2, lan_y - 4, 8, 8))
        pygame.draw.rect(screen, core_col, (lan_x, lan_y - 2, 4, 4))

        # Subtle warm pixel reflections from entrance lantern onto the timber post & lintel
        if light_alpha > 0.15:
            rim_col = lerp_color((108, 66, 36), (218, 146, 68), flick * light_alpha * 0.75)
            # Left post inner & outer highlight strip near lantern
            pygame.draw.rect(screen, rim_col, (195 * PIXEL + dx, 60 * PIXEL + dy, PIXEL, 14 * PIXEL))
            pygame.draw.rect(screen, rim_col, (194 * PIXEL + dx, 55 * PIXEL + dy, 12 * PIXEL, PIXEL))

        # 2. Glowing menacing red eyes inside the dark mine doorway
        if self._eye_blink_dur > 0:
            return
        look_x = round(self.camera.mouse_norm_x * 2.0)
        look_y = round(self.camera.mouse_norm_y * 1.0)
        ex = 842 + dx + look_x
        ey = 294 + dy + look_y
        pulse = 0.78 + 0.22 * flicker_wave(self.time, 0.9, 1.3) * light_alpha
        red_outer = tuple(round(c * pulse) for c in (228, 38, 32))
        red_core = tuple(round(c * pulse) for c in (255, 130, 80))

        for side in (-1, 1):
            cx = ex + side * 11
            pygame.draw.rect(screen, red_outer, (cx - 4, ey, 8, 4))
            pygame.draw.rect(screen, red_outer, (cx - 2 * side, ey + 2, 4, 4))
            pygame.draw.rect(screen, red_core, (cx - 2, ey + 1, 4, 2))

    def _draw_animated_lava(self, screen, dx, dy, light_alpha=1.0):
        """Bubbling molten lava + dynamic orange light reflections on nearby rocks & dirt."""
        left = 800 + dx
        right = 912 + dx
        base_top = 550 + dy
        bottom = 580 + dy
        width = right - left
        lava_pulse = (0.75 + 0.25 * flicker_wave(self.time, 1.15, 2.1)) * light_alpha

        # 1. Dynamic warm orange rim-reflections on cavity ceiling & nearby embedded stones
        if lava_pulse > 0.1:
            ceil_col = lerp_color((88, 42, 26), (218, 96, 32), lava_pulse * 0.85)
            rock_rim = lerp_color((90, 72, 62), (212, 104, 42), lava_pulse * 0.75)
            # Cavity upper arch warm reflection pixels
            for rbx in range(201, 228, 2):
                ry = 125 + (1 if rbx in (201, 227) else 0)
                pygame.draw.rect(screen, ceil_col, (rbx * PIXEL + dx, ry * PIXEL + dy, PIXEL, PIXEL))
            # Warm orange reflection on the right/bottom faces of nearby embedded dirt stones
            for rx_b, ry_b, rw_b in ((189, 143, 2), (181, 149, 3), (176, 155, 2), (173, 146, 3)):
                pygame.draw.rect(
                    screen, rock_rim,
                    (rx_b * PIXEL + dx, ry_b * PIXEL + dy, rw_b * PIXEL, PIXEL),
                )

        # 2. Deep molten body
        pygame.draw.rect(screen, (208, 56, 20), (left, base_top + 6, width, bottom - base_top - 6))
        pygame.draw.rect(screen, (238, 102, 26), (left, base_top + 3, width, 12))

        # 3. Animated pixel-art surface waves (4px columns) + bright hot crust glints
        for col_x in range(left, right, PIXEL):
            wave = math.sin(self.time * 3.4 + (col_x - left) * 0.07)
            wave2 = math.cos(self.time * 2.1 - (col_x - left) * 0.11)
            crest_y = base_top + round((wave + wave2 * 0.5) * 2.0)
            w = min(PIXEL, right - col_x)
            pygame.draw.rect(screen, (255, 168, 38), (col_x, crest_y + 3, w, 8))
            crest_col = (255, 246, 148) if wave > 0.65 else (255, 228, 86)
            pygame.draw.rect(screen, crest_col, (col_x, crest_y, w, 4))

        # Rocky cavity bottom lip & corner bevels overlapping the lava pool edge
        pygame.draw.rect(screen, (22, 14, 12), (left - 4, bottom, width + 8, 4))
        pygame.draw.rect(screen, (22, 14, 12), (left, bottom - 4, 8, 4))
        pygame.draw.rect(screen, (22, 14, 12), (right - 8, bottom - 4, 8, 4))
        pygame.draw.rect(screen, (58, 34, 24), (left + 4, bottom + 4, width - 8, 4))

        # 4. Swelling & popping lava bubbles
        for b in self.lava_bubbles:
            t = b['age'] / b['life']
            bx = round(b['x'] + dx)
            by = base_top + 2
            if t < 0.82:
                r = max(2, round(b['radius'] * math.sin(t / 0.82 * math.pi * 0.5)))
                pygame.draw.circle(screen, (255, 140, 32), (bx, by), r + 1)
                pygame.draw.circle(screen, (255, 236, 110), (bx, by - 1), max(1, r - 1))
            else:
                pop_t = (t - 0.82) / 0.18
                spread = round(pop_t * 8)
                for side in (-1, 1):
                    pygame.draw.rect(screen, (255, 224, 96),
                                     (bx + side * spread, by - round(pop_t * 6), 3, 3))

        # 5. Rising embers inside the lava pocket
        for e in self.lava_embers:
            ex = round(e['x'] + dx)
            ey = round(e['y'] + dy)
            heat = 1.0 - e['age'] / e['life']
            col = (255, 236, 120) if heat > 0.6 else (255, 142, 42) if heat > 0.3 else (204, 64, 24)
            size = e.get('size', 3)
            pygame.draw.rect(screen, col, (ex, ey, size, size))

        # 6. Animated Underground Water Pocket (bx = 152..168, by = 143..148) + Ceiling Drips
        w_left = 152 * PIXEL + dx
        w_right = 168 * PIXEL + dx
        w_top = 143 * PIXEL + dy
        w_bot = 148 * PIXEL + dy
        w_width = w_right - w_left
        pygame.draw.rect(screen, (22, 86, 132), (w_left, w_top + 4, w_width, w_bot - w_top - 4))
        for col_x in range(w_left, w_right, PIXEL):
            w_wave = math.sin(self.time * 3.1 + (col_x - w_left) * 0.09)
            wy = w_top + round(w_wave * 1.4)
            ww = min(PIXEL, w_right - col_x)
            pygame.draw.rect(screen, (38, 148, 202), (col_x, wy + 2, ww, 6))
            crest_c = (168, 242, 255) if w_wave > 0.55 else (84, 206, 244)
            pygame.draw.rect(screen, crest_c, (col_x, wy, ww, 3))
        # Dark stone bottom lip of water cavity
        pygame.draw.rect(screen, (14, 18, 22), (w_left - 4, w_bot, w_width + 8, 4))
        # Subtle cyan water reflection on the upper arch of the water pocket
        if light_alpha > 0.15:
            w_refl = lerp_color((32, 46, 54), (72, 168, 212), (0.6 + 0.4 * math.sin(self.time * 2.5)) * light_alpha)
            for rbx in range(154, 167, 2):
                pygame.draw.rect(screen, w_refl, (rbx * PIXEL + dx, 134 * PIXEL + dy, PIXEL, PIXEL))
        # Falling water droplets & tiny splash rings inside the water pocket
        for wd in self.water_drips:
            wx = round(wd['x'] + dx)
            wy = round(wd['y'] + dy)
            if not wd['splashed']:
                pygame.draw.rect(screen, (148, 234, 255), (wx, wy, 3, 5))
            else:
                sp_t = wd['splash_age'] / 0.25
                sp_dx = round(sp_t * 6)
                for side in (-1, 1):
                    pygame.draw.rect(
                        screen, (176, 244, 255),
                        (wx + side * sp_dx, w_top - round((1.0 - sp_t) * 4), 2, 2),
                    )

        # 7. Shimmering glints on the Underground Crystal Geode (bx = 153..161, by = 111..114)
        if light_alpha > 0.1:
            c_pulse = 0.5 + 0.5 * math.sin(self.time * 3.6)
            c_pulse2 = 0.5 + 0.5 * math.cos(self.time * 2.9 + 1.2)
            v_glint = lerp_color((198, 124, 252), (255, 240, 255), c_pulse * light_alpha)
            cy_glint = lerp_color((96, 218, 252), (236, 255, 255), c_pulse2 * light_alpha)
            pygame.draw.rect(screen, v_glint, (155 * PIXEL + dx, 111 * PIXEL + dy, PIXEL, PIXEL))
            pygame.draw.rect(screen, cy_glint, (159 * PIXEL + dx, 112 * PIXEL + dy, PIXEL, PIXEL))

    def _draw_animated_miner_and_fuse(self, screen, dx, dy, light_alpha=1.0):
        """Draw the breathing/blinking/hat-tilting Miner, helmet rim reflections & bomb fuse."""
        # 1. Miner idle cycle: gentle breathing + subtle hat/body shift + occasional glance + blink
        cycle = self.time % 4.8
        if 3.6 <= (self.time % 7.2) <= 4.35:
            pose = 'glance'
        elif 2.8 <= cycle <= 3.45:
            pose = 'hat'
        elif 1.1 <= cycle <= 2.4:
            pose = 'breath'
        else:
            pose = 'stand'
        blink = self._miner_blink_dur > 0
        lamp_flick = 0.80 + 0.20 * flicker_wave(self.time, 1.45, 0.2)
        bright_lamp = lamp_flick > 0.88
        frame = self.miner_frames[(pose, blink, bright_lamp)]

        miner_x = 716 + dx
        miner_y = 368 - frame.get_height() + dy
        screen.blit(frame, (miner_x, miner_y))

        # 2. Dynamic pixel rim-reflections from the Miner's helmet lamp onto crate, pickaxe, potion, bomb & moss
        if light_alpha > 0.15:
            beam_k = lamp_flick * light_alpha
            crate_rim = lerp_color((152, 96, 50), (242, 184, 88), beam_k * 0.78)
            bomb_rim = lerp_color((58, 63, 76), (168, 146, 108), beam_k * 0.65)
            moss_rim = lerp_color((104, 122, 76), (176, 178, 92), beam_k * 0.55)
            pick_glint = lerp_color((180, 192, 208), (255, 246, 198), beam_k * 0.85)
            # Right & top edge of wooden crate facing the miner's headlamp
            pygame.draw.rect(screen, crate_rim, (174 * PIXEL + dx, 82 * PIXEL + dy, PIXEL, 10 * PIXEL))
            pygame.draw.rect(screen, crate_rim, (166 * PIXEL + dx, 82 * PIXEL + dy, 9 * PIXEL, PIXEL))
            # Pickaxe steel tip glint from headlamp
            pygame.draw.rect(screen, pick_glint, (176 * PIXEL + dx, 81 * PIXEL + dy, PIXEL, PIXEL))
            # Speed Potion animated cyan liquid shimmer & tiny floating magic mote on top of crate
            pot_pulse = (0.55 + 0.45 * math.sin(self.time * 4.2)) * light_alpha
            pot_col = lerp_color((43, 220, 255), (210, 254, 255), pot_pulse)
            pygame.draw.rect(screen, pot_col, (168 * PIXEL + dx, 78 * PIXEL + dy, PIXEL, PIXEL))
            mote_y = 74 * PIXEL - round((self.time * 10.0) % 10.0) + dy
            mote_x = 169 * PIXEL + round(math.sin(self.time * 5.0) * 2.0) + dx
            pygame.draw.rect(screen, (148, 244, 255), (mote_x, mote_y, 2, 2))
            # Upper-right curve of the round black bomb catching headlamp glint
            pygame.draw.rect(screen, bomb_rim, (158 * PIXEL + dx, 83 * PIXEL + dy, PIXEL, 2 * PIXEL))
            pygame.draw.rect(screen, bomb_rim, (159 * PIXEL + dx, 85 * PIXEL + dy, PIXEL, 2 * PIXEL))
            # Warm grass tips between miner and crate
            for gx in (176, 178, 180):
                pygame.draw.rect(screen, moss_rim, (gx * PIXEL + dx, 92 * PIXEL + dy, PIXEL, PIXEL))

        # 3. Bomb fuse flickering spark tip
        fx, fy = 634 + dx, 314 + dy
        flick = flicker_wave(self.time, 2.6, 0.5)
        core_r = 4 if flick > 0.45 else 3
        pygame.draw.rect(screen, (255, 132, 38), (fx - core_r, fy - core_r, core_r * 2, core_r * 2))
        pygame.draw.rect(screen, (255, 244, 156), (fx - 2, fy - 2, 4, 4))
        for sx, sy, _, _, age, life in self.fuse_sparks:
            heat = 1.0 - age / life
            col = (255, 238, 130) if heat > 0.5 else (255, 140, 44)
            pygame.draw.rect(screen, col, (round(sx + dx), round(sy + dy), 3, 3))

    def _draw_layer6_particles_and_lights(self, screen, dx6, dy6, dx5, dy5, dx4, dy4, dx3, dy3,
                                          particle_alpha, light_alpha):
        """Floating dust, embers, fireflies, falling rocks & pixel-stepped atmospheric lighting."""
        if particle_alpha > 0.01:
            # 1. Multi-size ceiling & air dust motes (brighten when inside warm light cones)
            for d in self.ceiling_dust:
                a = round(d['alpha'] * particle_alpha)
                if a > 8:
                    px = round(d['x'] + dx6 * 0.65)
                    py = round(d['y'] + dy6 * 0.65)
                    in_beam = 600 <= px <= 760 and 260 <= py <= 368
                    dust_tint = (212, 182, 136) if in_beam else (156, 144, 132)
                    col = lerp_color(VOID_COLOR, dust_tint, a / 255.0)
                    s = d.get('size', 3)
                    pygame.draw.rect(screen, col, (px, py, s, s))

            # 2. Rising warm cavern embers
            for ce in self.cavern_embers:
                t = ce['age'] / ce['life']
                fade = math.sin(t * math.pi) * particle_alpha
                if fade > 0.08:
                    px = round(ce['x'] + dx6 * 0.85)
                    py = round(ce['y'] + dy6 * 0.85)
                    col = lerp_color((196, 68, 24), (255, 198, 78), (1.0 - t) * fade)
                    s = ce['size']
                    pygame.draw.rect(screen, col, (px, py, s, s))

            # 3. Occasional tiny falling rocks & bounce dust splashes
            for r in self.falling_rocks:
                px = round(r['x'] + dx6 * 0.75)
                py = round(r['y'] + dy6 * 0.75)
                s = r['size']
                pygame.draw.rect(screen, (24, 20, 18), (px - 1, py - 1, s + 2, s + 2))
                pygame.draw.rect(screen, (96, 90, 84), (px, py, s, s))

            for sx, sy, _, _, age, life in self.rock_splashes:
                fade = (1.0 - age / life) * particle_alpha
                col = lerp_color(VOID_COLOR, (148, 128, 104), fade)
                pygame.draw.rect(screen, col, (round(sx + dx5), round(sy + dy5), 3, 3))

            # 4. Floating glowing cave fireflies / light motes
            for p in self.fireflies:
                pulse = (0.45 + 0.55 * math.sin(self.time * 3.1 + p['phase'])) * particle_alpha
                if pulse <= 0.05:
                    continue
                px = round(p['x'] + dx6)
                py = round(p['y'] + dy6)
                size = p['size']
                glow = self._radial_light(12, (255, 168, 58), round(80 * pulse))
                screen.blit(glow, (px - 12, py - 12), special_flags=pygame.BLEND_RGB_ADD)
                core = lerp_color((255, 164, 52), (255, 240, 150), pulse)
                pygame.draw.rect(screen, core, (px - size // 2, py - size // 2, size, size))

        # Dynamic pixel-stepped warm lighting (helmet lamp, entrance lantern, lava, fuse, eyes)
        if light_alpha > 0.01:
            # 1. Miner helmet lamp golden ambient halo & forward beam cone
            lamp_flick = 0.82 + 0.18 * flicker_wave(self.time, 1.35, 0.2)
            lamp_x, lamp_y = 724 + dx5, 304 + dy5
            lamp_glow = self._radial_light(88, (238, 172, 68), round(40 * light_alpha * lamp_flick))
            screen.blit(lamp_glow, (lamp_x - 88, lamp_y - 88), special_flags=pygame.BLEND_RGB_ADD)
            beam_glow = self._radial_light(76, (228, 154, 56), round(36 * light_alpha * lamp_flick))
            screen.blit(beam_glow, (lamp_x - 118, lamp_y - 56), special_flags=pygame.BLEND_RGB_ADD)

            # 2. Mine entrance lantern warm flickering light
            ent_flick = 0.76 + 0.24 * flicker_wave(self.time, 1.85, 0.9)
            ent_x, ent_y = 192 * PIXEL + dx3, 65 * PIXEL + dy3
            ent_glow = self._radial_light(68, (242, 142, 46), round(44 * light_alpha * ent_flick))
            screen.blit(ent_glow, (ent_x - 68, ent_y - 68), special_flags=pygame.BLEND_RGB_ADD)

            # 3. Subterranean lava pocket warm pulsing orange glow
            lava_flick = 0.78 + 0.22 * flicker_wave(self.time, 0.95, 2.1)
            lava_x, lava_y = 856 + dx4, 552 + dy4
            lava_glow = self._radial_light(124, (248, 98, 28), round(92 * light_alpha * lava_flick))
            screen.blit(lava_glow, (lava_x - 124, lava_y - 124), special_flags=pygame.BLEND_RGB_ADD)

            # 4. Bomb fuse spark glow
            fuse_glow = self._radial_light(32, (255, 160, 52), round(76 * light_alpha * lamp_flick))
            screen.blit(fuse_glow, (634 + dx5 - 32, 314 + dy5 - 32), special_flags=pygame.BLEND_RGB_ADD)

            # 5. Doorway red eyes subtle crimson aura
            if self._eye_blink_dur <= 0:
                eye_glow = self._radial_light(40, (220, 32, 24), round(64 * light_alpha))
                screen.blit(eye_glow, (842 + dx3 - 40, 294 + dy3 - 40), special_flags=pygame.BLEND_RGB_ADD)

            # 6. Speed Potion bottle cool cyan glow on top of wooden crate
            pot_flick = 0.78 + 0.22 * math.sin(self.time * 3.8)
            pot_glow = self._radial_light(28, (43, 210, 255), round(52 * light_alpha * pot_flick))
            screen.blit(pot_glow, (169 * PIXEL + dx5 - 28, 78 * PIXEL + dy5 - 28), special_flags=pygame.BLEND_RGB_ADD)

            # 7. Underground Crystal Geode violet-cyan shimmer glow
            crys_flick = 0.72 + 0.28 * math.sin(self.time * 2.7 + 0.9)
            crys_glow = self._radial_light(44, (168, 96, 244), round(48 * light_alpha * crys_flick))
            screen.blit(crys_glow, (157 * PIXEL + dx4 - 44, 113 * PIXEL + dy4 - 44), special_flags=pygame.BLEND_RGB_ADD)

            # 8. Underground Water Pocket subtle azure ambient glow
            wat_glow = self._radial_light(52, (36, 156, 214), round(42 * light_alpha))
            screen.blit(wat_glow, (160 * PIXEL + dx4 - 52, 145 * PIXEL + dy4 - 52), special_flags=pygame.BLEND_RGB_ADD)

    # ------------------------------------------------------------------
    # Master Draw Call with Cinematic Intro Staged Reveal
    # ------------------------------------------------------------------
    def draw(self, screen, intro_state=None):
        """Render all 6 parallax layers, foreground details, and ambient animations."""
        if intro_state is None:
            bg_a = light_a = part_a = actor_a = 1.0
        else:
            bg_a = intro_state.get('bg_alpha', 1.0)
            light_a = intro_state.get('light_alpha', 1.0)
            part_a = intro_state.get('particle_alpha', 1.0)
            actor_a = intro_state.get('actor_alpha', 1.0)

        screen.fill(VOID_COLOR)
        if bg_a <= 0.005:
            return

        dx1, dy1 = self.camera.offset_for(self.LAYER_DEPTHS[1])
        dx2, dy2 = self.camera.offset_for(self.LAYER_DEPTHS[2])
        dx3, dy3 = self.camera.offset_for(self.LAYER_DEPTHS[3])
        dx4, dy4 = self.camera.offset_for(self.LAYER_DEPTHS[4])
        dx5, dy5 = self.camera.offset_for(self.LAYER_DEPTHS[5])
        dx6, dy6 = self.camera.offset_for(self.LAYER_DEPTHS[6])
        dx_fg, dy_fg = self.camera.offset_for(1.22)

        # Layer 1: Distant cave background + drifting shadow clouds
        screen.blit(self.layer1_distant, (-PAD_PX + dx1, -PAD_PX + dy1))
        for idx, cloud in enumerate(self.shadow_clouds):
            cx = 520 + idx * 130 + round(math.sin(self.time * 0.32 + idx * 2.1) * 45) + dx1
            cy = 175 + idx * 45 + round(math.cos(self.time * 0.24 + idx) * 10) + dy1
            screen.blit(cloud, (cx, cy))

        # Layer 2: Dark cave walls, arch ceiling, stalactites, swaying roots & hanging chains
        sway_idx = min(2, max(0, round(math.sin(self.time * 1.15) + 1)))
        chain_idx = min(2, max(0, round(math.sin(self.time * 0.92 + 0.8) + 1)))
        screen.blit(self.root_frames[sway_idx], (-PAD_PX + dx2, -PAD_PX + dy2))
        screen.blit(self.chain_frames[chain_idx], (-PAD_PX + dx2, -PAD_PX + dy2))
        screen.blit(self.layer2_walls, (-PAD_PX + dx2, -PAD_PX + dy2))

        # Layer 3: Wooden mine structures, swaying pulley bucket, minecart, entrance lantern & doorway eyes
        pulley_idx = min(2, max(0, round(math.sin(self.time * 1.05 + 0.4) + 1)))
        screen.blit(self.layer3_structures, (-PAD_PX + dx3, -PAD_PX + dy3))
        screen.blit(self.pulley_frames[pulley_idx], (-PAD_PX + dx3, -PAD_PX + dy3))
        self._draw_doorway_eyes(screen, dx3, dy3, light_a)

        # Layer 4: Main ground platform, ladder, rocks & animated lava chamber with wall reflections
        if actor_a > 0.01:
            if actor_a < 0.995:
                temp4 = self.layer4_platform.copy()
                temp4.set_alpha(round(255 * actor_a))
                screen.blit(temp4, (-PAD_PX + dx4, -PAD_PX + dy4))
            else:
                screen.blit(self.layer4_platform, (-PAD_PX + dx4, -PAD_PX + dy4))
            self._draw_animated_lava(screen, dx4, dy4, light_a)

        # Layer 5: Miner, crate, bomb & foreground rocks
        if actor_a > 0.01:
            if actor_a < 0.995:
                temp5 = self.layer5_static.copy()
                temp5.set_alpha(round(255 * actor_a))
                screen.blit(temp5, (-PAD_PX + dx5, -PAD_PX + dy5))
            else:
                screen.blit(self.layer5_static, (-PAD_PX + dx5, -PAD_PX + dy5))
            self._draw_animated_miner_and_fuse(screen, dx5, dy5, light_a)

        # Layer 6: Floating particles, ceiling dust, falling rocks, foreground silhouettes & lighting
        self._draw_layer6_particles_and_lights(
            screen, dx6, dy6, dx5, dy5, dx4, dy4, dx3, dy3, part_a, light_a
        )
        if actor_a > 0.01:
            if actor_a < 0.995:
                temp_fg = self.layer_fg_details.copy()
                temp_fg.set_alpha(round(255 * actor_a))
                screen.blit(temp_fg, (-PAD_PX + dx_fg, -PAD_PX + dy_fg))
            else:
                screen.blit(self.layer_fg_details, (-PAD_PX + dx_fg, -PAD_PX + dy_fg))

        # Cinematic intro darkness veil (smoothly reveals background from pitch black)
        if bg_a < 0.999:
            self.dark_veil.fill((*VOID_COLOR, round(255 * (1.0 - bg_a))))
            screen.blit(self.dark_veil, (0, 0))
