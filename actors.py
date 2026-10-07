"""Miner presentation: animation state, facing and a grounded contact shadow.

Purely visual. It reads the player's physics state (velocity, grounded,
ladder) and the current dig target, and never changes the collision box:
every frame is 32 x 32 with the boots on the box's bottom row.
"""

import pygame

from pixel_art import miner_frames


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
        vx = actor.velocity.x
        self.digging = dig_x is not None
        if self.digging:
            self.facing_right = dig_x >= actor.rect.centerx
            self.swing += dt
        else:
            self.swing = 0.0
            if abs(vx) > 1:
                self.facing_right = vx > 0
        if actor.grounded and abs(vx) > 1:
            self.stride += abs(vx) * dt

    def animation(self, actor):
        if actor.on_ladder:
            return 'climb', int(actor.pos.y // 10) % 2
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
        frames = self.hurt_frames if hurt > 0 and int(hurt * 14) % 2 == 0 else self.frames
        screen.blit(frames[self.facing_right][name][index], box.topleft)

    def head(self, actor):
        """World position of the helmet lamp, for lighting."""
        x = actor.rect.x + (24 if self.facing_right else 8)
        return x, actor.rect.y + 9
