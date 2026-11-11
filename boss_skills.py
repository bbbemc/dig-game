"""The Abyssal Colossus's skills beyond its greatsword swing.

* Shockwave: every few swings (or when the miner keeps out of reach) the
  boss raises its sword high and slams it flat; a wave runs along the floor
  both ways. It cannot be parried: the miner jumps it or stands on a ledge.
* Leap slam: a miner who stays on a ledge too long is leapt on. The boss
  crouches (the warning), flies to where the miner stood and lands hard,
  hurting anyone under it and caving in the dirt of the ledge it lands on.
  Left up on a ledge (stone, or the rock ends of a caved-in one), it hops
  back down to the floor beside the miner with a shorter crouch.
* Phase 2: at BOSS_ENRAGE_HP health left it is enraged. It glows red,
  walks and attacks faster, and follows a parried-or-not swing with
  BOSS_ENRAGE_COMBO quicker ones (a parry for each, just in time).

The Game owns the boss and its swing (Game.update_melee); this module only
runs the extra moves, and tells the Game when the boss is busy with one
(no swing, no walking) or flying (no physics). Everything advances with the
game's dt, so pause and hitstop freeze it like every other attack.
"""

import math
import random

import pygame

from config import (CELL, MACRO, BOSS_SPEED, BOSS_FIGHT_GRACE, BOSS_QUAKE_EVERY,
                    BOSS_QUAKE_RANGE, BOSS_QUAKE_KITE, BOSS_QUAKE_WINDUP,
                    BOSS_QUAKE_RECOVER, BOSS_WAVE_SPEED, BOSS_WAVE_SIZE,
                    BOSS_WAVE_DAMAGE, BOSS_LEAP_DELAY, BOSS_LEAP_CROUCH, BOSS_LEAP_AIR,
                    BOSS_LEAP_RECOVER, BOSS_LEAP_DAMAGE, BOSS_LEAP_REACH,
                    BOSS_SKILL_COOLDOWN, BOSS_ENRAGE_HP, BOSS_ENRAGE_SPEED,
                    BOSS_ENRAGE_TEMPO, BOSS_WAVE_ECHO, TELEGRAPH_TIME)
from level import DIRT, EMPTY

LEDGE_HEIGHT = 1.5 * MACRO   # feet this far above the arena floor: on a ledge
WAVE_LIFE = 3.0              # s before a wave that met nothing dies out
LEAP_ARC = 170               # px the leap rises above the straight line
HOP_CROUCH = 0.45            # s of crouch before hopping down off a ledge
HOP_ARC = 90


class Shockwave:
    """A crest of rock and fire running along the floor; parry cannot stop it."""

    unparryable = True

    def __init__(self, x, floor_y, direction, speed):
        self.x, self.floor_y = float(x), floor_y
        self.direction, self.speed = direction, speed
        self.age = 0.0
        self.hit = False
        self.dead = False

    @property
    def rect(self):
        width, height = BOSS_WAVE_SIZE
        return pygame.Rect(round(self.x - width / 2), self.floor_y - height, width, height)

    @property
    def pos(self):
        return pygame.Vector2(self.x, self.floor_y - BOSS_WAVE_SIZE[1] / 2)


class BossSkills:
    def __init__(self, game, boss, floor_y, seed=5505):
        self.game, self.boss, self.floor_y = game, boss, floor_y
        self.random = random.Random(seed)
        self.state = None            # quake_windup / quake_recover / leap_crouch / leap_air / leap_land
        self.timer = self.length = 0.0
        self.cooldown = 0.0
        self.grace = 0.0
        self.swings = 0
        self.quota = self.random.choice(BOSS_QUAKE_EVERY)
        self.ledge_time = self.kite_time = 0.0
        self.waves = []
        self.leap = None             # (start, end) top-left positions of the flight
        self.target = None           # world (x, y) the leap will land on
        self.hop = False             # this leap only drops back to the floor
        self.enraged = False
        self.ember_clock = 0.0
        self.echo = None             # s until an enraged quake's second pair of waves
        boss.skill_pose = None
        boss.enraged = False

    # ---- what the Game asks -------------------------------------------------
    @property
    def tempo(self):
        """Multiplier on every attack duration: below 1 when enraged."""
        return 1 / BOSS_ENRAGE_TEMPO if self.enraged else 1.0

    @property
    def busy(self):
        """A skill (or the opening pause) has the boss: no swing, no walking."""
        return self.state is not None or self.grace > 0

    @property
    def airborne(self):
        return self.state == 'leap_air'

    def note_swing(self):
        """The Game started a greatsword swing (counts toward the next quake)."""
        self.swings += 1
        self.kite_time = 0.0

    def start_fight(self):
        """The gates shut: hold still a moment so the miner can get ready."""
        self.grace = BOSS_FIGHT_GRACE

    # ---- update -------------------------------------------------------------
    def update(self, dt):
        game, boss = self.game, self.boss
        self._update_waves(dt)
        if boss not in game.monsters:
            self.state, boss.skill_pose, self.waves, self.echo = None, None, [], None
            return
        if self.echo is not None:
            self.echo -= dt
            if self.echo <= 0:
                self.echo = None
                if boss.rect.bottom > self.floor_y - LEDGE_HEIGHT:
                    self._slam(echo=True)
        self._check_enrage()
        self.grace = max(0.0, self.grace - dt)
        self.cooldown = max(0.0, self.cooldown - dt)
        if game.stunned(boss) and self.state not in (None, 'leap_air'):
            self._end(cooldown=BOSS_SKILL_COOLDOWN)   # a stagger cancels a wind-up
        if self.state is not None:
            self._advance(dt)
            return
        if not self._fight_on() or self.grace > 0 or game.stunned(boss):
            self.ledge_time = self.kite_time = 0.0
            return
        self._track_miner(dt)
        if self.cooldown > 0 or getattr(boss, 'melee_state', None):
            return
        if self.ledge_time >= BOSS_LEAP_DELAY:
            self._begin('leap_crouch', BOSS_LEAP_CROUCH)
        elif self._wants_quake():
            self._begin('quake_windup', BOSS_QUAKE_WINDUP)

    def _fight_on(self):
        game = self.game
        if game.arena_lock_x is not None:
            return game.arena_locked
        return game._can_enemy_see_player(self.boss)

    def _on_ledge(self):
        player = self.game.player
        return player.grounded and player.rect.bottom <= self.floor_y - LEDGE_HEIGHT

    def _track_miner(self, dt):
        game, boss, player = self.game, self.boss, self.game.player.rect
        self.ledge_time = self.ledge_time + dt if self._on_ledge() else 0.0
        on_floor = player.bottom > self.floor_y - LEDGE_HEIGHT
        if (on_floor and not game._in_melee_reach(boss)
                and abs(player.centerx - boss.rect.centerx) <= BOSS_QUAKE_RANGE
                and game._can_enemy_see_player(boss)):
            self.kite_time += dt
        else:
            self.kite_time = 0.0

    def _wants_quake(self):
        game, player = self.game, self.game.player.rect
        if player.bottom <= self.floor_y - LEDGE_HEIGHT:
            return False                        # a wave cannot reach a ledge
        if abs(player.centerx - self.boss.rect.centerx) > BOSS_QUAKE_RANGE:
            return False
        if not game._can_enemy_see_player(self.boss):
            return False
        return self.swings >= self.quota or self.kite_time >= BOSS_QUAKE_KITE

    def _begin(self, state, seconds):
        self.state = state
        self.timer = self.length = seconds * (self.tempo if state != 'leap_air' else 1.0)
        self.game.last_combat = self.game.world_time
        self._pose()

    def _end(self, cooldown):
        self.state, self.boss.skill_pose = None, None
        self.cooldown = cooldown * self.tempo
        self.leap = self.target = None
        self.hop = False

    def _advance(self, dt):
        self.timer -= dt
        if self.state == 'leap_crouch':
            # The landing spot follows the miner until take-off.
            self.target = self._landing_spot()
        if self.state == 'leap_air':
            self._fly()
        if self.timer > 0:
            self._pose()
            return
        if self.state == 'quake_windup':
            self._slam()
            self._begin('quake_recover', BOSS_QUAKE_RECOVER)
        elif self.state == 'quake_recover':
            self.swings, self.kite_time = 0, 0.0
            self.quota = self.random.choice(BOSS_QUAKE_EVERY)
            self._end(BOSS_SKILL_COOLDOWN)
        elif self.state == 'leap_crouch':
            self._take_off()
        elif self.state == 'leap_air':
            self._land()
            self._begin('leap_land', BOSS_LEAP_RECOVER)
        elif self.state == 'leap_land':
            self.ledge_time = 0.0
            if self.boss.rect.bottom <= self.floor_y - LEDGE_HEIGHT:
                self.hop = True              # up on a ledge: hop back down
                self._begin('leap_crouch', HOP_CROUCH)
            else:
                self._end(BOSS_SKILL_COOLDOWN)

    def _pose(self):
        """The attack frames the sprite shows (enemy_sprites reads skill_pose)."""
        progress = 1 - max(0.0, self.timer) / max(1e-6, self.length)
        frame = {'quake_windup': 0 if progress < 0.5 else 1,
                 'quake_recover': 3 if progress < 0.4 else 4 + (progress > 0.7),
                 'leap_crouch': 0,
                 'leap_air': 1,
                 'leap_land': 3 if progress < 0.5 else 5}[self.state]
        self.boss.skill_pose = ('attack', frame)

    # ---- shockwave ----------------------------------------------------------
    def _slam(self, echo=False):
        """The sword hits flat: a wave each way (enraged, a second pair follows)."""
        game, boss = self.game, self.boss
        speed = BOSS_WAVE_SPEED * (1.15 if self.enraged else 1.0)
        floor = boss.rect.bottom
        for direction, x in ((-1, boss.rect.left + 10), (1, boss.rect.right - 10)):
            self.waves.append(Shockwave(x, floor, direction, speed))
            game.particles.dust(x, floor, 1.0)
        game.quake(0.5 if echo else 0.75)
        game.camera_kick(0.3, 5 if echo else 7, 0, 0)
        game.sounds.play('guard_break')
        if self.enraged and not echo:
            self.echo = BOSS_WAVE_ECHO

    def _update_waves(self, dt):
        game, world = self.game, self.game.world
        player = game.player.rect
        for wave in self.waves:
            wave.age += dt
            wave.x += wave.direction * wave.speed * dt
            front = wave.x + wave.direction * BOSS_WAVE_SIZE[0] / 2
            if (wave.age > WAVE_LIFE
                    or world.solid(math.floor(front / CELL), math.floor((wave.floor_y - 8) / CELL))
                    or not world.solid(math.floor(wave.x / CELL),
                                       math.floor((wave.floor_y + 2) / CELL))):
                wave.dead = True          # a wall, a pit or the end of its run
                game.particles.dust(wave.x, wave.floor_y, 0.6)
                continue
            if int(wave.age * 20) != int((wave.age - dt) * 20):
                game.particles.dust(wave.x, wave.floor_y, 0.35)
            if (not wave.hit and game.state == 'play' and wave.rect.colliderect(player)):
                wave.hit = True
                if game.hurt_timer <= 0:
                    edge = player.left if wave.direction > 0 else player.right
                    game.enemy_hit(BOSS_WAVE_DAMAGE, self.boss, (edge, player.bottom - 6))
        self.waves = [wave for wave in self.waves if not wave.dead]

    # ---- leap slam ----------------------------------------------------------
    def _landing_spot(self):
        """(x, ground y) under the miner: the ledge it stands on, or below it.
        A hop lands on the arena floor beneath the miner instead."""
        game, world = self.game, self.game.world
        player = game.player.rect
        x = player.centerx
        if self.hop:
            return x, self.floor_y
        y = player.bottom
        column = math.floor(x / CELL)
        row = math.floor(y / CELL)
        while row < world.height - 1 and not world.solid(column, row):
            row += 1
        return x, row * CELL

    def _take_off(self):
        boss = self.boss
        self.target = self._landing_spot()
        x, ground = self.target
        left = max(boss.chase_left, min(x - boss.size / 2, boss.chase_right))
        start = pygame.Vector2(boss.pos)
        end = pygame.Vector2(left, ground - boss.size)
        self.leap = (start, end)
        boss.velocity.update(0, 0)
        boss.knockback = 0.0
        self.game.particles.dust(boss.rect.centerx, boss.rect.bottom, 1.0)
        self.game.sounds.play('parry_whoosh')
        self._begin('leap_air', BOSS_LEAP_AIR * (0.75 if self.hop else 1.0))

    def _fly(self):
        start, end = self.leap
        t = 1 - max(0.0, self.timer) / max(1e-6, self.length)
        rise = max(0.0, start.y - end.y) + (HOP_ARC if self.hop else LEAP_ARC)
        self.boss.pos.x = start.x + (end.x - start.x) * t
        self.boss.pos.y = start.y + (end.y - start.y) * t - 4 * rise * t * (1 - t)
        self.boss._sync_rect()

    def _land(self):
        game, boss, world = self.game, self.boss, self.game.world
        _, end = self.leap
        boss.pos.update(end)
        boss._sync_rect()
        boss.velocity.update(0, 0)
        # The dirt it lands on caves in (rock and stone hold).
        foot = boss.rect
        removed = []
        for cy in range(foot.bottom // CELL, (foot.bottom + MACRO) // CELL):
            for cx in range(foot.left // CELL, (foot.right - 1) // CELL + 1):
                if 0 <= cx < world.width and 0 <= cy < world.height:
                    i = world.index(cx, cy)
                    if world.foreground[i] == DIRT:
                        world.set_terrain(i, EMPTY)
                        removed.append(i)
        if removed:
            game.particles.dirt(world, removed, game.renderer.debris_colors)
            gold = getattr(game, 'gold_system', None)
            if gold is not None:
                gold.dug(removed)
        if boss.overlaps_terrain():
            boss._find_clear_position()
            boss._sync_rect()
        for side in (-1, 1):
            game.particles.dust(boss.rect.centerx + side * boss.size // 3, boss.rect.bottom, 1.0)
        game.quake(0.9)
        game.camera_kick(0.35, 9, 0, 0)
        game.sounds.play('guard_break')
        player = game.player.rect
        if (game.state == 'play' and game.hurt_timer <= 0
                and boss.rect.inflate(2 * BOSS_LEAP_REACH, 8).colliderect(player)):
            side = 1 if player.centerx >= boss.rect.centerx else -1
            game.enemy_hit(BOSS_LEAP_DAMAGE, boss, (player.centerx, player.bottom - 6))
            game.player.knockback = side * 260.0

    # ---- phase 2 --------------------------------------------------------------
    def _check_enrage(self):
        boss = self.boss
        if self.enraged or boss.hp > BOSS_ENRAGE_HP:
            return
        self.enraged = boss.enraged = True
        boss.speed = BOSS_SPEED * BOSS_ENRAGE_SPEED
        game = self.game
        x, y = boss.rect.center
        game.fx.enemy_break(x, y, True)
        game.fx.popup('ENRAGED!', x, boss.rect.top - 24, (255, 70, 48), 1.4)
        game.quake(0.8)
        game.sounds.play('enemy_guard_break')

    # ---- telegraphs, light and drawing ---------------------------------------
    def threats(self):
        """(side, seconds, source) the HUD warns of: waves on course and the
        moments a quake or a leap lands. Also marks the boss's telegraph_eta."""
        game, boss = self.game, self.boss
        player = game.player.rect
        threats = []
        for wave in self.waves:
            if wave.hit or player.bottom <= wave.floor_y - BOSS_WAVE_SIZE[1]:
                continue
            gap = (player.left - wave.rect.right if wave.direction > 0
                   else wave.rect.left - player.right)
            if gap < 0:
                continue
            eta = gap / wave.speed
            if eta <= TELEGRAPH_TIME:
                threats.append((-wave.direction, eta, wave))
        if self.state in ('quake_windup', 'leap_crouch', 'leap_air'):
            left = self.timer + (BOSS_LEAP_AIR if self.state == 'leap_crouch' else 0.0)
            if left <= TELEGRAPH_TIME:
                prev = getattr(boss, 'telegraph_eta', None)
                boss.telegraph_eta = left if prev is None else min(prev, left)
        return threats

    def lights(self):
        boss = self.boss
        if self.enraged and boss in self.game.monsters:
            yield ('lava', boss.rect.centerx, boss.rect.centery, round(boss.size * 1.4),
                   (255, 64, 36), 1)
        for wave in self.waves:
            yield ('lava', round(wave.x), wave.floor_y - 10, 96, (255, 120, 50), 2)

    def emit(self, dt):
        """Embers rising off an enraged boss."""
        if not self.enraged or self.boss not in self.game.monsters:
            return
        self.ember_clock += dt
        rect, rnd = self.boss.rect, self.random
        while self.ember_clock >= 0.06:
            self.ember_clock -= 0.06
            self.game.particles.ember(rnd.uniform(rect.left + 20, rect.right - 20),
                                      rnd.uniform(rect.top + 20, rect.bottom - 10))

    @staticmethod
    def _draw_wave(screen, wave, x, base, time):
        """A burning crest of broken rock (taller than its hitbox, which a
        jump clears) and the scorched glow it leaves along the floor."""
        add = pygame.BLEND_RGB_ADD
        back = -wave.direction
        fade = max(0.0, min(1.0, (WAVE_LIFE - wave.age) / 0.4))
        for n in range(8):                         # the trail: glowing floor behind
            k = (1 - n / 8) * fade
            screen.fill((round(150 * k), round(52 * k), round(14 * k)),
                        (x + back * (10 + n * 9) - 5, base - 4, 10, 4), special_flags=add)
        width, height = BOSS_WAVE_SIZE
        tall = height + 14
        for n, (scale, color) in enumerate(((1.0, (110, 26, 12)), (0.78, (236, 96, 32)),
                                            (0.5, (255, 200, 110)), (0.26, (255, 246, 214)))):
            sway = math.sin(time * 38 + wave.x * 0.13 + n) * 3
            w, h = (width + 10) * scale, tall * scale * (0.92 + 0.08 * math.sin(time * 50 + n))
            tip = x + back * w * 0.25 + sway * scale
            points = [(x + back * w, base), (x - back * w * 0.35, base),
                      (tip + back * w * 0.1, base - h), (x + back * w * 0.55, base - h * 0.55),
                      (x + back * w * 0.7, base - h * 0.75)]
            pygame.draw.polygon(screen, color, points)
        for n in range(3):                         # chips of rock thrown up ahead of it
            phase = (time * 6 + n * 0.37 + wave.x * 0.01) % 1.0
            px = x - back * (4 + n * 5)
            py = base - round(10 + 26 * math.sin(phase * math.pi))
            screen.fill((70, 52, 46), (px, py, 3, 3))
        glow = pygame.Rect(0, 0, width * 3, 8)
        glow.midbottom = (x, base)
        screen.fill((80, 30, 8), glow, special_flags=add)

    def draw(self, screen, camera, time):
        """Waves and the leap's landing mark (emissive: after the light map)."""
        cx, cy = camera
        for wave in self.waves:
            self._draw_wave(screen, wave, round(wave.x - cx), wave.floor_y - cy, time)
        if self.state in ('leap_crouch', 'leap_air') and self.target is not None:
            x, ground = self.target
            x, y = round(x - cx), round(ground - cy)
            pulse = int(time * 16) % 2
            color = (255, 236, 200) if pulse else (240, 60, 40)
            half = self.boss.size // 2
            pygame.draw.line(screen, color, (x - half, y - 1), (x + half, y - 1), 2)
            for side in (-1, 1):
                pygame.draw.line(screen, color, (x + side * half, y - 1),
                                 (x + side * (half - 8), y - 9), 2)
            pygame.draw.polygon(screen, color, [(x, y - 6), (x - 6, y - 16), (x + 6, y - 16)])
