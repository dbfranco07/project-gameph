"""Procedural placeholder sprites for the Kapre: a hairy tree-giant. idle/move/
attack + Q/W/E/R (Smash / Grove bolt / Ironbark / Dwell) and its bolt projectile.
The whole body is covered in scattered fur strands.

    uv run python scripts/gen_sprite_kapre.py
"""

from __future__ import annotations

import spritelib as sl
import pygame

PAL = {
    "skin": (96, 78, 54), "hair": (40, 30, 18),
    "cloth": (74, 92, 52), "cloth_dk": (50, 64, 34),
    "eye": (240, 210, 90),
}
FUR = (58, 44, 26)
FUR_HI = (86, 66, 38)


def overlay(s, action, facing, frame):
    # Hairy! Two passes of scattered strands; a frame-varied seed shimmers it.
    sl.fur(s, FUR, n=130, seed=1)
    sl.fur(s, FUR_HI, n=50, seed=2 + frame)


def skill_fx(s, key, frame):
    if key == "q":  # Smash: ground shockwave ring at the feet
        sl.ring(s, sl.CX, 52, 10 + 4 * frame, (235, 150, 60), width=3, alpha=200)
        sl.ring(s, sl.CX, 52, 18 + 4 * frame, (210, 120, 50), width=2, alpha=120)
    elif key == "w":  # Grove's Vigor: hurled bolt forming at the hand
        pygame.draw.circle(s, (150, 200, 110), (sl.CX + 16, 30), 5)
        pygame.draw.circle(s, (90, 130, 60), (sl.CX + 16, 30), 5, 2)
    elif key == "e":  # Ironbark: bark plates harden over the torso
        for y in (26, 32, 38):
            pygame.draw.line(s, (70, 52, 30), (sl.CX - 8, y), (sl.CX + 8, y), 2)
    else:  # r Dwell: leafy shimmer
        for dx, dy in ((-10, 18), (8, 14), (0, 24), (12, 22)):
            pygame.draw.circle(s, (120, 180, 90), (sl.CX + dx, 26 + dy), 2)


def projectile() -> int:
    s = sl.surf(40)
    pygame.draw.circle(s, (110, 150, 80), (20, 20), 8)
    pygame.draw.circle(s, (70, 100, 50), (20, 20), 8, 2)
    pygame.draw.circle(s, (150, 190, 110), (17, 17), 3)
    sl.save(s, "projectiles", "kapre_w", "fly")
    return 1


def main() -> int:
    n = sl.emit_hero("kapre", PAL, overlay=overlay, skill_fx=skill_fx)
    n += projectile()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
