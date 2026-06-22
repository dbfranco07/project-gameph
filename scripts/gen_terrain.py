"""Procedural placeholder terrain tiles: ground, river, lane. Each is a seamless
(edge-wrapped) speckled tile the renderer blits (ground tiled across the screen;
river/lane stretched along their geometry).

    uv run python scripts/gen_terrain.py
"""

from __future__ import annotations

import spritelib as sl


def main() -> int:
    # Ground: a 128x128 mossy-earth tile.
    sl.save(sl.tileable_noise(128, 128, (46, 64, 36), 240, seed=11),
            "terrain", "ground")
    # River: a 128x48 water strip (lighter, bluer speckle).
    sl.save(sl.tileable_noise(128, 48, (60, 110, 170), 120, seed=22),
            "terrain", "river")
    # Lane: a 128x48 worn-path strip.
    sl.save(sl.tileable_noise(128, 48, (78, 90, 64), 120, seed=33),
            "terrain", "lane")
    return 3


if __name__ == "__main__":
    sl.main_guard(main)
