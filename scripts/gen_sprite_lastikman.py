"""Procedural sprites for Lastikman: an elastic stretch-fighter.

His comic costume is checkered, so the base body isn't a flat blue recolor —
the torso is filled with a real shaded checkerboard via
sprite_engine.chibi_torso_patterned. Q (Stretch Punch) and W (Grapple) render
the stretched limb itself as a checkered capsule (sprite_engine.checkered_
streak) instead of a plain skin-color line, so the costume pattern carries
onto both those skills, not just his idle silhouette. R (Rubber Storm) is
reimagined as a Luffy-style gatling-gun flurry: a fan of checkered fist
afterimages punching outward across the 3 cast frames.

    uv run python scripts/gen_sprite_lastikman.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

LASTIKMAN_PAL = {
    "skin": (212, 178, 150), "hair": (30, 26, 40),
    "cloth": (60, 110, 200), "cloth_dk": (40, 76, 150),
    "eye": (40, 60, 110),
}

CHECKER = (LASTIKMAN_PAL["cloth"], LASTIKMAN_PAL["cloth_dk"])


def lastikman_torso(s, pal, action, facing, frame, lean, bob):
    se.chibi_torso_patterned(s, action, facing, frame, lean, bob,
                             colors=(pal["cloth"], pal["cloth_dk"]), cell=2.6)


def lastikman_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame, torso_fn=lastikman_torso)


def _fist(s, x, y, r=5.5):
    pygame.draw.circle(s, LASTIKMAN_PAL["skin"], (int(x), int(y)), int(r))
    pygame.draw.circle(s, se.OUTLINE, (int(x), int(y)), int(r), 1)


def lastikman_fx(s, key, frame):
    if key == "q":  # Stretch Punch: a checkered rubbery arm flung out
        reach = 20 + 5 * frame
        se.checkered_streak(s, CX + 6, 30, CX + reach, 28, CHECKER, width=5.5)
        _fist(s, CX + reach, 28)
    elif key == "w":  # Grapple: a checkered elastic line to a hook
        se.checkered_streak(s, CX + 5, 28, CX + 22, 16, CHECKER, width=4.0)
        pygame.draw.circle(s, (200, 210, 230), (CX + 22, 16), 3)
        pygame.draw.circle(s, se.OUTLINE, (CX + 22, 16), 3, 1)
    elif key == "e":  # Elastic Body: bouncy resilience rings
        for i, r in enumerate((10, 15, 20)):
            sl.ring(s, CX, 32, r, (120, 170, 240), width=2, alpha=170 - i * 45)
    else:  # r Rubber Storm: a fanned gatling-gun flurry of checkered punches
        n = 5 + frame
        for i in range(n):
            ang = math.radians(-70 + i * (140 / max(1, n - 1)) + frame * 14)
            reach = 16 + 6 * (i % 2)
            ex = CX + math.cos(ang) * reach
            ey = 30 + math.sin(ang) * reach * 0.7
            se.checkered_streak(s, CX, 30, ex, ey, CHECKER, width=4.5)
            _fist(s, ex, ey, r=4.0)


def _projectiles() -> int:
    n = 0
    # Stretch Punch: a flying fist trailing a checkered rubbery band.
    s = sl.surf(40)
    se_checker_small = ((60, 110, 200), (40, 76, 150))
    se.checkered_streak(s, 4, 22, 24, 20, se_checker_small, width=4.5)
    pygame.draw.circle(s, (212, 178, 150), (28, 20), 8)
    pygame.draw.circle(s, se.OUTLINE, (28, 20), 8, 2)
    pygame.draw.line(s, (255, 255, 255), (25, 16), (31, 16), 2)
    sl.save(s, "projectiles", "lastikman_q", "fly")
    n += 1
    # Grapple (W): a hooked anchor on a taut checkered band.
    s = sl.surf(40)
    se.checkered_streak(s, 4, 24, 22, 18, se_checker_small, width=3.5)
    pygame.draw.circle(s, (170, 175, 185), (26, 18), 7)
    pygame.draw.circle(s, (110, 115, 125), (26, 18), 7, 2)
    pygame.draw.line(s, (200, 205, 215), (26, 11), (33, 16), 3)
    pygame.draw.line(s, (200, 205, 215), (26, 25), (33, 20), 3)
    sl.save(s, "projectiles", "lastikman_w", "fly")
    n += 1
    return n


def main() -> int:
    n = se.emit_hero("lastikman", LASTIKMAN_PAL, body_fn=lastikman_body,
                     skill_fx=lastikman_fx)
    n += _projectiles()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
