"""Procedural sprites for Jose Rizal: a scholar-hero who fights with pen and
word, drawn to read as the historical figure in chibi form — a side-parted
hairstyle, a thin mustache and wire-frame glasses (via sprite_engine's
head_fn/hair_fn/face_fn hooks), and a lapelled coat over the base torso (via
torso_fn) instead of a flat "navy cloth" blob. He holds a small quill at idle
(a chibi_prop) distinct from the larger thrown quill his Q flings.

Q (Pluma Throw) already flies out and returns to hit enemies on both legs of
its flight in gameplay (server/heroes/rizal.py's Q spawns a return-pass bolt
from the far end back toward the caster, reusing the same "rizal_q"
projectile kind) — no server change needed here, just a feather that reads
clearly as a soft barbed quill rather than a flat triangle.

idle/move/attack + Q/W/E/R (Pluma Throw / Words of Reform / Polymath / Mi
Ultimo Adios) and the pen-boomerang projectile.

    uv run python scripts/gen_sprite_rizal.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

RIZAL_PAL = {
    "skin": (214, 184, 150), "hair": (28, 22, 20),
    "cloth": (40, 46, 78), "cloth_dk": (26, 30, 54),
    "eye": (60, 44, 30),
}

_INK = (30, 26, 24)


def rizal_hair(s, skin, hair, facing):
    cx, cy = CX, 15.0
    pts = [(cx - 13, cy - 3), (cx - 12, cy - 12), (cx - 3, cy - 15),
           (cx + 2, cy - 16), (cx + 8, cy - 13), (cx + 13, cy - 8),
           (cx + 13, cy - 3)]
    se.poly(s, hair, pts, hi=se.lighten(hair, 0.3))


def rizal_face(s, skin, facing):
    cx, cy = CX, 15.0
    # wire-frame glasses
    for side in (-1, 1):
        se.circle(s, (210, 215, 225), (cx + side * 4.5, cy), 3.2,
                  outline=_INK, ow=0.8, highlight=False, shadow=False)
    se.line(s, _INK, (cx - 1.3, cy), (cx + 1.3, cy), 0.8)
    # thin mustache
    se.line(s, _INK, (cx - 4.5, cy + 5), (cx, cy + 5.6), 1.0)
    se.line(s, _INK, (cx + 4.5, cy + 5), (cx, cy + 5.6), 1.0)


def rizal_head(s, pal, facing):
    se.chibi_head(s, pal.get("skin", (200, 180, 160)), pal.get("hair", sl.BLACK),
                 facing, pal.get("eye", (40, 30, 30)),
                 hair_fn=rizal_hair, face_fn=rizal_face)


def rizal_torso(s, pal, action, facing, frame, lean, bob):
    se.chibi_torso(s, pal["cloth"], pal["cloth_dk"], lean=lean, bob=bob)
    x = CX - 17 / 2 + lean
    y = 20 + bob
    # lapels
    se.line(s, _INK, (x + 3, y + 1), (x + 8, y + 8), 1.0)
    se.line(s, _INK, (x + 14, y + 1), (x + 9, y + 8), 1.0)
    se.circle(s, (215, 205, 180), (x + 8.5, y + 11), 1.2, outline=None,
             highlight=False, shadow=False)


def rizal_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame,
                      head_fn=rizal_head, torso_fn=rizal_torso)


def _feather(s, x0, y0, x1, y1, *, scale=1.0):
    """A soft barbed quill — a shaft with small angled barb strokes, rather
    than a flat triangle."""
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    pygame.draw.line(s, (235, 235, 240), (x0, y0), (x1, y1), max(1, int(2 * scale)))
    pygame.draw.line(s, _INK, (x0, y0), (x1, y1), 1)
    n_barbs = 5
    for i in range(1, n_barbs + 1):
        t = i / (n_barbs + 1)
        bx, by = x0 + dx * t, y0 + dy * t
        bl = (1 - t) * 5 * scale
        for sign in (-1, 1):
            ex = bx - ux * bl * 0.4 + nx * bl * sign
            ey = by - uy * bl * 0.4 + ny * bl * sign
            pygame.draw.line(s, (225, 222, 215), (bx, by), (ex, ey), 1)
    pygame.draw.circle(s, _INK, (int(x0), int(y0)), 1)


def _quill_small(s, x, y, angle):
    dx, dy = math.cos(angle), math.sin(angle)
    tip = (x + dx * 6, y + dy * 6)
    se.line(s, _INK, (x - dx * 4, y - dy * 4), tip, 1.0)
    se.circle(s, (230, 230, 235), tip, 1.3, outline=None, highlight=False,
             shadow=False)


def rizal_overlay(s, action, facing, frame):
    phase = se._phase_for(action, frame)
    se.chibi_prop(s, action, facing, phase, 1, _quill_small)


def rizal_fx(s, key, frame):
    if key == "q":  # Pluma Throw: a soft barbed quill cast forward
        _feather(s, CX + 8, 30, CX + 28, 20)
    elif key == "w":  # Words of Reform: hypnotic sound rings from the head
        for i, r in enumerate((6, 11, 16)):
            sl.ring(s, CX + 8, 14, r + frame, (190, 200, 240),
                    width=1, alpha=200 - i * 55)
    elif key == "e":  # Polymath: an open book glowing with insight
        pygame.draw.polygon(s, (235, 230, 215),
                            [(CX - 7, 30), (CX, 28), (CX + 7, 30),
                             (CX + 7, 36), (CX, 34), (CX - 7, 36)])
        pygame.draw.line(s, (120, 120, 130), (CX, 28), (CX, 34), 1)
    else:  # r Mi Ultimo Adios: a golden halo of inspiration
        sl.glow(s, CX, 14, 14, (245, 220, 120), alpha=140)
        sl.ring(s, CX, 14, 12, (255, 240, 180), width=2, alpha=210)


def _projectiles() -> int:
    s = sl.surf(40)
    _feather(s, 8, 28, 34, 12, scale=1.3)
    sl.save(s, "projectiles", "rizal_q", "fly")
    return 1


def main() -> int:
    n = se.emit_hero("rizal", RIZAL_PAL, body_fn=rizal_body,
                     overlay=rizal_overlay, skill_fx=rizal_fx)
    n += _projectiles()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
