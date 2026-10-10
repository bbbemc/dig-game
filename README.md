# Dig Game — Stage 1: The Sinking Mine

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
- **W or Up:** jump away from ladders; climb up while on a ladder.
- **S or Down:** climb down while on a ladder.
- **Space:** jump even while on a ladder; in water, a buoyant stroke.
- **Left mouse anywhere on screen:** excavate visible dirt. Rock and cooled stone remain solid.
- **Esc:** pause/resume or go back from controls. **R:** restart during play.
- **F3:** optional performance overlay during play.

The main menu offers Start Game, How to Play, and Quit. The in-game UI uses a
compact health bar and current-area sign; control prompts appear only in context.
The pause menu freezes gameplay and offers Resume, Restart, How to Play, and
Main Menu. Win and game-over screens retain the last gameplay scene behind a
darkened panel.

The game starts at its main menu and offers **Stage 1** (24 × 16 macro tiles), based on the
provided layout: a raised spawn shelf, ladder, upper water basin, enemy corridor,
open exit and lower lava pocket. Reach the exit to finish the stage. Enemies can
be defeated by leading them into lava.
Touching lava instantly kills the player or an enemy. When water touches lava,
all water evaporates with surrounding steam and all lava hardens into stone.
Water flows faster through the level. Original mine,
cave, crystal and ruin sprites remain as decoration.

## Systems

- `world.py`: permanent rear walls and independent mutable foreground collision.
- `physics.py`: float positions, fixed-step gravity, grounded spawn and swept tile collision.
- `main.py`: enemies fall under gravity and fire 50-damage projectiles when the player is in clear sight; entering the exit completes the stage.
- `liquids.py`: conservative transfers, faster water flow, and full-pool water evaporation/lava solidification on contact.
- `rendering.py`: visible 320-pixel chunk caches (opaque rear layer, transparent front
  layer), exposed-edge lips/undersides/rounded corners, rear-wall occlusion, interpolated fluids.
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
