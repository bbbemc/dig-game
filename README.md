# Dig Game — Stage 1: Abandoned Mine

Install Python and dependencies, then launch:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Requires **pygame-ce 2.5.8** (`import pygame`). Do not install classic `pygame`
in the same environment.

## Controls

- **A/D or Left/Right:** walk left/right.
- Walking slows while in water.
- **W or Up:** jump away from ladders; climb up while on a ladder.
- **S or Down:** climb down while on a ladder.
- **Space:** jump even while on a ladder; in water, a buoyant stroke.
- **Left mouse anywhere on screen:** excavate visible dirt. Rock and cooled stone remain solid.
- **Esc:** pause/resume or go back from controls. **R:** restart during play.
- **F3:** optional performance overlay during play.

The main menu offers Start Game, How to Play, and Quit. Start Game opens a
stage selector for Abandoned Mine, The Sinking Mine, Dirt Caverns, Water
Chamber, The Sinking Mine (Stage 5) and The Deep Descent (Stage 6). The
in-game UI uses compact health and oxygen bars plus a current-area sign; control
prompts appear only in context.
The pause menu freezes gameplay and offers Resume, Restart, How to Play, and
Main Menu. Win and game-over screens retain the last gameplay scene behind a
darkened panel.

Each original stage is a separate layout module in `levels/` (a 24 × 16
macro-tile map), now used as the opening chamber of that stage's world. Abandoned Mine has a raised spawn shelf, ladder, upper water
basin and lower lava pocket. The Sinking Mine has a deep water basin, a stepped
platform route, water-filled side channels, stone-faced indestructible
platforms, a lowered projectile enemy, and bomb pickups. Dirt Caverns has a
raised starting shelf, ladder shaft, flooded cache, lava channels and a dirt
chamber. Water Chamber has a deep swimmable pool, a rock barrier, piers, a
submerged bomb pickup, a projectile guard, and a bombable stone gate. Each stage
uses existing sprite-sheet props as visual-only scenery;
they do not change terrain or collision.
Reach the exit to finish a stage. Enemies can be defeated by leading them
into lava.
Touching lava instantly kills the player or an enemy. When water touches lava,
all water evaporates with surrounding steam and all lava hardens into stone.
Water flows faster through the level. Original mine,
cave, crystal and ruin sprites remain as decoration.
The oxygen meter drains over about 20 seconds while the player is fully
submerged, refills over about 7 seconds out of water, and causes 25 damage per
second while empty and submerged.

## Expanded worlds (every stage)

Every stage is now a generated four-layer world of 120 × 82 macro tiles
(4800 × 3280 px, 246,000 simulation cells): 5× wider and ~5× deeper than the
original 24 × 16 single-screen maps, about 25× the area. Each world descends
through B1 Abandoned Mine → B2 Dirt Cave → B3 Crystal Cave → B4 Volcanic Ruins.
The main route zig-zags right, left, right, left down to the boss arena at the
bottom left, where the exit is. Every layer is roughly 64–75 % solid,
mostly diggable dirt, so you can always dig your own shortcuts.

| Stage | Before | After | Opening map | Profile |
|---|---|---|---|---|
| 1 Abandoned Mine | 24 × 16 | 120 × 82 | original stage 1 | drier, mine-heavy; boss 1 hit |
| 2 The Sinking Mine | 24 × 16 | 120 × 82 | original stage 2 | many tanks and lakes; boss 2 |
| 3 Dirt Caverns | 24 × 16 | 120 × 82 | original stage 3 | more caves, less rock, lava lakes; boss 2 |
| 4 Water Chamber | 24 × 16 | 120 × 82 | original stage 4 | big lakes, stone seams, extra bombs; boss 3 |
| 5 The Sinking Mine | 24 × 16 | 120 × 82 | original stage 5 | water-over-lava pairs, more rock; boss 3 |
| 6 The Deep Descent | 64 × 74 | 120 × 82 | generated mine camp | balanced; new layout each run; boss 3 |

Stages 1–5 embed their original map, unchanged and at its authored
coordinates, at the world's top-left. Its old exit door is now a gate in its
east wall, and the route carries on from there. The real exit opens when the
boss falls: release the lava tank above the arena or bomb the boss. Other
enemies are optional. Restart keeps the same layout.

Generation (`levels/deep_world.py`): cellular-automata caves → stair-stepped
zig-zag route with landmark rooms (galleries, excavation chambers, grottos,
crystal rooms, ruins, enemy rooms) and drop shafts with ladders → sealed
water/lava reservoirs and hidden bomb pockets → massive off-route caverns with
floating ledges → noise rock formations → open-share balancing → lakes and
lava lakes in isolated caverns → validation. Validation checks a physics-style
walk from the gate to the exit, dig reachability of every enemy and pickup,
and that water and lava don't touch at start. A seed that fails validation is
retried. Stage profiles live in `levels/expanded.py`; biome decoration is in
`levels/deep_scenery.py`.

Size and tuning live in `config.py`: `WORLD_WIDTH_MULTIPLIER` /
`WORLD_HEIGHT_MULTIPLIER` (relative to 24 × 16), `STAGE_SEEDS`,
`DEEP_OPEN_RANGE` (cave share), `DEEP_BOMB_PICKUPS` and `BOSS_*`.
Large-world performance limits: `LIQUID_SIM_RADIUS`, `ENEMY_ACTIVE_RANGE`,
`CHUNK_CACHE_LIMIT`.

```sh
.venv/bin/python main.py --headless --stage 4 --frames 600 --profile /tmp/stage4.json
```

## Systems

- `world.py`: permanent rear walls and independent mutable foreground collision.
- `physics.py`: float positions, fixed-step gravity, grounded spawn and swept tile collision.
- `main.py`: shooters fire 50-damage projectiles when the player is in clear sight; larger walkers patrol a configurable range, reverse at walls, and deal 25 contact damage. Enemies fall under gravity; entering the exit completes the stage.
- `liquids.py`: conservative transfers, faster water flow, and evaporation/solidification of the touching water and lava bodies on contact (other pools are unaffected and can react later); moving liquid steps only within `LIQUID_SIM_RADIUS` of the player.
- `rendering.py`: visible 320-pixel chunk caches (opaque rear layer, transparent front
  layer), one neighbouring chunk prefetched on quiet frames, far chunks evicted past
  `CHUNK_CACHE_LIMIT`, lights indexed by chunk, exposed-edge lips/undersides/rounded corners,
  rear-wall occlusion, interpolated fluids.
- `terrain_art.py`: seamless ground mosaics built from the sheet's own tiles, dark mine
  walls, per-macro detail variants and edge pieces.
- `scenery.py`: original mine/cave/ruin props, composite timber and supported
  decorations for the first stage.
- `lighting.py`: screen light map (depth ambient, vignette, flickering lamps, lava and
  the miner's helmet lamp) plus warm additive bloom.
- `actors.py`, `pixel_art.py`: the animated miner and small hand-authored sprites.
- `effects.py`: pooled particles (dig debris, landing dust, embers, splashes, dust motes).
- `tiles.py`: supplied sprite source rectangles and preloaded art caches.
- `config.py`: physics, flow, reaction, particle, camera and performance tuning.
- `ui.py`: pixel-aligned HUD, contextual hints, area transitions and menus.

## Visual layers

Back to front: rear wall (texture, faint slabs, pick marks, soft occlusion) → distant and
rear timber, ladders, contact shadows → seamless ground with sparse details
(65% plain, 15% tone, 8% stones, 6% cracks, 4% dark, 2% rare) and exposed edges →
props → liquids → actors and particles → sparse foreground roots → lighting → HUD.
Edges, fillets and foreground pieces are visual only; collision stays on the 8-pixel grid.

Opaque layers are composed on surfaces without an alpha channel. On macOS the window
surface is ARGB, and pygame-ce blending onto an alpha-masked surface without SRCALPHA
clears its alpha, which the window shows as black (`tests/test_visuals.py` guards this).

Runtime images are loaded once. Static surfaces rebuild only after terrain edits;
liquids run at 25 Hz independently of 120 Hz actor physics and 60 FPS rendering.
The supplied art and its provenance are described in `assets/THIRD_PARTY_LICENSES.md`.
Accurate frame pacing is enabled in `config.py`; turning
`PRECISE_FRAME_PACING` off uses the lower-CPU standard clock limiter.

## Verification and profiling

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python main.py --headless --frames 600 --profile /tmp/dig-profile.json
.venv/bin/python tools/verify_world.py --frames 600 --output /tmp/dig-visual-review
.venv/bin/python tools/verify_world.py --native --frames 600 --output /tmp/dig-native-review
```

F3 shows FPS, system timings, chunks, visible tiles, draw calls, lights, particles
and the player's position.

The visual verification tool saves the Stage 1 entrance, gate, released water,
a lava-release sequence and measured CPU frame costs. These scripted
cases complement manual play; they do not claim full end-to-end player
completion. `--uncapped` measures reproducible CPU work without the FPS limiter.
