"""Visible chunk caches and mass-interpolated pixel-art liquid geometry."""
import math
import pygame
from config import CELL, SCALE, MACRO, CHUNK_CELLS, SCREEN_W, SCREEN_H
from level import DIRT, ROCK, STONE, WATER, LAVA, EMPTY

CHUNK_PIXELS = CHUNK_CELLS * CELL


def prop_supported(world, prop):
    anchors = prop.get('support_cells') or ([prop['support']] if prop.get('support') else [])
    attachment = prop.get('attachment', 'floor')
    for mx, my in anchors:
        gx, gy = mx * SCALE + SCALE // 2, my * SCALE
        if attachment == 'ceiling':
            gy += SCALE - 1
        elif attachment == 'wall_left':
            gx = mx * SCALE + SCALE - 1
            gy += SCALE // 2
        elif attachment == 'wall_right':
            gx = mx * SCALE
            gy += SCALE // 2
        if not world.solid(gx, gy):
            return False
    return True


class WorldRenderer:
    def __init__(self, world, art, scenery):
        self.world, self.art, self.scenery = world, art, scenery
        self.cache = {}
        self.prop_chunks, self.anchor_props = {}, {}
        self.prop_images = {}
        self.prop_boxes = {}
        self.visible_chunks = 0
        self.rebuilt_chunks = 0
        self.visible_liquids = 0
        self.rebuild_ms = 0.0
        self.ladders = []
        for number, prop in enumerate(scenery['props']):
            box = pygame.Rect(round(prop['x'] * MACRO), round(prop['y'] * MACRO),
                              max(1, round(prop['w'] * MACRO)), max(1, round(prop['h'] * MACRO)))
            self.prop_boxes[number] = box
            if prop.get('repeat_y'):
                image = pygame.Surface(box.size, pygame.SRCALPHA)
                height = max(1, round(prop['segment_h'] * MACRO))
                segment = art.sprite(prop['name'], box.w, height, prop['opacity'], prop['flip'])
                for y in range(0, box.h, height):
                    image.blit(segment, (0, y))
            else:
                image = art.sprite(prop['name'], box.w, box.h, prop['opacity'], prop['flip'])
            self.prop_images[number] = image
            if prop['name'] == 'ladder':
                self.ladders.append((box, prop))
            extent = box.copy()
            if 'glow' in prop:
                radius, color = prop['glow']
                radius = round(radius * MACRO)
                art.glow(radius, color)
                extent = extent.union(pygame.Rect(box.centerx-radius, box.y+box.h//3-radius, radius*2, radius*2))
            for cy in range(extent.top // CHUNK_PIXELS, (extent.bottom - 1) // CHUNK_PIXELS + 1):
                for cx in range(extent.left // CHUNK_PIXELS, (extent.right - 1) // CHUNK_PIXELS + 1):
                    self.prop_chunks.setdefault((cx, cy), []).append(number)
            anchors = prop.get('support_cells') or ([prop['support']] if prop.get('support') else [])
            for anchor in anchors:
                self.anchor_props.setdefault(tuple(anchor), []).append(number)
        world.listeners.append(self.terrain_changed)
        # Dynamic glow assets also load before entering the frame loop.
        art.glow(76, (56, 116, 185))
        art.glow(94, (255, 96, 28))
        self.cooling_stones = []
        for stage in range(8):
            stone = art.tile(STONE, 0, 80).copy()
            stone.fill((125,125,153),special_flags=pygame.BLEND_RGB_MULT)
            stone.set_alpha(55+stage*27)
            self.cooling_stones.append(stone)

    def terrain_changed(self, index):
        x, y = self.world.coords(index)
        for number in self.anchor_props.get((x // SCALE, y // SCALE), ()):
            box = self.prop_boxes[number]
            for cy in range(box.top // CHUNK_PIXELS, (box.bottom - 1) // CHUNK_PIXELS + 1):
                for cx in range(box.left // CHUNK_PIXELS, (box.right - 1) // CHUNK_PIXELS + 1):
                    self.world.dirty_chunks.add((cx, cy))
            # Glow can extend outside the physical prop's chunk.
            prop = self.scenery['props'][number]
            if 'glow' in prop:
                radius = math.ceil(prop['glow'][0] * MACRO / CHUNK_PIXELS)
                cx, cy = box.centerx // CHUNK_PIXELS, box.centery // CHUNK_PIXELS
                for yy in range(cy-radius, cy+radius+1):
                    for xx in range(cx-radius, cx+radius+1):
                        self.world.dirty_chunks.add((xx, yy))

    def ladder_at(self, rect):
        return any(box.colliderect(rect) and prop_supported(self.world, prop)
                   for box, prop in self.ladders)

    def _build(self, cx, cy):
        world, art = self.world, self.art
        origin_x, origin_y = cx * CHUNK_PIXELS, cy * CHUNK_PIXELS
        background = pygame.Surface((CHUNK_PIXELS, CHUNK_PIXELS)).convert()
        foreground = pygame.Surface((CHUNK_PIXELS, CHUNK_PIXELS), pygame.SRCALPHA).convert_alpha()
        background.fill((31, 26, 37))
        mx0, my0 = cx * CHUNK_CELLS // SCALE, cy * CHUNK_CELLS // SCALE
        macro_count = CHUNK_CELLS // SCALE
        for my in range(my0, min(world.height // SCALE, my0 + macro_count)):
            for mx in range(mx0, min(world.width // SCALE, mx0 + macro_count)):
                i = world.index(mx * SCALE, my * SCALE)
                background.blit(art.background(mx, my, world.background[i]),
                                (mx * MACRO-origin_x, my * MACRO-origin_y))
        for number in self.prop_chunks.get((cx, cy), ()):
            prop = self.scenery['props'][number]
            if not prop_supported(world, prop):
                continue
            box = self.prop_boxes[number]
            if 'glow' in prop:
                radius, color = prop['glow']
                radius = round(radius * MACRO)
                background.blit(art.glow(radius, color),
                                (box.centerx-radius-origin_x, box.y+box.h//3-radius-origin_y))
            if prop['layer'] == 'back':
                background.blit(self.prop_images[number], (box.x-origin_x, box.y-origin_y))
        # Static terrain is rebuilt only after edits. Mixed macro tiles retain
        # their original texture coordinates instead of repeating tiny squares.
        for my in range(my0, min(world.height // SCALE, my0 + macro_count)):
            for mx in range(mx0, min(world.width // SCALE, mx0 + macro_count)):
                gx, gy = mx * SCALE, my * SCALE
                material = self.scenery['materials'].get((mx, my))
                first = world.foreground[world.index(gx, gy)]
                uniform = all(world.foreground[world.index(gx+dx, gy+dy)] == first
                              for dy in range(SCALE) for dx in range(SCALE))
                px, py = mx * MACRO-origin_x, my * MACRO-origin_y
                if uniform and first != EMPTY:
                    foreground.blit(art.tile(first, mx, my, material if first in (DIRT, ROCK) else None), (px, py))
                elif not uniform:
                    for dy in range(SCALE):
                        for dx in range(SCALE):
                            kind = world.foreground[world.index(gx+dx, gy+dy)]
                            if kind != EMPTY:
                                tile = art.tile(kind, mx, my, material if kind in (DIRT, ROCK) else None)
                                foreground.blit(tile, (px+dx*CELL, py+dy*CELL),
                                                (dx*CELL, dy*CELL, CELL, CELL))
        # Exposed edges follow the actual collision cells, including newly dug
        # paths. Restrained shadow rims make passable spaces readable.
        for y in range(cy * CHUNK_CELLS, min(world.height, (cy+1)*CHUNK_CELLS)):
            for x in range(cx * CHUNK_CELLS, min(world.width, (cx+1)*CHUNK_CELLS)):
                if not world.solid(x, y):
                    continue
                px, py = x*CELL-origin_x, y*CELL-origin_y
                kind = world.foreground[world.index(x, y)]
                highlight = (121, 89, 63) if kind == DIRT else (99, 95, 115)
                if not world.solid(x, y-1):
                    pygame.draw.line(foreground, highlight, (px, py), (px+CELL-1, py))
                if not world.solid(x, y+1):
                    pygame.draw.rect(foreground, (36, 27, 32, 200), (px, py+CELL-2, CELL, 2))
                if not world.solid(x-1, y):
                    pygame.draw.line(foreground, (43, 31, 37, 185), (px, py), (px, py+CELL-1))
                if not world.solid(x+1, y):
                    pygame.draw.line(foreground, (35, 29, 38, 190), (px+CELL-1, py), (px+CELL-1, py+CELL-1))
        for number in self.prop_chunks.get((cx, cy), ()):
            prop = self.scenery['props'][number]
            if prop['layer'] == 'front' and prop_supported(world, prop):
                box = self.prop_boxes[number]
                foreground.blit(self.prop_images[number], (box.x-origin_x, box.y-origin_y))
        self.cache[cx, cy] = background, foreground
        world.dirty_chunks.discard((cx, cy))

    def draw_static(self, screen, camera):
        import time
        start = time.perf_counter()
        cx, cy = camera
        self.rebuilt_chunks = 0
        x0, y0 = max(0, cx // CHUNK_PIXELS), max(0, cy // CHUNK_PIXELS)
        x1 = min(math.ceil(self.world.pixel_width/CHUNK_PIXELS), (cx+screen.get_width()-1)//CHUNK_PIXELS+1)
        y1 = min(math.ceil(self.world.pixel_height/CHUNK_PIXELS), (cy+screen.get_height()-1)//CHUNK_PIXELS+1)
        visible = [(x, y) for y in range(y0, y1) for x in range(x0, x1)]
        for key in visible:
            if key not in self.cache or key in self.world.dirty_chunks:
                self._build(*key)
                self.rebuilt_chunks += 1
        self.rebuild_ms = (time.perf_counter()-start)*1000
        self.visible_chunks = len(visible)
        for x, y in visible:
            back, front = self.cache[x, y]
            screen.blit(back, (x*CHUNK_PIXELS-cx, y*CHUNK_PIXELS-cy))
            screen.blit(front, (x*CHUNK_PIXELS-cx, y*CHUNK_PIXELS-cy))

    def draw_liquids(self, screen, liquids, camera, alpha, world_time):
        cx, cy = camera
        x0, y0 = max(0, cx//CELL-1), max(0, cy//CELL-1)
        x1 = min(self.world.width, (cx+screen.get_width())//CELL+2)
        y1 = min(self.world.height, (cy+screen.get_height())//CELL+2)
        if hasattr(liquids, 'visible_indices'):
            indices = liquids.visible_indices(x0, y0, x1, y1)
        else:
            indices = (y*self.world.width+x for y in range(y0,y1) for x in range(x0,x1))
        cells, lava_landmarks = {}, set()
        for i in indices:
            mass = liquids.interpolated_mass(i, alpha)
            if mass <= .005 or self.world.foreground[i] != EMPTY:
                continue
            kind = liquids.types.get(i) or getattr(liquids, 'previous_types', {}).get(i)
            if kind not in (WATER, LAVA):
                continue
            x, y = self.world.coords(i)
            cells[x, y] = (i, kind, mass)
            if kind == LAVA:
                lava_landmarks.add((x//SCALE, y//SCALE))
        self.visible_liquids = len(cells)
        for mx, my in lava_landmarks:
            if (mx*3+my)%4 == 0:
                screen.blit(self.art.glow(94, (255,96,28)),
                            (mx*MACRO+MACRO//2-94-cx, my*MACRO+MACRO//2-94-cy))
        # Blit the original texture clipped to bottom-aligned pool geometry.
        # Falling cells use connected full-height ribbons instead of tiny bars.
        patches, surfaces, streaks, cooling = [], [], [], []
        for (x,y), (i,kind,mass) in cells.items():
            above, below = cells.get((x,y-1)), cells.get((x,y+1))
            left, right = cells.get((x-1,y)), cells.get((x+1,y))
            below_solid = self.world.solid(x,y+1)
            falling = (not below_solid and (mass < .98 or below is None or below[2] < .98)
                       and above is not None and above[1] == kind)
            sx, sy = x*CELL-cx, y*CELL-cy
            if falling:
                # Neighboring flowing cells meet without dark gaps. Width
                # ranges from half a grid cell to a full cell according to flow.
                width = CELL if (left and left[1]==kind) or (right and right[1]==kind) else max(CELL//2, round(CELL*min(1,mass*2)))
                offset = (CELL-width)//2
                rect = pygame.Rect(sx+offset, sy, width, CELL)
                if (x+y)%3 == int(world_time*12)%3:
                    streaks.append((kind, rect.x+width//2, rect.y, rect.bottom))
            else:
                height = max(1, min(CELL, round(CELL*mass)))
                rect = pygame.Rect(sx, sy+CELL-height, CELL, height)
            area = pygame.Rect((x%SCALE)*CELL, (y%SCALE)*CELL+CELL-rect.h, rect.w, rect.h)
            patches.append((self.art.liquid_patches[kind], rect.topleft, area))
            if (above is None or above[1] != kind) and not falling:
                surfaces.append((kind, rect.left, rect.top, rect.right-1))
            if i in liquids.reactions:
                progress = liquids.reaction_progress(i)
                cooling.append((rect, progress, x, y))
        screen.blits(patches, doreturn=False)
        for kind,left,top,right in surfaces:
            color = (91,194,255) if kind==WATER else (255,184,48)
            pygame.draw.line(screen,color,(left,top),(right,top))
        for kind,x,top,bottom in streaks:
            color = (47,147,220) if kind==WATER else (230,112,31)
            pygame.draw.line(screen,color,(x,top),(x,bottom-1))
        for rect, progress, x, y in cooling:
            # Darkening happens locally before solidity; a few restrained steam
            # pixels move upward without allocating particle emitters per tile.
            stone = self.cooling_stones[min(7,int(progress*8))]
            screen.blit(stone,rect.topleft,((x%SCALE)*CELL,(y%SCALE)*CELL,rect.w,rect.h))
            if (rect.x+rect.y)//CELL%7==int(world_time*8)%7:
                rise = int(world_time*20)%9
                pygame.draw.rect(screen,(192,191,199),(rect.centerx,rect.top-rise,2,3))
