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
    elif key == "w":  # Grove's Vigor: a gnarled branch-bolt cocked at the hand
        bx, by = sl.CX + 10, 30
        tx, ty = sl.CX + 24, 26
        pygame.draw.line(s, (96, 66, 38), (bx, by), (tx, ty), 4)   # wood shaft
        pygame.draw.line(s, (60, 42, 24), (bx, by), (tx, ty), 4, )
        pygame.draw.line(s, (120, 86, 50), (bx, by), (tx, ty), 2)  # lit edge
        for lx, ly in ((tx, ty), (tx - 5, ty + 3), (tx - 3, ty - 4)):
            pygame.draw.circle(s, (120, 180, 90), (lx, ly), 3)     # sprig leaves
            pygame.draw.circle(s, (80, 130, 60), (lx, ly), 3, 1)
    elif key == "e":  # Ironbark: bark plates harden over the torso
        for y in (26, 32, 38):
            pygame.draw.line(s, (70, 52, 30), (sl.CX - 8, y), (sl.CX + 8, y), 2)
    else:  # r Dwell: leafy shimmer
        for dx, dy in ((-10, 18), (8, 14), (0, 24), (12, 22)):
            pygame.draw.circle(s, (120, 180, 90), (sl.CX + dx, 26 + dy), 2)


def projectile() -> int:
    # A flung gnarled branch (not a round bolt) so it reads distinctly from the
    # Tiktik's tongue head: a knotted wooden shaft tipped with leaves.
    s = sl.surf(40)
    pygame.draw.line(s, (96, 66, 38), (8, 26), (32, 14), 5)    # shaft
    pygame.draw.line(s, (60, 42, 24), (8, 26), (32, 14), 5)
    pygame.draw.line(s, (124, 90, 52), (8, 26), (32, 14), 2)   # lit edge
    pygame.draw.circle(s, (74, 52, 30), (18, 20), 3)           # a knot
    for lx, ly in ((32, 14), (28, 9), (35, 18)):               # leaf cluster
        pygame.draw.circle(s, (120, 180, 90), (lx, ly), 4)
        pygame.draw.circle(s, (80, 130, 60), (lx, ly), 4, 1)
    sl.save(s, "projectiles", "kapre_w", "fly")
    return 1


def main() -> int:
    n = sl.emit_hero("kapre", PAL, overlay=overlay, skill_fx=skill_fx)
    n += projectile()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
