"""Dig Game: grounded exploration, permanent cave walls and fixed-step liquids."""
import argparse
import gc
import json
import math
import os
import time
from pathlib import Path

pygame = None
EMPTY = WATER = LAVA = None

from config import (CELL, SCALE, MACRO, SCREEN_W, SCREEN_H, FPS, PHYSICS_HZ,
                    FLUID_HZ, MAX_FRAME_DT, DIG_RADIUS)
from config import (PRECISE_FRAME_PACING, CAMERA_FOLLOW, SHAKE_DECAY, MOTE_LIMIT,
                    EMBER_INTERVAL)
from config import (ENEMY_SIGHT_RANGE, ENEMY_FIRE_INTERVAL, PROJECTILE_SPEED,
                    PROJECTILE_DAMAGE, PROJECTILE_RADIUS)
from combat import tick_enemy
from config import (WALKER_SIZE, WALKER_SPEED, WALKER_PATROL_RANGE,
                    WALKER_CHASE_MEMORY, ENEMY_CONTACT_DAMAGE,
                    WALKER_CONTACT_DAMAGE)
from config import (OXYGEN_DRAIN_TIME, OXYGEN_REFILL_TIME, OXYGEN_DAMAGE,
                    OXYGEN_DAMAGE_INTERVAL)
from config import (BOSS_SIZE, BOSS_SPEED, BOSS_HP, BOSS_CONTACT_DAMAGE,
                    ENEMY_ACTIVE_RANGE)
from config import (PARRY_STUN_DURATION, PARRY_KNOCKBACK, PARRY_KNOCKBACK_LIFT,
                    PARRY_HITSTOP, PARRY_FRONT_TOLERANCE, PARRY_SHAKE_TIME,
                    PARRY_SHAKE_PX, PARRY_PERFECT_TIME, PERFECT_PARRY_HITSTOP,
                    PERFECT_SHAKE_TIME, PERFECT_SHAKE_PX, PERFECT_RECOIL_PX)
from config import (GUARD_BREAK_HITSTOP, GUARD_BREAK_SHAKE_TIME, GUARD_BREAK_SHAKE_PX,
                    GUARD_BREAK_KNOCKBACK, ENEMY_BREAK_HITSTOP, ENEMY_STUN_DURATION,
                    BOSS_STAGGER_DURATION, DEATHBLOW_REACH, COMBAT_RANGE)

STAGE_NAMES = {
    1: 'ABANDONED MINE',
    2: 'THE SINKING MINE',
    3: 'DIRT CAVERNS',
    4: 'WATER CHAMBER',
    5: 'THE SINKING MINE',
    6: 'THE DEEP DESCENT',
}


def _ensure_pygame():
    global pygame
    if pygame is None:
        import pygame as _pygame
        pygame = _pygame
    return pygame


def jump_requested(key, on_ladder):
    """W/Up climbs a ladder; Space jumps even while attached to one."""
    _ensure_pygame()
    return key == pygame.K_SPACE or (key in (pygame.K_w, pygame.K_UP)
                                    and not on_ladder)


def _ensure_runtime_modules():
    _ensure_pygame()
    from level import build_level, validate_level, EMPTY, WATER, LAVA
    from world import World
    from physics import Player, Actor
    from liquids import LiquidSystem
    from tiles import TileArt
    from rendering import WorldRenderer
    from effects import Particles
    from lighting import Lighting
    from actors import MinerSprite
    globals()['EMPTY'] = EMPTY
    globals()['WATER'] = WATER
    globals()['LAVA'] = LAVA
    return {
        'build_level': build_level,
        'validate_level': validate_level,
        'WATER': WATER,
        'LAVA': LAVA,
        'EMPTY': EMPTY,
        'World': World,
        'Player': Player,
        'Actor': Actor,
        'LiquidSystem': LiquidSystem,
        'TileArt': TileArt,
        'WorldRenderer': WorldRenderer,
        'Particles': Particles,
        'Lighting': Lighting,
        'MinerSprite': MinerSprite,
    }


class Projectile:
    def __init__(self, position, velocity, owner=None):
        self.pos = pygame.Vector2(position)
        self.velocity = pygame.Vector2(velocity)
        self.owner = owner      # the shooter, which a parry stuns
        self.parryable = True


class Game:
    def __init__(self, art, lighting=None, bombs=False, stage=1, seed=None):
        # The previous level's objects become collectable again (see below).
        gc.unfreeze()
        runtime = _ensure_runtime_modules()
        build_level = runtime['build_level']
        validate_level = runtime['validate_level']
        World = runtime['World']
        Player = runtime['Player']
        Actor = runtime['Actor']
        LiquidSystem = runtime['LiquidSystem']
        WorldRenderer = runtime['WorldRenderer']
        Particles = runtime['Particles']
        Lighting = runtime['Lighting']
        MinerSprite = runtime['MinerSprite']
        from combat import PlayerCombat, give_posture
        rows, entities, scenery, self.optional_rooms = build_level(stage, seed)
        self.stage_number = stage
        self.stage_name = STAGE_NAMES[stage]
        # Generated worlds carry their seed (restart keeps the same layout)
        # and layer bands; authored stages have neither.
        self.seed = scenery.get('seed')
        self.layers = scenery.get('layers')
        self.density = validate_level(rows, entities,
                                      allow_lava_route=(stage == 5), size=None)
        # The authored opening map of stages 1-5 (macro box) and its old door,
        # which is now the gate into the large world.
        self.chamber = scenery.get('chamber')
        gate = scenery.get('chamber_gate')
        self.chamber_gate = (pygame.Rect(gate[0] * MACRO, gate[1] * MACRO,
                                         gate[2] * MACRO, gate[3] * MACRO) if gate else None)
        self.world = World(rows)
        self.world.sculpt(scenery.get('sculpt', {}))
        self.liquids = LiquidSystem(self.world)
        self.renderer = WorldRenderer(self.world, art, scenery)
        self.lighting = lighting or Lighting((SCREEN_W, SCREEN_H))
        self.lighting.band_rows = self.layers['rows'] if self.layers else 25
        x,y = entities['P'][0]
        self.player = Player(self.world,x*MACRO,y*MACRO)
        self.player.drop_to_ground()
        self.monsters = []
        enemy_spawn_offsets = scenery.get('enemy_spawn_offsets', {}).get('M', ())
        for n,(x,y) in enumerate(entities['M']):
            offset_x, offset_y = (enemy_spawn_offsets[n]
                                  if n < len(enemy_spawn_offsets) else (0, 0))
            actor = Actor(self.world,x*MACRO+offset_x,y*MACRO+offset_y,
                          size=24,speed=32)
            actor.drop_to_ground()
            actor.shot_cooldown = 0.0
            actor.shoots_projectiles = True
            actor.contact_damage = ENEMY_CONTACT_DAMAGE
            actor.in_chamber = self.in_chamber(x, y)
            give_posture(actor)
            self.monsters.append(actor)
        for x, y in entities['G']:
            actor = Actor(self.world, x * MACRO, y * MACRO,
                          size=WALKER_SIZE, speed=WALKER_SPEED)
            actor.drop_to_ground()
            actor.shoots_projectiles = False
            actor.contact_damage = WALKER_CONTACT_DAMAGE
            actor.patrol_left = max(0, x * MACRO - WALKER_PATROL_RANGE)
            actor.patrol_right = min(self.world.pixel_width - actor.size,
                                     x * MACRO + WALKER_PATROL_RANGE)
            actor.patrol_direction = 1
            actor.chase_left = max(0, actor.patrol_left - WALKER_PATROL_RANGE)
            actor.chase_right = min(self.world.pixel_width - actor.size,
                                    actor.patrol_right + WALKER_PATROL_RANGE)
            actor.chase_timer = 0.0
            actor.in_chamber = self.in_chamber(x, y)
            give_posture(actor)
            self.monsters.append(actor)
        self.boss = None
        for x, y in entities.get('B', ()):
            self.boss = self._make_boss(x, y, scenery['boss_arena'],
                                        scenery.get('boss_hp', BOSS_HP))
            self.monsters.append(self.boss)
        door_x, door_y, door_w, door_h = scenery['exit_door']
        self.exit_door = pygame.Rect(door_x * MACRO, door_y * MACRO,
                                     door_w * MACRO, door_h * MACRO)
        self.projectiles = []
        from bombs import BombSystem
        self.bombs = BombSystem(self, scenery.get('bomb_spawns', ()),
                                self.stage_number, force=bombs,
                                count=scenery.get('bomb_count'),
                                fixed=scenery.get('bomb_fixed', ()))
        self.particles = Particles()
        self.miner = MinerSprite()
        self.hp, self.oxygen, self.state = 100, 100.0, 'play'
        from audio import sounds
        from parry_fx import CombatEffects
        self.combat = PlayerCombat()  # parry, posture and guard-break stun
        self.parry_facing = True    # facing held from the press (True = right)
        self.hitstop = 0.0          # combat freeze after a clash or a break
        self.kick = None            # [left, duration, px, direction, recoil px] camera kick
        self.engaged = False        # a fight is on nearby (drives the posture bar)
        self.last_combat = -99.0    # world_time of the last parry, hit or attack
        self.perfect_parries = 0
        self.fx = CombatEffects()   # flashes, streaks, shockwaves, popups
        self.sounds = sounds()
        self.oxygen_damage_timer = 0.0
        self.physics_accumulator = self.fluid_accumulator = self.world_time = 0.0
        self.hurt_timer = 0.0
        self.jump_pending = False
        self.last_dig = None
        self.dig_x = None
        # Presentation only: a smoothed view, trauma-based shake, emitters.
        self.view = pygame.Vector2(self.camera())
        self.render_camera = self.camera()
        self.shake = self.view_time = 0.0
        self.was_swimming = False
        self.reactions_seen = 0
        self.ember_clock = self.mote_clock = 0.0
        self.draw_calls = 0
        self.metrics = {'physics_ms':0.,'fluid_ms':0.,'particles_ms':0.,'render_ms':0.}
        # A large world holds hundreds of thousands of long-lived objects.
        # Freezing them keeps periodic full collections from walking the
        # whole level, which otherwise caused ~20 ms hitches mid-play.
        gc.collect()
        gc.freeze()

    def in_chamber(self, x, y):
        """Whether macro (x, y) lies in the stage's authored opening map."""
        box = self.chamber
        return bool(box) and box[0] <= x <= box[2] and box[1] <= y <= box[3]

    @property
    def chamber_monsters(self):
        return [enemy for enemy in self.monsters if getattr(enemy, 'in_chamber', False)]

    def _make_boss(self, x, y, arena, hp=BOSS_HP):
        """A heavy walker confined to its arena; lava or ``hp`` bombs end it."""
        Actor = _ensure_runtime_modules()['Actor']
        boss = Actor(self.world, x * MACRO, y * MACRO, size=BOSS_SIZE, speed=BOSS_SPEED)
        boss.drop_to_ground()
        boss.shoots_projectiles = False
        boss.contact_damage = BOSS_CONTACT_DAMAGE
        boss.hp = boss.max_hp = hp
        boss.hurt_timer, boss.is_boss, boss.in_chamber = 0.0, True, False
        from combat import give_posture
        give_posture(boss, boss=True)
        x0, _, x1, _ = arena
        boss.patrol_left = boss.chase_left = (x0 + 2) * MACRO
        boss.patrol_right = boss.chase_right = (x1 + 1) * MACRO - BOSS_SIZE
        boss.patrol_direction = 1
        boss.chase_timer = 0.0
        return boss

    # ------------------------------------------------------------------
    # Combat (E): parry.py times the window, combat.py holds posture and the
    # player's state. The Game resolves hits and owns every consequence.
    # ------------------------------------------------------------------
    @property
    def parry(self):
        return self.combat.parry

    @property
    def combat_state(self):
        from combat import DEAD
        return DEAD if self.state == 'lose' else self.combat.state

    def can_act(self):
        """Whether the player may move, jump, parry, dig or throw right now."""
        return self.state == 'play' and self.combat.can_act()

    def press_e(self):
        """E: finish a guard-broken enemy in reach, otherwise parry."""
        if not self.can_act():
            return False
        target = self.deathblow_target()
        if target is not None:
            self.deathblow(target)
            return True
        return self.start_parry()

    def start_parry(self):
        """Open the parry window if the parry is ready (and the guard intact)."""
        if self.state != 'play' or not self.combat.start_parry():
            return False
        self.parry_facing = self.miner.facing_right
        self.miner.guarding = True
        self.miner.parry_time = 0.0      # anticipation, then the guard pose
        self.sounds.play('parry_whoosh')
        return True

    def _deflects(self, attacker, source_x):
        """Whether an enemy attack from world x ``source_x`` is parried now.

        Only enemy attacks reach this; lava, drowning and bomb blasts never do.
        The attack must arrive from the side the player faced on pressing E
        (a few pixels behind the centre still count, for hits from above).
        """
        if not self.parry.is_active() or not getattr(attacker, 'parryable', True):
            return False
        centre = self.player.rect.centerx
        if self.parry_facing:
            return source_x >= centre - PARRY_FRONT_TOLERANCE
        return source_x <= centre + PARRY_FRONT_TOLERANCE

    def camera_kick(self, duration, pixels, direction=0, recoil=0):
        """A short shake that eases back to rest; a weaker one never overrides.

        ``recoil`` px also pushes the view along ``direction`` and back.
        """
        if self.kick is not None:
            left, length, strength, _, _ = self.kick
            if strength * (left / length) ** 2 > pixels:
                return
        self.kick = [duration, duration, pixels, direction, recoil]

    def handle_successful_parry(self, attacker, point):
        """A successful deflect: no damage or posture for the player, layered
        clash effects, and a stunned, knocked-back attacker that gains posture.

        A hit landing within PARRY_PERFECT_TIME of the press is a perfectly
        timed parry: the same rules, with a bigger flash, slash, spark burst,
        hitstop, camera recoil and its own sound.
        """
        first = not self.parry.deflecting      # once per frame for the feedback
        perfect = self.parry.elapsed <= PARRY_PERFECT_TIME + 1e-9
        self.parry.succeed()
        self.last_combat = self.world_time
        facing = 1 if self.parry_facing else -1
        x, y = point
        broke = False
        if attacker is not None and attacker in self.monsters:
            broke = self._parried(attacker, facing)
        if not first:
            return
        rect = self.player.rect
        self.fx.parry(x, y, facing, perfect)
        self.miner.flash = 0.16
        self.miner.recoil = 0.12
        if perfect:
            self.perfect_parries += 1
            self.hitstop = max(self.hitstop, PERFECT_PARRY_HITSTOP)
            self.camera_kick(PERFECT_SHAKE_TIME, PERFECT_SHAKE_PX, -facing, PERFECT_RECOIL_PX)
            self.fx.popup('PERFECT!', rect.centerx, rect.top - 6, (255, 214, 92))
        else:
            self.hitstop = max(self.hitstop, PARRY_HITSTOP)
            self.camera_kick(PARRY_SHAKE_TIME, PARRY_SHAKE_PX, -facing)
            self.fx.popup('PARRY!', rect.centerx, rect.top - 6, (255, 236, 150))
        if not broke:      # a breaking guard has its own clash-and-break sound
            self.sounds.play('parry_perfect' if perfect else 'parry_clash')

    def _parried(self, enemy, facing):
        side = (enemy.rect.centerx > self.player.rect.centerx) - \
               (enemy.rect.centerx < self.player.rect.centerx) or facing
        posture = getattr(enemy, 'posture', None)
        broke = False
        if not getattr(enemy, 'broken', False):   # a broken guard has nothing left
            enemy.stun_timer = max(getattr(enemy, 'stun_timer', 0.0), PARRY_STUN_DURATION)
            enemy.chase_timer = 0.0
            if enemy.shoots_projectiles:
                enemy.shot_cooldown = max(enemy.shot_cooldown, PARRY_STUN_DURATION)
            broke = posture is not None and posture.add(1)
        # The boss barely moves; a breaking guard only staggers, staying in reach.
        weight = min(1.0, WALKER_SIZE / enemy.size) * (0.35 if broke else 1.0)
        enemy.knockback = side * PARRY_KNOCKBACK * weight
        enemy.velocity.y = -PARRY_KNOCKBACK_LIFT * weight
        enemy.grounded = False
        if broke:
            self.enemy_guard_break(enemy, side)
        return broke

    def enemy_guard_break(self, enemy, side=1):
        """Enemy posture full: a long stun (bosses only stagger) and big feedback."""
        boss = getattr(enemy, 'is_boss', False)
        enemy.broken = True
        enemy.stun_timer = BOSS_STAGGER_DURATION if boss else ENEMY_STUN_DURATION
        enemy.chase_timer = 0.0
        if enemy.shoots_projectiles:   # its attack is cancelled; aim starts over
            enemy.shot_cooldown = ENEMY_FIRE_INTERVAL
        x, y = enemy.rect.center
        self.fx.enemy_break(x, y, boss)
        self.fx.popup('STAGGER!' if boss else 'BREAK!', enemy.rect.centerx,
                      enemy.rect.top - 24, (255, 150, 60), 0.9)
        self.hitstop = max(self.hitstop, ENEMY_BREAK_HITSTOP)
        self.camera_kick(GUARD_BREAK_SHAKE_TIME * 0.8, GUARD_BREAK_SHAKE_PX - 2, side, 3)
        self.sounds.play('enemy_guard_break')

    def deathblow_target(self):
        """The nearest guard-broken normal enemy within reach, if any."""
        reach = self.player.rect.inflate(DEATHBLOW_REACH * 2, 16)
        targets = [enemy for enemy in self.monsters
                   if getattr(enemy, 'broken', False) and not getattr(enemy, 'is_boss', False)
                   and reach.colliderect(enemy.rect)]
        return min(targets, default=None,
                   key=lambda enemy: abs(enemy.rect.centerx - self.player.rect.centerx))

    def deathblow(self, enemy):
        """Finish a guard-broken enemy (never a boss: lava and bombs end those)."""
        self.monsters = [other for other in self.monsters if other is not enemy]
        self.miner.facing_right = self.parry_facing = \
            enemy.rect.centerx >= self.player.rect.centerx
        side = 1 if self.parry_facing else -1
        x, y = enemy.rect.center
        self.fx.deathblow(x, y)
        self.fx.popups.clear()             # the finisher's word stands alone
        self.fx.popup('DEATHBLOW!', x, enemy.rect.top - 24, (240, 70, 56), 0.9)
        self.hitstop = max(self.hitstop, ENEMY_BREAK_HITSTOP)
        self.camera_kick(GUARD_BREAK_SHAKE_TIME, GUARD_BREAK_SHAKE_PX - 2, side, 3)
        self.last_combat = self.world_time
        self.miner.flash = 0.12
        self.miner.recoil = 0.12
        self.sounds.play('deathblow')

    def enemy_hit(self, damage, attacker, point):
        """A parryable enemy attack got through the guard (a failed defence).

        HP damage as before, plus one posture point; the third breaks the
        guard. Death overrides: a lethal hit ends the game, not the guard.
        """
        self.hp -= damage
        self.hurt_timer = 0.8
        self.last_combat = self.world_time
        if self.hp <= 0:
            self.state = 'lose'
            self.combat.die()
            return
        x, y = point
        side = 1 if x >= self.player.rect.centerx else -1
        self.particles.thud(x, y, side)    # chips fly back toward the attacker
        result = self.combat.take_hit()
        if result == 'guard_break':
            self.player_guard_break(side, attacker)
            return
        self.sounds.play('parry_failed')
        if result == 'posture':
            self.sounds.play('posture_damage')   # the guard straining

    def player_guard_break(self, side, attacker=None):
        """Posture full: the guard shatters and the miner is stunned.

        The blow that broke it also bounces a touching attacker back, so the
        stun is a dangerous opening rather than a certain death.
        """
        rect = self.player.rect
        if (attacker is not None and attacker in self.monsters
                and rect.inflate(16, 16).colliderect(attacker.rect)):
            weight = min(1.0, WALKER_SIZE / attacker.size)
            attacker.knockback = side * PARRY_KNOCKBACK * 0.8 * weight
            attacker.velocity.y = -PARRY_KNOCKBACK_LIFT * 0.6 * weight
            attacker.grounded = False
        # A strong backward stagger: physics moves the miner, input stays locked.
        self.player.knockback = -side * GUARD_BREAK_KNOCKBACK
        self.hitstop = max(self.hitstop, GUARD_BREAK_HITSTOP)
        self.camera_kick(GUARD_BREAK_SHAKE_TIME, GUARD_BREAK_SHAKE_PX, -side, 4)
        self.fx.guard_break(rect.centerx, rect.centery)
        self.fx.popup('POSTURE BROKEN!', rect.centerx, rect.top - 6, (255, 112, 72), 1.2)
        self.miner.break_flash = 0.3
        self.miner.guarding = False
        self.miner.pose = 'recoil'
        self.jump_pending = False
        self.last_dig = None
        self.sounds.play('guard_break')

    def _update_combat(self, dt):
        """Player combat timers (start of a frame) and the miner's pose."""
        from combat import GUARD_BROKEN, PARRY_ACTIVE, STUNNED
        for event in self.combat.update(dt):
            if event == 'recovered':
                self.sounds.play('stun_recover')
                self.miner.recovering = 0.25      # back on guard
        state = self.combat.state
        self.miner.guarding = state == PARRY_ACTIVE
        self.miner.pose = {GUARD_BROKEN: 'recoil', STUNNED: 'stagger'}.get(state)

    @staticmethod
    def stunned(enemy):
        return getattr(enemy, 'stun_timer', 0.0) > 0

    def scan_combat(self):
        """Whether a fight is on: a hunting enemy, a shooter with a clear shot,
        a staggered foe or an enemy shot close to the player."""
        range_x, range_y = COMBAT_RANGE
        px, py = self.player.rect.center
        for enemy in self.monsters:
            if abs(enemy.rect.centerx - px) > range_x or abs(enemy.rect.centery - py) > range_y:
                continue
            if (self.stunned(enemy) or getattr(enemy, 'chase_timer', 0) > 0
                    or getattr(enemy, 'is_boss', False)):
                return True
            if enemy.shoots_projectiles and self._can_enemy_see_player(enemy):
                return True
        return any(abs(shot.pos.x - px) <= range_x and abs(shot.pos.y - py) <= range_y
                   for shot in self.projectiles)

    def layer_at(self, y):
        """1-based layer number for a world-pixel height (1 on authored stages)."""
        if not self.layers:
            return 1
        row = y // MACRO
        return 1 + sum(row >= top for top in self.layers['tops'][1:])

    def _enemy_active(self, enemy):
        """Distant enemies pause; only the area around the player is simulated."""
        range_x, range_y = ENEMY_ACTIVE_RANGE
        return (abs(enemy.rect.centerx - self.player.rect.centerx) <= range_x
                and abs(enemy.rect.centery - self.player.rect.centery) <= range_y)

    def touches(self, rect, kind):
        for y in range(max(0,rect.top//CELL), min(self.world.height,(rect.bottom-1)//CELL+1)):
            for x in range(max(0,rect.left//CELL), min(self.world.width,(rect.right-1)//CELL+1)):
                i = self.world.index(x,y)
                if self.liquids.types.get(i) == kind and self.liquids.mass.get(i,0) > .06:
                    # A partial cell only touches the actor below its surface.
                    surface = (y+1)*CELL-min(1,self.liquids.mass[i])*CELL
                    if rect.bottom > surface:
                        return True
        return False

    def fully_submerged(self, rect):
        """Whether water covers every point of a pixel rectangle."""
        left, right = rect.left // CELL, (rect.right - 1) // CELL
        top, bottom = rect.top // CELL, (rect.bottom - 1) // CELL
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                if not (0 <= x < self.world.width and 0 <= y < self.world.height):
                    return False
                index = self.world.index(x, y)
                mass = self.liquids.mass.get(index, 0.0)
                if self.liquids.types.get(index) != WATER or mass <= 0.06:
                    return False
                surface = (y + 1) * CELL - min(1.0, mass) * CELL
                if surface > max(rect.top, y * CELL):
                    return False
        return True

    def update_oxygen(self, dt):
        """Drain while fully submerged; recover in air and drown at zero."""
        if not dt:
            return
        if self.fully_submerged(self.player.rect):
            time_to_empty = self.oxygen * OXYGEN_DRAIN_TIME / 100
            self.oxygen = max(0.0, self.oxygen - 100 * dt / OXYGEN_DRAIN_TIME)
            self.oxygen_damage_timer += max(0.0, dt - time_to_empty)
            while self.oxygen_damage_timer + 1e-9 >= OXYGEN_DAMAGE_INTERVAL:
                self.oxygen_damage_timer = max(
                    0.0, self.oxygen_damage_timer - OXYGEN_DAMAGE_INTERVAL)
                self.hp = max(0, self.hp - OXYGEN_DAMAGE)
                if self.hp == 0:
                    self.state = 'lose'
                    break
        else:
            self.oxygen = min(100.0, self.oxygen + 100 * dt / OXYGEN_REFILL_TIME)
            self.oxygen_damage_timer = 0.0

    def camera(self):
        """Target view: the player centred, clamped to the world."""
        return (round(max(0,min(self.player.pos.x+self.player.size/2-SCREEN_W/2,
                                self.world.pixel_width-SCREEN_W))),
                round(max(0,min(self.player.pos.y+self.player.size/2-SCREEN_H/2,
                                self.world.pixel_height-SCREEN_H))))

    def follow_camera(self, dt):
        """Ease the drawn view toward the target; shake only on big events."""
        target = pygame.Vector2(self.camera())
        if (target - self.view).length() > SCREEN_W:
            self.view.update(target)  # restarts and teleports cut, not pan
        else:
            self.view += (target - self.view) * (1 - math.exp(-CAMERA_FOLLOW * dt))
        self.view_time += dt
        self.shake = max(0.0, self.shake - SHAKE_DECAY * dt)
        jolt = self.shake * self.shake * 4
        kick_x, kick_y = self.kick_offset(dt)
        x = round(self.view.x + math.sin(self.view_time * 47) * jolt + kick_x)
        y = round(self.view.y + math.cos(self.view_time * 41) * jolt + kick_y)
        self.render_camera = (max(0, min(x, self.world.pixel_width - SCREEN_W)),
                              max(0, min(y, self.world.pixel_height - SCREEN_H)))

    def kick_offset(self, dt):
        """Pixels of camera kick: starts toward the hit, swings back, settles.

        A smooth decaying wave (no noise), so it cannot jitter, and the base
        view is never moved: the camera is exactly at rest when it ends.
        """
        if self.kick is None:
            return 0.0, 0.0
        self.kick[0] -= dt
        left, length, pixels, direction, recoil = self.kick
        if left <= 0:
            self.kick = None
            return 0.0, 0.0
        elapsed = length - left
        envelope = pixels * (left / length) ** 2
        wave = math.cos(elapsed * 2 * math.pi * 16)
        # Recoil: out along the attack in the first quarter, eased back after.
        t = elapsed / length
        push = (math.sin(t / 0.25 * math.pi / 2) if t < 0.25
                else 0.5 + 0.5 * math.cos((t - 0.25) / 0.75 * math.pi))
        return (envelope * wave * (direction or 1) + recoil * push * (direction or 1),
                envelope * 0.45 * math.sin(elapsed * 2 * math.pi * 21))

    def excavate(self, target):
        if not self.combat.can_act():
            self.last_dig = None   # a broken guard cannot dig
            return
        self.dig_x = target[0]*CELL+CELL//2
        start = self.last_dig or target
        removed = self.world.dig_line(start,target,DIG_RADIUS)
        self.particles.dirt(self.world,removed,self.renderer.debris_colors)
        self.last_dig = target

    def update_stage_progress(self):
        self.monsters = [enemy for enemy in self.monsters
                         if not self.touches(enemy.rect, LAVA)]
        if self.exit_open and self.player.rect.colliderect(self.exit_door):
            self.state = 'win'

    @property
    def exit_open(self):
        if self.boss is not None:
            return self.boss not in self.monsters  # the deep exit needs the boss gone
        return not self.monsters

    def _can_enemy_see_player(self, enemy):
        start = pygame.Vector2(enemy.rect.center)
        end = pygame.Vector2(self.player.rect.center)
        delta = end - start
        distance = delta.length()
        if distance > ENEMY_SIGHT_RANGE:
            return False
        steps = max(1, math.ceil(distance / (CELL / 2)))
        for step in range(1, steps):
            point = start + delta * (step / steps)
            if self.world.solid(math.floor(point.x / CELL),
                                math.floor(point.y / CELL)):
                return False
        return True

    def _walker_direction(self, enemy, dt):
        player_x = self.player.rect.centerx
        in_chase_area = enemy.chase_left <= player_x <= enemy.chase_right
        if in_chase_area and self._can_enemy_see_player(enemy):
            enemy.chase_timer = WALKER_CHASE_MEMORY
        else:
            enemy.chase_timer = max(0.0, enemy.chase_timer - dt)
        if not in_chase_area:
            enemy.chase_timer = 0.0
        if enemy.chase_timer > 0.0:
            delta_x = player_x - enemy.rect.centerx
            return (delta_x > 0) - (delta_x < 0), True, False
        if enemy.pos.x < enemy.patrol_left:
            return 1, False, True
        if enemy.pos.x > enemy.patrol_right:
            return -1, False, True
        if (enemy.patrol_direction > 0
                and enemy.pos.x >= enemy.patrol_right):
            enemy.patrol_direction = -1
        elif (enemy.patrol_direction < 0
              and enemy.pos.x <= enemy.patrol_left):
            enemy.patrol_direction = 1
        return enemy.patrol_direction, False, False

    def update_enemy_combat(self, dt):
        for enemy in self.monsters:
            if (not enemy.shoots_projectiles or not self._enemy_active(enemy)
                    or self.stunned(enemy)):
                continue
            enemy.shot_cooldown = max(0.0, enemy.shot_cooldown - dt)
            if enemy.shot_cooldown == 0 and self._can_enemy_see_player(enemy):
                direction = pygame.Vector2(self.player.rect.center) - enemy.rect.center
                if direction.length_squared():
                    direction.scale_to_length(PROJECTILE_SPEED)
                    self.projectiles.append(
                        Projectile(enemy.rect.center, direction, enemy))
                    enemy.shot_cooldown = ENEMY_FIRE_INTERVAL
                    self.last_combat = self.world_time    # an attack: combat is on

        remaining = []
        for projectile in self.projectiles:
            distance = projectile.velocity.length() * dt
            steps = max(1, math.ceil(distance / (CELL / 2)))
            step = projectile.velocity * (dt / steps)
            expired = False
            for _ in range(steps):
                projectile.pos += step
                x, y = round(projectile.pos.x), round(projectile.pos.y)
                rect = pygame.Rect(x - PROJECTILE_RADIUS,
                                   y - PROJECTILE_RADIUS,
                                   PROJECTILE_RADIUS * 2,
                                   PROJECTILE_RADIUS * 2)
                if (rect.left < 0 or rect.top < 0
                        or rect.right > self.world.pixel_width
                        or rect.bottom > self.world.pixel_height):
                    expired = True
                    break
                left, right = rect.left // CELL, (rect.right - 1) // CELL
                top, bottom = rect.top // CELL, (rect.bottom - 1) // CELL
                if any(self.world.solid(tx, ty)
                       for ty in range(top, bottom + 1)
                       for tx in range(left, right + 1)):
                    expired = True
                    break
                if rect.colliderect(self.player.rect):
                    if self._deflects(projectile, projectile.pos.x):
                        self.handle_successful_parry(projectile.owner, projectile.pos)
                    elif self.hurt_timer <= 0 and self.state == 'play':
                        self.enemy_hit(PROJECTILE_DAMAGE, projectile.owner, projectile.pos)
                    expired = True
                    break
            if not expired:
                remaining.append(projectile)
        self.projectiles = remaining

    def update(self, dt, horizontal=0, jump=False, vertical=0):
        dt = min(max(dt,0),MAX_FRAME_DT)
        self.metrics['physics_ms'] = self.metrics['fluid_ms'] = 0.
        if self.state != 'play':
            if self.state == 'lose':
                self.combat.die()           # death overrides every combat state
            self.miner.guarding, self.miner.pose = False, None
            self.dig_x = None
            self.fx.update(dt)
            self.follow_camera(dt)
            return
        if not self.combat.can_act():
            # Guard broken: no walking, jumping or climbing; gravity still acts.
            horizontal = vertical = 0
            jump = self.jump_pending = False
        self.jump_pending |= jump
        if self.hitstop > 0:
            # A clash or a break freezes combat for a few frames. Liquids keep
            # their fixed step and effects keep moving, so nothing desyncs.
            self.hitstop = max(0.0, self.hitstop - dt)
            self.world_time += dt
            self.fluid_accumulator += dt
            while self.fluid_accumulator + 1e-10 >= 1 / FLUID_HZ:
                self.liquids.step(1 / FLUID_HZ)
                self.fluid_accumulator -= 1 / FLUID_HZ
            self.fx.update(dt)
            self.particles.update(dt)
            self.follow_camera(dt)
            return
        self._update_combat(dt)
        self.world_time += dt
        self.physics_accumulator += dt
        physics_dt, fluid_dt = 1/PHYSICS_HZ,1/FLUID_HZ
        self.liquids.focus = (self.player.rect.centerx // CELL,
                              self.player.rect.centery // CELL)
        active_enemies = [enemy for enemy in self.monsters if self._enemy_active(enemy)]
        for enemy in self.monsters:
            if getattr(enemy, 'hurt_timer', 0):
                enemy.hurt_timer = max(0.0, enemy.hurt_timer - dt)
            tick_enemy(enemy, dt)          # stun, guard break and posture recovery
        while self.physics_accumulator + 1e-10 >= physics_dt:
            start = time.perf_counter()
            on_ladder = self.renderer.ladder_at(self.player.rect)
            swimming = self.touches(self.player.rect,WATER)
            fall_speed = self.player.velocity.y
            # A stunned miner loses the ladder too: gravity keeps working.
            on_ladder = on_ladder and self.combat.can_act()
            self.player.update(physics_dt,horizontal,self.jump_pending,swimming,
                               vertical if on_ladder else 0,ladder_attached=on_ladder)
            if self.player.landed and fall_speed > 300:
                self.particles.dust(self.player.rect.centerx,self.player.rect.bottom,
                                    min(1.0,(fall_speed-300)/260))
            self.jump_pending = False
            for enemy in active_enemies:
                fall_speed = enemy.velocity.y
                if enemy.shoots_projectiles or self.stunned(enemy):
                    enemy.update(physics_dt, 0)  # stunned: gravity and knockback only
                else:
                    direction, chasing, returning = self._walker_direction(
                        enemy, physics_dt)
                    enemy.update(physics_dt, direction)
                    if chasing:
                        enemy.pos.x = max(enemy.chase_left,
                                          min(enemy.pos.x, enemy.chase_right))
                        enemy._sync_rect()
                    elif returning:
                        if enemy.pos.x <= enemy.patrol_left:
                            enemy.pos.x = enemy.patrol_left
                            enemy.patrol_direction = 1
                            enemy._sync_rect()
                        elif enemy.pos.x >= enemy.patrol_right:
                            enemy.pos.x = enemy.patrol_right
                            enemy.patrol_direction = -1
                            enemy._sync_rect()
                    elif enemy.hit_wall:
                        enemy.patrol_direction *= -1
                    elif enemy.pos.x <= enemy.patrol_left:
                        enemy.pos.x = enemy.patrol_left
                        enemy.patrol_direction = 1
                        enemy._sync_rect()
                    elif enemy.pos.x >= enemy.patrol_right:
                        enemy.pos.x = enemy.patrol_right
                        enemy.patrol_direction = -1
                        enemy._sync_rect()
                if enemy.landed and fall_speed > 300:
                    self.particles.dust(enemy.rect.centerx, enemy.rect.bottom,
                                        min(1.0, (fall_speed - 300) / 260))
            self.physics_accumulator -= physics_dt
            self.fluid_accumulator += physics_dt
            self.metrics['physics_ms'] += (time.perf_counter()-start)*1000
            if self.fluid_accumulator + 1e-10 >= fluid_dt:
                start = time.perf_counter()
                self.liquids.step(fluid_dt)
                self.fluid_accumulator -= fluid_dt
                self.metrics['fluid_ms'] += (time.perf_counter()-start)*1000
        self.hurt_timer = max(0,self.hurt_timer-dt)
        self.update_oxygen(dt)
        if self.state != 'play':
            self.follow_camera(dt)
            return
        self.update_stage_progress()
        if self.touches(self.player.rect,LAVA):
            self.hp,self.state = 0,'lose'
        if self.state != 'play':
            self.follow_camera(dt)
            return
        self.update_enemy_combat(dt)
        self.bombs.update(dt)
        if self.state != 'play':
            self.follow_camera(dt)
            return
        touching_enemies = []
        for enemy in self.monsters:
            if self.stunned(enemy) or not self.player.rect.colliderect(enemy.rect):
                continue
            if self._deflects(enemy, enemy.rect.centerx):
                edge = self.player.rect.right if self.parry_facing else self.player.rect.left
                self.handle_successful_parry(enemy, (edge, self.player.rect.centery))
            else:
                touching_enemies.append(enemy)
        if self.hurt_timer == 0 and touching_enemies:
            # One hit per contact (the 0.8 s grace stops repeats): one posture point.
            attacker = max(touching_enemies, key=lambda enemy: enemy.contact_damage)
            rect = self.player.rect
            edge = rect.right if attacker.rect.centerx >= rect.centerx else rect.left
            self.enemy_hit(attacker.contact_damage, attacker, (edge, rect.centery))
        self.engaged = self.scan_combat()
        start = time.perf_counter()
        self.emit(dt)
        self.particles.update(dt)
        self.fx.update(dt)
        self.miner.update(dt,self.player,self.dig_x)
        self.dig_x = None
        self.metrics['particles_ms'] = (time.perf_counter()-start)*1000
        self.follow_camera(dt)

    def emit(self, dt):
        """Ambient particles and feedback; none of it touches the simulation."""
        swimming = self.touches(self.player.rect,WATER)
        if swimming and not self.was_swimming and abs(self.player.velocity.y) > 60:
            self.particles.splash(self.player.rect.centerx,self.player.rect.centery,
                                  min(1.0,abs(self.player.velocity.y)/300))
        self.was_swimming = swimming
        # Several cells starting to cool at once is the one quake-worthy event.
        reactions = len(self.liquids.reactions)
        if reactions - self.reactions_seen >= 8:
            self.shake = min(0.45, self.shake + 0.22)
        self.reactions_seen = reactions
        rnd = self.particles.random
        surfaces = self.renderer.lava_surfaces
        self.ember_clock += dt
        while self.ember_clock >= EMBER_INTERVAL:
            self.ember_clock -= EMBER_INTERVAL
            if surfaces:
                x, y = surfaces[rnd.randrange(len(surfaces))]
                self.particles.ember(x+rnd.uniform(0,CELL),y)
        self.mote_clock += dt
        if self.mote_clock >= 0.3:
            self.mote_clock = 0.0
            lamps = self.renderer.visible_lamps
            if lamps and self.particles.count(0.0) < MOTE_LIMIT:
                x, y = lamps[rnd.randrange(len(lamps))]
                self.particles.mote(x+rnd.uniform(-46,46),y+rnd.uniform(-34,30))

    def light_sources(self):
        renderer = self.renderer
        view = pygame.Rect(self.render_camera, (SCREEN_W, SCREEN_H))
        for light in renderer.lights_near(view, 4 * MACRO):
            if renderer.supported(light['item']):
                yield (light['kind'],light['x'],light['y'],light['radius'],light['color'],light['phase'])
        for mx, my in renderer.visible_lava:
            if (mx+my*2)%3 == 0:
                yield ('lava',mx*MACRO+MACRO//2,my*MACRO+MACRO//2,128,(255,112,44),(mx*7+my)%6)
        for mx, my in renderer.visible_water:
            if (mx*3+my)%4 == 0:
                yield ('water',mx*MACRO+MACRO//2,my*MACRO+MACRO//2,72,(36,84,140),(mx+my*5)%6)
        yield from self.fx.lights()     # a clash or a break briefly lights the cave

    def draw(self, screen):
        start = time.perf_counter()
        # A zero-time follow cuts to the player after a teleport (restart,
        # scripted views) even when no update ran since the move.
        self.follow_camera(0)
        camera = self.render_camera
        renderer = self.renderer
        renderer.draw_static(screen,camera)
        renderer.draw_animated(screen,camera,self.world_time)
        renderer.draw_liquids(screen,self.liquids,camera,
                              self.fluid_accumulator*FLUID_HZ,self.world_time)
        self.draw_exit_door(screen, camera)
        for projectile in self.projectiles:
            center = (round(projectile.pos.x-camera[0]),
                      round(projectile.pos.y-camera[1]))
            pygame.draw.circle(screen,(255,190,88),center,PROJECTILE_RADIUS+2)
            pygame.draw.circle(screen,(226,73,43),center,PROJECTILE_RADIUS)
        for actor in self.monsters:
            if getattr(actor, 'is_boss', False):
                draw_boss(screen, actor, camera, self.world_time)
                continue
            color = (220, 75, 65) if actor.shoots_projectiles else (111, 161, 77)
            draw_actor(screen,actor,color,camera)
        self.bombs.draw(screen,camera,self.world_time)
        self.miner.draw(screen,self.player,camera,self.hurt_timer)
        draw_parry(screen, self, camera)
        self.bombs.draw_carried(screen,camera,self.player.rect)
        self.particles.draw(screen,camera)
        renderer.draw_foreground(screen,camera)
        self.lighting.draw(screen,camera,self.world_time,self.light_sources(),
                           self.miner.head(self.player))
        draw_combat_overlay(screen, self, camera)   # emissive: after the light map
        self.fx.draw_screen(screen)                 # edge flash and impact vignette
        self.metrics['render_ms'] = (time.perf_counter()-start)*1000
        self.draw_calls = (renderer.draw_calls+self.lighting.draw_calls+
                           len(self.monsters)+2+len(self.particles.items)+
                           2*len(self.projectiles))

    def draw_exit_door(self, screen, camera):
        door = self.exit_door.move(-camera[0], -camera[1])
        pygame.draw.rect(screen, (49, 34, 31), door)
        if self.exit_open:
            pygame.draw.rect(screen, (139, 92, 54), door.inflate(-6, -4))
            pygame.draw.rect(screen, (24, 21, 22), door.inflate(-14, -10))
            pygame.draw.line(screen, (244, 194, 83),
                             (door.x + 8, door.y + 5),
                             (door.right - 9, door.y + 5), 2)
        else:
            panel = door.inflate(-6, -4)
            pygame.draw.rect(screen, (92, 57, 34), panel)
            pygame.draw.line(screen, (139, 92, 54),
                             (panel.left + 2, panel.centery),
                             (panel.right - 2, panel.centery), 3)
            pygame.draw.circle(screen, (201, 61, 61),
                               (panel.centerx, panel.centery - 5), 3)


def draw_actor(screen, actor, color, camera):
    _ensure_pygame()
    # Monster and boss artwork remain the project's placeholder shapes.
    box = actor.rect.move(-camera[0],-camera[1])
    if not box.colliderect(screen.get_rect()):
        return
    outline = (19, 19, 25)
    if getattr(actor, 'broken', False):
        # Guard broken: slumped (shorter, wider) with a hot, blinking outline.
        box = pygame.Rect(box.x - 1, box.y + 4, box.w + 2, box.h - 4)
        outline = (226, 70, 44) if int(actor.stun_timer * 8) % 2 else (90, 24, 20)
    # Outline stays inside the collision bounds, so feet visually meet the floor.
    pygame.draw.rect(screen,outline,box,border_radius=3)
    pygame.draw.rect(screen,color,box.inflate(-4,-2),border_radius=2)
    pygame.draw.rect(screen,(240,240,215),(box.x+box.w//3,box.y+box.h//3,4,4))


def draw_parry(screen, game, camera):
    """The guard arc while the window is open (lit like the miner)."""
    from parry import ACTIVE, PARRY_ACTIVE_TIME
    from parry_fx import guard_arc
    player = game.player.rect.move(-camera[0], -camera[1])
    facing = 1 if game.parry_facing else -1
    parry = game.parry
    if parry.state == ACTIVE:
        guard_arc(screen, player, facing, parry.elapsed / PARRY_ACTIVE_TIME, 1.0)
    elif parry.succeeded and parry.elapsed < PARRY_ACTIVE_TIME + 0.12:
        guard_arc(screen, player, facing, 1.0, 1.4)


def draw_combat_overlay(screen, game, camera):
    """Flashes, streaks, shockwaves, dizzy sparks and deathblow marks."""
    from parry_fx import dizzy, deathblow_mark
    game.fx.draw(screen, camera)
    t = game.world_time
    for enemy in game.monsters:
        if not Game.stunned(enemy):
            continue
        box = enemy.rect.move(-camera[0], -camera[1])
        if not box.colliderect(screen.get_rect()):
            continue
        if getattr(enemy, 'broken', False):
            dizzy(screen, box, t, 5, (255, 150, 70), 3)
            if not getattr(enemy, 'is_boss', False):
                deathblow_mark(screen, box.centerx, box.y - 16, t)
        else:
            dizzy(screen, box, t)
    if not game.combat.can_act() and game.state == 'play':
        player = game.player.rect.move(-camera[0], -camera[1])
        dizzy(screen, player, t, 4, (255, 214, 92), 2)


def draw_boss(screen, boss, camera, world_time):
    """Placeholder boss art: a hulking purple block with a health readout."""
    _ensure_pygame()
    box = boss.rect.move(-camera[0], -camera[1])
    if not box.colliderect(screen.get_rect()):
        return
    flash = boss.hurt_timer > 0 and int(world_time * 20) % 2 == 0
    top = box.y                            # the health readout does not sag
    if getattr(boss, 'broken', False):     # staggered: sagging, rocking
        box = pygame.Rect(box.x + round(math.sin(world_time * 18) * 2), box.y + 5, box.w, box.h - 5)
    pygame.draw.rect(screen, (19, 19, 25), box, border_radius=6)
    pygame.draw.rect(screen, (240, 210, 240) if flash else (158, 52, 184),
                     box.inflate(-6, -4), border_radius=5)
    pygame.draw.rect(screen, (96, 30, 120), (box.x + 6, box.bottom - 16, box.w - 12, 10))
    for eye in (box.x + box.w // 3 - 4, box.x + 2 * box.w // 3 - 4):
        pygame.draw.rect(screen, (255, 214, 92), (eye, box.y + box.h // 3, 8, 6))
    for n in range(boss.max_hp):
        color = (226, 73, 43) if n < boss.hp else (60, 40, 40)
        pygame.draw.rect(screen, color, (box.centerx - boss.max_hp * 7 + n * 14, top - 12, 11, 6))


def next_stage_number(stage, total_stages=6):
    if total_stages <= 0:
        raise ValueError('total_stages must be positive')
    if not 1 <= stage < total_stages:
        raise ValueError(f'No stage follows stage {stage}')
    return stage + 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames',type=int,default=0,help='Exit after N frames for smoke testing.')
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--uncapped',action='store_true')
    parser.add_argument('--profile',type=Path,help='Save measured frame/system costs as JSON.')
    parser.add_argument('--bombs',action='store_true',help='Place bomb pickups even in stages without bombs (for testing).')
    parser.add_argument('--stage',type=int,default=1,help='Stage for headless/profile runs (6: The Deep Descent).')
    parser.add_argument('--seed',type=int,help='Layout seed for The Deep Descent.')
    args = parser.parse_args(argv)
    if args.headless:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    os.environ['SDL_RENDER_SCALE_QUALITY'] = '0'
    _ensure_pygame()
    from tiles import TileArt
    from lighting import Lighting
    from ui import GameUI
    from audio import sounds
    # A small mixer buffer keeps the clash on the same frame as the parry.
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.init()
    sounds().preload()   # loaded once at launch; silent without audio
    screen = pygame.display.set_mode((SCREEN_W,SCREEN_H),vsync=0)
    import parry_fx
    parry_fx.warm()      # combat effect frames, so the first parry never hitches
    pygame.display.set_caption('Dig Game — Stage 1: Abandoned Mine')
    art = TileArt(CELL,MACRO)
    lighting = Lighting((SCREEN_W,SCREEN_H))
    debug_font = pygame.font.SysFont('monospace',16)
    game = Game(art,lighting,bombs=args.bombs,stage=args.stage,seed=args.seed)
    ui = GameUI()
    selected_stage = args.stage
    if args.headless:
        ui.start(game)  # Preserve the gameplay path for automated smoke/profile runs.
    clock = pygame.time.Clock()
    frames,debug,running = 0,False,True
    costs,frame_times,samples = [],[],[]

    def activate(label):
        nonlocal game, running, selected_stage
        if label == 'START GAME':
            ui.screen = 'stage_select'
        elif label in ('STAGE 1', 'STAGE 2', 'STAGE 3', 'STAGE 4', 'STAGE 5', 'STAGE 6'):
            selected_stage = int(label[-1])
            game = Game(art, lighting, bombs=args.bombs, stage=selected_stage)
            ui.start(game)
        elif label == 'PLAY AGAIN':
            selected_stage = 1
            game = Game(art, lighting, bombs=args.bombs, stage=selected_stage)
            ui.start(game)
        elif label in ('RESTART', 'RETRY'):
            selected_stage = game.stage_number
            # A generated world restarts with the same layout.
            game = Game(art, lighting, bombs=args.bombs, stage=selected_stage,
                        seed=game.seed)
            ui.start(game)
        elif label == 'NEXT STAGE':
            selected_stage = next_stage_number(selected_stage)
            game = Game(art, lighting, bombs=args.bombs, stage=selected_stage)
            ui.start(game)
        elif label == 'BACK TO MENU':
            ui.screen = 'menu'
        elif label == 'RESUME':
            ui.screen = 'game'
        elif label == 'HOW TO PLAY':
            ui.controls_from = ui.screen
            ui.screen = 'controls'
        elif label == 'BACK':
            ui.screen = ui.controls_from
        elif label == 'MAIN MENU':
            ui.screen = 'menu'
        elif label == 'QUIT':
            running = False

    while running:
        tick = clock.tick_busy_loop if PRECISE_FRAME_PACING else clock.tick
        raw_frame_dt = tick(0 if args.uncapped else FPS)/1000
        frame_dt = min(raw_frame_dt,MAX_FRAME_DT)
        if args.uncapped:
            frame_dt = 1/FPS  # Reproducible benchmark simulation time.
        start = time.perf_counter()
        jump = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif (event.type == pygame.MOUSEBUTTONUP and event.button == 3
                  and game.bombs.aim is not None):
                # Hold the right button to aim (shows the arc), release to throw.
                if ui.screen == 'game' and game.can_act():
                    cx,cy = game.render_camera
                    game.bombs.throw((event.pos[0]+cx,event.pos[1]+cy))
                game.bombs.aim = None
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if ui.screen == 'controls':
                        ui.screen = ui.controls_from
                    elif ui.screen == 'stage_select':
                        ui.screen = 'menu'
                    elif ui.screen == 'paused':
                        ui.screen = 'game'
                    elif ui.screen == 'game' and game.state == 'play':
                        ui.screen = 'paused'
                elif event.key == pygame.K_r and ui.screen in ('game', 'paused'):
                    activate('RESTART')
                elif event.key == pygame.K_F3 and ui.screen == 'game':
                    debug = not debug
                elif event.key == pygame.K_e and ui.screen == 'game':
                    # KEYDOWN only (no key repeat), so holding E parries once.
                    game.press_e()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if ui.screen == 'menu':
                        activate('START GAME')
                    elif ui.screen == 'paused':
                        activate('RESUME')
                elif ui.screen == 'game' and event.key in (pygame.K_SPACE,pygame.K_w,pygame.K_UP):
                    jump |= jump_requested(event.key,
                                           game.renderer.ladder_at(game.player.rect))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                action = ui.click(event.pos)
                if action:
                    activate(action)
        keys = pygame.key.get_pressed()
        horizontal = int(keys[pygame.K_d] or keys[pygame.K_RIGHT])-int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        vertical = int(keys[pygame.K_s] or keys[pygame.K_DOWN])-int(keys[pygame.K_w] or keys[pygame.K_UP])
        digging = False
        if ui.screen == 'game' and game.state == 'play' and pygame.mouse.get_pressed()[0]:
            mx,my = pygame.mouse.get_pos()
            cx,cy = game.render_camera
            digging = ui._dig_target(game, (mx, my))
            game.excavate(((mx+cx)//CELL,(my+cy)//CELL))
        else:
            game.last_dig = None
        if (ui.screen == 'game' and game.can_act() and game.bombs.carried
                and pygame.mouse.get_pressed()[2]):
            mx,my = pygame.mouse.get_pos()
            cx,cy = game.render_camera
            game.bombs.aim = (mx+cx,my+cy)
        else:
            game.bombs.aim = None       # released, or the guard is broken
        if ui.screen == 'game' and game.state == 'play':
            ui.note_input(horizontal, jump, vertical, digging, game)
            game.update(frame_dt,horizontal,jump,vertical)
        ui.update(frame_dt, game)
        game.draw(screen)
        ui.draw(screen, game, pygame.mouse.get_pos())
        if debug and ui.screen == 'game':
            metrics = game.metrics
            player = game.player.rect
            lines = [f'{clock.get_fps():5.1f} FPS  frame {raw_frame_dt*1000:5.2f} ms',
                     f'physics {metrics["physics_ms"]:.2f}  liquid {metrics["fluid_ms"]:.2f}  render {metrics["render_ms"]:.2f} ms',
                     f'active {len(game.liquids.active)}  cooling {len(game.liquids.reactions)}',
                     f'chunks {game.renderer.visible_chunks}  dirty {len(game.world.dirty_chunks)}  rebuilt {game.renderer.rebuilt_chunks}',
                     f'tiles {game.renderer.visible_tiles}  draw calls {game.draw_calls}  lights {game.lighting.visible}',
                     f'visible liquid {game.renderer.visible_liquids}  particles {len(game.particles.items)}',
                     f'player x {player.x} y {player.y}  cell {player.centerx//CELL},{player.bottom//CELL}  layer {game.layer_at(player.centery)}',
                     f'enemies {len(game.monsters)}  cached chunks {len(game.renderer.cache)}  seed {game.seed}']
            panel = pygame.Surface((580,184),pygame.SRCALPHA)
            panel.fill((12,14,22,225))
            screen.blit(panel,(10,45))
            for n,line in enumerate(lines):
                screen.blit(debug_font.render(line,True,(219,231,243)),(18,52+n*19))
        cpu_cost = (time.perf_counter()-start)*1000
        present_start = time.perf_counter()
        pygame.display.flip()
        game.metrics['present_ms'] = (time.perf_counter()-present_start)*1000
        frames += 1
        # Discard warmup cache builds from steady-state cost statistics.
        if frames > 20:
            costs.append(cpu_cost)
            frame_times.append(raw_frame_dt*1000)
            samples.append(game.metrics.copy())
        if args.frames and frames >= args.frames:
            running = False
    if args.profile:
        import statistics
        def stats(values):
            values = sorted(values)
            return {'mean_ms':statistics.mean(values) if values else 0,
                    'p95_ms':values[int((len(values)-1)*.95)] if values else 0,
                    'max_ms':max(values,default=0)}
        report = {'pygame':pygame.version.ver,'frames':frames,'work':stats(costs),'frame':stats(frame_times),
                  'systems':{key:stats([s[key] for s in samples]) for key in game.metrics},
                  'fluid_active':len(game.liquids.active),'reaction_cells':len(game.liquids.reactions)}
        args.profile.parent.mkdir(parents=True,exist_ok=True)
        args.profile.write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    pygame.quit()


if __name__ == '__main__':
    main()
