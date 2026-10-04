"""Dense four-layer Dig Game world using the supplied tile art."""

import random
import pygame

from level import (WIDTH, HEIGHT, SCALE, EMPTY, DIRT, ROCK, WATER, LAVA,
                   STONE, DIGGABLE, FLUIDS, build_level, validate_level,
                   expand_level)
from tiles import TileArt

CELL, MACRO, DIG_RADIUS, DIG_REACH = 8, 40, 3, 18
SCREEN_W, SCREEN_H, FPS = 960, 640, 60


def dig(grid, cx, cy):
    for y in range(max(1, cy - DIG_RADIUS), min(len(grid) - 1, cy + DIG_RADIUS + 1)):
        for x in range(max(1, cx - DIG_RADIUS), min(len(grid[0]) - 1, cx + DIG_RADIUS + 1)):
            if (x - cx) ** 2 + (y - cy) ** 2 <= DIG_RADIUS ** 2 and grid[y][x] in DIGGABLE:
                grid[y][x] = EMPTY


def dig_line(grid, start, end):
    steps = max(abs(end[0] - start[0]), abs(end[1] - start[1]), 1)
    for i in range(steps + 1):
        dig(grid, start[0] + (end[0] - start[0]) * i // steps,
            start[1] + (end[1] - start[1]) * i // steps)


def step_fluids(grid, frame):
    """Original fall/diagonal/sideways simulation, run at 10 Hz."""
    h, w = len(grid), len(grid[0])
    moved = [[False] * w for _ in range(h)]
    xs = range(w) if frame % 2 == 0 else range(w - 1, -1, -1)
    for y in range(h - 2, 0, -1):
        row, below = grid[y], grid[y + 1]
        for x in xs:
            t = row[x]
            if t not in FLUIDS or moved[y][x]:
                continue
            if t == LAVA:
                hit = False
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == WATER:
                        grid[ny][nx] = STONE
                        hit = True
                if hit:
                    row[x] = STONE
                    continue
                if frame % 2:
                    continue
            if below[x] == EMPTY:
                below[x], row[x] = t, EMPTY
                moved[y + 1][x] = True
                continue
            d = random.choice((-1, 1))
            moved_diagonal = False
            for dx in (d, -d):
                nx = x + dx
                if 0 < nx < w - 1 and below[nx] == EMPTY and row[nx] == EMPTY:
                    below[nx], row[x] = t, EMPTY
                    moved[y + 1][nx] = True
                    moved_diagonal = True
                    break
            if moved_diagonal:
                continue
            for dx in (d, -d):
                nx = x + dx
                if 0 < nx < w - 1 and row[nx] == EMPTY:
                    row[nx], row[x] = t, EMPTY
                    moved[y][nx] = True
                    break


def blocked(grid, rect):
    if rect.left < SCALE or rect.top < SCALE or rect.right > len(grid[0]) - SCALE or rect.bottom > len(grid) - SCALE:
        return True
    return any(grid[y][x] in (DIRT, ROCK, STONE)
               for y in range(rect.top, rect.bottom)
               for x in range(rect.left, rect.right))


def touches(grid, rect, kind):
    return any(grid[y][x] == kind
               for y in range(rect.top, rect.bottom)
               for x in range(rect.left, rect.right))


def move_axis(grid, actor, amount, axis):
    key = "x" if axis == 0 else "y"
    old = actor[key]
    actor[key] += amount
    candidate = pygame.Rect(round(actor["x"]), round(actor["y"]), actor["size"], actor["size"])
    if blocked(grid, candidate):
        actor[key] = old
        return False
    actor["rect"] = candidate
    return True


def new_game():
    rows, entities, decorations, optional_rooms = build_level()
    density = validate_level(rows, entities)
    grid, expanded = expand_level(rows, entities)
    px, py = expanded["P"][0]
    bx, by = expanded["E"][0]
    player = {"x": float(px), "y": float(py), "size": 4,
              "rect": pygame.Rect(px, py, 4, 4)}
    boss = pygame.Rect(bx, by, 5, 5)
    monsters = [{"x": float(x), "y": float(y), "size": 3,
                 "rect": pygame.Rect(x, y, 3, 3), "direction": 1 if i % 2 else -1}
                for i, (x, y) in enumerate(expanded["M"])]
    return grid, player, boss, monsters, decorations, density, optional_rooms


def camera_for(player):
    cx = player["rect"].centerx * CELL - SCREEN_W // 2
    cy = player["rect"].centery * CELL - SCREEN_H // 2
    return (max(0, min(cx, WIDTH * MACRO - SCREEN_W)),
            max(0, min(cy, HEIGHT * MACRO - SCREEN_H)))


def prop_is_supported(grid, prop):
    support = prop['support']
    if support is None:
        return True
    x, y = support
    gx = x * SCALE + SCALE // 2
    gy = y * SCALE + (SCALE - 1 if prop['attachment'] == 'ceiling' else 0)
    return grid[gy][gx] in (DIRT, ROCK, STONE)


def draw_props(screen, grid, art, scenery, camera, layer):
    cx, cy = camera
    view = pygame.Rect(0, 0, SCREEN_W, SCREEN_H)
    for prop in scenery['props']:
        if prop['layer'] != layer or not prop_is_supported(grid, prop):
            continue
        box = pygame.Rect(round(prop['x'] * MACRO - cx), round(prop['y'] * MACRO - cy),
                          round(prop['w'] * MACRO), round(prop['h'] * MACRO))
        if view.colliderect(box):
            surface = art.sprite(prop['name'], box.w, box.h, prop['opacity'], prop['flip'])
            screen.blit(surface, box)


def draw_lights(screen, grid, art, scenery, camera, lava_tiles):
    cx, cy = camera
    lights = []
    for light in scenery['lights']:
        x, y = int(light['x'] * SCALE), int(light['y'] * SCALE)
        kind = LAVA if light['fluid'] == 'L' else WATER
        if grid[y][x] == kind:
            lights.append(light)
    for x, y in lava_tiles:
        if (x + y) % 3 == 0:
            lights.append(dict(x=x + 0.5, y=y + 0.5, radius=2.3, color=(255, 99, 33)))
    for prop in scenery['props']:
        if 'glow' in prop and prop_is_supported(grid, prop):
            radius, color = prop['glow']
            lights.append(dict(x=prop['x'] + prop['w'] / 2,
                               y=prop['y'] + prop['h'] / 3, radius=radius, color=color))
    for light in lights:
        radius = round(light['radius'] * MACRO)
        x, y = round(light['x'] * MACRO - cx), round(light['y'] * MACRO - cy)
        if -radius < x < SCREEN_W + radius and -radius < y < SCREEN_H + radius:
            screen.blit(art.glow(radius, light['color']), (x - radius, y - radius))


def draw_world(screen, grid, art, decorations, camera):
    cx, cy = camera
    x0, x1 = max(0, cx // MACRO - 1), min(WIDTH, (cx + SCREEN_W) // MACRO + 2)
    y0, y1 = max(0, cy // MACRO - 1), min(HEIGHT, (cy + SCREEN_H) // MACRO + 2)
    screen.fill((13, 14, 20))
    # Dim original rock/dirt art represents the distant cave wall. Its contrast
    # stays much lower than solid terrain, so open space remains recognizable.
    for my in range(y0, y1):
        group = 'dirt' if my < 50 else ('deep' if my < 66 else
                                      ('ancient_dirt' if my < 75 else 'dark'))
        for mx in range(x0, x1):
            screen.blit(art.backgrounds[group], (mx * MACRO - cx, my * MACRO - cy))
    draw_props(screen, grid, art, decorations, camera, 'back')
    fluids = []
    for my in range(y0, y1):
        gy, sy = my * SCALE, my * MACRO - cy
        for mx in range(x0, x1):
            gx, sx = mx * SCALE, mx * MACRO - cx
            first = grid[gy][gx]
            material = decorations['materials'].get((mx, my))
            above = grid[gy - 1][gx + 2] if gy > 0 else ROCK
            uniform = all(grid[gy + dy][gx + dx] == first
                          for dy in range(SCALE) for dx in range(SCALE))
            if uniform:
                if first in FLUIDS:
                    fluids.append((first, mx, my, sx, sy, None, above))
                elif first != EMPTY:
                    surface = art.tile(first, mx, my, material if first in (DIRT, ROCK) else None)
                    screen.blit(surface, (sx, sy))
            else:
                for dy in range(SCALE):
                    for dx in range(SCALE):
                        kind = grid[gy + dy][gx + dx]
                        area = pygame.Rect(dx * CELL, dy * CELL, CELL, CELL)
                        pos = (sx + dx * CELL, sy + dy * CELL)
                        if kind in FLUIDS:
                            fluids.append((kind, mx, my, *pos, area, above))
                        elif kind != EMPTY:
                            surface = art.tile(kind, mx, my, material if kind in (DIRT, ROCK) else None)
                            # Clip the full-size tile at dug cells; don't replace
                            # partially excavated art with tiny repeated textures.
                            screen.blit(surface, pos, area)
    lava_tiles = {(mx, my) for kind, mx, my, *_ in fluids if kind == LAVA}
    draw_lights(screen, grid, art, decorations, camera, lava_tiles)
    draw_props(screen, grid, art, decorations, camera, 'front')
    # Fluids cover submerged props and retain their actual simulation footprint.
    for kind, mx, my, sx, sy, area, above in fluids:
        screen.blit(art.tile(kind, mx, my, above=above), (sx, sy), area)
        gx, gy = mx * SCALE, my * SCALE
        side_open = ((gx > 0 and grid[gy][gx - 1] == EMPTY) or
                     (gx + SCALE < len(grid[0]) and grid[gy][gx + SCALE] == EMPTY))
        if area is None and above == kind and side_open:
            fall = 'water_fall' if kind == WATER else 'lava_fall'
            screen.blit(art.macro[fall], (sx, sy))


def draw_actor(screen, rect, color, camera):
    cx, cy = camera
    box = pygame.Rect(rect.x * CELL - cx, rect.y * CELL - cy,
                      rect.w * CELL, rect.h * CELL)
    pygame.draw.rect(screen, (19, 19, 25), box.inflate(4, 4), border_radius=4)
    pygame.draw.rect(screen, color, box, border_radius=4)
    pygame.draw.rect(screen, (240, 240, 215), (box.x + box.w // 3, box.y + box.h // 3, 4, 4))


def main():
    pygame.init()
    random.seed(42)
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Dig Game — Four Layers")
    art = TileArt(CELL, MACRO)
    font, big_font = pygame.font.SysFont(None, 27), pygame.font.SysFont(None, 54)
    clock = pygame.time.Clock()
    grid, player, boss, monsters, decorations, density, optional_rooms = new_game()
    hp, state, last_dig, fluid_timer, fluid_frame, hurt_timer = 100, "play", None, 0.0, 0, 0.0
    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000, 0.05)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                grid, player, boss, monsters, decorations, density, optional_rooms = new_game()
                hp, state, last_dig, fluid_timer, fluid_frame, hurt_timer = 100, "play", None, 0.0, 0, 0.0

        if state == "play":
            keys = pygame.key.get_pressed()
            direction = pygame.Vector2(
                int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
                int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP]))
            if direction.length_squared():
                speed = 11 if touches(grid, player["rect"], WATER) else 22
                direction = direction.normalize() * speed * dt
                move_axis(grid, player, direction.x, 0)
                move_axis(grid, player, direction.y, 1)
            camera = camera_for(player)
            if pygame.mouse.get_pressed()[0]:
                mx, my = pygame.mouse.get_pos()
                target = ((mx + camera[0]) // CELL, (my + camera[1]) // CELL)
                dx, dy = target[0] - player["rect"].centerx, target[1] - player["rect"].centery
                if dx * dx + dy * dy <= DIG_REACH * DIG_REACH:
                    dig_line(grid, last_dig or target, target)
                    last_dig = target
                else:
                    last_dig = None
            else:
                last_dig = None
            for monster in monsters:
                if not move_axis(grid, monster, monster["direction"] * 4 * dt, 0):
                    monster["direction"] *= -1
            hurt_timer = max(0.0, hurt_timer - dt)
            if touches(grid, player["rect"], LAVA):
                hp, state = 0, "lose"
            elif hurt_timer == 0 and (any(player["rect"].colliderect(m["rect"]) for m in monsters)
                                       or player["rect"].colliderect(boss)):
                hp -= 20
                hurt_timer = 0.8
                if hp <= 0:
                    state = "lose"
            if touches(grid, boss, LAVA):
                state = "win"
            fluid_timer += dt
            if fluid_timer >= 0.10:
                step_fluids(grid, fluid_frame)
                fluid_frame += 1
                fluid_timer -= 0.10
        else:
            camera = camera_for(player)

        draw_world(screen, grid, art, decorations, camera)
        for monster in monsters:
            draw_actor(screen, monster["rect"], (220, 75, 65), camera)
        draw_actor(screen, boss, (158, 52, 184), camera)
        wet = touches(grid, player["rect"], WATER)
        draw_actor(screen, player["rect"], (90, 180, 255) if wet else (77, 207, 117), camera)
        layer = min(4, player["rect"].centery // (25 * SCALE) + 1)
        hud = f"HP {hp}    B{layer}    WASD / Arrows: move    Mouse: dig nearby    R: restart"
        pygame.draw.rect(screen, (18, 17, 24), (0, 0, SCREEN_W, 37))
        screen.blit(font.render(hud, True, (245, 237, 223)), (11, 7))
        if state != "play":
            title = "YOU WIN!" if state == "win" else "YOU LOSE"
            label = big_font.render(title, True, (255, 245, 222))
            screen.blit(label, label.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2)))
            hint = font.render("Press R to restart", True, (255, 245, 222))
            screen.blit(hint, hint.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 42)))
        pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
