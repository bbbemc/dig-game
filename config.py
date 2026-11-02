"""Shared tuning in pixels and seconds; the simulation grid remains 8 pixels."""
CELL = 8
SCALE = 5
MACRO = CELL * SCALE
SCREEN_W, SCREEN_H = 960, 640
FPS = 60
PRECISE_FRAME_PACING = True
MAX_FRAME_DT = 0.1
PHYSICS_HZ = 120
FLUID_HZ = 40
GRAVITY = 1100.0
MAX_FALL_SPEED = 560.0
MOVE_SPEED = 176.0
JUMP_SPEED = 340.0
SWIM_SPEED = 130.0
WATER_MOVE_SPEED = 80.0
OXYGEN_DRAIN_TIME = 20.0
OXYGEN_REFILL_TIME = 7.0
OXYGEN_DAMAGE = 25
OXYGEN_DAMAGE_INTERVAL = 1.0
LADDER_JUMP_GRACE = 0.18
PLAYER_SIZE = 32
DIG_RADIUS = 3
ENEMY_SIGHT_RANGE = 450
ENEMY_FIRE_INTERVAL = 1.25
WALKER_SIZE = 40
WALKER_SPEED = 48.0
WALKER_PATROL_RANGE = 2 * MACRO
WALKER_CHASE_MEMORY = 5.0
ENEMY_CONTACT_DAMAGE = 20
WALKER_CONTACT_DAMAGE = 25
PROJECTILE_SPEED = 240.0
PROJECTILE_DAMAGE = 50
PROJECTILE_RADIUS = 4
BOMB_STAGES = (1, 2, 3, 4, 5, 6)  # stages with bomb pickups
BOMB_SPAWN_COUNT = 3     # pickups chosen at random from a stage's spots
BOMB_MAX_CARRY = 3
BOMB_THROW_SPEED = 360.0
BOMB_FUSE = 2.0          # seconds from throw to explosion
BOMB_SIZE = 20
BOMB_RADIUS = 6          # blast radius in cells (8 px each)
BOMB_PLAYER_DAMAGE = 20
CHUNK_CELLS = 40
MAX_PARTICLES = 150
MOTE_LIMIT = 18          # drifting dust specks in lantern light
EMBER_INTERVAL = 0.11    # seconds between embers from visible lava
CAMERA_FOLLOW = 14.0     # 1/s; higher follows tighter (no input delay)
SHAKE_DECAY = 1.6        # trauma lost per second
WATER_FLOW_RATE = 1.0
WATER_GRAVITY_STEPS = 4
LAVA_FLOW_RATE = 0.1375  # Preserves lava's former per-second flow at 40 Hz.
MIN_FLOW_UNITS = 8  # 8/1024 cell; below a visible quarter-pixel surface change.
REACTION_DURATION = 0.48
REACTION_STEP_LIMIT = 128

# Expanded worlds: every stage is a generated four-layer world (B1-B4).
# Sizes are macro tiles (MACRO = 40 px); the original stages were 24 x 16.
BASE_COLUMNS, BASE_ROWS = 24, 16
WORLD_WIDTH_MULTIPLIER = 5     # world width  = BASE_COLUMNS x this
WORLD_HEIGHT_MULTIPLIER = 5    # world height ~ BASE_ROWS x this (4 layers + border)
DEEP_COLUMNS = BASE_COLUMNS * WORLD_WIDTH_MULTIPLIER
DEEP_LAYER_ROWS = -(-(BASE_ROWS * WORLD_HEIGHT_MULTIPLIER - 2) // 4)  # rows per layer
# Layout seed per stage: an int gives the same world every run, None a new one.
STAGE_SEEDS = {1: 1101, 2: 2203, 3: 3307, 4: 4409, 5: 5519, 6: None}
DEEP_SEED = STAGE_SEEDS[6]     # kept for The Deep Descent's default
DEEP_OPEN_RANGE = (0.27, 0.36)  # share of open cave per layer; the rest is terrain
DEEP_BOMB_PICKUPS = 12     # world pickups chosen from candidate spots (plus authored ones)
BOSS_SIZE = 64
BOSS_SPEED = 62.0
BOSS_HP = 3                # bomb blasts needed (stage profiles may lower it); lava kills
BOSS_CONTACT_DAMAGE = 35

# Large-world performance limits. The authored stages fit inside all of them.
LIQUID_SIM_RADIUS = 170    # cells around the player in which moving liquid steps
ENEMY_ACTIVE_RANGE = (1400, 1000)  # px (x, y); enemies farther away pause
CHUNK_CACHE_LIMIT = 48     # cached 320 px chunks kept before far ones are evicted

# Parry (E). Timers are seconds of game time; pause and hitstop freeze them.
# Press -> ACTIVE (the window) -> RECOVERY -> COOLDOWN -> ready again.
PARRY_ACTIVE_TIME = 0.20   # PARRY_WINDOW: an enemy attack in front is deflected
PARRY_RECOVERY_TIME = 0.12 # after the window: guard lowers, no parry
PARRY_COOLDOWN = 0.65      # then no new parry until ready (0.97 s press to press)
PARRY_STUN_DURATION = 0.6  # a parried enemy cannot move, shoot or hurt
PARRY_KNOCKBACK = 340.0    # px/s horizontal push on the attacker (scaled by size)
PARRY_KNOCKBACK_LIFT = 180.0  # px/s upward pop
PARRY_KNOCKBACK_DECAY = 7.0   # 1/s; how quickly the push fades
PARRY_FRONT_TOLERANCE = 6  # px behind the player's centre still counted as front
# A deflect is "perfect" when the hit lands this soon after the press (a late,
# tight press, as in Sekiro); later in the window it is a normal parry.
PARRY_PERFECT_TIME = 0.08
PARRY_HITSTOP = 0.07       # combat freeze on a parry (liquids keep flowing)
PERFECT_PARRY_HITSTOP = 0.10
PARRY_FLASH_TIME = 0.08    # white/gold impact flash at the collision point
PARRY_SHAKE_TIME = 0.12    # camera kick, easing back to rest (px are the peak)
PARRY_SHAKE_PX = 3
PERFECT_SHAKE_TIME = 0.18
PERFECT_SHAKE_PX = 5
PERFECT_RECOIL_PX = 4      # the view also recoils this far along the attack
PARRY_SPARKS = 30          # trail sparks per parry (pooled, see parry_fx.py)
PERFECT_SPARKS = 44

# Posture (Sekiro-style). Points, not a gauge: each failed defence adds one.
PLAYER_MAX_POSTURE = 3
PLAYER_STUN_DURATION = 1.5 # guard broken: no move, jump, parry, bombs or digging
GUARD_BREAK_TIME = 0.35    # its first part is the GUARD_BROKEN recoil, then STUNNED
POSTURE_RECOVERY_DELAY = 4.0     # seconds without a posture hit before recovery...
POSTURE_RECOVERY_INTERVAL = 2.0  # ...then one point back per interval (2 -> 1 at 6 s)
GUARD_BREAK_HITSTOP = 0.14
GUARD_BREAK_SHAKE_TIME = 0.32    # the strongest kick
GUARD_BREAK_SHAKE_PX = 8
GUARD_BREAK_KNOCKBACK = 170.0    # px/s backward stagger of the broken miner
ENEMY_BREAK_HITSTOP = 0.12       # an enemy's guard breaking, or a deathblow
NORMAL_ENEMY_MAX_POSTURE = 3     # perfect parries that break a walker or shooter
BOSS_MAX_POSTURE = 6
ENEMY_STUN_DURATION = 2.0        # broken enemy: helpless, open to a deathblow (E)
BOSS_STAGGER_DURATION = 1.0      # a broken boss only staggers; HP and lava as before
ENEMY_POSTURE_RECOVERY_DELAY = 4.0
ENEMY_POSTURE_RECOVERY_INTERVAL = 2.0
DEATHBLOW_REACH = 24       # px beyond the player's box a broken enemy can be finished

# Player posture bar: bottom centre, shown only around combat.
POSTURE_BAR_WIDTH = 330
POSTURE_BAR_HEIGHT = 16
POSTURE_BAR_Y = SCREEN_H - 75  # centre line of the bar
COMBAT_RANGE = (420, 260)      # px (x, y): enemies this close and hunting = combat
POSTURE_BAR_HOLD = 4.0         # seconds after combat ends before the bar fades out

# Sound effects (assets/audio/combat, see audio.py).
SFX_VOLUME = 0.8           # master SFX volume, separate from music (0..1)
SFX_MIN_INTERVAL = 0.05    # s; the same event cannot restart faster than this
SFX_MAX_INSTANCES = 2      # copies of one event that may ring at once
SFX_PITCH_JITTER = 0.04    # variants +-4% in pitch (0 disables)
SFX_HEADROOM = 0.95        # summed peak of sounds starting together (no clipping)
SFX_ONSET_WINDOW = 0.08    # s; sounds closer than this share that budget
