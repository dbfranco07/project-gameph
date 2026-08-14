"""Procedural sprites for the Brawler: a bare-knuckle bruiser drawn as a bulky
chibi (sprite_engine) with bandage-wrapped fists (a chibi_prop pair at each
hand) and a fight scar, instead of a flat unadorned humanoid.

idle/move/attack + Q/W/E/R (Crushing Blow / Charge / Battle Fury /
Earthshatter). Melee, no projectile.

    uv run python scripts/gen_sprite_brawler.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

PAL = {
    "skin": (210, 168, 140),
    "hair": (30, 24, 22),
    "cloth": (150, 70, 40),
    "cloth_dk": (104, 46, 26),
    "eye": (60, 30, 20),
}


def brawler_face(s, skin, facing):
    if facing == "n":
        return
    se.line(s, (150, 64, 54), (CX - 6.5, 9.5), (CX - 3.5, 15.5), 1.2)


def brawler_head(s, pal, facing):
    se.chibi_head(s, pal["skin"], pal["hair"], facing, pal["eye"],
                 face_fn=brawler_face)


def brawler_torso(s, pal, action, facing, frame, lean, bob):
    w, h = 19.0, 15.0
    se.chibi_torso(s, pal["cloth"], pal["cloth_dk"], w=w, h=h, lean=lean, bob=bob)
    x = CX - w / 2 + lean
    y = 22 + bob
    se.line(s, (230, 210, 180), (x + 3, y + 1), (x + 3, y + 13), 1.4)
    se.line(s, (230, 210, 180), (x + 16, y + 1), (x + 16, y + 13), 1.4)


def brawler_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame,
                      head_fn=brawler_head, torso_fn=brawler_torso, scale=1.08)


def brawler_overlay(s, action, facing, frame):
    phase = se._phase_for(action, frame)
    (lx, ly), (rx, ry) = se.chibi_hand_points(action, phase, scale=1.08)
    for hx, hy in ((lx, ly), (rx, ry)):
        se.circle(s, (222, 208, 188), (hx, hy), 4.4, outline=se.OUTLINE, ow=1.2,
                 highlight=False, shadow=False)
        se.line(s, (180, 160, 140), (hx - 2.6, hy), (hx + 2.6, hy), 1.0)
        se.line(s, (180, 160, 140), (hx, hy - 2.6), (hx, hy + 2.6), 1.0)


def skill_fx(s, key, frame):
    if key == "q":  # Crushing Blow: impact star at the fist
        cx, cy = CX + 16, 30
        for ang in range(0, 360, 45):
            a = math.radians(ang)
            pygame.draw.line(s, (255, 230, 140), (cx, cy),
                             (cx + math.cos(a) * 8, cy + math.sin(a) * 8), 2)
    elif key == "w":  # Charge: speed lines behind
        for dy in (-6, 0, 6):
            pygame.draw.line(s, (230, 200, 160),
                             (CX - 20, 30 + dy), (CX - 10, 30 + dy), 2)
    elif key == "e":  # Battle Fury: red rage aura
        sl.glow(s, CX, 30, 18, (220, 70, 50), alpha=120)
    else:  # r Earthshatter: cracks bursting from the feet
        for dx in (-12, -4, 6, 14):
            pygame.draw.line(s, (120, 90, 60), (CX, 52),
                             (CX + dx, 58 + (2 if frame else 0)), 2)


def main() -> int:
    return se.emit_hero("brawler", PAL, body_fn=brawler_body,
                        overlay=brawler_overlay, skill_fx=skill_fx)


if __name__ == "__main__":
    sl.main_guard(main)
