"""Every stage as a large generated world: profiles and authored chambers.

Each stage keeps its identity in two ways:

* a profile tunes the shared generator (levels/deep_world.py): cave density,
  rock, reservoirs, lakes, caverns and the boss's toughness;
* stages 1-5 embed their original 24 x 16 map, unchanged, as the opening
  chamber at the world's top-left. Its puzzle, enemies, pickups and props
  keep their authored coordinates. A gate in its right wall leads into the
  four layers B1-B4, which end in the boss arena and the real exit.

Generated stages are cached per (stage, seed); callers get a deep copy.
"""

import copy

from config import STAGE_SEEDS

PROFILES = {
    1: {'hint': 'Leave the old mine through its far door.', 'boss_hp': 1,
        'cave_bias': -0.02, 'water_tanks': (2, 2, 1, 1), 'pairs': (0, 1, 1, 1),
        'lava_pockets': (0, 0, 1, 2)},
    2: {'hint': 'Climb the ledges above the flooded mine.', 'boss_hp': 2,
        'water_tanks': (3, 3, 2, 2), 'pairs': (0, 1, 1, 1),
        'lakes': ((0, 'W', 1), (1, 'W', 2), (2, 'W', 2), (3, 'L', 1))},
    3: {'hint': 'Dig through the caverns; mind the lava.', 'boss_hp': 2,
        'cave_bias': 0.03, 'rock_bias': 0.03, 'lava_pockets': (0, 1, 2, 2),
        'caverns': (1, 2, 1, 2), 'lakes': ((1, 'L', 1), (2, 'W', 1), (3, 'L', 2))},
    4: {'hint': 'Find the bomb and break the gate.', 'boss_hp': 3,
        'stone': 0.8, 'pockets': (2, 2, 2, 2),
        'lakes': ((0, 'W', 1), (1, 'W', 2), (2, 'W', 3), (3, 'L', 1))},
    5: {'hint': 'Cool the lava seam with the flooded tank.', 'boss_hp': 3,
        'rock_bias': -0.02, 'pairs': (1, 2, 2, 2), 'lava_pockets': (0, 1, 2, 3)},
    6: {'hint': None, 'boss_hp': 3},
}
# The standing row of each chamber's gate. Stage 3's door pocket sits under
# a lava channel, so its gate opens higher, behind the diggable east chamber.
GATE_ROWS = {3: 7}
_cache = {}


def authored_level(stage):
    """The original 24 x 16 stage: (rows, entities, scenery, optional_rooms)."""
    if stage == 1:
        from levels.stage_one import build_stage_one as build
    elif stage == 2:
        from levels.stage_two import build_stage_two as build
    elif stage == 3:
        from levels.stage_three import build_stage_three as build
    elif stage == 4:
        from levels.stage_four import build_stage_four as build
    elif stage == 5:
        from levels.stage_five import build_stage_five as build
    else:
        raise ValueError(f'Stage {stage} has no authored map')
    return build()


def chamber_for(stage):
    rows, entities, scenery, _ = authored_level(stage)
    door_x, door_y, door_w, door_h = scenery['exit_door']
    return {'rows': rows, 'entities': entities, 'scenery': scenery,
            'gate_row': GATE_ROWS.get(stage, door_y + door_h - 1)}


def build_stage(stage, seed=None):
    """Generate stage ``stage`` as a four-layer world; returns level tuples."""
    from levels.deep_scenery import decorate
    from levels.deep_world import generate_deep_world

    if stage not in PROFILES:
        raise ValueError(f'Unknown stage: {stage}')
    if seed is None:
        seed = STAGE_SEEDS.get(stage)
    key = (stage, seed)
    if seed is None or key not in _cache:
        profile = {k: v for k, v in PROFILES[stage].items() if k not in ('hint', 'boss_hp')}
        chamber = chamber_for(stage) if stage != 6 else None
        generator, rows = generate_deep_world(seed, profile=profile, chamber=chamber)
        scenery = decorate(generator, rows)
        scenery['boss_hp'] = PROFILES[stage]['boss_hp']
        scenery['hint'] = PROFILES[stage]['hint']
        entities = {kind: list(points) for kind, points in generator.entities.items()}
        result = (rows, entities, scenery, [])
        if seed is None:
            return result
        _cache[key] = result
    return copy.deepcopy(_cache[key])
