# Asset provenance

No external asset pack was downloaded for the world/physics/fluid polish pass.
All terrain, cave walls, water, lava and environmental props are cropped from
`underground_tiles.png`, the 1536 × 1024 contact sheet supplied with this project.
Source rectangles remain centralized in `tiles.py`.

Seamless ground, rear walls and liquid bodies are generated at start-up from those
same specimens. The miner, rails, pickaxe, shovel, rope and sign are small pixel
sprites authored in code for this project (`pixel_art.py`); no image files were added.

The supplied image does not include a creator or license document. Its license
has therefore not been relabeled as CC0. No commercial-game images, hotlinked
assets, or packs with an unclear downloaded license were added.

Recorded: 2026-10-04.

## Enemy sprites

`enemies/enemy_gunner.png`, `enemies/enemy_walker.png` and `enemies/enemy_boss.png`
were made from three pixel-art character images shared by the team in the
project chat. They were cut out from their white backgrounds and scaled down to
in-game size (the boss mirrored to face left like the others). The original
creator or tool for those images is not recorded here yet; add it before release.

Recorded: 2026-11-09.

## Miner portrait

`miner_portrait.png`, the stage intro portrait, is `miner_portrait_source.png`
(a pixel-art miner image shared by the team in the project chat) read back at
its own pixel grid by `tools/make_miner_portrait.py`: 94 x 96, no repainting.
The original creator or tool for that image is not recorded here yet; add it
before release.

Recorded: 2026-11-10.
