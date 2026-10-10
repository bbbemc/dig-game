"""Small, pixel-aligned interface for the underground game.

All UI is presentation state. The Game remains the owner of health, terrain,
liquids, enemies and win/lose conditions.
"""

import pygame

from config import CELL, MACRO, SCREEN_H, SCREEN_W
from level import DIRT, LAVA


INK = (23, 20, 16)
PANEL = (33, 25, 20)
WOOD_DARK = (59, 36, 24)
WOOD = (107, 61, 34)
WOOD_LIGHT = (167, 101, 50)
METAL = (86, 81, 74)
CREAM = (241, 223, 193)
MUTED = (169, 147, 120)
RED = (201, 61, 61)
ORANGE = (232, 163, 50)
ZONES = (
    ('ABANDONED MINE', ORANGE),
    ('EARTH CAVERN', (184, 129, 74)),
    ('CRYSTAL CAVE', (141, 98, 201)),
    ('VOLCANIC RUINS', (244, 91, 40)),
)


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
        self.fonts = {size: _font(size) for size in (16, 18, 20, 22, 26, 30, 44, 64)}
        self.buttons = []

    def start(self, game):
        self.screen = 'game'
        self.time = self.prompt_time = 0.0
        self.objective_time = 5.0
        self.transition_time = 0.0
        self.floor = self.current_floor(game)
        self.moved = self.jumped = self.climbed = self.dug = False
        self.last_hp = game.hp
        self.damage_flash = 0.0
        self.boss_hint_shown = False

    @staticmethod
    def current_floor(game):
        return min(4, game.player.rect.centery // (25 * MACRO) + 1)

    def note_input(self, horizontal, jump, vertical, digging, game):
        if horizontal:
            self.moved = True
        if jump:
            self.jumped = True
        if vertical and game.player.on_ladder:
            self.climbed = True
        if digging:
            self.dug = True

    def update(self, dt, game):
        self.time += dt
        self.damage_flash = max(0.0, self.damage_flash - dt)
        if self.screen != 'game':
            return
        self.prompt_time += dt
        self.objective_time = max(0.0, self.objective_time - dt)
        self.transition_time = max(0.0, self.transition_time - dt)
        floor = self.current_floor(game)
        if floor != self.floor:
            self.floor = floor
            self.transition_time = 2.0
            self.objective_time = 5.0
        if (floor == 4 and not self.boss_hint_shown and
                abs(game.player.rect.centerx - game.boss.rect.centerx) < 500 and
                abs(game.player.rect.centery - game.boss.rect.centery) < 400):
            self.boss_hint_shown = True
            self.objective_time = 5.0
        if game.hp < self.last_hp:
            self.damage_flash = 0.4
        self.last_hp = game.hp

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
        fill = round(155 * max(0, min(100, game.hp)) / 100)
        if fill:
            bar_color = RED if game.hp > 25 else (240, 93, 60)
            pygame.draw.rect(surface, bar_color, (56, 28, fill, 14))
            pygame.draw.line(surface, (250, 125, 105), (57, 29),
                             (55 + fill, 29))
        self.text(surface, f'{game.hp} / 100', 20, CREAM, center=(134, 35))

    def area(self, surface, game):
        number = self.current_floor(game)
        name, accent = ZONES[number - 1]
        rect = pygame.Rect(716, 14, 228, 42)
        self.frame(surface, rect, accent)
        pygame.draw.rect(surface, WOOD, (726, 23, 30, 23))
        self.text(surface, f'B{number}', 20, CREAM, center=(741, 35))
        self.text(surface, name, 20, CREAM, center=(847, 35))

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
        self.text(surface, '!  HEAT', 18, ORANGE, center=(SCREEN_W // 2, 30))

    def _dig_target(self, game, mouse):
        cx, cy = game.render_camera
        x, y = (mouse[0] + cx) // CELL, (mouse[1] + cy) // CELL
        if not (0 <= x < game.world.width and 0 <= y < game.world.height):
            return False
        px, py = game.player.rect.centerx // CELL, game.player.rect.centery // CELL
        from config import DIG_REACH
        return ((x - px) ** 2 + (y - py) ** 2 <= DIG_REACH ** 2 and
                game.world.foreground[game.world.index(x, y)] == DIRT)

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
        surface.blit(panel, (340, 552))

    def objective(self, surface, game):
        if self.objective_time <= 0 or self.transition_time > 0:
            return
        floor = self.current_floor(game)
        if floor == 1:
            message = 'Find a way deeper underground.'
        elif floor == 2:
            message = 'The cave reacts to flowing liquids.'
        elif floor == 3:
            message = 'Water and lava can reshape the cave.'
        elif abs(game.player.rect.centerx - game.boss.rect.centerx) < 500:
            message = 'Could the lava reach the creature?'
        else:
            message = 'Find a way to defeat the creature.'
        card = pygame.Surface((370, 56), pygame.SRCALPHA)
        self.frame(card, (0, 0, 370, 56))
        self.text(card, 'OBJECTIVE', 16, ORANGE, center=(185, 16))
        self.text(card, message, 20, CREAM, center=(185, 39))
        card.set_alpha(min(255, round(self.objective_time * 510)))
        surface.blit(card, (295, 72))

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
        self.health(surface, game)
        self.area(surface, game)
        self.danger(surface, game)
        self.objective(surface, game)
        self.tutorial(surface, game, mouse)
        self.transition(surface)

    def draw_menu(self, surface, mouse):
        self.buttons = []
        self.overlay(surface, 160)
        self.frame(surface, (280, 95, 400, 480))
        self.text(surface, 'DIG GAME', 64, WOOD_LIGHT, center=(480, 181))
        self.text(surface, 'DESCEND INTO THE DEEP', 20, MUTED, center=(480, 220))
        for n, label in enumerate(('START GAME', 'HOW TO PLAY', 'QUIT')):
            self.button(surface, label, (355, 302 + n * 68, 250, 48), mouse)

    def draw_controls(self, surface, mouse):
        self.buttons = []
        self.overlay(surface, 184)
        self.frame(surface, (245, 76, 470, 488))
        self.text(surface, 'CONTROLS', 30, ORANGE, center=(480, 117))
        rows = [(['A', 'D'], 'Move left / right'),
                (['W', 'SPACE'], 'Jump'),
                (['W', 'S'], 'Climb ladder'),
                (['MOUSE'], 'Hold to dig'),
                (['R'], 'Restart'),
                (['ESC'], 'Pause / back')]
        for n, (keys, action) in enumerate(rows):
            y = 157 + n * 56
            x = 274
            for key in keys:
                width = 62 if key in ('SPACE', 'MOUSE') else 30
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

    def draw_end(self, surface, mouse, won):
        self.buttons = []
        self.overlay(surface, 168, INK if won else (43, 18, 17))
        self.frame(surface, (306, 160, 348, 324), ORANGE if won else RED)
        self.text(surface, 'STAGE CLEAR!' if won else 'GAME OVER', 30,
                  ORANGE if won else RED, center=(480, 215))
        self.text(surface, 'The boss has been defeated.' if won else 'You were defeated.',
                  22, CREAM, center=(480, 264))
        for n, label in enumerate(('PLAY AGAIN' if won else 'RETRY', 'MAIN MENU')):
            self.button(surface, label, (355, 322 + n * 64, 250, 48), mouse)

    def draw(self, surface, game, mouse):
        if self.screen == 'menu':
            self.draw_menu(surface, mouse)
        elif self.screen == 'controls':
            self.draw_controls(surface, mouse)
        elif self.screen == 'paused':
            self.draw_pause(surface, mouse)
        elif game.state == 'win':
            self.draw_end(surface, mouse, True)
        elif game.state == 'lose':
            self.draw_end(surface, mouse, False)
        else:
            self.buttons = []
            self.draw_game(surface, game, mouse)

    def click(self, position):
        return next((label for rect, label in self.buttons if rect.collidepoint(position)), None)
