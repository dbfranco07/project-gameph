"""Procedural placeholder sprites for the Brawler (idle/move/attack + Q/W/E/R).
Melee, no projectile.

    uv run python scripts/gen_sprite_brawler.py
"""

from __future__ import annotations

import spritelib as sl
import pygame

PAL = {
    "skin": (210, 168, 140),
    "hair": (30, 24, 22),
    "cloth": (150, 70, 40),
    "cloth_dk": (104, 46, 26),
    "eye": (60, 30, 20),
}


def skill_fx(s, key, frame):
    if key == "q":  # Crushing Blow: impact star at the fist
        cx, cy = sl.CX + 16, 30
        for ang in range(0, 360, 45):
            import math
            a = math.radians(ang)
            pygame.draw.line(s, (255, 230, 140), (cx, cy),
                             (cx + math.cos(a) * 8, cy + math.sin(a) * 8), 2)
    elif key == "w":  # Charge: speed lines behind
        for dy in (-6, 0, 6):
            pygame.draw.line(s, (230, 200, 160),
                             (sl.CX - 20, 30 + dy), (sl.CX - 10, 30 + dy), 2)
    elif key == "e":  # Battle Fury: red rage aura
        sl.glow(s, sl.CX, 30, 18, (220, 70, 50), alpha=120)
    else:  # r Earthshatter: cracks bursting from the feet
        for dx in (-12, -4, 6, 14):
            pygame.draw.line(s, (120, 90, 60), (sl.CX, 52),
                             (sl.CX + dx, 58 + (2 if frame else 0)), 2)


def main() -> int:
    return sl.emit_hero("brawler", PAL, skill_fx=skill_fx)


if __name__ == "__main__":
    sl.main_guard(main)
