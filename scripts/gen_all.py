"""Regenerate every placeholder sprite asset in one go.

    uv run python scripts/gen_all.py

Runs each generator (heroes, entities, effects, terrain) under a single pygame
init. Drop real PNGs with the same paths/names (see client/assets/README.md) to
replace any of these procedural placeholders without touching game code.
"""

from __future__ import annotations

import spritelib as sl

import gen_sprite_ranger
import gen_sprite_brawler
import gen_sprite_mender
import gen_sprite_manananggal
import gen_sprite_kapre
import gen_sprite_tiktik
import gen_sprite_new_heroes
import gen_sprite_pedro
import gen_entities
import gen_effects
import gen_terrain

_MODULES = [
    gen_sprite_ranger, 
    gen_sprite_brawler, 
    gen_sprite_mender,
    gen_sprite_manananggal, 
    gen_sprite_kapre, 
    gen_sprite_tiktik,
    gen_sprite_new_heroes, 
    gen_sprite_pedro,
    gen_entities, 
    gen_effects, 
    gen_terrain,
]


def main() -> None:
    sl._ensure_init()
    try:
        total = 0
        for mod in _MODULES:
            count = mod.main()
            total += count
            print(f"  {mod.__name__}: {count}")
        print(f"[gen_all] wrote {total} PNGs under {sl.ASSETS}")
    finally:
        import pygame
        pygame.quit()


if __name__ == "__main__":
    main()
