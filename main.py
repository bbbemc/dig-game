import random
import pygame

# ---------------- ตั้งค่า ----------------
CELL = 6          # ขนาด 1 ช่อง (พิกเซล)
CHAR = 5          # 1 ตัวอักษรในแผนที่ = 5x5 ช่อง
DIG_RADIUS = 3    # รัศมีการขุด (หน่วย: ช่อง)
FPS = 60

EMPTY, DIRT, ROCK, WATER, LAVA, STONE = range(6)
COLORS = {
    EMPTY: (45, 30, 22), DIRT: (110, 70, 45), ROCK: (60, 60, 65),
    WATER: (40, 140, 230), LAVA: (255, 110, 20), STONE: (140, 140, 145),
}
DIGGABLE = {DIRT}          # ภายหลังเพิ่ม STONE ได้ (ขุดหินสุ่ม skill)
FLUIDS = {WATER, LAVA}

# แผนที่แบบตัวอักษร: # ดิน, R หินขุดไม่ได้, W น้ำ, L ลาวา, P ผู้เล่น, E ศัตรู, เว้นวรรค = ว่าง
LEVEL_1 = [
    "RRRRRRRRRRRRRRRRRRRR",
    "R##################R",
    "R#########WWWW#####R",
    "R#########WWWW#####R",
    "R##################R",
    "R##################R",
    "R##################R",
    "R      ############R",
    "R P    ############R",
    "RRRRRRR############R",
    "R##################R",
    "R##LLLL############R",
    "R##LLLL############R",
    "R##################R",
    "R##################R",
    "R##########        R",
    "R##########   E    R",
    "RRRRRRRRRRRRRRRRRRRR",
]


def load_level(rows):
    w, h = len(rows[0]) * CHAR, len(rows) * CHAR
    grid = [[EMPTY] * w for _ in range(h)]
    ents = {}
    mapping = {"#": DIRT, "R": ROCK, "W": WATER, "L": LAVA}
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            t = mapping.get(ch, EMPTY)
            for y in range(r * CHAR, (r + 1) * CHAR):
                for x in range(c * CHAR, (c + 1) * CHAR):
                    grid[y][x] = t
            if ch in "PE":
                ents[ch] = pygame.Rect(c * CHAR, r * CHAR, CHAR, CHAR)  # หน่วย: ช่อง
    return grid, ents


def dig(grid, cx, cy):
    h, w = len(grid), len(grid[0])
    r2 = DIG_RADIUS * DIG_RADIUS
    for y in range(cy - DIG_RADIUS, cy + DIG_RADIUS + 1):
        for x in range(cx - DIG_RADIUS, cx + DIG_RADIUS + 1):
            if 0 <= x < w and 0 <= y < h and (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                if grid[y][x] in DIGGABLE:
                    grid[y][x] = EMPTY


def dig_line(grid, a, b):
    """ขุดตามเส้นระหว่างตำแหน่งเมาส์เฟรมก่อนกับเฟรมนี้ ไม่ให้รอยขุดขาดเป็นจุดๆ"""
    steps = max(abs(b[0] - a[0]), abs(b[1] - a[1]), 1)
    for i in range(steps + 1):
        dig(grid, a[0] + (b[0] - a[0]) * i // steps, a[1] + (b[1] - a[1]) * i // steps)


def step_fluids(grid, frame):
    h, w = len(grid), len(grid[0])
    moved = [[False] * w for _ in range(h)]
    xs = range(w) if frame % 2 == 0 else range(w - 1, -1, -1)
    for y in range(h - 2, -1, -1):          # วนจากล่างขึ้นบน
        row, below = grid[y], grid[y + 1]
        for x in xs:
            t = row[x]
            if t not in FLUIDS or moved[y][x]:
                continue
            # ลาวาเจอน้ำ -> กลายเป็นหิน
            if t == LAVA:
                hit = False
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == WATER:
                        grid[ny][nx] = STONE
                        hit = True
                if hit:
                    row[x] = STONE
                    continue
                if frame % 2:               # ลาวาไหลช้ากว่าน้ำ
                    continue
            # 1) ตกลงตรงๆ
            if below[x] == EMPTY:
                below[x], row[x] = t, EMPTY
                moved[y + 1][x] = True
                continue
            d = random.choice((-1, 1))
            done = False
            # 2) ไหลเฉียงลง
            for dx in (d, -d):
                nx = x + dx
                if 0 <= nx < w and below[nx] == EMPTY and row[nx] == EMPTY:
                    below[nx], row[x] = t, EMPTY
                    moved[y + 1][nx] = True
                    done = True
                    break
            if done:
                continue
            # 3) ไหลออกด้านข้าง
            for dx in (d, -d):
                nx = x + dx
                if 0 <= nx < w and row[nx] == EMPTY:
                    row[nx], row[x] = t, EMPTY
                    moved[y][nx] = True
                    break


def touches(grid, rect, kind):
    return any(grid[y][x] == kind
               for y in range(rect.top, rect.bottom)
               for x in range(rect.left, rect.right))


def to_screen(rect):
    return pygame.Rect(rect.x * CELL, rect.y * CELL, rect.w * CELL, rect.h * CELL)


def main():
    pygame.init()
    grid, ents = load_level(LEVEL_1)
    h, w = len(grid), len(grid[0])
    screen = pygame.display.set_mode((w * CELL, h * CELL))
    pygame.display.set_caption("Dig Game - prototype")
    small = pygame.Surface((w, h))
    font = pygame.font.SysFont(None, 40)
    clock = pygame.time.Clock()
    frame, state, last, hp = 0, "play", None, 100

    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_r:   # Retry
                grid, ents = load_level(LEVEL_1)
                state, hp = "play", 100

        # ขุดด้วยเมาส์ซ้าย
        if state == "play" and pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            cur = (mx // CELL, my // CELL)
            dig_line(grid, last or cur, cur)
            last = cur
        else:
            last = None

        step_fluids(grid, frame)
        frame += 1

        # เช็คแพ้/ชนะ
        slow = False
        if state == "play":
            p = ents["P"]
            if touches(grid, p, LAVA):
                hp, state = 0, "lose"
            elif touches(grid, p, WATER):
                slow = True                 # ไว้ใช้ตอนทำระบบเดินของผู้เล่น
            if "E" in ents and touches(grid, ents["E"], LAVA):
                del ents["E"]
                state = "win"

        # วาด
        pa = pygame.PixelArray(small)
        for y, row in enumerate(grid):
            for x, t in enumerate(row):
                pa[x, y] = COLORS[t]
        pa.close()
        screen.blit(pygame.transform.scale(small, screen.get_size()), (0, 0))
        if "P" in ents:
            pygame.draw.rect(screen, (90, 200, 255) if slow else (60, 220, 90), to_screen(ents["P"]))
        if "E" in ents:
            pygame.draw.rect(screen, (220, 40, 60), to_screen(ents["E"]))
        screen.blit(font.render(f"HP {hp}", True, (255, 255, 255)), (10, 8))
        if state != "play":
            msg = "YOU WIN!  (R = retry)" if state == "win" else "YOU LOSE  (R = retry)"
            img = font.render(msg, True, (255, 255, 255))
            screen.blit(img, img.get_rect(center=screen.get_rect().center))

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
