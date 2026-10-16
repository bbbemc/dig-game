"""Small, pixel-aligned interface for the underground game.

All UI is presentation state. The Game remains the owner of health, terrain,
liquids, enemies and win/lose conditions.
"""

import pygame

from config import CELL, MACRO, SCREEN_H, SCREEN_W
from level import DIRT, LAVA, FINAL_STAGE


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
# Posture fill by how full the meter is: 1 yellow, 2 orange, 3 red (broken).
POSTURE_COLORS = ((255, 214, 92), (240, 136, 40), (226, 58, 46))
ZONES = (
    ('ABANDONED MINE', ORANGE),
    ('DIRT CAVE', (184, 129, 74)),
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
        self.fonts = {size: _font(size) for size in (16, 18, 19, 20, 22, 26, 30, 44, 64)}
        self.buttons = []
        from posture_hud import PostureHUD
        self.posture = PostureHUD()     # the player's bar, bottom centre
        self.text_cache = {}

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
        self.posture.reset()

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

    def update(self, dt, game):
        self.time += dt
        self.damage_flash = max(0.0, self.damage_flash - dt)
        if self.screen != 'game':
            return
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
        if hasattr(game, 'combat'):
            self.posture.update(dt, game)     # paused: not reached, so it freezes

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

    def bomb_count(self, surface, game):
        bombs = getattr(game, 'bombs', None)
        if bombs is None or not bombs.enabled:
            return
        rect = pygame.Rect(16, 62, 112, 34)
        self.frame(surface, rect)
        from bombs import draw_bomb
        draw_bomb(surface, pygame.Rect(26, 67, 24, 24), 24)
        self.text(surface, f'x {bombs.carried}', 20, CREAM, topleft=(58, 70))
        if bombs.carried:
            self.text(surface, 'HOLD RMB TO AIM', 18, CREAM, topleft=(134, 72))

    def area(self, surface, game):
        number = self.current_floor(game)
        if self.layered(game) and not self.in_opening_map(game):
            name, accent = ZONES[number - 1]
            label = f'B{number}'
        else:
            name, accent = game.stage_name, ORANGE
            label = f'S{game.stage_number}'
        rect = pygame.Rect(716, 14, 228, 42)
        self.frame(surface, rect, accent)
        pygame.draw.rect(surface, WOOD, (726, 23, 30, 23))
        self.text(surface, label, 20, CREAM, center=(741, 35))
        self.text(surface, name, 18, CREAM, center=(847, 35))

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
        # Every stage allows digging visible dirt anywhere on screen.
        return game.world.foreground[game.world.index(x, y)] == DIRT

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
        if self.objective_time <= 0 or self.transition_time > 0:
            return
        if self.layered(game):
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
        elif game.stage_number == 4:
            message = 'Find the bomb and break the gate.'
        else:
            message = 'Cross the mine and reach the exit.'
        card = pygame.Surface((370, 56), pygame.SRCALPHA)
        self.frame(card, (0, 0, 370, 56))
        title = f'S{game.stage_number}  {game.stage_name}' if hasattr(game, 'stage_name') else 'OBJECTIVE'
        self.text(card, title, 16, ORANGE, center=(185, 16))
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
        if hasattr(game, '_can_enemy_see_player'):
            cx, cy = game.render_camera
            for enemy in game.monsters:
                if game._can_enemy_see_player(enemy):
                    x, y = enemy.rect.centerx - cx, enemy.rect.top - cy - 15
                    if 0 <= x < SCREEN_W and 0 <= y < SCREEN_H:
                        self.text(surface, '!', 26, RED, center=(x, y))
        if hasattr(game, 'combat'):
            self.enemy_posture(surface, game)
            self.parry_feedback(surface, game)
        self.health(surface, game)
        if hasattr(game, 'combat'):
            self.posture.draw(surface)
        self.bomb_count(surface, game)
        self.area(surface, game)
        self.danger(surface, game)
        self.objective(surface, game)
        self.tutorial(surface, game, mouse)
        self.transition(surface)

    def parry_feedback(self, surface, game):
        """Combat popups over the action, and a slim recharge bar while it cools."""
        parry = getattr(game, 'parry', None)
        if parry is None:
            return
        cx, cy = game.render_camera
        for text, x, y, age, life, color in game.fx.popups:
            image, shadow = self.rendered(text, 26 if len(text) > 10 else 22, color)
            fade_from = life * 0.65
            alpha = 255 if age < fade_from else round(255 * (life - age) / (life - fade_from))
            image.set_alpha(alpha)
            shadow.set_alpha(alpha)
            rect = image.get_rect(midbottom=(round(x - cx), round(y - cy)))
            rect.clamp_ip(surface.get_rect())
            surface.blit(shadow, rect.move(1, 1))
            surface.blit(image, rect)
        left = parry.cooldown_fraction()
        if left and not parry.is_active() and game.combat.can_act():
            box = game.player.rect.move(-cx, -cy)
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
        small framed bars over engaged enemies, a centre-out bar on the boss."""
        cx, cy = game.render_camera
        boss = getattr(game, 'boss', None)
        for enemy in game.monsters:
            posture = getattr(enemy, 'posture', None)
            if posture is None:
                continue                   # not part of parry combat: no bar
            box = enemy.rect.move(-cx, -cy)
            if not box.colliderect(surface.get_rect()):
                continue
            is_boss = enemy is boss
            engaged = (posture.value or enemy.broken or (self.boss_near(game) if is_boss
                       else game._can_enemy_see_player(enemy)))
            if not engaged:
                continue
            value = posture.maximum if enemy.broken else posture.value
            blink = enemy.broken and int(enemy.stun_timer * 8) % 2
            if is_boss:
                self.boss_posture(surface, box, posture, value, blink)
                continue
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

    def boss_posture(self, surface, box, posture, value, blink):
        """Above the boss's health pips: a framed bar filling from the centre."""
        width, height = 84, 6
        rect = pygame.Rect(0, 0, width, height)
        rect.midbottom = (box.centerx, box.y - 18)
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

    def draw_menu(self, surface, mouse):
        self.buttons = []
        self.overlay(surface, 160)
        self.frame(surface, (280, 95, 400, 480))
        self.text(surface, 'DIG GAME', 64, WOOD_LIGHT, center=(480, 181))
        self.text(surface, 'DESCEND INTO THE DEEP', 20, MUTED, center=(480, 220))
        for n, label in enumerate(('START GAME', 'HOW TO PLAY', 'QUIT')):
            self.button(surface, label, (355, 302 + n * 68, 250, 48), mouse)

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
            ('STAGE 6', 'THE DEEP DESCENT', (244, 91, 40)),
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
                (['E'], 'Parry / deathblow'),
                (['R'], 'Restart'),
                (['ESC'], 'Pause / back')]
        for n, (keys, action) in enumerate(rows):
            y = 152 + n * 48
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

    def draw_end(self, surface, mouse, game, won):
        self.buttons = []
        self.overlay(surface, 168, INK if won else (43, 18, 17))
        self.frame(surface, (306, 160, 348, 380 if won else 324),
                   ORANGE if won else RED)
        final_stage = game.stage_number == FINAL_STAGE
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
            choices = (('PLAY AGAIN', 'MAIN MENU') if final_stage else
                       ('NEXT STAGE', 'MAIN MENU'))
        else:
            choices = ('RETRY', 'MAIN MENU')
        for n, label in enumerate(choices):
            self.button(surface, label, (355, 316 + n * 56, 250, 44), mouse)

    def draw(self, surface, game, mouse):
        if self.screen == 'menu':
            self.draw_menu(surface, mouse)
        elif self.screen == 'stage_select':
            self.draw_stage_select(surface, mouse)
        elif self.screen == 'controls':
            self.draw_controls(surface, mouse)
        elif self.screen == 'paused':
            self.draw_pause(surface, mouse)
        elif game.state == 'win':
            self.draw_end(surface, mouse, game, True)
        elif game.state == 'lose':
            self.draw_end(surface, mouse, game, False)
        else:
            self.buttons = []
            self.draw_game(surface, game, mouse)

    def click(self, position):
        return next((label for rect, label in self.buttons if rect.collidepoint(position)), None)
