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
                    ENEMY_ACTIVE_RANGE, PLAYER_MAX_HP)
from config import (PARRY_STUN_DURATION, PARRY_KNOCKBACK, PARRY_KNOCKBACK_LIFT,
                    PARRY_HITSTOP, PARRY_FRONT_TOLERANCE, PARRY_SHAKE_TIME,
                    PARRY_SHAKE_PX, PARRY_PERFECT_TIME, PERFECT_PARRY_HITSTOP,
                    PERFECT_SHAKE_TIME, PERFECT_SHAKE_PX, PERFECT_RECOIL_PX)
from config import (GUARD_BREAK_HITSTOP, GUARD_BREAK_SHAKE_TIME, GUARD_BREAK_SHAKE_PX,
                    GUARD_BREAK_KNOCKBACK, ENEMY_BREAK_HITSTOP, ENEMY_STUN_DURATION,
                    BOSS_STAGGER_DURATION, DEATHBLOW_REACH, COMBAT_RANGE)
from config import (MELEE_REACH, BOSS_MELEE_REACH, MELEE_WINDUP, BOSS_MELEE_WINDUP,
                    MELEE_STRIKE, BOSS_MELEE_STRIKE, MELEE_RECOVER, MELEE_COOLDOWN,
                    TELEGRAPH_TIME)
from level import FINAL_STAGE

STAGE_NAMES = {
    1: 'ABANDONED MINE',
    2: 'THE SINKING MINE',
    3: 'DIRT CAVERNS',
    4: 'WATER CHAMBER',
    5: 'THE SINKING MINE',
    6: 'THE DEEP DESCENT',  # not selectable; source of the Stage 5.5 boss room
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
    def __init__(self, art, lighting=None, bombs=False, stage=1, seed=None,
                 bonus_room=False, return_game=None, starting_gold=0):
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
        self.bonus_room = bonus_room
        self.return_game = return_game
        if bonus_room:
            from levels.bonus import (build_bonus_stage,
                                      build_final_boss_bonus_stage,
                                      build_water_bonus_stage)
            build_bonus = {
                2: build_water_bonus_stage,
                5: build_final_boss_bonus_stage,
            }.get(stage, build_bonus_stage)
            rows, entities, scenery, self.optional_rooms = build_bonus()
            scenery['bonus_room'] = True
        else:
            rows, entities, scenery, self.optional_rooms = build_level(stage, seed)
        self.stage_number = stage
        self.final_boss_room = scenery.get('final_boss_room', False)
        self.stage_name = ('STAGE 5.5: THE DEEP DESCENT'
                           if self.final_boss_room else
                           f'BONUS MINE {stage}.5' if bonus_room else
                           STAGE_NAMES[stage])
        self.return_sign = (pygame.font.Font(None, 14).render(
            f'STAGE {stage}', True, (239, 210, 151))
            if bonus_room and not self.final_boss_room else None)
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
        # Dig energy is measured on this exact map before anything is dug.
        from dig_budget import plan_stage, plan_shortcut, DigMeter
        door = scenery['exit_door']
        goals = list(entities.get('B', ())) + [(door[0], door[1] + door[3] - 1)]
        minimum, self.dig_route = plan_stage(self.world, entities['P'][0], goals)
        shortcut, _ = plan_shortcut(self.world, entities['P'][0], goals)
        self.dig_meter = DigMeter(minimum, shortcut)
        self.dig_gain, self.dig_gain_timer = 0, 0.0
        from dig_orbs import OrbSystem
        self.orbs = OrbSystem(self)
        self.liquids = LiquidSystem(self.world)
        # Each stage grades the soil to its own colours (tiles.THEMES).
        render_stage = 6 if self.final_boss_room else stage
        self.renderer = WorldRenderer(self.world, art.for_stage(render_stage), scenery)
        self.lighting = lighting or Lighting((SCREEN_W, SCREEN_H))
        self.lighting.band_rows = self.layers['rows'] if self.layers else 25
        x,y = entities['P'][0]
        self.player = Player(self.world,x*MACRO,y*MACRO)
        self.gold = starting_gold
        self.gold_checkpoint = self.gold
        self.player.drop_to_ground()
        from potions import PotionSystem
        self.potions = PotionSystem(self)
        self.dying = []      # death animations of defeated enemies
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
        bonus_door = scenery.get('bonus_door')
        self.bonus_door = (pygame.Rect(bonus_door[0] * MACRO,
                                       bonus_door[1] * MACRO,
                                       bonus_door[2] * MACRO,
                                       bonus_door[3] * MACRO)
                           if bonus_door else None)
        self.has_key = False
        key_pickup = scenery.get('key_pickup')
        self.key_pickup = None
        self.key_image = None
        if stage in (1, 2) or key_pickup:
            from pathlib import Path
            self.key_image = pygame.transform.scale(
                pygame.image.load(str(Path(__file__).parent / 'assets' / 'key.png'))
                .convert_alpha(), (40, 40))
        self.key_collected = False
        self.door_cooldown = 0.0
        self.door_locked_until_exit = False
        self.stage_sign = None
        if scenery.get('stage_sign'):
            from pathlib import Path
            sign_image = pygame.image.load(
                str(Path(__file__).parent / 'assets' / 'sign.png')).convert_alpha()
            sign_image = pygame.transform.smoothscale(sign_image, (80, 64))
            sign_rect = sign_image.get_rect()
            sign_rect.midbottom = (scenery['stage_sign'][0] * MACRO + MACRO // 2,
                                   scenery['stage_sign'][1] * MACRO)
            self.stage_sign = (sign_image, sign_rect)
        if key_pickup:
            self.key_pickup = pygame.Rect(key_pickup[0] * MACRO + 5,
                                          key_pickup[1] * MACRO + 5, 40, 40)
        self.projectiles = []
        from bombs import BombSystem
        self.bombs = BombSystem(self, scenery.get('bomb_spawns', ()),
                                self.stage_number, force=bombs,
                                count=scenery.get('bomb_count'),
                                fixed=scenery.get('bomb_fixed', ()))
        from dirt_gun import DirtGun
        self.gun = DirtGun(self)         # F: the dirt pistol, paid from the dig meter
        self.particles = Particles()
        self.miner = MinerSprite()
        self.hp, self.oxygen, self.state = PLAYER_MAX_HP, 100.0, 'play'
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
        from gold import GoldSystem
        self.gold_system = GoldSystem(self, entities, scenery)
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

    @property
    def monsters(self):
        return self._monsters

    @monsters.setter
    def monsters(self, survivors):
        # Lava, bombs and every other kill replace this list; any enemy that
        # left it (other than the boss) bursts into dirt orbs that refill the
        # dig meter. Orbs from a lava death fly to the player on their own.
        old = getattr(self, '_monsters', None)
        self._monsters = survivors
        if old:
            import enemy_sprites
            alive = {id(m) for m in survivors}
            target = self.player.rect.center if hasattr(self, 'player') else None
            for enemy in old:
                if id(enemy) not in alive:
                    self.dying.append(enemy_sprites.Death(
                        enemy, target, getattr(self, "world_time", 0.0)))
        orbs = getattr(self, 'orbs', None)
        gold = getattr(self, 'gold_system', None)
        if not old:
            return
        alive = {id(m) for m in survivors}
        for enemy in old:
            if id(enemy) not in alive:
                homing = self.touches(enemy.rect, LAVA)
                if gold is not None:
                    gold.drop(enemy.rect.center,
                              50 if getattr(enemy, 'is_boss', False) else 15)
                if enemy is self.boss or orbs is None:
                    continue
                orbs.drop(enemy.rect.center, homing=homing)
                potions = getattr(self, 'potions', None)
                if potions is not None:
                    kind = ('speed' if getattr(enemy, 'shoots_projectiles', False)
                            else 'health')
                    potions.drop(kind, enemy.rect.center)

    @property
    def gold(self):
        return getattr(self, '_gold', 0)

    @gold.setter
    def gold(self, amount):
        self._gold = max(0, int(amount))
        if hasattr(self, 'player'):
            self.player.gold = self._gold

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
        enemy.hurt_time = self.world_time         # flinch before the stun
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
        """The nearest guard-broken enemy within reach, including the boss."""
        reach = self.player.rect.inflate(DEATHBLOW_REACH * 2, 16)
        targets = [enemy for enemy in self.monsters
                   if getattr(enemy, 'broken', False)
                   and reach.colliderect(enemy.rect)]
        return min(targets, default=None,
                   key=lambda enemy: abs(enemy.rect.centerx - self.player.rect.centerx))

    def deathblow(self, enemy):
        """Finish a normal guard-broken enemy or damage a staggered boss."""
        self.miner.facing_right = self.parry_facing = \
            enemy.rect.centerx >= self.player.rect.centerx
        if getattr(enemy, 'is_boss', False):
            return self.damage_boss(enemy, 'DEATHBLOW!')
        self.finish_enemy(enemy, 'DEATHBLOW!')
        self.miner.flash = 0.12
        self.miner.recoil = 0.12
        return True

    def damage_boss(self, boss, word):
        """A gun hit or deathblow during a boss stagger removes one health pip."""
        if boss not in self.monsters or not boss.broken:
            return False
        boss.hp -= 1
        boss.hurt_timer = 0.5
        boss.hurt_time = self.world_time
        self.last_combat = self.world_time
        boss.broken = False
        boss.stun_timer = 0.0
        boss.posture.reset()
        if boss.hp <= 0:
            self.finish_enemy(boss, word)
        else:
            self.fx.popup(word, boss.rect.centerx, boss.rect.top - 24,
                          (240, 70, 56), 0.9)
            self.hitstop = max(self.hitstop, ENEMY_BREAK_HITSTOP)
            side = 1 if boss.rect.centerx >= self.player.rect.centerx else -1
            self.camera_kick(GUARD_BREAK_SHAKE_TIME, GUARD_BREAK_SHAKE_PX - 2,
                             side, 3)
            self.sounds.play('deathblow')
        return True

    def finish_enemy(self, enemy, word):
        """Kill a guard-broken enemy with the finisher's flash, word and shake
        (the E deathblow, or a dirt-gun shot)."""
        self.monsters = [other for other in self.monsters if other is not enemy]
        side = 1 if enemy.rect.centerx >= self.player.rect.centerx else -1
        x, y = enemy.rect.center
        self.fx.deathblow(x, y)
        self.fx.popups.clear()             # the finisher's word stands alone
        self.fx.popup(word, x, enemy.rect.top - 24, (240, 70, 56), 0.9)
        self.hitstop = max(self.hitstop, ENEMY_BREAK_HITSTOP)
        self.camera_kick(GUARD_BREAK_SHAKE_TIME, GUARD_BREAK_SHAKE_PX - 2, side, 3)
        self.last_combat = self.world_time
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
        self.player.jump_buffer = 0.0
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
        if self.dig_meter.empty or not self.combat.can_act():
            self.last_dig = None   # out of dig energy, or a broken guard
            return
        self.dig_x = target[0]*CELL+CELL//2
        start = self.last_dig or target
        removed = self.world.dig_line(start,target,DIG_RADIUS)
        self.dig_meter.spend(len(removed))
        self.particles.dirt(self.world,removed,self.renderer.debris_colors)
        self.gold_system.dug(removed)
        self.last_dig = target

    def update_stage_progress(self):
        self.monsters = [enemy for enemy in self.monsters
                         if not self.touches(enemy.rect, LAVA)]
        if self.door_locked_until_exit:
            blocked_door = self.exit_door if self.bonus_room else self.bonus_door
            if blocked_door is None or not self.player.rect.colliderect(blocked_door):
                self.door_locked_until_exit = False
        if (self.key_pickup is not None
                and self.player.rect.colliderect(self.key_pickup)):
            self.key_pickup = None
            self.key_collected = True
        if self.door_locked_until_exit:
            return
        if self.bonus_room:
            if self.final_boss_room:
                if (self.exit_open and self.door_cooldown <= 0
                        and self.player.rect.colliderect(self.exit_door)):
                    self.door_cooldown = 3.0
                    self.state = 'win'
                return
            if (self.door_cooldown <= 0
                    and self.player.rect.colliderect(self.exit_door)):
                self.door_cooldown = 3.0
                self.state = 'return_stage'
            return
        if self.stage_number in (1, 2):
            if (self.bonus_door is not None
                    and self.door_cooldown <= 0
                    and self.player.rect.colliderect(self.bonus_door)):
                self.door_cooldown = 3.0
                self.state = 'enter_bonus'
            elif (self.has_key and self.door_cooldown <= 0
                  and self.player.rect.colliderect(self.exit_door)):
                self.state = 'win'
            return
        elif self.exit_open and self.player.rect.colliderect(self.exit_door):
            if self.door_cooldown <= 0:
                self.door_cooldown = 3.0
                self.state = ('enter_bonus' if self.stage_number in (1, 2, 5)
                              else 'win')

    @property
    def exit_open(self):
        if self.boss is not None:
            return self.boss not in self.monsters  # the deep exit needs the boss gone
        return not self.monsters

    def inherit_player_state(self, source):
        """Carry the shared Stage 1 / Stage 1.5 player state across maps."""
        self.hp = source.hp
        self.oxygen = source.oxygen
        self.oxygen_damage_timer = source.oxygen_damage_timer
        self.dig_meter.remaining = (self.dig_meter.capacity *
                                    source.dig_meter.fraction)
        self.bombs.carried = source.bombs.carried
        self.has_key = source.has_key or source.key_collected
        self.key_collected = self.has_key
        if self.has_key:
            self.key_pickup = None
        self.potions.speed_timer = source.potions.speed_timer
        self.player.speed_multiplier = source.player.speed_multiplier
        self.gold = source.gold
        self.gold_checkpoint = source.gold_checkpoint
        self.combat.posture.value = source.combat.posture.value
        self.combat.posture.calm = source.combat.posture.calm
        self.combat.posture.since_rise = source.combat.posture.since_rise

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

    def _muzzle(self, enemy):
        """Where a gunner's shot starts: the cannon tip, unless that is in a wall."""
        import enemy_sprites
        right = self.player.rect.centerx > enemy.rect.centerx
        tip = pygame.Vector2(enemy_sprites.muzzle(enemy, right))
        center = pygame.Vector2(enemy.rect.center)
        for n in range(1, 5):                  # the barrel must not poke through rock
            point = center.lerp(tip, n / 4)
            if self.world.solid(math.floor(point.x / CELL), math.floor(point.y / CELL)):
                return center
        return tip

    # ---- melee: wind-up, strike, recover (walkers and the boss) -----------
    def _melee_reach(self, enemy):
        return BOSS_MELEE_REACH if getattr(enemy, 'is_boss', False) else MELEE_REACH

    def _melee_box(self, enemy, side):
        """The strip in front of an enemy its swing covers."""
        reach = self._melee_reach(enemy)
        rect = enemy.rect
        box = pygame.Rect(0, rect.top - 8, reach, rect.height + 8)
        if side > 0:
            box.left = rect.right
        else:
            box.right = rect.left
        return box.union(rect)

    def _in_melee_reach(self, enemy):
        side = 1 if self.player.rect.centerx >= enemy.rect.centerx else -1
        return self._melee_box(enemy, side).colliderect(self.player.rect)

    def update_melee(self, enemy, dt):
        """Advance one walker's or the boss's attack; a stun cancels it."""
        if self.stunned(enemy) or not self._enemy_active(enemy):
            enemy.melee_state = None
            return
        enemy.melee_cooldown = max(0.0, getattr(enemy, 'melee_cooldown', 0.0) - dt)
        state = getattr(enemy, 'melee_state', None)
        player = self.player.rect
        if state is None:
            side = 1 if player.centerx >= enemy.rect.centerx else -1
            if (enemy.melee_cooldown == 0 and self.combat.dead is False
                    and self._melee_box(enemy, side).colliderect(player)
                    and self._can_enemy_see_player(enemy)):
                enemy.melee_state, enemy.melee_side = 'windup', side
                enemy.melee_timer = (BOSS_MELEE_WINDUP if getattr(enemy, 'is_boss', False)
                                     else MELEE_WINDUP)
                enemy.melee_length = enemy.melee_timer
                self.last_combat = self.world_time
            return
        enemy.melee_timer -= dt
        if state == 'windup' and enemy.melee_timer <= 0:
            strike = BOSS_MELEE_STRIKE if getattr(enemy, 'is_boss', False) else MELEE_STRIKE
            enemy.melee_state, enemy.melee_timer = 'strike', strike
            enemy.melee_length, enemy.melee_struck = strike, False
            enemy.attack_time = self.world_time
            state = 'strike'
            enemy.melee_slammed = False
        if state == 'strike':
            # The boss's blade lands in the strike's second half (its frame
            # with the sword in the ground); before that it is still swinging.
            landed = (not getattr(enemy, 'is_boss', False)
                      or enemy.melee_timer <= enemy.melee_length * 0.5)
            if landed and getattr(enemy, 'is_boss', False) and not enemy.melee_slammed:
                # The sword hits the ground: the cave shakes and dust flies.
                enemy.melee_slammed = True
                self.shake = min(1.0, self.shake + 0.55)
                front = enemy.rect.left if enemy.melee_side < 0 else enemy.rect.right
                self.particles.dust(front + enemy.melee_side * 40, enemy.rect.bottom, 1.0)
            if (landed and not enemy.melee_struck
                    and self._melee_box(enemy, enemy.melee_side).colliderect(player)):
                enemy.melee_struck = True
                edge = player.left if enemy.melee_side > 0 else player.right
                point = (edge, player.centery)
                if self._deflects(enemy, enemy.rect.centerx):
                    enemy.melee_state = None          # the swing is cancelled
                    enemy.melee_cooldown = MELEE_COOLDOWN
                    self.handle_successful_parry(enemy, point)
                    return
                if self.hurt_timer == 0:
                    self.enemy_hit(enemy.contact_damage, enemy, point)
            if enemy.melee_timer <= 0 and enemy.melee_state == 'strike':
                enemy.melee_state, enemy.melee_timer = 'recover', MELEE_RECOVER
                enemy.melee_length = MELEE_RECOVER
        elif state == 'recover' and enemy.melee_timer <= 0:
            enemy.melee_state = None
            enemy.melee_cooldown = MELEE_COOLDOWN

    def update_enemy_combat(self, dt):
        for enemy in list(self.monsters):
            if not enemy.shoots_projectiles:
                self.update_melee(enemy, dt)
        for enemy in self.monsters:
            enemy.aiming = False     # the last TELEGRAPH_TIME before a shot it can fire
            if (not enemy.shoots_projectiles or not self._enemy_active(enemy)
                    or self.stunned(enemy)):
                continue
            enemy.shot_cooldown = max(0.0, enemy.shot_cooldown - dt)
            enemy.aiming = (enemy.shot_cooldown <= TELEGRAPH_TIME
                            and self._can_enemy_see_player(enemy))
            if enemy.shot_cooldown == 0 and enemy.aiming:
                start = self._muzzle(enemy)
                direction = pygame.Vector2(self.player.rect.center) - start
                if direction.length_squared():
                    direction.scale_to_length(PROJECTILE_SPEED)
                    self.projectiles.append(
                        Projectile(start, direction, enemy))
                    enemy.shot_cooldown = ENEMY_FIRE_INTERVAL
                    enemy.aiming = False
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
        self.threats = self.incoming_threats()

    # ---- telegraphs: what is about to hit the player, and from which side ---
    def _projectile_eta(self, projectile):
        """Seconds until a shot reaches the player on its course (None: it misses
        or a wall stops it first)."""
        box = self.player.rect.inflate(PROJECTILE_RADIUS * 2, PROJECTILE_RADIUS * 2)
        enter, leave = 0.0, math.inf
        for p, v, low, high in ((projectile.pos.x, projectile.velocity.x, box.left, box.right),
                                (projectile.pos.y, projectile.velocity.y, box.top, box.bottom)):
            if abs(v) < 1e-9:
                if not low <= p <= high:
                    return None
                continue
            a, b = sorted(((low - p) / v, (high - p) / v))
            enter, leave = max(enter, a), min(leave, b)
        if enter > leave:
            return None
        travel = projectile.velocity * enter
        steps = math.ceil(travel.length() / (CELL / 2))
        for n in range(1, steps):
            point = projectile.pos + travel * (n / steps)
            if self.world.solid(math.floor(point.x / CELL), math.floor(point.y / CELL)):
                return None
        return enter

    def incoming_threats(self):
        """Attacks that can hit within TELEGRAPH_TIME: (side, seconds, source).

        ``side`` is +1 if it comes from the player's right, -1 from the left;
        ``source`` is the enemy or Projectile. Shots on course, swings about to
        land on the player and enemies about to be touched all count, and mark
        the attacking enemy's ``telegraph_eta`` so its sprite flashes too.
        """
        for enemy in self.monsters:
            enemy.telegraph_eta = None
        if self.state != 'play':
            return []
        rect = self.player.rect
        threats = []
        for projectile in self.projectiles:
            eta = self._projectile_eta(projectile)
            if eta is not None and eta <= TELEGRAPH_TIME:
                side = 1 if projectile.pos.x >= rect.centerx else -1
                threats.append((side, eta, projectile))
                owner = projectile.owner
                if owner is not None:
                    prev = getattr(owner, 'telegraph_eta', None)
                    owner.telegraph_eta = eta if prev is None else min(prev, eta)
        for enemy in self.monsters:
            if self.stunned(enemy) or not self._enemy_active(enemy):
                continue
            side = 1 if enemy.rect.centerx >= rect.centerx else -1
            melee = getattr(enemy, 'melee_state', None)
            if melee in ('windup', 'strike'):
                if melee == 'windup':
                    left = enemy.melee_timer
                    if getattr(enemy, 'is_boss', False):
                        left += BOSS_MELEE_STRIKE / 2     # its blade lands mid-strike
                elif getattr(enemy, 'is_boss', False):
                    left = enemy.melee_timer - getattr(enemy, 'melee_length', 0.0) * 0.5
                    if left <= 0:
                        continue
                else:
                    continue
                if (left <= TELEGRAPH_TIME
                        and self._melee_box(enemy, enemy.melee_side).colliderect(rect)):
                    eta = max(0.0, left)
                    threats.append((side, eta, enemy))
                    prev = enemy.telegraph_eta
                    enemy.telegraph_eta = eta if prev is None else min(prev, eta)
                continue
            if enemy.rect.colliderect(rect):
                continue                               # already touching: no warning left
            if enemy.rect.bottom <= rect.top or enemy.rect.top >= rect.bottom:
                continue
            gap = enemy.rect.left - rect.right if side > 0 else rect.left - enemy.rect.right
            closing = (self.player.velocity.x - enemy.velocity.x) * side
            if closing > 0 and gap / closing <= TELEGRAPH_TIME:
                eta = gap / closing
                threats.append((side, eta, enemy))
                prev = enemy.telegraph_eta
                enemy.telegraph_eta = eta if prev is None else min(prev, eta)
        if self.hurt_timer > 0:        # after a hit the miner cannot be hurt for a moment
            threats = [threat for threat in threats if threat[1] >= self.hurt_timer]
        return threats

    def update(self, dt, horizontal=0, jump=False, vertical=0):
        dt = min(max(dt,0),MAX_FRAME_DT)
        self.metrics['physics_ms'] = self.metrics['fluid_ms'] = 0.
        self.door_cooldown = max(0.0, self.door_cooldown - dt)
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
            self.player.jump_buffer = 0.0
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
        self.potions.update(dt)
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
                if (enemy.shoots_projectiles or self.stunned(enemy)
                        or getattr(enemy, 'melee_state', None)
                        or self._in_melee_reach(enemy)):
                    # Stunned, swinging, or holding its ground in reach
                    # between swings (not shoving into the player, so every
                    # hit comes from a telegraphed swing): gravity and
                    # knockback only.
                    enemy.update(physics_dt, 0)
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
        self.dig_gain_timer = max(0.0, self.dig_gain_timer - dt)
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
        self.dying = [death for death in self.dying if not death.done(self.world_time)]
        self.bombs.update(dt)
        self.gun.update(dt)
        self.orbs.update(dt)
        self.gold_system.update(dt)
        if self.state != 'play':
            self.follow_camera(dt)
            return
        touching_enemies = []
        for enemy in self.monsters:
            if self.stunned(enemy) or not self.player.rect.colliderect(enemy.rect):
                continue
            if self._deflects(enemy, enemy.rect.centerx):
                enemy.attack_time = self.world_time     # its swing, caught by the guard
                edge = self.player.rect.right if self.parry_facing else self.player.rect.left
                self.handle_successful_parry(enemy, (edge, self.player.rect.centery))
            else:
                touching_enemies.append(enemy)
        if self.hurt_timer == 0 and touching_enemies:
            # One hit per contact (the 0.8 s grace stops repeats): one posture point.
            attacker = max(touching_enemies, key=lambda enemy: enemy.contact_damage)
            attacker.attack_time = self.world_time      # the swing animation lands now
            rect = self.player.rect
            edge = rect.right if attacker.rect.centerx >= rect.centerx else rect.left
            self.enemy_hit(attacker.contact_damage, attacker, (edge, rect.centery))
        self.engaged = self.scan_combat()
        start = time.perf_counter()
        self.emit(dt)
        self.particles.update(dt)
        self.fx.update(dt)
        self.miner.update(dt,self.player,self.dig_x)
        self.gun.face(self.miner)
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
        yield from self.bombs.lights()  # fuse sparks and explosions

    def draw(self, screen):
        start = time.perf_counter()
        # A zero-time follow cuts to the player after a teleport (restart,
        # scripted views) even when no update ran since the move.
        self.follow_camera(0)
        self.threats = self.incoming_threats()   # read by the overlay and the HUD
        camera = self.render_camera
        renderer = self.renderer
        renderer.draw_static(screen,camera)
        renderer.draw_animated(screen,camera,self.world_time)
        renderer.draw_liquids(screen,self.liquids,camera,
                              self.fluid_accumulator*FLUID_HZ,self.world_time)
        if self.stage_sign is not None:
            image, sign = self.stage_sign
            screen.blit(image, sign.move(-camera[0], -camera[1]))
        if self.key_pickup is not None:
            screen.blit(self.key_image, self.key_pickup.move(-camera[0], -camera[1]))
        self.draw_exit_door(screen, camera)
        for projectile in self.projectiles:
            center = (round(projectile.pos.x-camera[0]),
                      round(projectile.pos.y-camera[1]))
            pygame.draw.circle(screen,(255,190,88),center,PROJECTILE_RADIUS+2)
            pygame.draw.circle(screen,(226,73,43),center,PROJECTILE_RADIUS)
        for actor in self.monsters:
            if getattr(actor, 'is_boss', False):
                draw_boss(screen, actor, camera, self.world_time, self.player.rect.center)
                continue
            color = (220, 75, 65) if actor.shoots_projectiles else (111, 161, 77)
            draw_actor(screen,actor,color,camera,self.player.rect.center,self.world_time)
        for death in self.dying:
            death.draw(screen, camera, self.world_time)
        self.bombs.draw(screen,camera,self.world_time)
        self.gun.draw(screen,camera,self.world_time)
        self.potions.draw(screen,camera,self.world_time)
        self.orbs.draw(screen,camera,self.world_time)
        self.gold_system.draw(screen,camera,self.world_time)
        self.miner.draw(screen,self.player,camera,self.hurt_timer)
        self.gun.draw_gun(screen,camera,self.world_time)
        draw_parry(screen, self, camera)
        self.bombs.draw_carried(screen,camera,self.player.rect)
        self.particles.draw(screen,camera)
        renderer.draw_foreground(screen,camera)
        self.lighting.draw(screen,camera,self.world_time,self.light_sources(),
                           self.miner.head(self.player))
        draw_combat_overlay(screen, self, camera)   # emissive: after the light map
        self.bombs.draw_emissive(screen, camera, self.world_time)
        self.fx.draw_screen(screen)                 # edge flash and impact vignette
        self.metrics['render_ms'] = (time.perf_counter()-start)*1000
        self.draw_calls = (renderer.draw_calls+self.lighting.draw_calls+
                           len(self.monsters)+2+len(self.particles.items)+
                           2*len(self.projectiles))

    def draw_exit_door(self, screen, camera):
        door = self.exit_door.move(-camera[0], -camera[1])
        if self.final_boss_room:
            entry = self.renderer.scenery['entry_door']
            entry_rect = pygame.Rect(entry[0] * MACRO, entry[1] * MACRO,
                                     entry[2] * MACRO, entry[3] * MACRO)
            self._draw_mine_door(screen, entry_rect.move(-camera[0], -camera[1]),
                                 True, palette='gray')
            self._draw_final_gate(screen, door, self.exit_open)
            return
        if not self.bonus_room:
            self._draw_mine_door(
                screen, door,
                (self.has_key if self.stage_number in (1, 2) else self.exit_open),
                palette=('gold' if self.stage_number in (1, 2) else 'wood'))
            if self.bonus_door is not None:
                self._draw_mine_door(
                    screen, self.bonus_door.move(-camera[0], -camera[1]), True,
                    palette='gray')
            return
        self._draw_mine_door(screen, door, True, palette='gray')
        if self.return_sign:
            sign_width = max(door.width + 12, self.return_sign.get_width() + 8)
            sign = pygame.Rect(0, door.top - 18, sign_width, 14)
            sign.centerx = door.centerx
            pygame.draw.rect(screen, (47, 31, 24), sign)
            pygame.draw.rect(screen, (139, 92, 54), sign, 1)
            screen.blit(self.return_sign, self.return_sign.get_rect(center=sign.center))

    @staticmethod
    def _draw_mine_door(screen, door, opened, palette='wood'):
        palettes = {
            'wood': ((65, 43, 31), (125, 78, 43), (92, 57, 34)),
            'gray': ((47, 51, 56), (112, 119, 124), (76, 82, 87)),
            'gold': ((75, 48, 16), (173, 120, 35), (131, 87, 24)),
        }
        frame_color, door_color, post_color = palettes[palette]
        top = door.inflate(18, 8)
        pygame.draw.rect(screen, frame_color, top)
        pygame.draw.rect(screen, door_color, top.inflate(-5, -4))
        pygame.draw.rect(screen, (25, 22, 20), door.inflate(-4, -2))
        pygame.draw.rect(screen, post_color,
                         pygame.Rect(door.left - 5, door.top - 6, 5, door.height + 6))
        pygame.draw.rect(screen, post_color,
                         pygame.Rect(door.right, door.top - 6, 5, door.height + 6))
        if not opened:
            pygame.draw.line(screen, (139, 92, 54),
                             (door.left + 3, door.centery),
                             (door.right - 3, door.centery), 3)
            pygame.draw.circle(screen, (201, 61, 61),
                               (door.centerx, door.centery - 5), 3)
        else:
            pygame.draw.line(screen, (244, 194, 83),
                             (door.left + 3, door.top + 4),
                             (door.right - 3, door.top + 4), 2)

    @staticmethod
    def _draw_final_gate(screen, door, opened):
        """A fitted stone-and-iron exit, with its grille lifted after the boss."""
        surround = door.inflate(18, 10)
        lintel = pygame.Rect(surround.left - 3, surround.top - 5,
                             surround.width + 6, 8)
        pygame.draw.rect(screen, (24, 21, 29), surround)
        pygame.draw.rect(screen, (73, 72, 91), surround.inflate(-3, -3))
        pygame.draw.rect(screen, (43, 42, 57), door.inflate(2, 0))
        pygame.draw.rect(screen, (21, 20, 30), door.inflate(-4, -3))
        pygame.draw.rect(screen, (91, 87, 105), lintel)
        pygame.draw.line(screen, (131, 124, 137),
                         (lintel.left + 3, lintel.top + 1),
                         (lintel.right - 4, lintel.top + 1), 2)
        for x in (surround.left + 3, surround.right - 6):
            pygame.draw.rect(screen, (93, 89, 107),
                             (x, surround.top + 4, 3, surround.height - 8))
            pygame.draw.line(screen, (132, 125, 139),
                             (x + 1, surround.top + 5),
                             (x + 1, surround.bottom - 4), 1)
        if opened:
            pygame.draw.ellipse(screen, (54, 39, 68), door.inflate(-7, -5))
            pygame.draw.arc(screen, (143, 111, 157), door.inflate(-4, -2),
                            0.1, 3.04, 2)
            pygame.draw.ellipse(screen, (101, 75, 119), door.inflate(-15, -16), 1)
        else:
            for x in range(door.left + 5, door.right - 3, 9):
                pygame.draw.line(screen, (105, 107, 121),
                                 (x, door.top + 3), (x, door.bottom - 3), 2)
            for y in (door.top + 5, door.centery, door.bottom - 5):
                pygame.draw.line(screen, (87, 89, 105),
                                 (door.left + 3, y), (door.right - 3, y), 2)

def draw_actor(screen, actor, color, camera, target=None, time=0.0):
    """An enemy: its animated sprite (``target`` is the player's centre)."""
    _ensure_pygame()
    import enemy_sprites
    broken = getattr(actor, 'broken', False)
    blink = broken and int(getattr(actor, 'stun_timer', 0) * 8) % 2
    # Guard broken: the stun animation slumps and sways, and it flashes.
    if enemy_sprites.draw(screen, actor, camera, target, flash=bool(blink),
                          offset=(0, 3) if broken else (0, 0), time=time):
        return
    # Placeholder shape, used only if the sprite image is missing.
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
            deathblow_mark(screen, box.centerx, box.y - 16, t)
        else:
            dizzy(screen, box, t)
    if not game.combat.can_act() and game.state == 'play':
        player = game.player.rect.move(-camera[0], -camera[1])
        dizzy(screen, player, t, 4, (255, 214, 92), 2)
    draw_telegraphs(screen, game, camera)


def draw_telegraphs(screen, game, camera):
    """Warnings for attacks landing within TELEGRAPH_TIME: a contracting ring
    on each shot on course, and a blinking chevron at the miner's side the
    hit comes from (gold if the miner already faces it, red: turn to parry)."""
    threats = getattr(game, 'threats', None) or ()
    t = game.world_time
    nearest = {}
    for side, eta, source in threats:
        nearest[side] = min(nearest.get(side, TELEGRAPH_TIME), eta)
        if isinstance(source, Projectile):
            urgency = 1 - eta / TELEGRAPH_TIME
            blink = int(t * (14 if urgency < 0.5 else 24)) % 2
            center = (round(source.pos.x - camera[0]), round(source.pos.y - camera[1]))
            radius = PROJECTILE_RADIUS + 4 + round(5 * (1 - urgency))
            pygame.draw.circle(screen, (255, 250, 236) if blink else (255, 90, 60),
                               center, radius, 2)
    if not nearest:
        return
    box = game.player.rect.move(-camera[0], -camera[1])
    facing = 1 if game.miner.facing_right else -1
    for side, eta in nearest.items():
        urgency = max(0.0, min(1.0, 1 - eta / TELEGRAPH_TIME))
        blink = int(t * (14 if urgency < 0.5 else 24)) % 2
        base = (255, 214, 92) if side == facing else (240, 60, 40)
        color = (255, 250, 236) if blink else base
        size = 6 + round(3 * urgency)
        # Slides in toward the miner as the hit nears; the tip points at the threat.
        x = box.centerx + side * (box.w // 2 + 6 + round(6 * (1 - urgency)))
        y = box.centery - 2
        notch = max(2, size // 2)
        pygame.draw.polygon(screen, (19, 19, 25), [(x + side * (size + 3), y),
                                                   (x - side * 2, y - size - 3),
                                                   (x + side * (notch - 2), y),
                                                   (x - side * 2, y + size + 3)])
        pygame.draw.polygon(screen, color, [(x + side * size, y),
                                            (x, y - size),
                                            (x + side * notch, y),
                                            (x, y + size)])


def draw_boss(screen, boss, camera, world_time, target=None):
    """The Stage 6 Abyssal Volcanic Ruin Colossus boss sprite with its health readout above it."""
    _ensure_pygame()
    import enemy_sprites
    box = boss.rect.move(-camera[0], -camera[1])
    flash = boss.hurt_timer > 0 and int(world_time * 20) % 2 == 0
    rock = round(math.sin(world_time * 18) * 2) if getattr(boss, 'broken', False) else 0
    art = enemy_sprites.sprite('boss')
    if enemy_sprites.draw(screen, boss, camera, target, flash=flash,
                          offset=(rock, 5 if rock or getattr(boss, 'broken', False) else 0),
                          time=world_time):
        top = box.bottom - art.get_height() + 4
        for n in range(boss.max_hp):
            color = (226, 73, 43) if n < boss.hp else (60, 40, 40)
            pygame.draw.rect(screen, color, (box.centerx - boss.max_hp * 7 + n * 14, top - 12, 11, 6))
        return
    # Placeholder shape, used only if the sprite image is missing.
    if not box.colliderect(screen.get_rect()):
        return
    top = box.y                            # the health readout does not sag
    if getattr(boss, 'broken', False):     # staggered: sagging, rocking
        box = pygame.Rect(box.x + rock, box.y + 5, box.w, box.h - 5)
    pygame.draw.rect(screen, (19, 19, 25), box, border_radius=6)
    pygame.draw.rect(screen, (240, 210, 240) if flash else (158, 52, 184),
                     box.inflate(-6, -4), border_radius=5)
    pygame.draw.rect(screen, (96, 30, 120), (box.x + 6, box.bottom - 16, box.w - 12, 10))
    for eye in (box.x + box.w // 3 - 4, box.x + 2 * box.w // 3 - 4):
        pygame.draw.rect(screen, (255, 214, 92), (eye, box.y + box.h // 3, 8, 6))
    for n in range(boss.max_hp):
        color = (226, 73, 43) if n < boss.hp else (60, 40, 40)
        pygame.draw.rect(screen, color, (box.centerx - boss.max_hp * 7 + n * 14, top - 12, 11, 6))


def next_stage_number(stage, total_stages=FINAL_STAGE):
    if total_stages <= 0:
        raise ValueError('total_stages must be positive')
    if not 1 <= stage < total_stages:
        raise ValueError(f'No stage follows stage {stage}')
    return stage + 1


def parent_stage_number(game):
    """Whole-number stage identity for a main stage or its half-stage room."""
    if game.final_boss_room:
        return 5
    return game.stage_number


def retry_stage_number(game):
    """Restart at the whole-number stage that owns the current room."""
    return parent_stage_number(game)


def retry_gold_checkpoint(game):
    """Gold to restore when retrying this level attempt."""
    return game.gold_checkpoint


class SkipSequence:
    """Recognize the hidden skip code when its letters arrive within a window."""

    def __init__(self, sequence='skip', window=2.0):
        self.sequence = sequence
        self.window = window
        self.buffer = ''
        self.started_at = None

    def reset(self):
        self.buffer = ''
        self.started_at = None

    def feed(self, text, now):
        if self.started_at is not None and now - self.started_at > self.window:
            self.reset()
        if not isinstance(text, str) or len(text) != 1 or not text.isalpha():
            self.reset()
            return False
        character = text.lower()
        candidate = self.buffer + character
        if self.sequence.startswith(candidate):
            self.buffer = candidate
            if candidate == self.sequence:
                self.reset()
                return True
            if self.started_at is None:
                self.started_at = now
            return False
        self.buffer = 's' if character == self.sequence[0] else ''
        self.started_at = now if self.buffer else None
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames',type=int,default=0,help='Exit after N frames for smoke testing.')
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--uncapped',action='store_true')
    parser.add_argument('--profile',type=Path,help='Save measured frame/system costs as JSON.')
    parser.add_argument('--bombs',action='store_true',help='Place bomb pickups even in stages without bombs (for testing).')
    parser.add_argument('--stage', type=int, choices=range(1, FINAL_STAGE + 1),
                        help='Stage to launch; defaults to Stage 1.')
    parser.add_argument('--boss-room-test', action='store_true',
                        help='Start directly in the Stage 5.5 boss room for testing.')
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

    def _create_display(fullscreen=False):
        if args.headless:
            return pygame.display.set_mode((SCREEN_W, SCREEN_H), vsync=0)
        flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE)
        try:
            return pygame.display.set_mode((SCREEN_W, SCREEN_H), flags, vsync=0)
        except pygame.error:
            return pygame.display.set_mode((SCREEN_W, SCREEN_H), vsync=0)

    screen = _create_display(False)
    import parry_fx
    parry_fx.warm()      # combat effect frames, so the first parry never hitches
    pygame.display.set_caption('Dig Game — Stage 1: Abandoned Mine')
    art = TileArt(CELL,MACRO)
    lighting = Lighting((SCREEN_W,SCREEN_H))
    debug_font = pygame.font.SysFont('monospace',16)
    start_in_boss_room = args.boss_room_test
    start_stage = (5 if start_in_boss_room else
                   1 if args.stage is None else args.stage)
    game = Game(art,lighting,bombs=args.bombs,stage=start_stage,seed=args.seed,
                bonus_room=start_in_boss_room)
    return_game = None
    ui = GameUI()
    selected_stage = start_stage
    if args.headless or args.stage is None or start_in_boss_room:
        ui.start(game)  # Preserve the gameplay path for automated smoke/profile runs.
    clock = pygame.time.Clock()
    frames,debug,running = 0,False,True
    costs,frame_times,samples = [],[],[]

    def _start_new_game():
        nonlocal game, selected_stage, return_game
        selected_stage = 1
        return_game = None
        game = Game(art, lighting, bombs=args.bombs, stage=selected_stage)
        ui.start(game)

    def _toggle_fullscreen(enable):
        nonlocal screen
        screen = _create_display(enable)

    def _exit_game():
        nonlocal running
        running = False

    ui.on_start_play = _start_new_game
    ui.on_toggle_fullscreen = _toggle_fullscreen
    ui.on_exit_game = _exit_game

    def activate(label):
        nonlocal game, running, selected_stage, return_game
        if label == 'PLAY':
            ui.trigger_menu_action('PLAY')
        elif label == 'SETTINGS':
            ui.trigger_menu_action('SETTINGS')
        elif label == 'EXIT':
            ui.trigger_menu_action('EXIT')
        elif label == 'START GAME':
            ui.screen = 'stage_select'
        elif label in ('STAGE 1', 'STAGE 2', 'STAGE 3', 'STAGE 4', 'STAGE 5'):
            selected_stage = int(label[-1])
            game = Game(art, lighting, bombs=args.bombs, stage=selected_stage)
            ui.start(game)
        elif label == 'PLAY AGAIN':
            selected_stage = 1
            game = Game(art, lighting, bombs=args.bombs, stage=selected_stage)
            ui.start(game)
        elif label == 'CANCEL RESTART':
            ui.close_restart_confirm()
        elif label in ('RESTART', 'RETRY', 'CONFIRM RESTART'):
            restarting_bonus = game.bonus_room
            selected_stage = retry_stage_number(game)
            game = Game(art, lighting, bombs=args.bombs, stage=selected_stage,
                        seed=None if restarting_bonus else game.seed,
                        starting_gold=retry_gold_checkpoint(game))
            return_game = None
            ui.start(game)
        elif label == 'NEXT STAGE' and game.state == 'win':
            selected_stage = next_stage_number(parent_stage_number(game))
            game = Game(art, lighting, bombs=args.bombs, stage=selected_stage,
                        starting_gold=game.gold)
            ui.start(game)
        elif label == 'BACK TO MENU':
            ui.open_menu(replay_intro=False)
        elif label == 'RESUME':
            skip_sequence.reset()
            ui.screen = 'game'
        elif label == 'HOW TO PLAY':
            ui.controls_from = ui.screen
            ui.screen = 'controls'
        elif label == 'BACK':
            if ui.screen == 'menu':
                ui.trigger_menu_action('BACK')
            else:
                ui.screen = ui.controls_from
        elif label == 'MAIN MENU':
            ui.open_menu(replay_intro=False)
        elif label == 'QUIT':
            running = False


    skip_sequence = SkipSequence()
    q_held = False
    gun_mouse = gun_key = False   # right button / F holding the dirt gun

    def skip_to_next_stage():
        nonlocal game, selected_stage, return_game
        if game.final_boss_room or game.stage_number >= FINAL_STAGE:
            game.state = 'win'
            ui.screen = 'game'
            return
        selected_stage = next_stage_number(parent_stage_number(game))
        game = Game(art, lighting, bombs=args.bombs, stage=selected_stage,
                    starting_gold=game.gold)
        return_game = None
        ui.start(game)

    def pull_trigger(screen_pos):
        """Fire the dirt gun once now, toward a screen point."""
        if ui.screen == 'game':
            cx,cy = game.render_camera
            game.gun.aim = (screen_pos[0]+cx,screen_pos[1]+cy)
            game.gun.fire()

    def is_f(event):
        """The F key by its position (dirt pistol), any keyboard layout."""
        return event.key == pygame.K_f or getattr(event, 'scancode', None) == pygame.KSCAN_F

    def is_q(event):
        """The Q key by its position, so a Thai (or any) layout works too."""
        return event.key == pygame.K_q or getattr(event, 'scancode', None) == pygame.KSCAN_Q

    def throw_bomb(screen_pos):
        """Throw a carried bomb toward a screen point (mouse or Q release)."""
        if ui.screen == 'game' and game.can_act() and game.bombs.carried:
            cx,cy = game.render_camera
            game.bombs.throw((screen_pos[0]+cx,screen_pos[1]+cy))
        game.bombs.aim = None
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
            elif event.type == pygame.MOUSEMOTION:
                ui.handle_mouse_motion(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP:
                ui.handle_mouse_up(event.pos, event.button)
                if event.button == 3:
                    gun_mouse = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                # Right button: the dirt gun (hold for repeat fire). The
                # first shot goes out on the press itself, so a touchpad's
                # two-finger tap (press and release in one frame) fires too.
                gun_mouse = ui.screen == 'game'
                pull_trigger(event.pos)
            elif event.type in (pygame.KEYDOWN, pygame.KEYUP) and is_f(event):
                gun_key = event.type == pygame.KEYDOWN and ui.screen == 'game'
                if gun_key:
                    pull_trigger(pygame.mouse.get_pos())
            elif event.type == pygame.KEYDOWN and is_q(event):
                q_held = True
            elif event.type == pygame.KEYUP and is_q(event):
                # Q throws bombs: hold to aim at the cursor (shows the arc),
                # release to throw there.
                q_held = False
                throw_bomb(pygame.mouse.get_pos())
            elif event.type == pygame.KEYDOWN:
                if ui.screen == 'paused' and skip_sequence.feed(
                        getattr(event, 'unicode', ''), time.monotonic()):
                    skip_to_next_stage()
                    continue
                if ui.screen != 'paused':
                    skip_sequence.reset()
                if ui.confirm_restart_open:     # the sign takes every key
                    action = ui.handle_restart_confirm_key(event.key)
                    if action:
                        activate(action)
                    continue
                if ui.screen == 'game' and event.key in (
                        pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
                    ui.dialog.dismiss()     # Space still jumps below
                if ui.screen == 'menu':
                    ui.handle_menu_key(event.key)
                elif event.key == pygame.K_ESCAPE:
                    if ui.screen == 'controls':
                        ui.screen = ui.controls_from
                    elif ui.screen == 'stage_select':
                        ui.open_menu(replay_intro=False)
                    elif ui.screen == 'paused':
                        skip_sequence.reset()
                        ui.screen = 'game'
                    elif ui.screen == 'game' and game.state == 'play':
                        ui.screen = 'paused'
                elif event.key == pygame.K_r and ui.screen in ('game', 'paused'):
                    if game.state == 'play':
                        ui.open_restart_confirm()   # asks first; the game waits
                    else:
                        activate('RESTART')         # end screens: retry at once
                elif event.key == pygame.K_F3 and ui.screen == 'game':
                    debug = not debug
                elif event.key == pygame.K_e and ui.screen == 'game':
                    # KEYDOWN only (no key repeat), so holding E parries once.
                    game.press_e()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if ui.screen == 'paused':
                        activate('RESUME')
                elif ui.screen == 'game' and event.key in (pygame.K_SPACE,pygame.K_w,pygame.K_UP):
                    jump |= jump_requested(event.key,
                                           game.renderer.ladder_at(game.player.rect))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if ui.screen == 'menu':
                    ui.handle_mouse_down(event.pos, event.button)
                else:
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
                and q_held):
            mx,my = pygame.mouse.get_pos()
            cx,cy = game.render_camera
            game.bombs.aim = (mx+cx,my+cy)
        else:
            game.bombs.aim = None       # released, or the guard is broken
        if ui.screen == 'game':
            mx,my = pygame.mouse.get_pos()
            cx,cy = game.render_camera
            game.gun.aim = (mx+cx,my+cy)
            game.gun.held = gun_mouse or gun_key
        else:
            game.gun.held = gun_mouse = gun_key = False
        if ui.screen == 'game' and game.state == 'play':
            ui.note_input(horizontal, jump, vertical, digging, game)
            game.update(frame_dt,horizontal,jump,vertical)
            if game.state == 'enter_bonus':
                return_game = game
                bonus = Game(art, lighting, bombs=args.bombs,
                             stage=return_game.stage_number, bonus_room=True,
                             return_game=return_game)
                bonus.inherit_player_state(return_game)
                bonus.door_cooldown = 3.0
                bonus.door_locked_until_exit = True
                game = bonus
                ui.start(game)
            elif game.state == 'return_stage':
                if game.return_game is None:
                    raise RuntimeError('Bonus room has no originating stage')
                return_game = game.return_game
                return_game.has_key = return_game.has_key or game.key_collected
                return_game.inherit_player_state(game)
                return_game.door_cooldown = 3.0
                return_game.door_locked_until_exit = True
                return_game.player.pos.update(return_game.bonus_door.topleft)
                return_game.player._sync_rect()
                game = return_game
                game.state = 'play'
                ui.start(game, intro=False)
        ui.update(frame_dt, game)
        if ui.exit_requested:
            running = False
        if ui.screen != 'menu':
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
