"""Procedural sprites for the Mender: a hooded field healer drawn as a chibi
(sprite_engine) with a soft cowl (hair_fn), a long trimmed robe (torso_fn)
instead of a flat tunic, and a small light-orb held at idle (chibi_prop).

idle/move/attack + Q/W/E/R (Spirit Bolt / Renewing Wave / Blink / Sanctuary),
its Spirit Bolt skill projectile, and a distinct ranged basic-attack bolt.

    uv run python scripts/gen_sprite_mender.py
"""

from __future__ import annotations

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

PAL = {
    "skin": (220, 200, 180), "hair": (210, 210, 220),
    "cloth": (90, 130, 200), "cloth_dk": (60, 92, 150),
    "eye": (60, 90, 140),
}


def mender_hair(s, skin, hair, facing):
    cx, cy = CX, 15.0
    pts = [(cx - 12, cy - 2), (cx - 11, cy - 10), (cx - 4, cy - 15),
           (cx + 4, cy - 15), (cx + 11, cy - 10), (cx + 12, cy - 2),
           (cx + 9, cy - 4), (cx, cy - 9), (cx - 9, cy - 4)]
    se.poly(s, hair, pts, hi=se.lighten(hair, 0.3))


def mender_head(s, pal, facing):
    se.chibi_head(s, pal["skin"], pal["hair"], facing, pal["eye"],
                 hair_fn=mender_hair)


def mender_torso(s, pal, action, facing, frame, lean, bob):
    w, h = 17.0, 19.0
    x = CX - w / 2 + lean
    y = 20 + bob
    se.rect(s, pal["cloth"], (x, y, w, h), sh=pal["cloth_dk"])
    se.line(s, (235, 240, 250), (CX + lean, y + 2), (CX + lean, y + h - 2), 1.2)


def mender_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame,
                      head_fn=mender_head, torso_fn=mender_torso)


def _orb_prop(s, x, y, angle):
    se.circle(s, (210, 235, 255), (x, y), 2.6, outline=se.OUTLINE, ow=1.0)


def mender_overlay(s, action, facing, frame):
    phase = se._phase_for(action, frame)
    se.chibi_prop(s, action, facing, phase, 1, _orb_prop)


def skill_fx(s, key, frame):
    if key == "q":  # Spirit Bolt: a glowing orb forming at the hand
        sl.glow(s, CX + 16, 30, 9, (150, 210, 255), alpha=160)
        pygame.draw.circle(s, (235, 245, 255), (CX + 16, 30), 4)
    elif key == "w":  # Renewing Wave: green healing sparkles
        for dx, dy in ((-8, 20), (0, 14), (10, 22), (6, 12)):
            pygame.draw.circle(s, (150, 240, 170),
                               (CX + dx, 30 + dy - (3 if frame else 0)), 2)
    elif key == "e":  # Blink: teleport shimmer
        for i, r in enumerate((8, 13, 18)):
            sl.ring(s, CX, CX, r, (190, 210, 255), width=2, alpha=170 - i * 50)
    else:  # r Sanctuary: a radiant halo
        sl.glow(s, CX, 26, 18, (240, 235, 170), alpha=120)
        sl.ring(s, CX, 26, 16, (255, 250, 210), width=2, alpha=200)


def _projectiles() -> int:
    n = 0
    s = sl.surf(40)
    sl.glow(s, 16, 20, 11, (130, 200, 255), alpha=150)
    pygame.draw.circle(s, (235, 245, 255), (20, 20), 6)
    pygame.draw.circle(s, (180, 220, 255), (20, 20), 6, 2)
    pygame.draw.line(s, (190, 225, 255), (6, 20), (14, 20), 2)
    sl.save(s, "projectiles", "mender_q", "fly")
    n += 1
    # Distinct ranged-basic-attack bolt: a thin quick spark, not the full orb.
    s2 = sl.surf(40)
    pygame.draw.line(s2, (220, 235, 255), (8, 20), (30, 20), 2)
    pygame.draw.circle(s2, (255, 255, 255), (31, 20), 3)
    sl.save(s2, "projectiles", "mender_atk", "fly")
    n += 1
    return n


def main() -> int:
    n = se.emit_hero("mender", PAL, body_fn=mender_body,
                     overlay=mender_overlay, skill_fx=skill_fx)
    n += _projectiles()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
