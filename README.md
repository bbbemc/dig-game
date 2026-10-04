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
- `liquids.py`: conservative mass transfers, sleeping active cells, timed reaction frontier.
- `rendering.py`: visible 320-pixel chunk caches, excavation rims, interpolated fluids.
- `scenery.py`: authored biome clusters, full-footprint occupancy and geological attachments.
- `tiles.py`: supplied sprite source rectangles and preloaded nearest-neighbor art caches.
- `config.py`: physics, flow, reaction and performance tuning.

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

The visual verification tool saves grounded-start, all four depth themes,
excavated backgrounds, a reaction sequence and measured CPU frame costs. These
scripted cases complement manual play; they do not claim full end-to-end player
completion. `--uncapped` measures reproducible CPU work without the FPS limiter.
