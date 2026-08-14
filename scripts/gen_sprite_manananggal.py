"""Procedural sprites for the Manananggal: idle/move/attack, the Q/W/E/R cast
poses (Scratch / Pounce / Bloodlust / Split), the detached flying upper half
with emphasized flapping bat wings, the grounded lower body, and the
recombine/death effects — all on sprite_engine's shaded chibi rig.

    uv run python scripts/gen_sprite_manananggal.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

WING = (52, 30, 40)
WING_EDGE = (94, 56, 72)
GUT = (158, 48, 58)
GUT_DK = (112, 32, 44)

PAL = {
    "skin": (216, 186, 162), "hair": (22, 18, 26),
    "cloth": (116, 30, 44), "cloth_dk": (84, 20, 32),
    "claw": sl.WHITE, "eye": (220, 70, 60),
}


def _spread(action, frame):
    return {"idle": 0.3 + 0.1 * frame, "move": 0.6 + 0.3 * frame,
            "attack": 0.5, "q": 0.6, "w": 0.95, "split_flyer": 0.7 + 0.3 * frame
            }.get(action, 0.4)


def bat_wing(s, side, spread, col, edge):
    """A leathery bat wing on the SS canvas, side=-1 left/+1 right."""
    sx, sy = CX + side * 6, 22
    tipx = CX + side * (15 + spread * 20)
    tipy = 17 - spread * 15
    pts = [
        (sx, sy - 7), (tipx, tipy),
        (CX + side * (13 + spread * 13), sy + 2),
        (CX + side * (11 + spread * 9), sy + 12),
        (CX + side * (8 + spread * 6), sy + 20),
        (sx, sy + 10)]
    se.poly(s, col, pts, sh=edge, highlight=False)
    for fx, fy in (pts[1], pts[2], pts[3], pts[4]):
        se.line(s, edge, (sx, sy - 3), (fx, fy), 0.6)


def back_wings(s, action, facing, frame):
    sp = _spread(action, frame)
    bat_wing(s, -1, sp, WING, WING_EDGE)
    bat_wing(s, 1, sp, WING, WING_EDGE)


def skill_fx(s, key, frame):
    if key == "q":  # Scratch: a claw-slash arc
        for k in (-4, 0, 4):
            pygame.draw.arc(s, (245, 230, 235),
                            (CX + 4, 18 + k, 22, 22), -0.8, 0.8, 2)
    elif key == "w":  # Pounce: leap motion blur below
        for i, r in enumerate((8, 13, 18)):
            sl.ring(s, CX, 50, r, (200, 120, 140), width=2, alpha=150 - i * 45)
    elif key == "e":  # Bloodlust: red aura + drip
        sl.glow(s, CX, 30, 17, (200, 50, 60), alpha=130)
        pygame.draw.circle(s, GUT, (CX, 46 + (2 if frame else 0)), 2)
    else:  # r Split: detach line across the waist
        pygame.draw.line(s, GUT, (CX - 9, 40), (CX + 9, 40), 3)
        for dx in (-6, 0, 6):
            pygame.draw.circle(s, GUT_DK, (CX + dx, 44), 2)


def _entrails(s, n, frame):
    x, y = CX, 40
    for i in range(n):
        nx = CX + 3.2 * math.sin(i * 0.7 + frame)
        pygame.draw.line(s, GUT_DK, (x, y), (nx, y + 3), 3)
        x, y = nx, y + 3
    pygame.draw.circle(s, GUT, (int(x), int(y)), 3)


def split_flyer(facing, frame) -> pygame.Surface:
    s = se.canvas()
    back_wings(s, "split_flyer", facing, frame)
    se.chibi_torso(s, PAL["cloth"], PAL["cloth_dk"])
    se.chibi_arms(s, PAL["skin"], "split_flyer", PAL["claw"], phase=0.5)
    se.chibi_head(s, PAL["skin"], PAL["hair"], facing, PAL["eye"])
    out = se.downsample(s)
    _entrails(out, 6, frame)
    return se.oriented(out, facing)


def split_body() -> pygame.Surface:
    s = se.canvas()
    se.shadow(s)
    se.ellipse(s, GUT, (CX - 9, 30, 18, 9), sh=GUT_DK)
    se.rect(s, PAL["cloth"], (CX - 9, 35, 18, 13))
    se.chibi_legs(s, PAL["cloth"], PAL["cloth_dk"])
    return se.downsample(s)


def main() -> int:
    n = se.emit_hero("manananggal", PAL, back=back_wings, skill_fx=skill_fx)
    for f in se.FACINGS:
        for fr in (0, 1):
            sl.save(split_flyer(f, fr), "heroes", "manananggal",
                    f"split_flyer_{f}_{fr}")
            n += 1
    sl.save(split_body(), "heroes", "manananggal", "split_body")
    n += 1
    return n


if __name__ == "__main__":
    sl.main_guard(main)
