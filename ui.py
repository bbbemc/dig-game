"""Small, pixel-aligned interface for the underground game.

All UI is presentation state. The Game remains the owner of health, terrain,
liquids, enemies and win/lose conditions.
"""

import math

import pygame

from config import CELL, MACRO, SCREEN_H, SCREEN_W, SPEED_POTION_DURATION
from config import OFFSCREEN_ARROW_RANGE, PLAYER_MAX_HP, BOSS_NAME, BOSS_BAR_DRAIN
from config import BOSS_MUSIC_FADE_MS, BOSS_MUSIC_VOLUME, ARENA_FADE_IN, ARENA_FADE_HOLD
from config import DOOR_FADE_OUT
import cutscene as cutscenes
from level import DIRT, LAVA, FINAL_STAGE
from menu_scene import (
    MenuAudio,
    MenuEnvironment,
    clamp,
    ease_in_out_quad,
    ease_out_back,
    ease_out_cubic,
    flicker_wave,
    lerp,
    lerp_color,
    smooth_damp,
)


INK = (23, 20, 16)
PANEL = (33, 25, 20)
WOOD_DARK = (59, 36, 24)
WOOD = (107, 61, 34)
WOOD_LIGHT = (167, 101, 50)
METAL = (86, 81, 74)
METAL_LIGHT = (142, 136, 126)
CREAM = (241, 223, 193)
MUTED = (169, 147, 120)
RED = (201, 61, 61)
ORANGE = (232, 163, 50)
ORANGE_RED = (238, 104, 46)
GOLD_BRIGHT = (255, 242, 162)
GOLD = (252, 208, 68)
GOLD_DEEP = (224, 152, 34)
GOLD_SHADOW = (156, 92, 18)
MENU_SILVER = (186, 190, 200)
MENU_SILVER_DIM = (128, 132, 144)

# Only three options in the Main Menu — CONTINUE is completely removed.
MENU_OPTIONS = ('PLAY', 'SETTINGS', 'EXIT')
RESTART_SIGN = pygame.Rect((SCREEN_W - 380) // 2, (SCREEN_H - 180) // 2, 380, 180)
SETTINGS_ITEMS = ('MUSIC VOLUME', 'SFX VOLUME', 'FULLSCREEN', 'BACK')

# Posture fill by how full the meter is: 1 yellow, 2 orange, 3 red (broken).
POSTURE_COLORS = ((255, 214, 92), (240, 136, 40), (226, 58, 46))
# The boss bar along the foot of the screen, below the miner's posture bar.
BOSS_BAR = pygame.Rect((SCREEN_W - 560) // 2, SCREEN_H - 64, 560, 52)
BOSS_RED, BOSS_TRAIL = (196, 40, 36), (244, 196, 120)


def to_screen(game, x, y):
    """A world point on the screen, through the game's camera and zoom."""
    cx, cy = game.render_camera
    zoom = getattr(game, 'zoom', 1.0)
    return (x - cx) * zoom, (y - cy) * zoom


def screen_rect(game, rect):
    """A world rectangle as it appears on the screen."""
    x, y = to_screen(game, rect.x, rect.y)
    zoom = getattr(game, 'zoom', 1.0)
    return pygame.Rect(round(x), round(y), round(rect.w * zoom), round(rect.h * zoom))
ZONES = (
    ('ABANDONED MINE', ORANGE),
    ('DIRT CAVE', (184, 129, 74)),
    ('CRYSTAL CAVE', (141, 98, 201)),
    ('VOLCANIC RUINS', (244, 91, 40)),
)

# ---------------------------------------------------------------------------
# Hand-crafted pixel-art block font for the "DIG GAME" logo & menu glyphs
# ---------------------------------------------------------------------------
TITLE_GLYPHS = {
    'D': (
        '#######.',
        '########',
        '##....##',
        '##....##',
        '##....##',
        '##....##',
        '##....##',
        '##....##',
        '########',
        '#######.',
    ),
    'I': (
        '######',
        '######',
        '..##..',
        '..##..',
        '..##..',
        '..##..',
        '..##..',
        '..##..',
        '######',
        '######',
    ),
    'G': (
        '.#######',
        '########',
        '##....##',
        '##......',
        '##..####',
        '##..####',
        '##....##',
        '##....##',
        '########',
        '.#######',
    ),
    'A': (
        '.######.',
        '########',
        '##....##',
        '##....##',
        '########',
        '########',
        '##....##',
        '##....##',
        '##....##',
        '##....##',
    ),
    'M': (
        '##....##',
        '###..###',
        '########',
        '########',
        '##.##.##',
        '##.##.##',
        '##....##',
        '##....##',
        '##....##',
        '##....##',
    ),
    'E': (
        '########',
        '########',
        '##......',
        '##......',
        '######..',
        '######..',
        '##......',
        '##......',
        '########',
        '########',
    ),
    ' ': (
        '....',
        '....',
        '....',
        '....',
        '....',
        '....',
        '....',
        '....',
        '....',
        '....',
    ),
}

PIXEL_GLYPHS_5X7 = {
    'A': ('.###.', '##.##', '##.##', '#####', '##.##', '##.##', '##.##'),
    'B': ('####.', '##.##', '##.##', '####.', '##.##', '##.##', '####.'),
    'C': ('.####', '##...', '##...', '##...', '##...', '##...', '.####'),
    'D': ('####.', '##.##', '##.##', '##.##', '##.##', '##.##', '####.'),
    'E': ('#####', '##...', '##...', '####.', '##...', '##...', '#####'),
    'F': ('#####', '##...', '##...', '####.', '##...', '##...', '##...'),
    'G': ('.####', '##...', '##...', '##.##', '##.##', '##.##', '.####'),
    'H': ('##.##', '##.##', '##.##', '#####', '##.##', '##.##', '##.##'),
    'I': ('#####', '.###.', '.###.', '.###.', '.###.', '.###.', '#####'),
    'K': ('##.##', '##.##', '####.', '###..', '####.', '##.##', '##.##'),
    'L': ('##...', '##...', '##...', '##...', '##...', '##...', '#####'),
    'M': ('#...#', '##.##', '#####', '#####', '##.##', '##.##', '##.##'),
    'N': ('##.##', '###.#', '#####', '#####', '#.###', '##.##', '##.##'),
    'O': ('.###.', '##.##', '##.##', '##.##', '##.##', '##.##', '.###.'),
    'P': ('####.', '##.##', '##.##', '####.', '##...', '##...', '##...'),
    'R': ('####.', '##.##', '##.##', '####.', '####.', '##.##', '##.##'),
    'S': ('.####', '##...', '##...', '.###.', '...##', '...##', '####.'),
    'T': ('#####', '.###.', '.###.', '.###.', '.###.', '.###.', '.###.'),
    'U': ('##.##', '##.##', '##.##', '##.##', '##.##', '##.##', '.###.'),
    'V': ('##.##', '##.##', '##.##', '##.##', '##.##', '.###.', '..#..'),
    'X': ('##.##', '##.##', '.###.', '..#..', '.###.', '##.##', '##.##'),
    'Y': ('##.##', '##.##', '.###.', '.###.', '.###.', '.###.', '.###.'),
    '>': ('##...', '.##..', '..##.', '...##', '..##.', '.##..', '##...'),
    '<': ('...##', '..##.', '.##..', '##...', '.##..', '..##.', '...##'),
    '0': ('.###.', '##.##', '##.##', '##.##', '##.##', '##.##', '.###.'),
    '1': ('.##..', '###..', '.##..', '.##..', '.##..', '.##..', '####.'),
    '2': ('.###.', '##.##', '...##', '.###.', '##...', '##...', '#####'),
    '3': ('####.', '...##', '...##', '.###.', '...##', '...##', '####.'),
    '4': ('##.##', '##.##', '##.##', '#####', '...##', '...##', '...##'),
    '5': ('#####', '##...', '##...', '####.', '...##', '...##', '####.'),
    '6': ('.###.', '##...', '##...', '####.', '##.##', '##.##', '.###.'),
    '7': ('#####', '...##', '..##.', '..##.', '.##..', '.##..', '.##..'),
    '8': ('.###.', '##.##', '##.##', '.###.', '##.##', '##.##', '.###.'),
    '9': ('.###.', '##.##', '##.##', '.####', '...##', '...##', '.###.'),
    '%': ('##..#', '##.#.', '..#..', '.#...', '.#.##', '#..##', '...##'),
    ':': ('.....', '..#..', '..#..', '.....', '..#..', '..#..', '.....'),
    '.': ('...', '...', '...', '...', '...', '.#.', '.#.'),
    '-': ('.....', '.....', '.....', '#####', '.....', '.....', '.....'),
    ' ': ('...', '...', '...', '...', '...', '...', '...'),
}


def _build_title_surfaces(text='DIG GAME', scale=6):
    """Build the golden pixel-art title surface and its soft warm glow."""
    cols = []
    for idx, ch in enumerate(text):
        glyph = TITLE_GLYPHS.get(ch, TITLE_GLYPHS[' '])
        w = len(glyph[0])
        for gx in range(w):
            cols.append([glyph[gy][gx] == '#' for gy in range(10)])
        if idx < len(text) - 1:
            cols.append([False] * 10)
            if ch != ' ' and text[idx + 1] != ' ':
                cols.append([False] * 10)

    gw = len(cols)
    gh = 10
    pad = 4
    bw, bh = gw + pad * 2, gh + pad * 2
    base = pygame.Surface((bw, bh), pygame.SRCALPHA)

    def filled(x, y):
        return 0 <= x < gw and 0 <= y < gh and cols[x][y]

    # 1. Deep 3D block extrusion & dark pixel outline
    for x in range(gw):
        for y in range(gh):
            if not filled(x, y):
                continue
            px, py = x + pad, y + pad
            # Drop shadow & block depth
            base.set_at((px + 1, py + 2), (16, 10, 8, 255))
            base.set_at((px + 2, py + 2), (16, 10, 8, 235))
            base.set_at((px, py + 2), (22, 13, 9, 255))
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    if ox == 0 and oy == 0:
                        continue
                    if not filled(x + ox, y + oy):
                        base.set_at((px + ox, py + oy), (28, 16, 10, 255))

    # 2. Inner 3D bronze lower bevel
    for x in range(gw):
        for y in range(gh):
            if filled(x, y) and not filled(x, y + 1):
                base.set_at((x + pad, y + pad + 1), (132, 74, 16, 255))

    # 3. Chiseled golden-yellow gradient fill with bright top highlight
    row_colors = (
        (255, 236, 138),
        (255, 224, 96),
        (255, 212, 72),
        (252, 200, 58),
        (246, 188, 48),
        (240, 174, 40),
        (232, 160, 34),
        (222, 146, 28),
        (208, 132, 24),
        (188, 114, 20),
    )
    for x in range(gw):
        for y in range(gh):
            if not filled(x, y):
                continue
            px, py = x + pad, y + pad
            top_edge = not filled(x, y - 1)
            bottom_edge = not filled(x, y + 1)
            left_edge = not filled(x - 1, y)
            if top_edge:
                col = (255, 246, 176)
            elif bottom_edge:
                col = (176, 104, 20)
            elif left_edge and y < 5:
                col = (255, 232, 124)
            else:
                col = row_colors[y]
            base.set_at((px, py), (*col, 255))

    scaled = pygame.transform.scale(base, (bw * scale, bh * scale))

    # Letter-shaped warm golden glow (no oval rings)
    glow_base = pygame.Surface((bw, bh))
    glow_base.fill((0, 0, 0))
    for y in range(bh):
        for x in range(bw):
            # Distance to nearest filled letter pixel
            min_d2 = 999
            for gy in range(max(0, y - pad - 4), min(gh, y - pad + 5)):
                for gx in range(max(0, x - pad - 4), min(gw, x - pad + 5)):
                    if cols[gx][gy]:
                        d2 = (x - (gx + pad)) ** 2 + (y - (gy + pad)) ** 2
                        if d2 < min_d2:
                            min_d2 = d2
            if min_d2 <= 16:
                falloff = (1.0 - math.sqrt(min_d2) / 4.2) ** 2.0
                r = round(38 * falloff)
                g = round(24 * falloff)
                b = round(6 * falloff)
                glow_base.set_at((x, y), (r, g, b))
    glow = pygame.transform.smoothscale(glow_base, (bw * scale, bh * scale))

    # 4. Pre-baked pixel-art shimmer/sheen frames across the letter faces
    shimmer_frames = []
    num_frames = 24
    for f in range(num_frames):
        # Band sweeps across the letters during the first 16 frames, rests for 8
        band_center = -6.0 + (gw + 16.0) * (f / 16.0)
        sh_base = pygame.Surface((bw, bh), pygame.SRCALPHA)
        # Subtle overall warm breathing pulse on top edge
        breath = math.sin(f * (2.0 * math.pi / num_frames)) * 0.5 + 0.5
        top_boost = round(14 * breath)
        for x in range(gw):
            for y in range(gh):
                if not filled(x, y):
                    continue
                px, py = x + pad, y + pad
                # Diagonal sheen distance
                diag_d = abs((x + y * 0.65) - band_center)
                add_r = add_g = add_b = 0
                if f < 16 and diag_d < 3.4:
                    if diag_d < 1.3:
                        add_r, add_g, add_b = 42, 36, 26
                    elif diag_d < 2.4:
                        add_r, add_g, add_b = 24, 20, 12
                    else:
                        add_r, add_g, add_b = 12, 10, 6
                if not filled(x, y - 1):
                    add_r = max(add_r, top_boost)
                    add_g = max(add_g, top_boost)
                    add_b = max(add_b, top_boost // 2)
                if add_r > 0 or add_g > 0 or add_b > 0:
                    orig = base.get_at((px, py))
                    sh_base.set_at(
                        (px, py),
                        (
                            min(255, orig[0] + add_r),
                            min(255, orig[1] + add_g),
                            min(255, orig[2] + add_b),
                            255,
                        ),
                    )
        shimmer_frames.append(pygame.transform.scale(sh_base, (bw * scale, bh * scale)))

    return scaled, glow, shimmer_frames


def render_pixel_text(message, scale=4, color=MENU_SILVER, shadow=(16, 12, 10),
                      highlight_top=False):
    """Render crisp uppercase pixel-art text with a 3D pixel drop shadow."""
    message = message.upper()
    cols = []
    for idx, ch in enumerate(message):
        glyph = PIXEL_GLYPHS_5X7.get(ch, PIXEL_GLYPHS_5X7[' '])
        w = len(glyph[0])
        for gx in range(w):
            cols.append([glyph[gy][gx] == '#' for gy in range(7)])
        if idx < len(message) - 1:
            cols.append([False] * 7)

    gw = max(1, len(cols))
    gh = 7
    pad = 2
    bw, bh = gw + pad * 2, gh + pad * 2
    base = pygame.Surface((bw, bh), pygame.SRCALPHA)

    def filled(x, y):
        return 0 <= x < gw and 0 <= y < gh and cols[x][y]

    if shadow is not None:
        for x in range(gw):
            for y in range(gh):
                if not filled(x, y):
                    continue
                px, py = x + pad, y + pad
                base.set_at((px + 1, py + 1), (*shadow, 240))
                base.set_at((px, py + 1), (*shadow, 220))
                for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    if not filled(x + ox, y + oy):
                        base.set_at((px + ox, py + oy), (*shadow, 210))

    top_col = (
        min(255, color[0] + 28),
        min(255, color[1] + 28),
        min(255, color[2] + 24),
    )
    bot_col = (
        max(0, color[0] - 26),
        max(0, color[1] - 26),
        max(0, color[2] - 22),
    )
    for x in range(gw):
        for y in range(gh):
            if not filled(x, y):
                continue
            px, py = x + pad, y + pad
            if highlight_top and not filled(x, y - 1):
                c = top_col
            elif highlight_top and not filled(x, y + 1):
                c = bot_col
            else:
                c = color
            base.set_at((px, py), (*c, 255))

    return pygame.transform.scale(base, (bw * scale, bh * scale))


def _font(size):
    # pygame's bundled bitmap face stays crisp with antialiasing disabled.
    return pygame.font.Font(None, size)


class GameUI:
    def __init__(self):
        self.screen = 'menu'
        self.controls_from = 'menu'
        self.time = 0.0
        self.prompt_time = 0.0
        self.objective_time = 0.0
        self.transition_time = 0.0
        self.floor = 1
        self.moved = self.jumped = self.climbed = self.dug = False
        self.last_hp = 100
        self.damage_flash = 0.0
        self.boss_hint_shown = False
        self.hover = None
        self.fonts = {size: _font(size) for size in (16, 18, 19, 20, 22, 26, 30, 44, 64)}
        self.buttons = []
        from posture_hud import PostureHUD
        self.posture = PostureHUD()     # the player's bar, bottom centre
        from dialog import StageDialog
        self.dialog = StageDialog()     # the miner's stage intro, along the bottom
        self.confirm_restart_from = 'game'      # where NO goes back to
        self.confirm_restart_choice = 'YES'     # the highlighted button
        self.text_cache = {}

        # --- Cinematic Main Menu State ---
        self.menu_options = MENU_OPTIONS
        self.selected_index = 0
        self.option_highlight = [1.0, 0.0, 0.0]
        self.menu_time = 0.0
        self.intro_duration = 2.55

        # Animated Settings Panel State
        self.settings_open = False
        self.settings_progress = 0.0
        self.settings_index = 0
        self.settings_highlight = [1.0, 0.0, 0.0, 0.0]
        self.music_volume = 0.70
        self.sfx_volume = 0.80
        self.cutscene = self.pending_line = None   # the boss intro, while it plays
        self.fade_in = 0.0                         # s of fade from black left
        self.door_fade = None                      # s of fade to black left (boss door)
        self.boss_music = False
        self.fullscreen = False
        self.dragging_slider = None
        self.slider_rects = {}

        # Screen Transitions ('PLAY', 'EXIT')
        self.menu_transition = None
        self.exit_requested = False
        self.on_start_play = None
        self.on_toggle_fullscreen = None
        self.on_exit_game = None

        # Separated 6-layer Parallax Environment & Procedural UI Audio
        self.menu_env = MenuEnvironment()
        self.menu_audio = MenuAudio()
        self.menu_audio.set_music_volume(self.music_volume)
        self.menu_audio.set_sfx_volume(self.sfx_volume)
        self._last_mouse_pos = None
        self._title_surface, self._title_glow, self._title_shimmer_frames = _build_title_surfaces(
            'DIG GAME', scale=5
        )
        self.selection_pulse = 0.0
        self._pixel_text_cache = {}
        self._menu_sparks = [
            {'x': 0.0, 'y': 0.0, 'vx': 12.0, 'vy': -14.0, 'age': i * 0.25, 'life': 0.9}
            for i in range(5)
        ]

    def _cached_pixel_text(self, message, scale, color, highlight_top=False):
        qcol = (color[0] // 4 * 4, color[1] // 4 * 4, color[2] // 4 * 4)
        key = (message, scale, qcol, highlight_top)
        if key not in self._pixel_text_cache:
            if len(self._pixel_text_cache) > 256:
                self._pixel_text_cache.clear()
            self._pixel_text_cache[key] = render_pixel_text(
                message, scale=scale, color=qcol, highlight_top=highlight_top
            )
        return self._pixel_text_cache[key]

    def open_menu(self, replay_intro=False):
        """Return to the Main Menu cleanly."""
        self.stop_boss_music()
        self.screen = 'menu'
        self.settings_open = False
        self.settings_progress = 0.0
        self.menu_transition = None
        self.dragging_slider = None
        if replay_intro:
            self.menu_time = 0.0
            self.menu_env.reset()
        else:
            self.menu_time = max(self.menu_time, self.intro_duration + 0.1)

    def start(self, game, intro=True, cutscene=None):
        """Begin play. A ``cutscene`` (cutscene.Cutscene) plays first; the
        stage's intro line then waits until it ends (see end_cutscene)."""
        from dialog import dialogue_for
        self.stop_boss_music()
        line = dialogue_for(game) if intro else None
        self.cutscene, self.pending_line, self.fade_in = cutscene, line, 0.0
        self.door_fade = None
        if cutscene is None and getattr(game, 'final_boss_room', False):
            self.fade_in = ARENA_FADE_IN        # out of the dark into the arena
        self.dialog.start(None if cutscene else line)
        self.screen = 'game'
        self.buttons = []
        self.settings_open = False
        self.settings_progress = 0.0
        self.dragging_slider = None
        self.time = self.prompt_time = 0.0
        self.objective_time = 5.0
        self.transition_time = 0.0
        self.floor = self.current_floor(game)
        self.moved = self.jumped = self.climbed = self.dug = False
        self.last_hp = game.hp
        self.damage_flash = 0.0
        self.boss_hint_shown = False
        self.boss_bar_alpha = 0.0     # the boss bar fades in when the fight starts
        self.boss_trail = None        # damage trail, in health pips
        self.boss_bar_hold = 0.0      # seconds the emptied bar stays after the kill
        self.posture.reset()
        self.menu_audio.update_ambient(active=False)
        if cutscene is not None:
            self.screen = 'cutscene'      # the game waits behind it, like the pause menu
            cutscene.start()

    def start_door_fade(self):
        """Through the boss room's door: the stage fades to black first."""
        if self.door_fade is None:
            self.door_fade = DOOR_FADE_OUT

    @property
    def door_fade_done(self):
        return self.door_fade is not None and self.door_fade <= 0

    def skip_cutscene(self):
        if self.cutscene is not None:
            self.cutscene.skip()          # ends on the next update

    def end_cutscene(self, game):
        """The intro is over: fade the arena in, start the fight and its music."""
        self.cutscene = None
        self.screen = 'game'
        self.fade_in = ARENA_FADE_IN
        self.objective_time = 5.0
        self.dialog.start(self.pending_line)
        if hasattr(game, 'start_boss_fight'):
            game.start_boss_fight()
        self.boss_music = cutscenes.play_music(
            cutscenes.BOSS_MUSIC, BOSS_MUSIC_VOLUME * self.music_volume, BOSS_MUSIC_FADE_MS)

    def stop_boss_music(self):
        if self.boss_music:
            cutscenes.stop_music()
        self.boss_music = False

    # ------------------------------------------------------------------
    # Cinematic Intro Timeline (non-blocking, ~2.55 seconds)
    # ------------------------------------------------------------------
    def intro_progress(self, t=None):
        """Compute staged alpha/scale values for the 7-step cinematic intro."""
        if t is None:
            t = self.menu_time
        # 1. Start completely dark (0.00s - 0.18s)
        # 2. Underground cave background slowly fades in (0.18s - 1.15s)
        bg_alpha = ease_out_cubic(clamp((t - 0.18) / 0.97))
        # 3. Ambient lighting gradually appears (0.45s - 1.45s)
        light_alpha = ease_in_out_quad(clamp((t - 0.45) / 1.00))
        # 4. Small glowing particles begin floating (0.65s - 1.60s)
        particle_alpha = ease_out_cubic(clamp((t - 0.65) / 0.95))
        # 5. Miner and foreground elements become visible (0.82s - 1.75s)
        actor_alpha = ease_out_cubic(clamp((t - 0.82) / 0.93))
        # 6. Game title "DIG GAME" fades in with subtle scale-up (1.20s - 2.02s)
        title_raw = clamp((t - 1.20) / 0.82)
        title_alpha = ease_out_cubic(title_raw)
        title_scale = lerp(0.88, 1.0, ease_out_back(title_raw, overshoot=0.9))
        # 7. Menu options appear one by one with slight delay (1.68s - 2.55s)
        option_alphas = []
        option_offsets = []
        for idx in range(len(self.menu_options)):
            start_t = 1.68 + idx * 0.18
            opt_raw = clamp((t - start_t) / 0.48)
            opt_ease = ease_out_cubic(opt_raw)
            option_alphas.append(opt_ease)
            option_offsets.append(round((1.0 - opt_ease) * -14))
        return {
            'bg_alpha': bg_alpha,
            'light_alpha': light_alpha,
            'particle_alpha': particle_alpha,
            'actor_alpha': actor_alpha,
            'title_alpha': title_alpha,
            'title_scale': title_scale,
            'option_alphas': option_alphas,
            'option_offsets': option_offsets,
            'complete': t >= self.intro_duration,
        }

    @staticmethod
    def layered(game):
        """Whether the game is a multi-layer world (The Deep Descent)."""
        return bool(getattr(game, 'layers', None))

    @classmethod
    def current_floor(cls, game):
        if not cls.layered(game):
            return 1
        return min(len(ZONES), game.layer_at(game.player.rect.centery))

    @staticmethod
    def in_opening_map(game):
        rect = game.player.rect
        return bool(getattr(game, 'chamber', None)) and game.in_chamber(
            rect.centerx // MACRO, rect.centery // MACRO)

    @staticmethod
    def boss_near(game):
        boss = getattr(game, 'boss', None)
        return (boss is not None and boss in game.monsters
                and abs(game.player.rect.centerx - boss.rect.centerx) < 500
                and abs(game.player.rect.centery - boss.rect.centery) < 400)

    def note_input(self, horizontal, jump, vertical, digging, game):
        if horizontal:
            self.moved = True
        if jump:
            self.jumped = True
        if vertical and game.player.on_ladder:
            self.climbed = True
        if digging:
            self.dug = True

    def _update_menu_state(self, dt):
        self.menu_time += dt
        self.selection_pulse = max(0.0, self.selection_pulse - dt * 4.2)
        self.menu_env.update(dt, self._last_mouse_pos)

        # Smoothly interpolate option selection highlights
        for i in range(len(self.menu_options)):
            target = 1.0 if (i == self.selected_index and not self.settings_open) else 0.0
            self.option_highlight[i] = smooth_damp(self.option_highlight[i], target, 12.0, dt)

        # Smoothly interpolate Settings panel slide-in / slide-out
        target_settings = 1.0 if self.settings_open else 0.0
        self.settings_progress = smooth_damp(self.settings_progress, target_settings, 11.0, dt)
        if abs(self.settings_progress - target_settings) < 0.004:
            self.settings_progress = target_settings

        for i in range(len(SETTINGS_ITEMS)):
            target = 1.0 if (self.settings_open and i == self.settings_index) else 0.0
            self.settings_highlight[i] = smooth_damp(self.settings_highlight[i], target, 12.0, dt)

        # Update tiny pixel selection sparks around the selected option
        for idx, sp in enumerate(self._menu_sparks):
            sp['age'] += dt
            if sp['age'] >= sp['life']:
                sp['age'] = 0.0
                sp['x'] = (idx * 23) % 78
                sp['y'] = ((idx * 11) % 16) - 8
                sp['vx'] = 8.0 + (idx % 3) * 5.0
                sp['vy'] = -10.0 - (idx % 2) * 6.0
            else:
                sp['x'] += sp['vx'] * dt
                sp['y'] += sp['vy'] * dt

    def _update_menu_transition(self, dt):
        if self.menu_transition is None:
            return
        tr = self.menu_transition
        tr['timer'] += dt
        action = tr['action']
        if action == 'PLAY':
            # At 0.45s (screen fully dark), switch into Stage 1 gameplay
            if not tr['switched'] and tr['timer'] >= 0.45:
                tr['switched'] = True
                if callable(self.on_start_play):
                    self.on_start_play()
                else:
                    self.screen = 'game'
            if tr['timer'] >= tr['duration']:
                self.menu_transition = None
        elif action == 'EXIT':
            if not tr['switched'] and tr['timer'] >= tr['duration']:
                tr['switched'] = True
                self.exit_requested = True
                if callable(self.on_exit_game):
                    self.on_exit_game()

    def update(self, dt, game):
        self.time += dt
        self.damage_flash = max(0.0, self.damage_flash - dt)
        self._update_menu_transition(dt)

        if self.screen == 'menu':
            self._update_menu_state(dt)
            intro = self.intro_progress()
            fade = intro['bg_alpha']
            if self.menu_transition is not None:
                t = self.menu_transition['timer']
                fade *= clamp(1.0 - t / 0.45)
            self.menu_audio.update_ambient(active=True, fade=fade)
            return

        self.menu_audio.update_ambient(active=False)
        if self.screen == 'cutscene' and self.cutscene is not None:
            self.cutscene.update(dt)
            if self.cutscene.done:
                self.end_cutscene(game)
            return
        self.fade_in = max(0.0, self.fade_in - dt)
        if self.door_fade is not None:
            self.door_fade = max(0.0, self.door_fade - dt)
        if self.screen != 'game' or game is None:
            return
        self.dialog.update(dt)
        if not self.dialog.active:      # control prompts wait for the intro line
            self.prompt_time += dt
        self.objective_time = max(0.0, self.objective_time - dt)
        self.transition_time = max(0.0, self.transition_time - dt)
        if self.layered(game):
            floor = self.current_floor(game)
            if floor > self.floor:          # announce each new, deeper layer
                self.transition_time = 2.0
                self.objective_time = 5.0
            self.floor = floor
            if not self.boss_hint_shown and self.boss_near(game):
                self.boss_hint_shown = True
                self.objective_time = 5.0
        if game.hp < self.last_hp:
            self.damage_flash = 0.4
        self.last_hp = game.hp
        self.update_boss_bar(dt, game)
        if hasattr(game, 'combat'):
            self.posture.update(dt, game)     # paused: not reached, so it freezes

    # ------------------------------------------------------------------
    # Menu Keyboard & Mouse Interaction
    # ------------------------------------------------------------------
    def trigger_menu_action(self, label):
        """Execute a Main Menu or Settings action with smooth transitions."""
        if self.menu_transition is not None:
            return None
        if label == 'PLAY':
            self.menu_audio.play('select')
            self.settings_open = False
            self.menu_transition = {
                'action': 'PLAY',
                'timer': 0.0,
                'duration': 1.35,
                'switched': False,
            }
            return 'PLAY'
        if label == 'SETTINGS':
            self.menu_audio.play('select')
            self.settings_open = True
            self.settings_index = 0
            return 'SETTINGS'
        if label == 'EXIT':
            self.menu_audio.play('back')
            self.settings_open = False
            self.menu_transition = {
                'action': 'EXIT',
                'timer': 0.0,
                'duration': 0.45,
                'switched': False,
            }
            return 'EXIT'
        if label in ('BACK', 'SETTINGS_BACK'):
            self.menu_audio.play('back')
            self.settings_open = False
            self.dragging_slider = None
            return 'BACK'
        if label == 'FULLSCREEN_TOGGLE':
            self.toggle_fullscreen()
            return 'FULLSCREEN_TOGGLE'
        if label == 'MUSIC_DOWN':
            self.set_music_volume(self.music_volume - 0.10)
            return 'MUSIC_DOWN'
        if label == 'MUSIC_UP':
            self.set_music_volume(self.music_volume + 0.10)
            return 'MUSIC_UP'
        if label == 'SFX_DOWN':
            self.set_sfx_volume(self.sfx_volume - 0.10)
            return 'SFX_DOWN'
        if label == 'SFX_UP':
            self.set_sfx_volume(self.sfx_volume + 0.10)
            return 'SFX_UP'
        return label

    def set_music_volume(self, value):
        new_val = round(clamp(value, 0.0, 1.0), 2)
        if abs(new_val - self.music_volume) > 0.005:
            self.music_volume = new_val
            self.menu_audio.set_music_volume(self.music_volume)
            self.menu_audio.play('slider')
        else:
            self.music_volume = new_val
            self.menu_audio.set_music_volume(self.music_volume)
        if self.boss_music:
            cutscenes.set_music_volume(BOSS_MUSIC_VOLUME * self.music_volume)

    def set_sfx_volume(self, value):
        new_val = round(clamp(value, 0.0, 1.0), 2)
        changed = abs(new_val - self.sfx_volume) > 0.005
        self.sfx_volume = new_val
        self.menu_audio.set_sfx_volume(self.sfx_volume)
        if changed:
            self.menu_audio.play('slider')

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.menu_audio.play('select')
        if callable(self.on_toggle_fullscreen):
            self.on_toggle_fullscreen(self.fullscreen)

    def handle_menu_key(self, key):
        """Keyboard navigation for Main Menu and Settings panel."""
        if self.screen != 'menu' or self.menu_transition is not None:
            return None

        # Fast-forward intro if player presses a key while intro is still fading in
        if self.menu_time < self.intro_duration * 0.75:
            self.menu_time = self.intro_duration

        if self.settings_open:
            if key == pygame.K_ESCAPE:
                return self.trigger_menu_action('BACK')
            if key in (pygame.K_UP, pygame.K_w):
                self.settings_index = (self.settings_index - 1) % len(SETTINGS_ITEMS)
                self.menu_audio.play('hover')
                return 'NAV'
            if key in (pygame.K_DOWN, pygame.K_s):
                self.settings_index = (self.settings_index + 1) % len(SETTINGS_ITEMS)
                self.menu_audio.play('hover')
                return 'NAV'
            if key in (pygame.K_LEFT, pygame.K_a):
                if self.settings_index == 0:
                    self.set_music_volume(self.music_volume - 0.10)
                    return 'MUSIC_DOWN'
                if self.settings_index == 1:
                    self.set_sfx_volume(self.sfx_volume - 0.10)
                    return 'SFX_DOWN'
                if self.settings_index == 2:
                    self.toggle_fullscreen()
                    return 'FULLSCREEN_TOGGLE'
            if key in (pygame.K_RIGHT, pygame.K_d):
                if self.settings_index == 0:
                    self.set_music_volume(self.music_volume + 0.10)
                    return 'MUSIC_UP'
                if self.settings_index == 1:
                    self.set_sfx_volume(self.sfx_volume + 0.10)
                    return 'SFX_UP'
                if self.settings_index == 2:
                    self.toggle_fullscreen()
                    return 'FULLSCREEN_TOGGLE'
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                if self.settings_index == 2:
                    self.toggle_fullscreen()
                    return 'FULLSCREEN_TOGGLE'
                if self.settings_index == 3:
                    return self.trigger_menu_action('BACK')
            return None

        # Main Menu navigation (PLAY, SETTINGS, EXIT)
        if key in (pygame.K_UP, pygame.K_w):
            self.selected_index = (self.selected_index - 1) % len(self.menu_options)
            self.selection_pulse = 1.0
            self.menu_audio.play('hover')
            return 'NAV'
        if key in (pygame.K_DOWN, pygame.K_s):
            self.selected_index = (self.selected_index + 1) % len(self.menu_options)
            self.selection_pulse = 1.0
            self.menu_audio.play('hover')
            return 'NAV'
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.selection_pulse = 1.0
            chosen = self.menu_options[self.selected_index]
            return self.trigger_menu_action(chosen)
        return None

    def _apply_slider_mouse(self, kind, mx):
        rect = self.slider_rects.get(kind)
        if rect is None or rect.width <= 0:
            return
        ratio = clamp((mx - rect.left) / rect.width, 0.0, 1.0)
        if kind == 'music':
            self.set_music_volume(ratio)
        elif kind == 'sfx':
            self.set_sfx_volume(ratio)

    # ------------------------------------------------------------------
    # Restart confirmation (R during play)
    # ------------------------------------------------------------------
    @property
    def confirm_restart_open(self):
        return self.screen == 'confirm_restart'

    def open_restart_confirm(self):
        """Ask before restarting. Like the pause menu, the game waits behind it."""
        if self.confirm_restart_open:
            return
        self.confirm_restart_from = self.screen
        self.confirm_restart_choice = 'YES'     # so Enter confirms straight away
        self.screen = 'confirm_restart'

    def close_restart_confirm(self):
        if self.confirm_restart_open:
            self.screen = self.confirm_restart_from

    def handle_restart_confirm_key(self, key):
        """Returns 'CONFIRM RESTART' or 'CANCEL RESTART' once the player decides."""
        if key == pygame.K_y:
            return 'CONFIRM RESTART'
        if key in (pygame.K_n, pygame.K_ESCAPE):
            return 'CANCEL RESTART'
        if key in (pygame.K_a, pygame.K_LEFT):
            self.confirm_restart_choice = 'YES'
        elif key in (pygame.K_d, pygame.K_RIGHT):
            self.confirm_restart_choice = 'NO'
        elif key in (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER):
            return ('CONFIRM RESTART' if self.confirm_restart_choice == 'YES'
                    else 'CANCEL RESTART')
        return None

    def handle_mouse_motion(self, pos):
        """Update mouse parallax target, hover states, and active slider drag."""
        self._last_mouse_pos = pos
        if self.confirm_restart_open:
            for rect, label in self.buttons:
                if rect.collidepoint(pos):
                    self.confirm_restart_choice = ('YES' if label == 'CONFIRM RESTART'
                                                   else 'NO')
        if self.screen != 'menu' or self.menu_transition is not None:
            return
        if self.dragging_slider is not None and self.settings_open:
            self._apply_slider_mouse(self.dragging_slider, pos[0])
            return
        for rect, label in self.buttons:
            if not rect.collidepoint(pos):
                continue
            if self.settings_open:
                row_map = {
                    'MUSIC_SLIDER': 0, 'MUSIC_DOWN': 0, 'MUSIC_UP': 0,
                    'SFX_SLIDER': 1, 'SFX_DOWN': 1, 'SFX_UP': 1,
                    'FULLSCREEN_TOGGLE': 2,
                    'BACK': 3,
                }
                if label in row_map and self.settings_index != row_map[label]:
                    self.settings_index = row_map[label]
                    self.menu_audio.play('hover')
            else:
                if label in self.menu_options:
                    idx = self.menu_options.index(label)
                    if idx != self.selected_index:
                        self.selected_index = idx
                        self.selection_pulse = 1.0
                        self.menu_audio.play('hover')

    def handle_mouse_down(self, pos, button=1):
        """Handle mouse click on Main Menu options or Settings controls."""
        self._last_mouse_pos = pos
        if button != 1:
            return None
        if self.screen == 'menu':
            if self.menu_transition is not None:
                return None
            if self.menu_time < self.intro_duration * 0.75:
                self.menu_time = self.intro_duration
            if self.settings_open:
                for kind in ('music', 'sfx'):
                    srect = self.slider_rects.get(kind)
                    if srect is not None and srect.inflate(8, 10).collidepoint(pos):
                        self.settings_index = 0 if kind == 'music' else 1
                        self.dragging_slider = kind
                        self._apply_slider_mouse(kind, pos[0])
                        return f'{kind.upper()}_SLIDER'
            hit = self.click(pos)
            if hit:
                return self.trigger_menu_action(hit)
            return None
        return self.click(pos)

    def handle_mouse_up(self, pos, button=1):
        if button == 1:
            self.dragging_slider = None

    def text(self, surface, message, size, color, center=None, topleft=None):
        image = self.fonts[size].render(message, False, color)
        rect = image.get_rect()
        if center is not None:
            rect.center = center
        else:
            rect.topleft = topleft
        surface.blit(image, rect)
        return rect

    def frame(self, surface, rect, accent=WOOD_LIGHT, fill=PANEL):
        rect = pygame.Rect(rect)
        pygame.draw.rect(surface, INK, rect)
        pygame.draw.rect(surface, WOOD_DARK, rect.inflate(-2, -2))
        pygame.draw.rect(surface, WOOD, rect.inflate(-6, -6), 2)
        pygame.draw.line(surface, accent, (rect.x + 7, rect.y + 6),
                         (rect.right - 8, rect.y + 6), 2)
        pygame.draw.rect(surface, fill, rect.inflate(-12, -12))
        for x in (rect.x + 5, rect.right - 8):
            for y in (rect.y + 5, rect.bottom - 8):
                pygame.draw.rect(surface, (28, 28, 27), (x, y, 4, 4))
                pygame.draw.rect(surface, METAL, (x, y, 2, 2))

    def overlay(self, surface, alpha=185, color=INK):
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((*color, alpha))
        surface.blit(shade, (0, 0))

    def button(self, surface, label, rect, mouse, accent=WOOD_LIGHT):
        rect = pygame.Rect(rect)
        hovered = rect.collidepoint(mouse)
        self.frame(surface, rect, ORANGE if hovered else accent,
                   (63, 40, 26) if hovered else PANEL)
        self.text(surface, label, 22, CREAM if hovered else MUTED,
                  center=(rect.centerx, rect.centery + (1 if hovered else 0)))
        self.buttons.append((rect, label))

    def keycap(self, surface, label, x, y, width=28):
        self.frame(surface, (x, y, width, 28), METAL, (49, 39, 32))
        self.text(surface, label, 18, CREAM, center=(x + width // 2, y + 14))

    def health(self, surface, game):
        rect = pygame.Rect(16, 14, 210, 42)
        self.frame(surface, rect, RED if self.damage_flash else WOOD_LIGHT)
        # A tiny block-built heart avoids antialiased icon edges.
        heart = ((2, 0, 4, 3), (10, 0, 4, 3), (0, 3, 16, 7),
                 (2, 10, 12, 3), (5, 13, 6, 3), (7, 16, 2, 2))
        for x, y, w, h in heart:
            pygame.draw.rect(surface, RED, (28 + x, 25 + y, w, h))
        pygame.draw.rect(surface, (12, 10, 10), (54, 26, 159, 18))
        fill = round(155 * max(0, min(PLAYER_MAX_HP, game.hp)) / PLAYER_MAX_HP)
        if fill:
            bar_color = RED if game.hp > PLAYER_MAX_HP / 4 else (240, 93, 60)
            pygame.draw.rect(surface, bar_color, (56, 28, fill, 14))
            pygame.draw.line(surface, (250, 125, 105), (57, 29),
                             (55 + fill, 29))
        self.text(surface, f'{round(game.hp)} / {PLAYER_MAX_HP}', 20, CREAM, center=(134, 35))
        oxygen_rect = pygame.Rect(234, 14, 184, 42)
        oxygen_color = (69, 180, 214)
        self.frame(surface, oxygen_rect, oxygen_color)
        self.text(surface, 'O2', 18, CREAM, center=(254, 35))
        pygame.draw.rect(surface, (12, 10, 10), (272, 26, 136, 18))
        oxygen = max(0.0, min(100.0, game.oxygen))
        oxygen_fill = round(132 * oxygen / 100)
        if oxygen_fill:
            pygame.draw.rect(surface, oxygen_color, (274, 28, oxygen_fill, 14))
            pygame.draw.line(surface, (143, 224, 243), (275, 29),
                             (273 + oxygen_fill, 29))
        self.text(surface, f'{round(oxygen)}%', 18, CREAM, center=(340, 35))

    def dig_energy(self, surface, game):
        meter = getattr(game, 'dig_meter', None)
        if meter is None:
            return
        low = meter.fraction < 0.25
        color = (240, 93, 60) if low else (214, 150, 62)
        rect = pygame.Rect(426, 14, 184, 42)
        self.frame(surface, rect, color)
        self.text(surface, 'DIG', 18, CREAM, center=(450, 35))
        pygame.draw.rect(surface, (12, 10, 10), (472, 26, 128, 18))
        fill = round(124 * meter.fraction)
        if fill:
            pygame.draw.rect(surface, color, (474, 28, fill, 14))
            pygame.draw.line(surface, (246, 205, 130), (475, 29), (473 + fill, 29))
        self.text(surface, f'{round(meter.fraction * 100)}%', 18, CREAM, center=(536, 35))
        gun = getattr(game, 'gun', None)
        if gun is not None:
            status = 'READY' if gun.cooldown <= 0 else f'{gun.cooldown:.1f}s'
            self.text(surface, f'RMB GUN {status}', 16,
                      CREAM if gun.cooldown <= 0 else (150, 120, 110),
                      topleft=(618, 28))
        if getattr(game, 'dig_gain_timer', 0) > 0 and game.dig_gain:
            rise = round((1.6 - game.dig_gain_timer) * 12)
            self.text(surface, f'+{round(game.dig_gain / meter.capacity * 100)}% DIG', 20,
                      (150, 230, 120), center=(536, 72 - rise))
        if meter.empty and game.state == 'play':
            panel = pygame.Rect(0, 0, 470, 64)
            panel.center = (SCREEN_W // 2, 156)
            self.frame(surface, panel, RED)
            self.text(surface, 'OUT OF DIG ENERGY', 22, RED,
                      center=(panel.centerx, panel.top + 22))
            self.text(surface, 'Press R to retry the stage', 18, CREAM,
                      center=(panel.centerx, panel.top + 45))

    def bomb_count(self, surface, game):
        bombs = getattr(game, 'bombs', None)
        if bombs is None or not bombs.enabled:
            return
        rect = pygame.Rect(16, 102, 112, 34)
        self.frame(surface, rect)
        from bombs import draw_bomb
        draw_bomb(surface, pygame.Rect(26, 107, 24, 24), 24)
        self.text(surface, f'x {bombs.carried}', 20, CREAM, topleft=(58, 110))
        if bombs.carried:
            self.text(surface, 'HOLD Q TO AIM', 18, CREAM, topleft=(134, 112))

    def gold_wallet(self, surface, game):
        rect = pygame.Rect(16, 62, 112, 34)
        self.frame(surface, rect, (226, 166, 55))
        from gold import draw_coin_icon
        draw_coin_icon(surface, (34, rect.centery), size=22)
        self.text(surface, f'G {game.gold}', 20, CREAM, topleft=(52, 70))

    def key_inventory(self, surface, game):
        if ((game.stage_number not in (1, 2) and not game.bonus_room)
                or getattr(game, 'final_boss_room', False)):
            return
        has_key = game.has_key or game.key_collected
        rect = pygame.Rect(SCREEN_W - 172, SCREEN_H - 62, 158, 48)
        self.frame(surface, rect, ORANGE if has_key else WOOD_LIGHT)
        self.text(surface, 'KEY: YES' if has_key else 'KEY: NO',
                  20, CREAM, center=(rect.centerx - 3, rect.centery))
        if has_key:
            icon = pygame.Rect(rect.right - 42, rect.y + 4, 40, 40)
            surface.blit(game.key_image, game.key_image.get_rect(center=icon.center))

    def speed_potion_timer(self, surface, game):
        potions = getattr(game, 'potions', None)
        remaining = getattr(potions, 'speed_timer', 0.0)
        if remaining <= 0:
            return
        rect = pygame.Rect(16, SCREEN_H - 54, 170, 38)
        color = (43, 220, 255)
        self.frame(surface, rect, color)
        self.text(surface, 'SPEED', 18, CREAM, topleft=(29, rect.y + 8))
        self.text(surface, f'{math.ceil(remaining)}s', 18, color,
                  topleft=(133, rect.y + 8))
        bar = pygame.Rect(30, rect.y + 26, 142, 4)
        pygame.draw.rect(surface, (12, 10, 10), bar)
        fill = round(bar.width * min(1.0, remaining / SPEED_POTION_DURATION))
        if fill:
            pygame.draw.rect(surface, color, (bar.x, bar.y, fill, bar.height))

    def area(self, surface, game):
        number = self.current_floor(game)
        if self.layered(game) and not self.in_opening_map(game):
            name, accent = ZONES[number - 1]
            label = f'B{number}'
        else:
            name, accent = self.stage_title(game), ORANGE
            label = ('S5.5' if getattr(game, 'final_boss_room', False)
                     else f'S{game.stage_number}')
        rect = pygame.Rect(716, 14, 228, 42)
        self.frame(surface, rect, accent)
        tag = pygame.Rect(726, 23, max(30, self.fonts[20].size(label)[0] + 10), 23)
        pygame.draw.rect(surface, WOOD, tag)
        self.text(surface, label, 20, CREAM, center=tag.center)
        room = pygame.Rect(tag.right + 6, rect.y, rect.right - 10 - tag.right - 6, rect.h)
        size = next((size for size in (18, 16) if self.fonts[size].size(name)[0] <= room.w), 16)
        self.text(surface, name, size, CREAM, center=room.center)

    @staticmethod
    def stage_title(game):
        """The stage's name without a 'STAGE n:' prefix the label already shows."""
        return game.stage_name.split(': ', 1)[-1]

    def _near_lava(self, game):
        px, py = game.player.rect.centerx // CELL, game.player.rect.centery // CELL
        nearest = 1000
        for y in range(max(0, py - 12), min(game.world.height, py + 13)):
            for x in range(max(0, px - 12), min(game.world.width, px + 13)):
                if game.liquids.types.get(game.world.index(x, y)) == LAVA:
                    nearest = min(nearest, abs(x - px) + abs(y - py))
        return nearest

    def danger(self, surface, game):
        distance = self._near_lava(game)
        if distance > 9:
            return
        strength = max(0, (10 - distance) / 10)
        edge = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        color = (244, 91, 40, round(12 + 28 * strength))
        for width in (3, 7, 12):
            pygame.draw.rect(edge, color, (0, 0, SCREEN_W, SCREEN_H), width)
        surface.blit(edge, (0, 0))
        self.text(surface, '!  HEAT', 18, ORANGE, center=(SCREEN_W // 2, 78))

    def _dig_target(self, game, mouse):
        cx, cy = game.render_camera
        zoom = getattr(game, 'zoom', 1.0)
        x, y = round(cx + mouse[0] / zoom) // CELL, round(cy + mouse[1] / zoom) // CELL
        if not (0 <= x < game.world.width and 0 <= y < game.world.height):
            return False
        # Every stage allows digging visible dirt anywhere on screen.
        return game.world.foreground[game.world.index(x, y)] == DIRT

    def offscreen_arrows(self, surface, game, seen=()):
        """Edge arrows toward enemies just off screen, since a gunner sees
        (and shoots) farther than half the screen. Gunners are red, the
        boss violet, walkers amber; bright if it sees the miner, flashing
        when it is about to fire, dim otherwise."""
        view = surface.get_rect()
        player = pygame.Vector2(to_screen(game, *game.player.rect.center))
        inner = pygame.Rect(20, 72, SCREEN_W - 40, SCREEN_H - 72 - 20)  # below the top HUD
        start = pygame.Vector2(max(inner.left + 1, min(player.x, inner.right - 1)),
                               max(inner.top + 1, min(player.y, inner.bottom - 1)))
        blink = int(getattr(game, 'world_time', 0.0) * 12) % 2
        for enemy in game.monsters:
            box = screen_rect(game, enemy.rect)
            if box.colliderect(view):
                continue
            delta = pygame.Vector2(box.center) - player
            distance = delta.length()
            if not distance or distance > OFFSCREEN_ARROW_RANGE:
                continue
            direction = delta / distance
            reach = min((((inner.right if direction.x > 0 else inner.left) - start.x) / direction.x
                         if direction.x else math.inf),
                        (((inner.bottom if direction.y > 0 else inner.top) - start.y) / direction.y
                         if direction.y else math.inf))
            tip = start + direction * max(0.0, reach)
            if getattr(enemy, 'is_boss', False):
                color, size = (196, 96, 232), 11
            elif getattr(enemy, 'shoots_projectiles', False):
                color, size = (240, 70, 50), 10
            else:
                color, size = (232, 163, 50), 8
            if getattr(enemy, 'aiming', False) and blink:
                color = (255, 250, 236)
            elif id(enemy) not in seen:
                color = tuple(round(c * 0.55) for c in color)   # not hunting yet
                size -= 2
            side = pygame.Vector2(-direction.y, direction.x)
            wing = size * 0.85
            back = tip - direction * (size * 1.75)
            notch = tip - direction * (size * 1.1)
            outline = [tip + direction * 2,
                       back + side * (wing + 2) - direction * 2,
                       notch - direction * 2,
                       back - side * (wing + 2) - direction * 2]
            pygame.draw.polygon(surface, INK, outline)
            pygame.draw.polygon(surface, color,
                                [tip, back + side * wing, notch, back - side * wing])

    def tutorial(self, surface, game, mouse):
        if self.prompt_time < 0.45:
            return
        if not self.moved:
            keys, label = ('A', 'D'), 'MOVE'
        elif not self.jumped:
            keys, label = ('SPACE',), 'JUMP'
        elif not self.climbed and game.renderer.ladder_at(game.player.rect.inflate(70, 30)):
            keys, label = ('W', 'S'), 'CLIMB'
        elif not self.dug and self._dig_target(game, mouse):
            keys, label = ('MOUSE',), 'HOLD TO DIG'
        else:
            return
        panel = pygame.Surface((280, 54), pygame.SRCALPHA)
        panel.fill((23, 20, 16, 225))
        pygame.draw.rect(panel, WOOD, (0, 0, 280, 54), 2)
        x = 353
        for key in keys:
            width = 60 if key in ('SPACE', 'MOUSE') else 28
            self.keycap(panel, key, x - 340, 13, width)
            x += width + 5
        self.text(panel, label, 20, CREAM, center=((x + 609) // 2 - 340, 27))
        panel.set_alpha(min(255, round((self.prompt_time - 0.45) * 1100)))
        # The posture bar owns the bottom centre in combat: the prompt moves up.
        surface.blit(panel, (340, 552 - round(72 * self.posture.visibility)))

    def objective(self, surface, game):
        sign_message = self.stage_sign_message(game)
        near_stage_sign = sign_message is not None
        if (not near_stage_sign
                and (self.objective_time <= 0 or self.transition_time > 0)):
            return
        if near_stage_sign:
            title = f'STAGE {game.stage_number} SIGN'
            message = sign_message
        elif self.layered(game):
            floor = self.current_floor(game)
            if game.exit_open:
                message = 'The way out is open. Reach the door!'
            elif self.boss_near(game):
                message = 'Could the lava reach the creature?'
            elif self.in_opening_map(game) and game.renderer.scenery.get('hint'):
                message = game.renderer.scenery['hint']
            else:
                message = ('Explore the old mine and head right.',
                           'Follow the cave back to the left.',
                           'Crystals light the way down.',
                           'Find a way to defeat the creature.')[floor - 1]
        elif getattr(game, 'final_boss_room', False):
            if game.exit_open:
                message = 'The gate is open. Leave the arena!'
            elif getattr(game, 'arena_locked', False):
                message = 'Parry to break its posture, then strike!'
            else:
                message = 'Defeat the Colossus to open the gate.'
        elif game.stage_number == 1 and not game.has_key and game.exit_open:
            message = 'Enter the side door for the key.'
        elif game.stage_number == 4:
            message = 'Find the bomb and break the gate.'
        else:
            message = 'Cross the mine and reach the exit.'
        if not near_stage_sign:
            title = (('STAGE 5.5: ' if getattr(game, 'final_boss_room', False)
                      else f'S{game.stage_number}  ') + self.stage_title(game)
                     if hasattr(game, 'stage_name') else 'OBJECTIVE')
        width = 500 if near_stage_sign else 370
        card = pygame.Surface((width, 56), pygame.SRCALPHA)
        self.frame(card, (0, 0, width, 56))
        self.text(card, title, 16, ORANGE, center=(width // 2, 16))
        self.text(card, message, 20, CREAM, center=(width // 2, 39))
        alpha = (255 if near_stage_sign else
                 min(255, round(self.objective_time * 510)))
        card.set_alpha(alpha)
        surface.blit(card, ((SCREEN_W - width) // 2, 72))

    @staticmethod
    def stage_sign_message(game):
        if (game.stage_sign is not None and not game.bonus_room
                and game.stage_number in (1, 3, 4, 5)
                and pygame.Vector2(game.player.rect.center).distance_to(
                    game.stage_sign[1].center) <= 110):
            if game.stage_number == 1:
                return 'The door will open for those who have a key'
            return 'The door will open after all enemies is gone'
        return None

    def transition(self, surface):
        if self.transition_time <= 0:
            return
        elapsed = 2.0 - self.transition_time
        alpha = round(255 * min(1, elapsed / 0.25, self.transition_time / 0.4))
        card = pygame.Surface((360, 126), pygame.SRCALPHA)
        self.frame(card, (0, 0, 360, 126), ZONES[self.floor - 1][1])
        self.text(card, f'B{self.floor}', 44, ZONES[self.floor - 1][1], center=(180, 34))
        self.text(card, ZONES[self.floor - 1][0], 30, CREAM, center=(180, 72))
        self.text(card, 'GOING DEEPER...', 18, MUTED, center=(180, 103))
        card.set_alpha(alpha)
        surface.blit(card, (300, 242))

    def draw_game(self, surface, game, mouse):
        seen = set()
        if hasattr(game, '_can_enemy_see_player'):
            # Enemies about to hit (a shot ready, a swing or body landing) blink.
            warned = {id(source) for _, _, source in getattr(game, 'threats', None) or ()}
            blink = int(getattr(game, 'world_time', 0.0) * 20) % 2
            for enemy in game.monsters:
                sees = game._can_enemy_see_player(enemy)
                if sees:
                    seen.add(id(enemy))
                telegraph = getattr(enemy, 'aiming', False) or id(enemy) in warned
                if sees or telegraph:
                    x, y = to_screen(game, enemy.rect.centerx, enemy.rect.top)
                    y -= 15
                    if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
                        if telegraph:
                            self.text(surface, '!', 30, CREAM if blink else RED, center=(x, y))
                        else:
                            self.text(surface, '!', 26, RED, center=(x, y))
            self.offscreen_arrows(surface, game, seen)
        if hasattr(game, 'combat'):
            self.enemy_posture(surface, game)
            self.parry_feedback(surface, game)
        self.health(surface, game)
        self.gold_wallet(surface, game)
        self.dig_energy(surface, game)
        if hasattr(game, 'combat'):
            self.posture.draw(surface)
        self.bomb_count(surface, game)
        if not self.dialog.active:      # the intro box covers the bottom strip
            self.key_inventory(surface, game)
            self.speed_potion_timer(surface, game)
            self.boss_bar(surface, game)
        self.area(surface, game)
        self.danger(surface, game)
        self.objective(surface, game)
        self.transition(surface)
        self.dialog.draw(surface, self.fonts)

    def parry_feedback(self, surface, game):
        """Combat popups over the action, and a slim recharge bar while it cools."""
        parry = getattr(game, 'parry', None)
        if parry is None:
            return
        for text, x, y, age, life, color in game.fx.popups:
            image, shadow = self.rendered(text, 26 if len(text) > 10 else 22, color)
            fade_from = life * 0.65
            alpha = 255 if age < fade_from else round(255 * (life - age) / (life - fade_from))
            image.set_alpha(alpha)
            shadow.set_alpha(alpha)
            sx, sy = to_screen(game, x, y)
            rect = image.get_rect(midbottom=(round(sx), round(sy)))
            rect.clamp_ip(surface.get_rect())
            surface.blit(shadow, rect.move(1, 1))
            surface.blit(image, rect)
        left = parry.cooldown_fraction()
        if left and not parry.is_active() and game.combat.can_act():
            box = screen_rect(game, game.player.rect)
            x, y = box.centerx - 9, box.top - 7
            pygame.draw.rect(surface, INK, (x - 1, y - 1, 20, 4))
            pygame.draw.rect(surface, (70, 64, 58), (x, y, 18, 2))
            pygame.draw.rect(surface, ORANGE, (x, y, round(18 * (1 - left)), 2))

    def rendered(self, text, size, color):
        """A text image and its shadow, rendered once (popups reuse them)."""
        key = (text, size, color)
        if key not in self.text_cache:
            self.text_cache[key] = (self.fonts[size].render(text, False, color),
                                    self.fonts[size].render(text, False, INK))
        return self.text_cache[key]      # callers set the alpha before each blit

    def enemy_posture(self, surface, game):
        """Enemy posture, kept apart from the player's bottom-centre bar:
        small framed bars over engaged enemies; the boss's is on its bar
        at the foot of the screen (boss_bar)."""
        boss = getattr(game, 'boss', None)
        for enemy in game.monsters:
            posture = getattr(enemy, 'posture', None)
            if posture is None or enemy is boss:
                continue                   # not part of parry combat: no bar
            box = screen_rect(game, enemy.rect)
            if not box.colliderect(surface.get_rect()):
                continue
            engaged = (posture.value or enemy.broken
                       or game._can_enemy_see_player(enemy))
            if not engaged:
                continue
            value = posture.maximum if enemy.broken else posture.value
            blink = enemy.broken and int(enemy.stun_timer * 8) % 2
            width, height, gap = 7, 3, 1
            total = posture.maximum * (width + gap) - gap
            x0, y = box.centerx - total // 2, box.y - 7
            frame = pygame.Rect(x0 - 1, y - 1, total + 2, height + 2)
            if posture.since_rise < 0.25:      # an orange impact pulse
                k = posture.since_rise / 0.25
                pulse = frame.inflate(round(2 + 6 * k), round(2 + 4 * k))
                pygame.draw.rect(surface, (255, round(180 - 80 * k), 60), pulse, 1)
            pygame.draw.rect(surface, INK, frame)
            for n in range(posture.maximum):
                color = (46, 36, 30)
                if n < value:
                    color = POSTURE_COLORS[min(3, value) - 1]
                    if blink:
                        color = (255, 236, 220)       # broken: flashes red/white
                    elif n == value - 1 and posture.since_rise < 0.12:
                        color = (255, 250, 236)
                pygame.draw.rect(surface, color, (x0 + n * (width + gap), y, width, height))

    def update_boss_bar(self, dt, game):
        """Fade the boss bar in once the fight is on (the arena sealed, or
        the boss close), drain its damage trail, and hold it after the kill."""
        boss = getattr(game, 'boss', None)
        if boss is None:
            return
        alive = boss in game.monsters
        if alive:
            self.boss_bar_hold = 1.4
        else:
            self.boss_bar_hold = max(0.0, self.boss_bar_hold - dt)
        fighting = getattr(game, 'arena_locked', False) or self.boss_near(game)
        shown = (alive and fighting) or (not alive and self.boss_bar_hold > 0)
        step = dt / (0.5 if shown else 0.35)
        self.boss_bar_alpha = (min(1.0, self.boss_bar_alpha + step) if shown
                               else max(0.0, self.boss_bar_alpha - step))
        health = max(0, boss.hp) if alive else 0
        if self.boss_trail is None or self.boss_trail < health:
            self.boss_trail = float(health)
        else:
            self.boss_trail = max(health, self.boss_trail - BOSS_BAR_DRAIN * dt)

    def boss_bar(self, surface, game):
        """The boss's name, health and posture along the foot of the screen,
        clear of the action: health in pips with a draining damage trail, and
        the centre-out posture bar beneath it."""
        boss = getattr(game, 'boss', None)
        if boss is None or self.boss_bar_alpha <= 0:
            return
        panel = pygame.Surface(BOSS_BAR.size, pygame.SRCALPHA)
        width = BOSS_BAR.w
        enraged = getattr(boss, 'enraged', False)
        title_text = BOSS_NAME + ('  -  ENRAGED' if enraged else '')
        name = self.fonts[20].render(title_text, False, (255, 110, 80) if enraged else CREAM)
        shadow = self.fonts[20].render(title_text, False, INK)
        title = name.get_rect(midtop=(width // 2, 0))
        panel.blit(shadow, title.move(1, 1))
        panel.blit(name, title)
        for side in (-1, 1):                         # small diamonds flank the name
            x = width // 2 + side * (title.w // 2 + 14)
            pygame.draw.polygon(panel, ORANGE, [(x, title.centery - 4), (x + 4, title.centery),
                                                (x, title.centery + 4), (x - 4, title.centery)])
            pygame.draw.line(panel, WOOD_LIGHT, (x + side * 8, title.centery),
                             (width // 2 + side * 200, title.centery))
        bar = pygame.Rect(20, 24, width - 40, 12)
        pygame.draw.rect(panel, INK, bar.inflate(6, 6))
        pygame.draw.rect(panel, METAL, bar.inflate(4, 4), 1)
        pygame.draw.rect(panel, (24, 14, 14), bar)
        alive = boss in game.monsters
        maximum = max(1, getattr(boss, 'max_hp', 1))
        health = max(0, boss.hp) if alive else 0
        trail = self.boss_trail if self.boss_trail is not None else health
        trail_w = round(bar.w * min(maximum, trail) / maximum)
        health_w = round(bar.w * health / maximum)
        if trail_w > health_w:
            panel.fill(BOSS_TRAIL, (bar.x + health_w, bar.y, trail_w - health_w, bar.h))
        if health_w:
            flash = getattr(boss, 'hurt_timer', 0) > 0 and int(self.time * 20) % 2
            panel.fill((255, 236, 220) if flash else BOSS_RED, (bar.x, bar.y, health_w, bar.h))
            panel.fill((236, 92, 76), (bar.x, bar.y, health_w, 2))
            panel.fill((120, 20, 22), (bar.x, bar.bottom - 2, health_w, 2))
        for n in range(1, maximum):                  # a notch between health pips
            x = bar.x + round(bar.w * n / maximum)
            panel.fill(INK, (x - 1, bar.y - 1, 2, bar.h + 2))
        posture = getattr(boss, 'posture', None)
        if posture is not None and alive:
            value = posture.maximum if boss.broken else posture.value
            blink = boss.broken and int(boss.stun_timer * 8) % 2
            self.boss_posture(panel, pygame.Rect(width // 2 - 150, 44, 300, 5),
                              posture, value, blink)
        panel.set_alpha(round(255 * self.boss_bar_alpha))
        surface.blit(panel, BOSS_BAR.topleft)

    def boss_posture(self, surface, rect, posture, value, blink):
        """The boss's posture under its health: a framed bar filling from the centre."""
        width, height = rect.size
        if posture.since_rise < 0.3:
            k = posture.since_rise / 0.3
            pygame.draw.rect(surface, (255, round(190 - 90 * k), 70),
                             rect.inflate(round(4 + 8 * k), round(4 + 6 * k)), 1)
        pygame.draw.rect(surface, INK, rect.inflate(4, 4))
        pygame.draw.rect(surface, (128, 118, 108), rect.inflate(2, 2), 1)
        pygame.draw.rect(surface, (20, 14, 12), rect)
        level = min(3, 1 + 3 * value // (posture.maximum + 1)) if value else 1
        color = (255, 236, 220) if blink else POSTURE_COLORS[level - 1]
        if posture.since_rise < 0.12 and not blink:
            color = (255, 250, 236)
        half = round((width // 2) * value / posture.maximum)
        if half:
            pygame.draw.rect(surface, color, (rect.centerx - half, rect.y, 2 * half, height))
            pygame.draw.line(surface, (255, 246, 210), (rect.centerx - half, rect.y),
                             (rect.centerx + half - 1, rect.y))
        for n in range(1, posture.maximum):    # a notch per point, mirrored
            offset = round((width // 2) * n / posture.maximum)
            for x in (rect.centerx - offset, rect.centerx + offset):
                surface.fill(INK, (x, rect.y, 1, height))
        surface.fill((232, 176, 72), (rect.centerx - 1, rect.y - 3, 2, height + 6))

    # ------------------------------------------------------------------
    # Cinematic Main Menu Scene & Animated Settings Panel
    # ------------------------------------------------------------------
    def _draw_menu_title(self, surface, intro):
        title_alpha = intro['title_alpha']
        if title_alpha <= 0.004:
            return
        scale = intro['title_scale']
        float_y = math.sin(self.menu_time * 1.75) * 2.0 * title_alpha
        glow_pulse = 0.78 + 0.22 * flicker_wave(self.menu_time, 0.75, 0.42)

        base_x, base_y = 50, round(158 + float_y)
        title_img = self._title_surface
        shimmer_idx = int((self.menu_time * 6.0) % len(self._title_shimmer_frames))
        shimmer_img = self._title_shimmer_frames[shimmer_idx]
        if abs(scale - 1.0) > 0.004:
            tw = max(1, round(title_img.get_width() * scale))
            th = max(1, round(title_img.get_height() * scale))
            title_img = pygame.transform.scale(title_img, (tw, th))
            shimmer_img = pygame.transform.scale(shimmer_img, (tw, th))
        else:
            title_img = title_img.copy()
            shimmer_img = shimmer_img.copy()

        glow_img = self._title_glow.copy()
        glow_img.set_alpha(round(225 * title_alpha * glow_pulse))
        title_img.set_alpha(round(255 * title_alpha))
        shimmer_img.set_alpha(round(240 * title_alpha))

        center_x = base_x + self._title_surface.get_width() // 2
        center_y = base_y + self._title_surface.get_height() // 2
        g_rect = glow_img.get_rect(center=(center_x, center_y))
        t_rect = title_img.get_rect(center=(center_x, center_y))
        surface.blit(glow_img, g_rect, special_flags=pygame.BLEND_RGB_ADD)
        surface.blit(title_img, t_rect)
        surface.blit(shimmer_img, t_rect)

    def _draw_menu_options(self, surface, mouse, intro):
        option_alphas = intro['option_alphas']
        option_offsets = intro['option_offsets']
        base_x = 96
        base_y = 308
        row_step = 56

        # Hover detection when Settings is closed
        if not self.settings_open and self.menu_transition is None and mouse != self._last_mouse_pos:
            self._last_mouse_pos = mouse
            for idx, label in enumerate(self.menu_options):
                hit_rect = pygame.Rect(base_x - 36, base_y + idx * row_step - 6, 224, 42)
                if hit_rect.collidepoint(mouse) and idx != self.selected_index:
                    self.selected_index = idx
                    self.selection_pulse = 1.0
                    self.menu_audio.play('hover')

        for idx, label in enumerate(self.menu_options):
            hit_rect = pygame.Rect(base_x - 36, base_y + idx * row_step - 6, 224, 42)
            if not self.settings_open:
                self.buttons.append((hit_rect, label))

            opt_alpha = option_alphas[idx]
            if opt_alpha <= 0.004:
                continue

            hi = self.option_highlight[idx]
            pulse = self.selection_pulse if idx == self.selected_index else 0.0
            base_gold = lerp_color(GOLD, GOLD_BRIGHT, pulse * 0.65)
            color = lerp_color(MENU_SILVER, base_gold, hi)
            # Smooth 4-6 pixel right shift when selected/hovered (5px at full selection)
            slide_x = round(5.0 * hi) + option_offsets[idx]
            item_x = base_x + slide_x
            item_y = base_y + idx * row_step

            # Animated '>' selection chevron beside selected option
            if hi > 0.08:
                arrow_bob = round(math.sin(self.menu_time * 6.2) * 2.0 + pulse * 2.0)
                arrow_col = lerp_color(GOLD, GOLD_BRIGHT, pulse * 0.7)
                arrow_surf = self._cached_pixel_text('>', 3, arrow_col, highlight_top=True).copy()
                arrow_surf.set_alpha(round(255 * hi * opt_alpha))
                surface.blit(arrow_surf, (base_x - 34 + arrow_bob + option_offsets[idx], item_y + 2))

                # Subtle pixel selection sparks around the selected option
                for sp in self._menu_sparks:
                    k = sp['age'] / sp['life']
                    sp_alpha = round(210 * math.sin(k * math.pi) * hi * opt_alpha)
                    if sp_alpha > 12:
                        sx = item_x + round(sp['x'])
                        sy = item_y + 12 + round(sp['y'])
                        dot = pygame.Surface((3, 3), pygame.SRCALPHA)
                        dot.fill((255, 224, 112, sp_alpha))
                        surface.blit(dot, (sx, sy))

            txt_surf = self._cached_pixel_text(
                label, 3, color, highlight_top=(hi > 0.4)
            ).copy()
            txt_surf.set_alpha(round(255 * opt_alpha))
            surface.blit(txt_surf, (item_x, item_y))

    def _draw_settings_panel(self, surface, mouse):
        self.slider_rects = {}
        if self.settings_progress <= 0.004:
            return

        p = ease_out_cubic(clamp(self.settings_progress))
        # Darken background slightly while keeping the cave world visible and alive
        self.overlay(surface, alpha=round(148 * p), color=(10, 9, 12))

        panel_w, panel_h = 460, 376
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        self.frame(panel_surf, (0, 0, panel_w, panel_h), accent=ORANGE, fill=PANEL)

        # Panel Title
        title_img = self._cached_pixel_text('SETTINGS', 3, GOLD, highlight_top=True)
        panel_surf.blit(title_img, title_img.get_rect(center=(panel_w // 2, 40)))
        pygame.draw.line(panel_surf, WOOD, (32, 66), (panel_w - 32, 66), 2)
        pygame.draw.line(panel_surf, WOOD_LIGHT, (72, 66), (panel_w - 72, 66), 2)

        slide_offset_y = round((1.0 - p) * 42)
        panel_x = (SCREEN_W - panel_w) // 2
        panel_y = (SCREEN_H - panel_h) // 2 + slide_offset_y

        if self.settings_open:
            self.buttons = []

        # Row 0 & Row 1: Music Volume & SFX Volume sliders
        sliders = (
            (0, 'MUSIC VOLUME', self.music_volume, 'music', 'MUSIC_DOWN', 'MUSIC_UP', 102),
            (1, 'SFX VOLUME', self.sfx_volume, 'sfx', 'SFX_DOWN', 'SFX_UP', 166),
        )
        for idx, label, val, kind, down_id, up_id, ry in sliders:
            hi = self.settings_highlight[idx]
            lbl_col = lerp_color(CREAM, GOLD, hi)
            if hi > 0.1:
                arr = self._cached_pixel_text('>', 2, GOLD, highlight_top=True)
                panel_surf.blit(arr, (22, ry + 4))
            lbl_img = self._cached_pixel_text(label, 2, lbl_col)
            panel_surf.blit(lbl_img, (40, ry + 4))

            # '<' button, segmented pixel bar, '>' button, percentage
            btn_down = pygame.Rect(218, ry - 2, 26, 26)
            bar_rect = pygame.Rect(250, ry + 2, 120, 18)
            btn_up = pygame.Rect(376, ry - 2, 26, 26)

            for brect, sym in ((btn_down, '<'), (btn_up, '>')):
                screen_brect = brect.move(panel_x, panel_y)
                hov = self.settings_open and screen_brect.collidepoint(mouse)
                pygame.draw.rect(panel_surf, INK, brect)
                pygame.draw.rect(panel_surf, ORANGE if hov else WOOD, brect.inflate(-2, -2), 2)
                pygame.draw.rect(panel_surf, (58, 38, 26) if hov else (38, 28, 22), brect.inflate(-6, -6))
                sym_img = self._cached_pixel_text(sym, 2, GOLD if hov else CREAM)
                panel_surf.blit(sym_img, sym_img.get_rect(center=brect.center))

            # Pixel-art segmented volume bar
            pygame.draw.rect(panel_surf, INK, bar_rect.inflate(4, 4))
            pygame.draw.rect(panel_surf, WOOD_DARK, bar_rect.inflate(2, 2))
            pygame.draw.rect(panel_surf, (16, 13, 12), bar_rect)
            segments = 10
            seg_w = 10
            seg_gap = 2
            active_segs = round(val * segments)
            for s in range(segments):
                sx = bar_rect.x + 2 + s * (seg_w + seg_gap)
                sy = bar_rect.y + 3
                srect = pygame.Rect(sx, sy, seg_w, bar_rect.height - 6)
                if s < active_segs:
                    scol = lerp_color(ORANGE, GOLD, s / max(1, segments - 1))
                    pygame.draw.rect(panel_surf, scol, srect)
                    pygame.draw.line(panel_surf, GOLD_BRIGHT, (srect.x, srect.y), (srect.right - 1, srect.y))
                else:
                    pygame.draw.rect(panel_surf, (38, 30, 26), srect)

            pct_img = self._cached_pixel_text(f'{round(val * 100)}%', 2, GOLD if hi > 0.3 else MUTED)
            panel_surf.blit(pct_img, (408, ry + 4))

            if self.settings_open:
                self.slider_rects[kind] = bar_rect.move(panel_x, panel_y)
                self.buttons.append((btn_down.move(panel_x, panel_y), down_id))
                self.buttons.append((btn_up.move(panel_x, panel_y), up_id))
                self.buttons.append((bar_rect.move(panel_x, panel_y), f'{kind.upper()}_SLIDER'))

        # Row 2: Fullscreen Toggle
        ry_fs = 232
        hi_fs = self.settings_highlight[2]
        if hi_fs > 0.1:
            arr = self._cached_pixel_text('>', 2, GOLD, highlight_top=True)
            panel_surf.blit(arr, (22, ry_fs + 6))
        fs_lbl = self._cached_pixel_text('FULLSCREEN', 2, lerp_color(CREAM, GOLD, hi_fs))
        panel_surf.blit(fs_lbl, (40, ry_fs + 6))

        toggle_rect = pygame.Rect(250, ry_fs, 120, 28)
        screen_toggle = toggle_rect.move(panel_x, panel_y)
        hov_fs = self.settings_open and screen_toggle.collidepoint(mouse)
        self.frame(
            panel_surf,
            toggle_rect,
            accent=GOLD if (self.fullscreen or hov_fs or hi_fs > 0.4) else WOOD_LIGHT,
            fill=(68, 44, 26) if self.fullscreen else (36, 26, 20),
        )
        state_txt = 'ON' if self.fullscreen else 'OFF'
        state_col = GOLD if self.fullscreen else MENU_SILVER
        st_img = self._cached_pixel_text(state_txt, 2, state_col, highlight_top=self.fullscreen)
        panel_surf.blit(st_img, st_img.get_rect(center=toggle_rect.center))
        if self.settings_open:
            self.buttons.append((screen_toggle, 'FULLSCREEN_TOGGLE'))

        # Row 3: Back Button
        ry_back = 304
        hi_back = self.settings_highlight[3]
        back_rect = pygame.Rect((panel_w - 190) // 2, ry_back, 190, 44)
        screen_back = back_rect.move(panel_x, panel_y)
        hov_back = self.settings_open and screen_back.collidepoint(mouse)
        active_back = hov_back or hi_back > 0.4
        self.frame(
            panel_surf,
            back_rect,
            accent=GOLD if active_back else WOOD_LIGHT,
            fill=(66, 42, 26) if active_back else PANEL,
        )
        back_col = GOLD if active_back else CREAM
        if active_back:
            arr = self._cached_pixel_text('>', 2, GOLD, highlight_top=True)
            panel_surf.blit(arr, (back_rect.x + 26, back_rect.centery - 7))
        back_img = self._cached_pixel_text('BACK', 2, back_col, highlight_top=active_back)
        panel_surf.blit(back_img, back_img.get_rect(center=(back_rect.centerx + (6 if active_back else 0), back_rect.centery)))
        if self.settings_open:
            self.buttons.append((screen_back, 'BACK'))

        panel_surf.set_alpha(round(255 * p))
        surface.blit(panel_surf, (panel_x, panel_y))

    def draw_menu_transition(self, surface):
        """Render cinematic fade-out / stage intro / fade-in transitions."""
        if self.menu_transition is None:
            return
        tr = self.menu_transition
        t = tr['timer']
        action = tr['action']

        if action == 'EXIT':
            alpha = round(255 * ease_in_out_quad(clamp(t / tr['duration'])))
            self.overlay(surface, alpha=alpha, color=(6, 6, 8))
            return

        if action == 'PLAY':
            # 0.00 - 0.45s: Fade menu to darkness
            # 0.45 - 0.90s: Hold darkness with cinematic Stage 1 card
            # 0.90 - 1.35s: Fade into Stage 1 gameplay
            if t < 0.45:
                alpha = round(255 * ease_in_out_quad(clamp(t / 0.45)))
            elif t < 0.90:
                alpha = 255
            else:
                alpha = round(255 * (1.0 - ease_out_cubic(clamp((t - 0.90) / 0.45))))
            self.overlay(surface, alpha=alpha, color=(6, 6, 8))

            # Cinematic card during middle of transition (0.26s - 1.12s)
            if 0.26 <= t <= 1.12:
                if t < 0.50:
                    card_k = ease_out_cubic(clamp((t - 0.26) / 0.24))
                elif t <= 0.86:
                    card_k = 1.0
                else:
                    card_k = 1.0 - ease_in_out_quad(clamp((t - 0.86) / 0.26))
                card_alpha = round(255 * card_k)
                card = pygame.Surface((420, 118), pygame.SRCALPHA)
                self.frame(card, (0, 0, 420, 118), accent=ORANGE, fill=PANEL)
                s1 = self._cached_pixel_text('STAGE 1 - ABANDONED MINE', 2, GOLD, highlight_top=True)
                s2 = self._cached_pixel_text('DESCENDING INTO THE DARK...', 2, CREAM)
                card.blit(s1, s1.get_rect(center=(210, 42)))
                card.blit(s2, s2.get_rect(center=(210, 78)))
                card.set_alpha(card_alpha)
                surface.blit(card, ((SCREEN_W - 420) // 2, (SCREEN_H - 118) // 2))

    def draw_menu(self, surface, mouse):
        self.buttons = []
        intro = self.intro_progress()

        # 1. Draw 6-layer parallax underground cave scene with environmental animations
        self.menu_env.draw(surface, intro)

        # 2. Draw "DIG GAME" title & 3 menu options (PLAY, SETTINGS, EXIT)
        self._draw_menu_title(surface, intro)
        self._draw_menu_options(surface, mouse, intro)

        # 3. Draw animated Settings panel if open or sliding closed
        self._draw_settings_panel(surface, mouse)

        # 4. Draw any active screen transition overlay
        self.draw_menu_transition(surface)

    def draw_stage_select(self, surface, mouse):
        self.buttons = []
        self.overlay(surface, 172)
        self.frame(surface, (250, 65, 460, 520))
        self.text(surface, 'SELECT A STAGE', 30, ORANGE, center=(480, 105))
        stages = (
            ('STAGE 1', 'ABANDONED MINE', (167, 101, 50)),
            ('STAGE 2', 'THE SINKING MINE', ORANGE),
            ('STAGE 3', 'DIRT CAVERNS', (184, 129, 74)),
            ('STAGE 4', 'WATER CHAMBER', (44, 163, 214)),
            ('STAGE 5', 'THE SINKING MINE', (52, 160, 205)),
        )
        for n, (label, name, accent) in enumerate(stages):
            y = 128 + n * 62
            self.frame(surface, (292, y, 376, 56), accent)
            self.text(surface, name, 19, CREAM, center=(480, y + 17))
            self.button(surface, label, (407, y + 30, 146, 22), mouse, accent)
        self.button(surface, 'BACK TO MENU', (355, 512, 250, 44), mouse)

    def draw_controls(self, surface, mouse):
        self.buttons = []
        self.overlay(surface, 184)
        self.frame(surface, (245, 76, 470, 488))
        self.text(surface, 'CONTROLS', 30, ORANGE, center=(480, 117))
        rows = [(['A', 'D'], 'Move left / right'),
                (['W', 'SPACE'], 'Jump away from ladder'),
                (['W', 'S'], 'Climb ladder'),
                (['MOUSE'], 'Hold to dig'),
                (['RMB', 'F'], 'Dirt gun (uses DIG)'),
                (['Q'], 'Aim / throw bomb'),
                (['E'], 'Parry / deathblow'),
                (['R'], 'Restart'),
                (['ESC'], 'Pause / back')]
        for n, (keys, action) in enumerate(rows):
            y = 148 + n * 39
            x = 274
            for key in keys:
                width = 62 if key in ('SPACE', 'MOUSE') else (40 if key == 'RMB' else 30)
                self.keycap(surface, key, x, y, width)
                x += width + 6
            self.text(surface, action, 22, CREAM, topleft=(440, y + 4))
        self.button(surface, 'BACK', (370, 502, 220, 42), mouse)

    def draw_pause(self, surface, mouse):
        self.buttons = []
        self.overlay(surface, 185)
        self.frame(surface, (320, 138, 320, 368))
        self.text(surface, 'PAUSED', 30, ORANGE, center=(480, 183))
        for n, label in enumerate(('RESUME', 'RESTART', 'HOW TO PLAY', 'MAIN MENU')):
            self.button(surface, label, (355, 226 + n * 62, 250, 45), mouse)

    def metal_sign(self, surface, rect):
        """An old mine sign: dark planks in a grey metal band, riveted at the corners."""
        rect = pygame.Rect(rect)
        pygame.draw.rect(surface, INK, rect)
        pygame.draw.rect(surface, METAL, rect.inflate(-4, -4))
        pygame.draw.line(surface, METAL_LIGHT, (rect.x + 2, rect.y + 2),
                         (rect.right - 3, rect.y + 2), 2)
        pygame.draw.line(surface, METAL_LIGHT, (rect.x + 2, rect.y + 2),
                         (rect.x + 2, rect.bottom - 3), 2)
        pygame.draw.rect(surface, INK, rect.inflate(-20, -20))
        board = rect.inflate(-24, -24)
        pygame.draw.rect(surface, WOOD_DARK, board)
        for y in range(board.y + 39, board.bottom - 8, 39):     # plank seams
            pygame.draw.line(surface, (44, 27, 18), (board.x, y), (board.right - 1, y), 2)
            pygame.draw.line(surface, (72, 44, 29), (board.x, y + 2), (board.right - 1, y + 2))
        for x in (rect.x + 3, rect.right - 9):
            for y in (rect.y + 3, rect.bottom - 9):
                pygame.draw.rect(surface, INK, (x, y, 6, 6))
                pygame.draw.rect(surface, METAL_LIGHT, (x + 1, y + 1, 4, 4))
                pygame.draw.rect(surface, (214, 208, 196), (x + 1, y + 1, 2, 2))

    def draw_restart_confirm(self, surface, mouse):
        self.buttons = []
        self.overlay(surface, 150, (0, 0, 0))
        sign = RESTART_SIGN
        self.metal_sign(surface, sign)
        self.text(surface, 'RESTART STAGE?', 30, ORANGE, center=(sign.centerx, sign.y + 40))
        self.text(surface, 'Are you sure you want to restart this stage?', 20, CREAM,
                  center=(sign.centerx, sign.y + 80))
        for choice, label, action, color, x in (
                ('YES', '[Y / ENTER] YES', 'CONFIRM RESTART', ORANGE_RED, sign.centerx - 168),
                ('NO', '[N / ESC] NO', 'CANCEL RESTART', CREAM, sign.centerx + 8)):
            rect = pygame.Rect(x, sign.bottom - 64, 160, 40)
            selected = self.confirm_restart_choice == choice
            self.frame(surface, rect, color if selected else METAL,
                       (63, 40, 26) if selected else PANEL)
            if selected:
                pygame.draw.rect(surface, GOLD_BRIGHT, rect.inflate(8, 8), 2)
            self.text(surface, label, 20, color if choice == 'YES' or selected else MUTED,
                      center=rect.center)
            self.buttons.append((rect, action))

    def draw_end(self, surface, mouse, game, won):
        self.buttons = []
        self.overlay(surface, 168, INK if won else (43, 18, 17))
        self.frame(surface, (306, 160, 348, 380 if won else 324),
                   ORANGE if won else RED)
        final_stage = game.stage_number == FINAL_STAGE or game.final_boss_room
        title = 'STAGE CLEAR!' if won else 'GAME OVER'
        self.text(surface, title, 30,
                  ORANGE if won else RED, center=(480, 215))
        if won:
            message = ('You escaped the depths.' if self.layered(game)
                       else 'You reached the exit.')
        else:
            message = 'You were defeated.'
        self.text(surface, message, 22, CREAM, center=(480, 264))
        if won:
            if game.final_boss_room:
                choices = ('RESTART', 'MAIN MENU')
            else:
                choices = (('PLAY AGAIN', 'MAIN MENU') if final_stage else
                           ('NEXT STAGE', 'MAIN MENU'))
        else:
            choices = ('RETRY', 'MAIN MENU')
        for n, label in enumerate(choices):
            self.button(surface, label, (355, 316 + n * 56, 250, 44), mouse)

    def draw(self, surface, game, mouse):
        if self.screen == 'cutscene' and self.cutscene is not None:
            self.buttons = []
            self.cutscene.draw(surface, self.fonts[16])
        elif self.screen == 'menu':
            self.draw_menu(surface, mouse)
        elif self.screen == 'stage_select':
            self.draw_stage_select(surface, mouse)
        elif self.screen == 'controls':
            self.draw_controls(surface, mouse)
        elif self.screen == 'paused':
            self.draw_pause(surface, mouse)
        elif self.screen == 'confirm_restart':
            self.draw_game(surface, game, mouse)
            self.draw_restart_confirm(surface, mouse)
        elif game.state == 'win':
            self.draw_end(surface, mouse, game, True)
        elif game.state == 'lose':
            self.draw_end(surface, mouse, game, False)
        else:
            self.buttons = []
            self.draw_game(surface, game, mouse)
            if self.menu_transition is not None:
                self.draw_menu_transition(surface)
        if self.door_fade is not None and self.screen != 'cutscene':
            k = 1 - self.door_fade / DOOR_FADE_OUT          # 0 .. 1 toward black
            self.overlay(surface, round(255 * k * k * (3 - 2 * k)), (0, 0, 0))
        if self.fade_in > 0 and self.screen != 'cutscene':
            # Into the arena: black for a moment, then it eases in.
            k = min(1.0, self.fade_in / (ARENA_FADE_IN - ARENA_FADE_HOLD))
            self.overlay(surface, round(255 * k * k * (3 - 2 * k)), (0, 0, 0))

    def click(self, position):
        return next((label for rect, label in self.buttons if rect.collidepoint(position)), None)
