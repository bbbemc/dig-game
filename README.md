# Dig Game — Four Underground Layers

Install Python and dependencies, then launch:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Requires **pygame-ce 2.5.8** (`import pygame`). Do not install classic `pygame`
in the same environment.

## Controls

- **A/D or Left/Right:** walk.
- **Space, W or Up:** jump; in water, a buoyant stroke.
- **W/S or Up/Down on a ladder:** climb. Gravity operates elsewhere.
- **Left mouse held near the player:** excavate dirt. Rock and cooled stone remain solid.
- **R:** restart. **F3:** optional performance overlay.

Explore the original **124 × 100 macro-tile world (4960 × 4000 pixels)**. About
**63.9% remains diggable dirt**. Caves are isolated pockets inside thick terrain;
create stairs and shortcuts by digging. B1 is an abandoned human mine, B2 an
earth cave, B3 a crystal grotto, and B4 volcanic ruins. Use the existing lava
interaction to defeat the bottom boss; the arena ladder reaches the reservoir
roof. Water and lava start separated and cool progressively when connected.

## Systems

- `world.py`: permanent rear walls and independent mutable foreground collision.
- `physics.py`: float positions, fixed-step gravity, grounded spawn and swept tile collision.
- `main.py`: enemies hold their ground and fire 20-damage projectiles when the player is in clear sight.
- `liquids.py`: conservative mass transfers, sleeping active cells, timed reaction frontier.
- `rendering.py`: visible 320-pixel chunk caches (opaque rear layer, transparent front
  layer), exposed-edge lips/undersides/rounded corners, rear-wall occlusion, interpolated fluids.
- `terrain_art.py`: seamless ground mosaics built from the sheet's own tiles, dark mine
  walls, per-macro detail variants and edge pieces.
- `caves.py`: deterministic cell-level shaping (rounded upper corners, uneven roofs,
  wall bumps/cavities) that never touches floors, spawns, props, liquids or the boss area.
- `scenery.py`: authored biome clusters, composite mine timber and staged B1 scenes,
  full-footprint occupancy and geological attachments.
- `lighting.py`: screen light map (depth ambient, vignette, flickering lamps, lava and
  the miner's helmet lamp) plus warm additive bloom.
- `actors.py`, `pixel_art.py`: the animated miner and small hand-authored sprites.
- `effects.py`: pooled particles (dig debris, landing dust, embers, splashes, dust motes).
- `tiles.py`: supplied sprite source rectangles and preloaded art caches.
- `config.py`: physics, flow, reaction, particle, camera and performance tuning.

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

The visual verification tool saves grounded-start, all four depth themes,
excavated backgrounds, a reaction sequence and measured CPU frame costs. These
scripted cases complement manual play; they do not claim full end-to-end player
completion. `--uncapped` measures reproducible CPU work without the FPS limiter.
