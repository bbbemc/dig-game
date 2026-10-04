Dig Game — Four Layers

Run with Python and pygame-ce (`pip install pygame-ce`), then `python main.py`.

Move with WASD or arrow keys. Hold the left mouse button near the player to dig.
Press R to restart. Dig through the four underground layers and use lava to
defeat the boss in the deepest arena. The supplied tile contact sheet is stored
in `assets/underground_tiles.png` and cropped at runtime by `tiles.py`.

The scenery uses all 21 categories on the supplied sheet. `scenery.py` places
fixed decoration clusters, mine frames/rails, crystal caves, damp cave plants,
and ruins. Surface attachment checks hide props when their supporting terrain
is excavated. Material variation and depth transitions affect rendering only;
the dense level geometry, collision, digging and fluid rules stay the same.
