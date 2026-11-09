"""Miner presentation: animation state, facing and a grounded contact shadow.

Purely visual. It reads the player's physics state (velocity, grounded,
ladder) and the current dig target, and never changes the collision box:
every frame is 32 x 32 with the boots on the box's bottom row.
"""

import pygame

from pixel_art import miner_frames

ANTICIPATION = 0.04     # seconds of wind-up before the guard pose


class MinerSprite:
    def __init__(self):
        right = miner_frames()
        left = {name: [pygame.transform.flip(f, True, False) for f in frames]
                for name, frames in right.items()}
        self.frames = {True: right, False: left}
        hurt = {}
        for facing, animations in self.frames.items():
            hurt[facing] = {}
            for name, frames in animations.items():
                tinted = []
                for frame in frames:
                    copy = frame.copy()
                    copy.fill((255, 120, 110), special_flags=pygame.BLEND_RGB_MULT)
                    tinted.append(copy)
                hurt[facing][name] = tinted
        self.hurt_frames = hurt
        # A parry flashes the miner white for a moment.
        flash = {}
        for facing, animations in self.frames.items():
            flash[facing] = {}
            for name, frames in animations.items():
                bright = []
                for frame in frames:
                    copy = frame.copy()
                    copy.fill((150, 150, 135), special_flags=pygame.BLEND_RGB_ADD)
                    bright.append(copy)
                flash[facing][name] = bright
        self.flash_frames = flash
        # A guard break flashes the miner red-orange.
        broken = {}
        for facing, animations in self.frames.items():
            broken[facing] = {}
            for name, frames in animations.items():
                hot = []
                for frame in frames:
                    copy = frame.copy()
                    copy.fill((150, 46, 8), special_flags=pygame.BLEND_RGB_ADD)
                    hot.append(copy)
                broken[facing][name] = hot
        self.break_frames = broken
        self.flash = 0.0
        self.break_flash = 0.0
        self.guarding = False   # parry window open: guard pose, facing held
        self.pose = None        # 'recoil' / 'stagger' while the guard is broken
        self.parry_time = 9.0   # seconds since E: a short wind-up, then the guard
        self.recoil = 0.0       # after a deflect: blade thrown out, body pushed back
        self.recovering = 0.0   # after a stun: back on guard
        self.shadow = pygame.Surface((22, 5), pygame.SRCALPHA)
        pygame.draw.ellipse(self.shadow, (0, 0, 0, 70), (0, 0, 22, 5))
        pygame.draw.ellipse(self.shadow, (0, 0, 0, 60), (4, 1, 14, 3))
        self.facing_right = True
        self.stride = 0.0
        self.clock = 0.0
        self.swing = 0.0
        self.digging = False

    def update(self, dt, actor, dig_x=None):
        """``dig_x`` is the world x being excavated this frame, if any."""
        self.clock += dt
        self.flash = max(0.0, self.flash - dt)
        self.break_flash = max(0.0, self.break_flash - dt)
        self.parry_time += dt
        self.recoil = max(0.0, self.recoil - dt)
        self.recovering = max(0.0, self.recovering - dt)
        vx = actor.velocity.x
        self.digging = dig_x is not None
        if self.guarding or self.pose:
            self.swing = 0.0     # parry and stun keep the facing they started with
        elif self.digging:
            self.facing_right = dig_x >= actor.rect.centerx
            self.swing += dt
        else:
            self.swing = 0.0
            if abs(vx) > 1:
                self.facing_right = vx > 0
        if actor.grounded and abs(vx) > 1:
            self.stride += abs(vx) * dt

    def animation(self, actor):
        if self.pose == 'recoil':
            return 'recoil', 0
        if self.pose == 'stagger':
            return 'stagger', int(self.clock * 3) % 2
        if actor.on_ladder:
            return 'climb', int(actor.pos.y // 10) % 2
        if self.recoil > 0:
            return 'dig', 1      # the blade thrown out by the clash
        if self.guarding and self.parry_time < ANTICIPATION:
            return 'idle', 0     # a hair of wind-up: pick drawn back
        if self.guarding or self.recovering > 0:
            return 'dig', 0      # pickaxe raised across the body
        if self.digging and actor.grounded:
            return 'dig', int(self.swing * 8) % 2
        if not actor.grounded:
            return ('jump' if actor.velocity.y < 0 else 'fall'), 0
        if abs(actor.velocity.x) > 1:
            return 'walk', int(self.stride // 9) % 4
        return 'idle', int(self.clock * 1.6) % 2

    def draw(self, screen, actor, camera, hurt=0.0):
        box = actor.rect.move(-camera[0], -camera[1])
        if not box.colliderect(screen.get_rect()):
            return
        if actor.grounded:
            screen.blit(self.shadow, (box.centerx - 11, box.bottom - 3))
        name, index = self.animation(actor)
        box = box.move(self.lean() * (1 if self.facing_right else -1), 0)
        if self.break_flash > 0 and int(self.break_flash * 30) % 2 == 0:
            frames = self.break_frames
        elif self.flash > 0:
            frames = self.flash_frames
        elif hurt > 0 and int(hurt * 14) % 2 == 0:
            frames = self.hurt_frames
        else:
            frames = self.frames
        screen.blit(frames[self.facing_right][name][index], box.topleft)
        if self.guarding and ANTICIPATION <= self.parry_time < ANTICIPATION + 0.08:
            self._glint(screen, box)              # light catching the raised blade
        elif self.recovering > 0.15:
            self._glint(screen, box)

    def lean(self):
        """Pixels the drawn sprite shifts forward (+) or back (-); never the box."""
        if self.recoil > 0:
            return -round(3 * self.recoil / 0.12)
        if self.guarding:
            return -1 if self.parry_time < ANTICIPATION else 1
        return 0

    def _glint(self, screen, box):
        x = box.x + (27 if self.facing_right else 4)
        y = box.y + 13
        screen.fill((255, 255, 255), (x - 1, y, 3, 1))
        screen.fill((255, 255, 255), (x, y - 1, 1, 3))

    def head(self, actor):
        """World position of the helmet lamp, for lighting."""
        x = actor.rect.x + (24 if self.facing_right else 8)
        return x, actor.rect.y + 9
