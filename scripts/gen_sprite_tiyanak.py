"""Procedural sprites for Tiyanak: a blood-hungry demon-infant assassin.

Split out of gen_sprite_new_heroes.py onto sprite_engine.py's shaded chibi
rig — a slightly smaller, impish chibi with small horn nubs, pointed ears,
bared fangs and clawed hands (via head_fn/face_fn hooks and the `claw` pal
key), instead of a stock silhouette with only her `skill_fx` distinguishing
her. idle/move/attack + Q/W/E/R (Cradle Bite / Tantrum / Feral Hunger /
Umbilical Cord).

    uv run python scripts/gen_sprite_tiyanak.py
"""

from __future__ import annotations

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

TIYANAK_PAL = {
    "skin": (172, 166, 170), "hair": (30, 24, 28),
    "cloth": (124, 40, 46), "cloth_dk": (84, 26, 32),
    "eye": (236, 60, 55), "claw": sl.WHITE,
}

SCALE = 0.9  # a touch smaller than the roster — reads as an infant


def _horns(s, skin, hair, facing):
    cx, cy = CX, 15.0 * SCALE + 1
    for side in (-1, 1):
        bx = cx + side * 7 * SCALE
        se.poly(s, (216, 210, 198), [(bx, cy - 6), (bx + side * 3, cy - 13),
                                      (bx + side * 1, cy - 6)],
               sh=(170, 164, 152), highlight=False)
    for side in (-1, 1):  # pointed ears
        ex = cx + side * 10.5 * SCALE
        se.poly(s, skin, [(ex, cy - 1), (ex + side * 5, cy - 4), (ex, cy + 3)],
               highlight=False)


def _fangs(s, skin, facing):
    cx, cy = CX, 15.0 * SCALE + 1
    for fx in (cx - 2.2, cx + 2.2):
        pygame.draw.polygon(s, sl.WHITE,
                            [(fx - 1.3, cy + 4), (fx + 1.3, cy + 4), (fx, cy + 7)])


def tiyanak_head(s, pal, facing):
    se.chibi_head(s, pal.get("skin"), pal.get("hair"), facing, pal.get("eye"),
                 r=11.0 * SCALE, hair_fn=_horns, face_fn=_fangs)


def tiyanak_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame, head_fn=tiyanak_head,
                      scale=SCALE)


def tiyanak_fx(s, key, frame):
    if key == "q":  # Cradle Bite: bared fangs lunging forward
        mx = CX + 12 + 2 * frame
        pygame.draw.circle(s, (150, 24, 36), (mx, 18), 4)
        for fx in (mx - 2, mx + 2):
            pygame.draw.polygon(s, sl.WHITE,
                                [(fx - 2, 15), (fx + 2, 15), (fx, 21)])
    elif key == "w":  # Tantrum: frenzied red aura
        sl.glow(s, CX, 30, 18, (230, 60, 60), alpha=130)
    elif key == "e":  # Feral Hunger: raking claw marks
        for dx in (-3, 1, 5):
            pygame.draw.line(s, (235, 235, 235),
                             (CX + 10 + dx, 22), (CX + 16 + dx, 38), 2)
    else:  # r Umbilical Cord: a fleshy tether snaking down
        pts = [(CX, 40), (CX - 5, 46), (CX + 4, 52), (CX - 3, 58)]
        pygame.draw.lines(s, (170, 90, 96), False, pts, 4)
        pygame.draw.circle(s, (120, 40, 46), (CX - 3, 58), 4)


def main() -> int:
    return se.emit_hero("tiyanak", TIYANAK_PAL, body_fn=tiyanak_body,
                        skill_fx=tiyanak_fx)


if __name__ == "__main__":
    sl.main_guard(main)
