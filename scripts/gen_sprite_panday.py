"""Procedural sprites for Panday, the blacksmith-swordsman, on the expressive
sprite_engine.py chibi engine (matching Rizal/Kapre/Bonifacio/etc.):

  - identity via se's hair_fn/torso_fn (a soot-dark crop and a leather smith's
    apron over the base torso) plus a chibi_prop-held short sword at idle;
  - the standard hero set (idle/move/attack + Q/W/E/R cast poses + a `face`
    portrait) via ``sprite_engine.emit_hero``;
  - a ground-item icon for the sword he forges into a wall (Q) and can walk
    up to claim (client/assets/entities/panday_sword_ground/idle.png);
  - the two new ability decals (``panday_disarm``, ``panday_pin``) referenced
    by his kit, alongside the rest of the effect library.

    uv run python scripts/gen_sprite_panday.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX
_INK = (30, 26, 24)

PANDAY_PAL = {
    "skin": (198, 162, 128), "hair": (36, 28, 24),
    "cloth": (122, 74, 42), "cloth_dk": (84, 50, 28),
    "eye": (48, 34, 24),
}


def panday_hair(s, skin, hair, facing):
    cx, cy = CX, 15.0
    pts = [(cx - 11, cy - 1), (cx - 10, cy - 10), (cx - 2, cy - 14),
           (cx + 2, cy - 14), (cx + 10, cy - 10), (cx + 11, cy - 1)]
    se.poly(s, hair, pts, hi=se.lighten(hair, 0.3))


def panday_head(s, pal, facing):
    se.chibi_head(s, pal.get("skin", (200, 180, 160)), pal.get("hair", sl.BLACK),
                 facing, pal.get("eye", (40, 30, 30)), hair_fn=panday_hair)


def panday_torso(s, pal, action, facing, frame, lean, bob):
    se.chibi_torso(s, pal["cloth"], pal["cloth_dk"], lean=lean, bob=bob)
    # A smith's leather apron strapped over the chest.
    x, y = CX + lean, 24 + bob
    apron = se.darken(pal["cloth"], 0.05)
    se.poly(s, apron,
           [(x - 7, y - 3), (x + 7, y - 3), (x + 5, y + 10), (x - 5, y + 10)],
           sh=se.darken(apron, 0.3), outline=_INK, ow=1.0)
    se.line(s, (60, 44, 28), (x - 6, y - 3), (x - 3, y - 8), 1.4)
    se.line(s, (60, 44, 28), (x + 6, y - 3), (x + 3, y - 8), 1.4)


def panday_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame,
                      head_fn=panday_head, torso_fn=panday_torso)


def _short_sword(s, x, y, angle):
    dx, dy = math.cos(angle), math.sin(angle)
    nx, ny = -dy, dx
    tip = (x + dx * 15, y + dy * 15)
    base_l = (x - nx * 2.2, y - ny * 2.2)
    base_r = (x + nx * 2.2, y + ny * 2.2)
    se.poly(s, (215, 220, 228), [base_l, tip, base_r], outline=_INK, ow=1.0,
           hi=(245, 248, 252))
    # crossguard + grip
    gx, gy = x - dx * 2, y - dy * 2
    se.line(s, (120, 108, 60), (gx - nx * 4, gy - ny * 4),
           (gx + nx * 4, gy + ny * 4), 1.6)
    se.line(s, (70, 44, 30), (gx, gy), (gx - dx * 4, gy - dy * 4), 2.0)


def panday_overlay(s, action, facing, frame):
    phase = se._phase_for(action, frame)
    se.chibi_prop(s, action, facing, phase, 1, _short_sword)


def panday_fx(s, key, frame):
    if key == "q":  # Sword of Panday: a bright strike-spark into stone
        sl.glow(s, CX + 14, 26, 9, (235, 210, 140), alpha=150)
        for ang in range(0, 360, 60):
            a = math.radians(ang)
            pygame.draw.line(s, (255, 235, 190), (CX + 14, 26),
                             (CX + 14 + math.cos(a) * 8, 26 + math.sin(a) * 8), 2)
    elif key == "w":  # Weakness Reader: a discerning glint at the eyes
        sl.glow(s, CX, 13, 7, (200, 220, 255), alpha=140)
        pygame.draw.line(s, (230, 240, 255), (CX - 6, 13), (CX + 6, 13), 1)
    elif key == "e":  # Panday's Throw: a whirling motion streak
        pygame.draw.arc(s, (225, 225, 235), (CX - 2, 14, 30, 30), -0.6, 1.4, 2)
        sl.glow(s, CX + 16, 28, 6, (235, 220, 180), alpha=120)
    else:  # r Master's Slash: a wide double-arc cleave
        pygame.draw.arc(s, (230, 232, 240), (CX - 20, 10, 60, 46), -1.3, 1.3, 3)
        pygame.draw.arc(s, (255, 255, 255), (CX - 14, 16, 48, 34), -1.1, 1.1, 1)


def _ground_sword() -> int:
    """The sword Panday forges into a wall (Q): a stationary ground pickup
    the client draws for `EntityType.PICKUP` entities via the "entities"
    sprite category (`client/sprites.py`'s generic `frame()` lookup)."""
    s = sl.surf(48)
    cx, cy = 24, 30
    sl.glow(s, cx, cy - 4, 14, (235, 210, 140), alpha=90)
    # Blade planted point-down, angled slightly.
    tip = (cx - 3, cy + 16)
    base_l, base_r = (cx - 6, cy - 14), (cx + 4, cy - 14)
    pygame.draw.polygon(s, (215, 220, 228), [base_l, tip, base_r])
    pygame.draw.polygon(s, (40, 36, 34), [base_l, tip, base_r], 2)
    pygame.draw.line(s, (150, 118, 60), (cx - 9, cy - 15), (cx + 1, cy - 13), 3)
    sl.save(s, "entities", "panday_sword_ground", "idle")
    return 1


def _effects() -> int:
    n = 0
    for i in range(5):
        frac = i / 4
        s = sl.surf(96)
        c = 48
        sl.ring(s, c, c, int((c - 6) * frac), (170, 190, 230),
               width=max(2, int(5 * (1 - frac))), alpha=int(210 * (1 - frac)))
        for ang in range(0, 360, 30):
            a = math.radians(ang) + frac * 1.5
            r0 = (c - 10) * frac
            pygame.draw.line(s, (200, 215, 245, int(200 * (1 - frac))),
                             (c + math.cos(a) * r0, c + math.sin(a) * r0),
                             (c + math.cos(a) * (r0 + 6), c + math.sin(a) * (r0 + 6)), 2)
        sl.save(s, "effects", "panday_disarm", f"play_{i}")
        n += 1
    for i in range(5):
        frac = i / 4
        s = sl.surf(96)
        c = 48
        a = int(230 * (1 - frac))
        pygame.draw.line(s, (*(220, 225, 235), a), (c, c - 30), (c, c + 20), 5)
        sl.ring(s, c, c + 10, int((c - 20) * (0.3 + 0.7 * frac)), (235, 210, 140),
               width=3, alpha=a)
        sl.save(s, "effects", "panday_pin", f"play_{i}")
        n += 1
    return n


def main() -> int:
    n = 0
    n += se.emit_hero("panday", PANDAY_PAL, body_fn=panday_body,
                      overlay=panday_overlay, skill_fx=panday_fx)
    n += _ground_sword()
    n += _effects()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
