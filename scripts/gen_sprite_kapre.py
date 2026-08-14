"""Procedural sprites for the Kapre: a hairy tree-giant.

Drawn on sprite_engine's shaded chibi rig at a bigger `scale` than default so
he reads as a giant among the roster, with shaded fur strands scattered over
his silhouette and a lit cigar (mouth-anchored, tracking his head pose).
idle/move/attack + Q/W/E/R (Smash / Grove bolt / Ironbark / Dwell) and its
bolt projectile.

    uv run python scripts/gen_sprite_kapre.py
"""

from __future__ import annotations

import math
import random

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

PAL = {
    "skin": (96, 78, 54),
    "hair": (40, 30, 18),
    "cloth": (74, 92, 52),
    "cloth_dk": (50, 64, 34),
    "eye": (240, 210, 90),
}
FUR = (58, 44, 26)
FUR_HI = (92, 70, 40)
SCALE = 1.35


def kapre_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame, scale=SCALE)


def _fur(s, col, n, seed, spread=1.0):
    """Fur scattered over the torso/limb region on the SS canvas."""
    rng = random.Random(seed)
    for _ in range(n):
        x = rng.uniform(CX - 9 * SCALE, CX + 9 * SCALE)
        y = rng.uniform(18 * SCALE, 22 * SCALE + 18)
        ang = rng.uniform(0, math.tau)
        ln = rng.uniform(1.4, 3.2) * spread
        se.line(s, col, (x, y), (x + math.cos(ang) * ln, y + math.sin(ang) * ln), 1.1)


def _cigar(s, x, y, angle):
    x0, y0 = x - 3, y + 1
    x1, y1 = x + 3, y - 1
    se.line(s, (74, 52, 30), (x0, y0), (x1, y1), 1.6)
    se.circle(s, (220, 120, 60), (x1 + 1, y1 - 1), 1.4, outline=None,
             highlight=False, shadow=False)


def kapre_overlay(s, action, facing, frame):
    _fur(s, FUR, 90, 1)
    _fur(s, FUR_HI, 34, 2 + frame, spread=0.8)
    mx, my = se.chibi_mouth_point(facing, r=11.0 * SCALE)
    _cigar(s, mx, my, 0.0)


def skill_fx(s, key, frame):
    if key == "q":  # Smash: ground shockwave ring at the feet
        sl.ring(s, CX, 52, 10 + 4 * frame, (235, 150, 60), width=3, alpha=200)
        sl.ring(s, CX, 52, 18 + 4 * frame, (210, 120, 50), width=2, alpha=120)
    elif key == "w":  # Grove's Vigor: a gnarled branch-bolt cocked at the hand
        bx, by = CX + 12, 32
        tx, ty = CX + 27, 27
        pygame.draw.line(s, (96, 66, 38), (bx, by), (tx, ty), 4)
        pygame.draw.line(s, (60, 42, 24), (bx, by), (tx, ty), 4)
        pygame.draw.line(s, (120, 86, 50), (bx, by), (tx, ty), 2)
        for lx, ly in ((tx, ty), (tx - 6, ty + 3), (tx - 3, ty - 5)):
            pygame.draw.circle(s, (120, 180, 90), (lx, ly), 3)
            pygame.draw.circle(s, (80, 130, 60), (lx, ly), 3, 1)
    elif key == "e":  # Ironbark: bark plates harden over the torso
        for y in (28, 35, 42):
            pygame.draw.line(s, (70, 52, 30), (CX - 9, y), (CX + 9, y), 2)
    else:  # r Dwell: leafy shimmer
        for dx, dy in ((-11, 18), (9, 14), (0, 24), (13, 22)):
            pygame.draw.circle(s, (120, 180, 90), (CX + dx, 28 + dy), 2)


def projectile() -> int:
    s = sl.surf(40)
    pygame.draw.line(s, (96, 66, 38), (8, 26), (32, 14), 5)
    pygame.draw.line(s, (60, 42, 24), (8, 26), (32, 14), 5)
    pygame.draw.line(s, (124, 90, 52), (8, 26), (32, 14), 2)
    pygame.draw.circle(s, (74, 52, 30), (18, 20), 3)
    for lx, ly in ((32, 14), (28, 9), (35, 18)):
        pygame.draw.circle(s, (120, 180, 90), (lx, ly), 4)
        pygame.draw.circle(s, (80, 130, 60), (lx, ly), 4, 1)
    sl.save(s, "projectiles", "kapre_w", "fly")
    return 1


def main() -> int:
    n = se.emit_hero("kapre", PAL, body_fn=kapre_body, overlay=kapre_overlay,
                     skill_fx=skill_fx)
    n += projectile()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
