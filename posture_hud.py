"""The player's posture bar: bottom centre, cinematic, shown around combat.

Pure presentation. It reads the game's combat state (posture points, the
guard-break stun) and whether a fight is on, and keeps only its own
animation state, so it always agrees with the real combat numbers.

Like Sekiro's, the bar fills from the centre outward to both ends. Each
point fills a third of each half, and notches mark the thirds:
gold at 1/3, pulsing orange at 2/3, red and cracked when the guard breaks.
It slides up and fades in when combat starts, stays up while combat (or any
posture) lasts, then holds POSTURE_BAR_HOLD seconds before it slides down
and fades. A new combat interaction cancels the fade.
"""

import math
import random

import pygame

from config import (SCREEN_W, POSTURE_BAR_WIDTH, POSTURE_BAR_HEIGHT, POSTURE_BAR_Y,
                    POSTURE_BAR_HOLD)

INK = (23, 20, 16)
BACK = (14, 10, 8, 200)
STEEL_LIGHT, STEEL, STEEL_DARK = (176, 168, 156), (112, 104, 96), (56, 50, 46)
TRIM = (232, 176, 72)
# Per level: body, highlight, shadow, glow.
LEVELS = {
    1: ((246, 194, 62), (255, 236, 150), (180, 124, 34), (255, 200, 80)),
    2: ((240, 130, 36), (255, 188, 100), (164, 74, 22), (255, 140, 50)),
    3: ((226, 50, 40), (255, 134, 106), (136, 24, 24), (255, 70, 50)),
}
FADE_IN, FADE_OUT = 0.22, 0.6     # seconds for a full fade
SLIDE = 14                        # px the bar travels while fading
RISE_PULSE = 0.3                  # seconds a rising point flashes
BREAK_SPLIT = 4                   # px the halves part when the guard breaks


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


class PostureHUD:
    def __init__(self):
        width, height = POSTURE_BAR_WIDTH, POSTURE_BAR_HEIGHT
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (SCREEN_W // 2, POSTURE_BAR_Y)
        pad_x, pad_y = 26, 16             # room for end caps, glow and emblem
        self.canvas = pygame.Surface((width + 2 * pad_x, height + 2 * pad_y), pygame.SRCALPHA)
        self.origin = (self.rect.x - pad_x, self.rect.y - pad_y)
        self.local = pygame.Rect(pad_x, pad_y, width, height)
        self.reset()

    def reset(self):
        self.visibility = 0.0     # 0 hidden .. 1 fully shown
        self.hold = 0.0           # seconds the bar stays up after combat
        self.shown = 0.0          # animated fill, 0..1 of the whole bar
        self.value = 0
        self.broken = False
        self.time = 0.0
        self.pulse = 9.0          # seconds since a point was added
        self.pulse_from = 0.0     # fill fraction before that point
        self.break_age = 9.0      # seconds since the guard broke
        self.heal_age = 9.0       # seconds since the stun ended
        self.appear = 9.0         # seconds since the bar began to show
        self.shards = []          # [x, y, vx, vy, life, colour] in screen px
        self.random = random.Random(5)

    # -- state ------------------------------------------------------------
    @staticmethod
    def in_combat(game):
        combat = game.combat
        return (game.engaged or combat.posture.value > 0 or not combat.can_act()
                or game.world_time - game.last_combat < 0.25)

    def bar_rect(self):
        """Where the bar body is drawn right now (it slides while fading)."""
        return self.rect.move(0, self.slide())

    def slide(self):
        eased = 1 - (1 - self.visibility) ** 2
        return round(SLIDE * (1 - eased))

    def update(self, dt, game):
        self.time += dt
        for name in ('pulse', 'break_age', 'heal_age', 'appear'):
            setattr(self, name, getattr(self, name) + dt)
        combat = game.combat
        posture = combat.posture
        broken = game.state == 'play' and not combat.can_act()
        if posture.value > self.value and not broken:
            self.pulse, self.pulse_from = 0.0, self.shown
        if broken and not self.broken:
            self.break_age = 0.0
            self._shatter()
        if self.broken and not broken:
            self.heal_age = 0.0
        self.value, self.broken = posture.value, broken
        if self.in_combat(game):
            if self.visibility < 0.05 and self.hold <= 0:
                self.appear = 0.0
            self.hold = POSTURE_BAR_HOLD          # also cancels a fade in progress
        else:
            self.hold = max(0.0, self.hold - dt)
        target = 1.0 if self.hold > 0 else 0.0
        step = dt / (FADE_IN if target > self.visibility else FADE_OUT)
        if target > self.visibility:
            self.visibility = min(target, self.visibility + step)
        else:
            self.visibility = max(target, self.visibility - step)
        goal = 1.0 if broken else max(0.0, posture.value - posture.recovery_progress()) / posture.maximum
        speed = 18.0 if goal > self.shown else 5.0
        self.shown += (goal - self.shown) * (1 - math.exp(-speed * dt))
        if abs(goal - self.shown) < 0.002:
            self.shown = goal
        alive = []
        for shard in self.shards:
            shard[4] -= dt
            if shard[4] > 0:
                shard[3] += 520 * dt
                shard[0] += shard[2] * dt
                shard[1] += shard[3] * dt
                alive.append(shard)
        self.shards = alive

    def _shatter(self):
        rnd = self.random
        cx, cy = self.rect.center
        for _ in range(16):
            x = cx + rnd.uniform(-self.rect.w * 0.45, self.rect.w * 0.45)
            self.shards.append([x, cy + rnd.uniform(-4, 4), rnd.uniform(-90, 90),
                                rnd.uniform(-220, -80), rnd.uniform(0.35, 0.7),
                                rnd.choice(((255, 236, 220), LEVELS[3][0], LEVELS[3][1]))])

    def level(self):
        if self.broken:
            return 3
        if self.value:
            return min(3, self.value)
        return 1          # draining to empty keeps the first colour

    # -- drawing ----------------------------------------------------------
    def draw(self, surface):
        if self.visibility <= 0.01:
            return
        canvas, bar = self.canvas, self.local
        canvas.fill((0, 0, 0, 0))
        level = self.level()
        body, light, shadow, glow = LEVELS[level]
        wave = 0.5 + 0.5 * math.sin(self.time * 2 * math.pi * 1.6)
        if level == 2 and not self.broken:            # warning pulse
            body = _lerp(body, light, 0.22 * wave)
        if self.broken and self.break_age < 0.36 and int(self.break_age * 16) % 2:
            body, light = (255, 236, 220), (255, 255, 255)   # the whole bar flashes
        half = bar.w // 2 - 2
        fill = round(half * min(1.0, self.shown))
        split = 0
        if self.broken:
            split = round(BREAK_SPLIT * min(1.0, self.break_age / 0.08))
        elif self.heal_age < 0.25:
            split = round(BREAK_SPLIT * (1 - self.heal_age / 0.25))
        cx = bar.centerx
        self._glow(canvas, bar, cx, fill, glow, level, wave)
        for side in (-1, 1):
            self._half(canvas, bar, cx, side, side * split, fill, body, light, shadow)
        if split:
            self._crack(canvas, bar, cx)
        self._emblem(canvas, bar, cx, body if self.shown > 0.01 or self.broken else None, glow)
        shake = 0
        if self.pulse < 0.22:
            shake = round(2 * (1 - self.pulse / 0.22) * math.sin(self.pulse * 70))
        elif self.broken and self.break_age < 0.3:
            shake = 2 if int(self.break_age * 40) % 2 else -2
        canvas.set_alpha(round(255 * self.visibility))
        x, y = self.origin
        surface.blit(canvas, (x + shake, y + self.slide()))
        self._flourish(surface, shake)

    def _glow(self, canvas, bar, cx, fill, glow, level, wave):
        strength = {1: 0.55, 2: 0.8 + 0.3 * wave, 3: 1.0}[level]
        if self.pulse < RISE_PULSE:
            strength += 0.6 * (1 - self.pulse / RISE_PULSE)
        if fill > 0:
            for grow, alpha in ((7, 14), (5, 22), (3, 34)):
                rect = pygame.Rect(cx - fill - grow, bar.y - grow, 2 * (fill + grow), bar.h + 2 * grow)
                canvas.fill((*glow, min(255, round(alpha * strength))), rect)
        if self.appear < 0.6:                          # golden glow as it arrives
            k = 1 - self.appear / 0.6
            for grow, alpha in ((8, 18), (4, 30)):
                canvas.fill((255, 200, 90, round(alpha * k)), bar.inflate(2 * grow, 2 * grow))

    def _half(self, canvas, bar, cx, side, offset, fill, body, light, shadow):
        """One half: frame, translucent back, notches and the fill from the centre."""
        left = bar.x if side < 0 else cx
        width = cx - bar.x if side < 0 else bar.right - cx
        box = pygame.Rect(left + offset, bar.y, width, bar.h)
        canvas.fill((*INK, 255), box.inflate(0, 4).move(0, 0))
        if side < 0:
            canvas.fill((*INK, 255), (box.x - 2, box.y - 2, 2, box.h + 4))
        else:
            canvas.fill((*INK, 255), (box.right, box.y - 2, 2, box.h + 4))
        inner = box.inflate(0, -2)
        canvas.fill(BACK, inner)
        canvas.fill((6, 4, 3, 230), (inner.x, inner.y, inner.w, 2))           # inner shadow
        # Thin metallic border: light above, dark below.
        canvas.fill((*STEEL_LIGHT, 255), (box.x, box.y - 1, box.w, 1))
        canvas.fill((*STEEL_DARK, 255), (box.x, box.bottom, box.w, 1))
        if fill > 0:
            span = min(fill, width - 2)
            x0 = cx + offset - span if side < 0 else cx + offset
            rows = ((1, 2, light), (3, inner.h - 5, body), (inner.h - 2, 2, shadow))
            for top, height, color in rows:
                canvas.fill((*color, 255), (x0, inner.y + top - 1, span, height))
            if self.pulse < RISE_PULSE:                # the new point flashes in
                start = round((bar.w // 2 - 2) * self.pulse_from)
                k = 1 - self.pulse / RISE_PULSE
                if span > start:
                    nx = cx + offset - span if side < 0 else cx + offset + start
                    canvas.fill((255, 250, 230, round(200 * k)), (nx, inner.y, span - start, inner.h))
            tip = x0 if side < 0 else x0 + span - 2    # bright leading edge
            canvas.fill((255, 246, 210, 255), (tip, inner.y, 2, inner.h))
        for k in (1, 2):                               # segment notches at thirds
            nx = cx + offset + side * round((bar.w // 2) * k / 3)
            canvas.fill((*INK, 220), (nx, inner.y, 1, inner.h))
            canvas.fill((*STEEL_LIGHT, 255), (nx, box.y - 2, 1, 2))
        self._cap(canvas, bar, side, offset)

    def _cap(self, canvas, bar, side, offset):
        """A small sword-guard ornament with a spike, on each end."""
        x = (bar.x - 3 if side < 0 else bar.right + 2) + offset
        cy = bar.centery
        diamond = [(x, cy - 11), (x + 5, cy), (x, cy + 11), (x - 5, cy)]
        spike = [(x - 4 * side, cy - 3), (x + 13 * side, cy), (x - 4 * side, cy + 3)]
        pygame.draw.polygon(canvas, (*INK, 255), [(px - 1, py) for px, py in spike] +
                            [(px + 1, py) for px, py in reversed(spike)])
        pygame.draw.polygon(canvas, (*STEEL, 255), spike)
        pygame.draw.polygon(canvas, (*INK, 255), [(x, cy - 13), (x + 7, cy), (x, cy + 13), (x - 7, cy)])
        pygame.draw.polygon(canvas, (*STEEL, 255), diamond)
        pygame.draw.line(canvas, (*STEEL_LIGHT, 255), (x, cy - 10), (x - 4 * side, cy - 1))
        canvas.fill((*TRIM, 255), (x - 1, cy - 1, 2, 2))   # gold rivet

    def _crack(self, canvas, bar, cx):
        points = [(cx + (1 if n % 2 else -1), bar.y - 2 + n * 4) for n in range(bar.h // 4 + 2)]
        pygame.draw.lines(canvas, (255, 236, 220, 255), False, points, 1)

    def _emblem(self, canvas, bar, cx, color, glow):
        """The centre mark: dark when empty, glowing in the level's colour."""
        cy = bar.y - 1
        pygame.draw.polygon(canvas, (*INK, 255), [(cx, cy - 9), (cx + 7, cy), (cx, cy + 9), (cx - 7, cy)])
        pygame.draw.polygon(canvas, (*STEEL_LIGHT, 255), [(cx, cy - 7), (cx + 5, cy), (cx, cy + 7), (cx - 5, cy)])
        inner = color if color is not None else (44, 34, 30)
        if self.pulse < RISE_PULSE:
            inner = _lerp(inner, (255, 250, 230), 1 - self.pulse / RISE_PULSE)
        pygame.draw.polygon(canvas, (*inner, 255), [(cx, cy - 5), (cx + 3, cy), (cx, cy + 5), (cx - 3, cy)])
        if color is not None:
            canvas.fill((255, 250, 230, 255), (cx - 1, cy - 3, 1, 2))

    def _flourish(self, surface, shake):
        """Additive sparkle at the fill tips on a rise, heal shimmer, shards."""
        from parry_fx import flash_frames
        bar = self.bar_rect().move(shake, 0)
        fill = round((bar.w // 2 - 2) * min(1.0, self.shown))
        if self.pulse < 0.12:
            frames = flash_frames(0.5, 'gold')
            image = frames[min(len(frames) - 1, int(self.pulse / 0.12 * len(frames)))]
            half = image.get_width() // 2
            for x in (bar.centerx - fill, bar.centerx + fill):
                surface.blit(image, (x - half, bar.centery - half), special_flags=pygame.BLEND_RGB_ADD)
        if self.heal_age < 0.35:                       # recovered: a gold sweep outward
            k = self.heal_age / 0.35
            for side in (-1, 1):
                x = bar.centerx + side * round(bar.w / 2 * k)
                surface.fill((255, 226, 140), (x - 1, bar.y + 2, 3, bar.h - 4))
        for x, y, _, _, life, color in self.shards:
            size = 3 if life > 0.3 else 2
            surface.fill(color, (round(x), round(y), size, size))
