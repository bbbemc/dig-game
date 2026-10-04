"""Short-lived, capped excavation debris; deterministic and camera culled."""
import random
import pygame
from config import CELL, MAX_PARTICLES


class Particles:
    def __init__(self):
        self.items = []
        self.random = random.Random(42)

    def dirt(self, world, removed):
        for i in removed[::max(1,len(removed)//12)][:12]:
            if len(self.items) >= MAX_PARTICLES:
                break
            x,y = world.coords(i)
            self.items.append([x*CELL+CELL/2,y*CELL+CELL/2,
                               self.random.uniform(-65,65),self.random.uniform(-100,-35),
                               self.random.uniform(.2,.5)])

    def update(self, dt):
        alive = []
        for p in self.items:
            p[4] -= dt
            if p[4] > 0:
                p[3] += 450*dt
                p[0] += p[2]*dt
                p[1] += p[3]*dt
                alive.append(p)
        self.items = alive

    def draw(self, screen, camera):
        cx,cy = camera
        for x,y,_,_,life in self.items:
            sx,sy = round(x-cx),round(y-cy)
            if 0 <= sx < screen.get_width() and 0 <= sy < screen.get_height():
                pygame.draw.rect(screen,(158,112,73),(sx,sy,2 if life>.2 else 1,2))
