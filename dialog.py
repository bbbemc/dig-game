"""The miner's stage intro: a message box along the bottom with his portrait.

Laid out like an RPG message window: a dark box across the foot of the
screen, the speaker's bust standing over its left end, a name tab above the
text. Presentation only, like the rest of the UI: the game keeps running
while the line types itself out, holds, and fades away on its own.
"""

from pathlib import Path

import pygame

from config import SCREEN_H, SCREEN_W

# Made from the team's miner art by tools/make_miner_portrait.py.
PORTRAIT_ART = Path(__file__).with_name('assets') / 'miner_portrait.png'

# One line per stage; 'boss' is the Stage 5.5 boss room.
STAGE_DIALOGUES = {
    1: "The old mine is collapsing... I need to dig my way to the far exit door!",
    2: "The lower tunnels are flooded! I'll climb the ledges and keep an eye on my air.",
    3: "Lava pockets in these caverns... If I channel water onto lava, "
       "it'll cool into solid stone.",
    4: "A stone gate blocks the way. There must be a bomb somewhere in this "
       "flooded chamber.",
    5: "The heat is rising fast. One misstep into the magma and it's all over. "
       "Watch the footing!",
    'boss': "Ancient volcanic ruins... Something massive awaits ahead. "
            "Parry its strikes or use water to crush it!",
}
SPEAKER = 'MINER'

SHOW_TIME = 4.5          # seconds on screen before the fade
FADE_TIME = 0.5
CHARS_PER_SECOND = 40    # typewriter speed

BOX = pygame.Rect(0, SCREEN_H - 112, SCREEN_W, 112)
PORTRAIT_SCALE = 2                            # the art is 94 x 96: whole pixels only
PORTRAIT = pygame.Rect(10, SCREEN_H - 192, 188, 192)   # stands over the box's left end
NAME_TAB = pygame.Rect(206, BOX.y - 26, 132, 30)
TEXT_LEFT = 216
TEXT_TOP = BOX.y + 20
TEXT_WIDTH = SCREEN_W - TEXT_LEFT - 28
NAME_SIZE, TEXT_SIZE, HINT_SIZE = 22, 26, 16  # GameUI font sizes
LINE_HEIGHT = 26
MAX_LINES = 3
SKIP_HINT = 'SPACE / ENTER : SKIP'

INK = (23, 20, 16)
BOX_TOP = (58, 40, 28)       # the box shades from this, under the trim,
BOX_BOTTOM = (20, 15, 12)    # down to this at the foot of the screen
BOX_ALPHA = 228              # the mine shows through faintly
WOOD_DARK = (59, 36, 24)
WOOD = (107, 61, 34)
WOOD_LIGHT = (167, 101, 50)
TEXT_COLOR = (241, 223, 193)
NAME_COLOR = (232, 163, 50)
HINT_COLOR = (169, 147, 120)


def dialogue_for(game):
    """The intro line for a freshly started game, or None for no dialog."""
    if getattr(game, 'final_boss_room', False):
        return STAGE_DIALOGUES['boss']
    if getattr(game, 'bonus_room', False):
        return None
    return STAGE_DIALOGUES.get(game.stage_number)


def wrap_text(font, text, width):
    """Break text into lines no wider than ``width`` pixels, on spaces."""
    lines, line = [], ''
    for word in text.split():
        trial = f'{line} {word}' if line else word
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def box_surface():
    """The message box: a shaded, slightly see-through panel under a wood trim."""
    surface = pygame.Surface(BOX.size, pygame.SRCALPHA)
    for y in range(BOX.h):
        t = y / (BOX.h - 1)
        shade = [round(a + (b - a) * t) for a, b in zip(BOX_TOP, BOX_BOTTOM)]
        surface.fill((*shade, BOX_ALPHA), (0, y, BOX.w, 1))
    for y, color in ((0, INK), (2, WOOD_LIGHT), (4, WOOD), (6, INK)):
        surface.fill(color, (0, y, BOX.w, 2))
    return surface


def name_tab_surface(font):
    """The speaker's name on a plate that rises from the box's top edge."""
    surface = pygame.Surface(NAME_TAB.size, pygame.SRCALPHA)
    w, h = NAME_TAB.size
    for inset, color in ((0, INK), (2, WOOD), (4, WOOD_DARK)):
        cut = 6 - inset                    # chamfered top corners
        pygame.draw.polygon(surface, color, (
            (inset, h), (inset, cut + inset), (cut + inset, inset),
            (w - 1 - cut - inset, inset), (w - 1 - inset, cut + inset), (w - 1 - inset, h)))
    name = font.render(f'- {SPEAKER} -', False, NAME_COLOR)
    surface.blit(name, name.get_rect(center=(w // 2, h // 2 + 1)))
    return surface


def portrait_surface():
    """The miner's bust, enlarged by whole pixels so it stays crisp."""
    art = pygame.image.load(PORTRAIT_ART).convert_alpha()
    return pygame.transform.scale(art, (art.get_width() * PORTRAIT_SCALE,
                                        art.get_height() * PORTRAIT_SCALE))


class StageDialog:
    def __init__(self):
        self.text = None
        self.time = 0.0
        self._backdrop = None   # box, name tab and portrait, drawn once
        self._lines = None      # (font, wrapped lines) of the current text

    @property
    def active(self):
        return self.text is not None

    def start(self, text):
        self.text = text or None
        self.time = 0.0
        self._lines = None

    def dismiss(self):
        self.text = None

    def update(self, dt):
        if not self.active:
            return
        self.time += dt
        if self.time >= SHOW_TIME + FADE_TIME:
            self.dismiss()

    @property
    def visible_chars(self):
        return int(self.time * CHARS_PER_SECOND)

    @property
    def alpha(self):
        if self.time <= SHOW_TIME:
            return 255
        return max(0, round(255 * (1 - (self.time - SHOW_TIME) / FADE_TIME)))

    def _backdrop_image(self, fonts):
        if self._backdrop is None:
            area = BOX.union(PORTRAIT).union(NAME_TAB)
            self._origin = ox, oy = area.topleft
            self._backdrop = pygame.Surface(area.size, pygame.SRCALPHA)
            self._backdrop.blit(name_tab_surface(fonts[NAME_SIZE]),
                                (NAME_TAB.x - ox, NAME_TAB.y - oy))
            self._backdrop.blit(box_surface(), (BOX.x - ox, BOX.y - oy))
            portrait = portrait_surface()
            self._backdrop.blit(portrait, portrait.get_rect(
                midbottom=(PORTRAIT.centerx - ox, PORTRAIT.bottom - oy)))
            hint = fonts[HINT_SIZE].render(SKIP_HINT, False, HINT_COLOR)
            self._backdrop.blit(hint, hint.get_rect(
                bottomright=(BOX.right - 16 - ox, BOX.bottom - 10 - oy)))
        return self._backdrop

    def _wrapped(self, font):
        if self._lines is None or self._lines[0] is not font:
            self._lines = (font, wrap_text(font, self.text, TEXT_WIDTH)[:MAX_LINES])
        return self._lines[1]

    def draw(self, surface, fonts):
        """Draw onto the screen; ``fonts`` maps a size to a font (GameUI.fonts)."""
        if not self.active:
            return
        card = self._backdrop_image(fonts).copy()
        ox, oy = self._origin
        font = fonts[TEXT_SIZE]
        left = self.visible_chars
        y = TEXT_TOP - oy
        for line in self._wrapped(font):
            if left <= 0:
                break
            shown = line[:left]
            left -= len(line) + 1           # the space the wrap consumed
            card.blit(font.render(shown, False, INK), (TEXT_LEFT - ox + 2, y + 2))
            card.blit(font.render(shown, False, TEXT_COLOR), (TEXT_LEFT - ox, y))
            y += LINE_HEIGHT

        if self.alpha < 255:
            card.set_alpha(self.alpha)
        surface.blit(card, (ox, oy))
