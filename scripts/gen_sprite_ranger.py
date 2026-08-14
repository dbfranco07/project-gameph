"""Procedural sprites for the Ranger: a forest scout drawn as a chibi
(sprite_engine) with a pointed woodland hood (hair_fn), a belted leather vest
(torso_fn), and a held bow (chibi_prop) instead of a flat green humanoid.

idle/move/attack + Q/W/E/R (Piercing Shot / Tumble / Hunter's Focus / Arrow
Storm), its Piercing Shot skill arrow, and a distinct ranged basic-attack
arrow.

    uv run python scripts/gen_sprite_ranger.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

PAL = {
    "skin": (214, 184, 150), "hair": (60, 40, 24),
    "cloth": (46, 104, 70), "cloth_dk": (30, 70, 48),
    "eye": (30, 60, 40),
}


def ranger_hair(s, skin, hair, facing):
    cx, cy = CX, 15.0
    pts = [(cx - 11, cy - 2), (cx - 9, cy - 11), (cx, cy - 16),
           (cx + 9, cy - 11), (cx + 11, cy - 2), (cx + 7, cy - 3),
           (cx, cy - 9), (cx - 7, cy - 3)]
    se.poly(s, hair, pts, hi=se.lighten(hair, 0.3))


def ranger_head(s, pal, facing):
    se.chibi_head(s, pal["skin"], pal["hair"], facing, pal["eye"],
                 hair_fn=ranger_hair)


def ranger_torso(s, pal, action, facing, frame, lean, bob):
    se.chibi_torso(s, pal["cloth"], pal["cloth_dk"], lean=lean, bob=bob)
    x = CX - 17 / 2 + lean
    y = 22 + bob
    se.line(s, (90, 70, 40), (x, y + 9), (x + 17, y + 9), 1.4)


def ranger_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame,
                      head_fn=ranger_head, torso_fn=ranger_torso)


def _bow_prop(s, x, y, angle):
    nx, ny = -math.sin(angle), math.cos(angle)
    p0 = (x - nx * 5, y - ny * 5)
    p1 = (x + nx * 5, y + ny * 5)
    se.line(s, (90, 60, 30), p0, p1, 1.4)
    se.line(s, (210, 200, 180), p0, p1, 0.6)


def ranger_overlay(s, action, facing, frame):
    phase = se._phase_for(action, frame)
    se.chibi_prop(s, action, facing, phase, -1, _bow_prop)


def skill_fx(s, key, frame):
    if key == "q":  # Piercing Shot: a long arrow loosed forward
        y = 30
        pygame.draw.line(s, (230, 220, 180), (CX + 6, y), (CX + 26, y), 2)
        pygame.draw.polygon(s, (240, 235, 200),
                            [(CX + 26, y), (CX + 22, y - 3), (CX + 22, y + 3)])
    elif key == "w":  # Tumble: roll motion arcs
        for i, r in enumerate((10, 14, 18)):
            sl.ring(s, CX, CX, r, (180, 220, 190), width=2, alpha=150 - i * 40)
    elif key == "e":  # Hunter's Focus: keen-eye glow
        sl.glow(s, CX, 28, 16, (240, 220, 120), alpha=120)
    else:  # r Arrow Storm: arrows raining down
        for dx in (-10, 0, 10):
            x = CX + dx + (2 if frame else 0)
            pygame.draw.line(s, (235, 225, 190), (x, 6), (x, 16), 2)


def _projectiles() -> int:
    n = 0
    s = sl.surf(40)
    pygame.draw.line(s, (235, 225, 190), (6, 20), (30, 20), 3)
    pygame.draw.polygon(s, (245, 240, 210), [(34, 20), (28, 16), (28, 24)])
    pygame.draw.line(s, (160, 130, 90), (6, 20), (10, 17), 2)
    pygame.draw.line(s, (160, 130, 90), (6, 20), (10, 23), 2)
    sl.save(s, "projectiles", "ranger_q", "fly")
    n += 1
    # Distinct ranged-basic-attack arrow: a plain quick shaft, no fletching flourish.
    s2 = sl.surf(40)
    pygame.draw.line(s2, (210, 205, 180), (10, 20), (30, 20), 2)
    pygame.draw.polygon(s2, (230, 225, 200), [(33, 20), (28, 17), (28, 23)])
    sl.save(s2, "projectiles", "ranger_atk", "fly")
    n += 1
    return n


def main() -> int:
    n = se.emit_hero("ranger", PAL, body_fn=ranger_body,
                     overlay=ranger_overlay, skill_fx=skill_fx)
    n += _projectiles()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
