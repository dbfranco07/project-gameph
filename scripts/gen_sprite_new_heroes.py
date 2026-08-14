"""Procedural sprites for three of the newer heroes, now on the expressive
sprite_engine.py chibi engine (matching Rizal/Kapre/etc.):

    Apolinario Mabini · Melchora Aquino · Andres Bonifacio

Each gets identity hooks via se's head_fn/hair_fn/face_fn/torso_fn instead of
the flat default chibi look: Mabini keeps his wheelchair (now se-shaded, not
raw pygame circles) plus a side-parted hairline and round spectacles;
Melchora gets a grey hair bun and a draped shawl over the base torso; and
Bonifacio gets a rebel red bandana and carries a bolo at idle via chibi_prop.

Each gets the standard set (idle/move/attack + Q/W/E/R cast poses + a `face`
portrait for hero-select) via ``sprite_engine.emit_hero``, plus one projectile
per kit that fires something: Mabini's Constitution Bolt (Q, distinct from
his ranged basic attack) and both Mabini's and Melchora's plain ranged basic
attack bolt (Bonifacio is melee, no projectile).

    uv run python scripts/gen_sprite_new_heroes.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX
_INK = (30, 26, 24)


# ---------------------------------------------------------------------------
# Apolinario Mabini — the Sublime Paralytic (a seated control mage)
# ---------------------------------------------------------------------------
MABINI_PAL = {
    "skin": (210, 180, 150), "hair": (26, 22, 20),
    "cloth": (98, 60, 52), "cloth_dk": (66, 40, 34),
    "eye": (50, 40, 30),
}


def mabini_hair(s, skin, hair, facing):
    cx, cy = CX, 15.0
    pts = [(cx - 12, cy - 2), (cx - 11, cy - 11), (cx - 1, cy - 15),
           (cx + 3, cy - 14), (cx + 12, cy - 9), (cx + 12, cy - 2)]
    se.poly(s, hair, pts, hi=se.lighten(hair, 0.3))


def mabini_face(s, skin, facing):
    cx, cy = CX, 15.0
    for side in (-1, 1):
        se.circle(s, (205, 210, 220), (cx + side * 4.5, cy), 3.0,
                  outline=_INK, ow=0.8, highlight=False, shadow=False)
    se.line(s, _INK, (cx - 1.5, cy), (cx + 1.5, cy), 0.8)


def mabini_head(s, pal, facing):
    se.chibi_head(s, pal.get("skin", (200, 180, 160)), pal.get("hair", sl.BLACK),
                 facing, pal.get("eye", (40, 30, 30)),
                 hair_fn=mabini_hair, face_fn=mabini_face)


def mabini_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame, head_fn=mabini_head)


def mabini_overlay(s, action, facing, frame):
    # His wheelchair: a pair of shaded wheels flanking the lower body.
    for side in (-1, 1):
        wx = CX + side * 9
        se.circle(s, (40, 36, 40), (wx, 50), 6, outline=(20, 18, 20), ow=1.2)
        se.dot(s, (150, 144, 150), (wx, 50), 1.1)


def mabini_fx(s, key, frame):
    if key == "q":  # Constitution Bolt: a charged blue bolt at the hand
        sl.glow(s, CX + 16, 30, 8, (130, 180, 255), alpha=160)
        pygame.draw.circle(s, (220, 235, 255), (CX + 16, 30), 4)
    elif key == "w":  # Decalogue: a graven tablet of edicts
        pygame.draw.rect(s, (210, 205, 190), (CX + 8, 22, 14, 18),
                         border_radius=2)
        for y in (27, 31, 35):
            pygame.draw.line(s, (110, 100, 90), (CX + 11, y), (CX + 19, y), 1)
    elif key == "e":  # Brains over Brawn: a glowing intellect
        sl.glow(s, CX, 12, 11, (235, 150, 200), alpha=130)
    else:  # r Paralysis: crackling stun bolts
        for dx in (-12, 0, 12):
            x = CX + dx
            pygame.draw.lines(s, (180, 215, 255), False,
                              [(x, 10), (x - 3, 18), (x + 3, 24), (x - 2, 32)], 2)


# ---------------------------------------------------------------------------
# Melchora Aquino ("Tandang Sora") — matronly guardian support
# ---------------------------------------------------------------------------
MELCHORA_PAL = {
    "skin": (224, 200, 180), "hair": (220, 218, 222),
    "cloth": (178, 142, 88), "cloth_dk": (132, 102, 58),
    "eye": (90, 70, 50),
}


def melchora_hair(s, skin, hair, facing):
    cx, cy = CX, 15.0
    se.circle(s, hair, (cx, cy - 2), 10.5, hi=se.lighten(hair, 0.3))
    se.circle(s, hair, (cx, cy - 11), 3.2, outline=_INK, ow=1.0,
             hi=se.lighten(hair, 0.35))


def melchora_head(s, pal, facing):
    se.chibi_head(s, pal.get("skin", (200, 180, 160)), pal.get("hair", sl.BLACK),
                 facing, pal.get("eye", (40, 30, 30)), hair_fn=melchora_hair)


def melchora_torso(s, pal, action, facing, frame, lean, bob):
    se.chibi_torso(s, pal["cloth"], pal["cloth_dk"], lean=lean, bob=bob)
    x = CX + lean
    y = 24 + bob
    # a shawl draped over the shoulders
    shawl = se.darken(pal["cloth"], 0.12)
    se.poly(s, shawl,
           [(x - 9, y - 2), (x + 9, y - 2), (x + 6, y + 9), (x - 6, y + 9)],
           sh=se.darken(shawl, 0.3), outline=_INK, ow=1.0)


def melchora_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame,
                      head_fn=melchora_head, torso_fn=melchora_torso)


def melchora_fx(s, key, frame):
    if key == "q":  # Sheltering Hand: a warding shield at the hand
        _shield(s, CX + 16, 30)
    elif key == "w":  # Rallying Words: emboldening sparks rising
        for dx, dy in ((-8, 18), (0, 12), (9, 16)):
            y = 30 + dy - (3 if frame else 0)
            pygame.draw.polygon(s, (250, 225, 150),
                                [(CX + dx, y - 4), (CX + dx - 3, y),
                                 (CX + dx + 3, y)])
    elif key == "e":  # Matriarch: a warm protective aura
        sl.glow(s, CX, 30, 18, (240, 210, 140), alpha=120)
    else:  # r Refuge: a sheltering dome
        pygame.draw.arc(s, (255, 240, 190), (CX - 22, 14, 44, 44),
                        0.05, math.pi - 0.05, 3)
        sl.glow(s, CX, 34, 14, (250, 235, 180), alpha=110)


def _shield(s, x, y):
    pts = [(x - 6, y - 7), (x + 6, y - 7), (x + 6, y + 1),
           (x, y + 8), (x - 6, y + 1)]
    pygame.draw.polygon(s, (230, 210, 150), pts)
    pygame.draw.polygon(s, (150, 120, 70), pts, 2)


# ---------------------------------------------------------------------------
# Andres Bonifacio — the Supremo: bolo-wielding frontline rallier
# ---------------------------------------------------------------------------
BONIFACIO_PAL = {
    "skin": (206, 170, 140), "hair": (26, 22, 20),
    "cloth": (172, 52, 44), "cloth_dk": (120, 34, 30),
    "eye": (50, 34, 26),
}


def bonifacio_hair(s, skin, hair, facing):
    cx, cy = CX, 15.0
    spikes = [(cx + dx, cy + dy) for dx, dy in
             ((-11, -1), (-11, -10), (-4, -13), (0, -6), (4, -13),
              (11, -10), (11, -1))]
    se.poly(s, hair, spikes, hi=se.lighten(hair, 0.3))
    # red Katipunan bandana knotted at the brow
    band = (210, 40, 34)
    se.rect(s, band, (cx - 12, cy - 3, 24, 4.5), outline=_INK, ow=1.0,
           hi=se.lighten(band, 0.3))


def bonifacio_head(s, pal, facing):
    se.chibi_head(s, pal.get("skin", (200, 180, 160)), pal.get("hair", sl.BLACK),
                 facing, pal.get("eye", (40, 30, 30)), hair_fn=bonifacio_hair)


def _bolo(s, x, y, angle):
    dx, dy = math.cos(angle), math.sin(angle)
    nx, ny = -dy, dx
    tip = (x + dx * 13, y + dy * 13)
    base_l = (x - nx * 2, y - ny * 2)
    base_r = (x + nx * 2, y + ny * 2)
    se.poly(s, (215, 220, 228), [base_l, tip, base_r], outline=_INK, ow=1.0,
           hi=(245, 248, 252))
    se.line(s, (70, 44, 30), (x - dx * 3, y - dy * 3), (x, y), 2.0)


def bonifacio_overlay(s, action, facing, frame):
    phase = se._phase_for(action, frame)
    se.chibi_prop(s, action, facing, phase, 1, _bolo)


def bonifacio_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame, head_fn=bonifacio_head)


def bonifacio_fx(s, key, frame):
    if key == "q":  # Bolo Cleave: a sweeping steel arc
        pygame.draw.arc(s, (220, 225, 235), (CX - 2, 16, 30, 30),
                        -1.1, 1.1, 3)
        pygame.draw.arc(s, (255, 255, 255), (CX, 18, 28, 26), -0.9, 0.9, 1)
    elif key == "w":  # Rip the Cedula: torn paper scraps
        for dx, dy in ((-6, 24), (4, 22), (10, 28)):
            pygame.draw.polygon(s, (235, 230, 215),
                                [(CX + dx, 30 + dy), (CX + dx + 5, 28 + dy),
                                 (CX + dx + 3, 34 + dy)])
    elif key == "e":  # Katipunero: a red rallying aura
        sl.glow(s, CX, 30, 17, (220, 60, 50), alpha=120)
    else:  # r KKK Warcry: the Katipunan sun bursting forth
        pygame.draw.circle(s, (245, 210, 90), (CX, 26), 5)
        for ang in range(0, 360, 45):
            a = math.radians(ang)
            pygame.draw.line(s, (245, 210, 90), (CX, 26),
                             (CX + math.cos(a) * 11, 26 + math.sin(a) * 11), 2)


# ---------------------------------------------------------------------------
# Projectiles (skillshot + ranged basic attacks — kept visually distinct)
# ---------------------------------------------------------------------------
def _projectiles() -> int:
    n = 0
    # Mabini's Constitution Bolt (Q): a charged, ringed special bolt.
    s = sl.surf(40)
    sl.glow(s, 20, 20, 12, (130, 180, 255), alpha=160)
    pygame.draw.circle(s, (225, 238, 255), (20, 20), 6)
    pygame.draw.circle(s, (150, 195, 255), (20, 20), 6, 2)
    sl.save(s, "projectiles", "mabini_q", "fly")
    n += 1
    # Mabini's plain ranged basic attack: a small unadorned magic dart.
    s = sl.surf(40)
    pygame.draw.circle(s, (170, 205, 255), (20, 20), 4)
    pygame.draw.circle(s, (225, 238, 255), (20, 20), 2)
    sl.save(s, "projectiles", "mabini_atk", "fly")
    n += 1
    # Melchora's ranged basic attack: a warm tossed ember of light.
    s = sl.surf(40)
    sl.glow(s, 20, 20, 7, (250, 220, 150), alpha=130)
    pygame.draw.circle(s, (255, 240, 195), (20, 20), 3)
    sl.save(s, "projectiles", "melchora_atk", "fly")
    n += 1
    return n


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main() -> int:
    n = 0
    n += se.emit_hero("mabini", MABINI_PAL, body_fn=mabini_body,
                      overlay=mabini_overlay, skill_fx=mabini_fx)
    n += se.emit_hero("melchora", MELCHORA_PAL, body_fn=melchora_body,
                      skill_fx=melchora_fx)
    n += se.emit_hero("bonifacio", BONIFACIO_PAL, body_fn=bonifacio_body,
                      overlay=bonifacio_overlay, skill_fx=bonifacio_fx)
    n += _projectiles()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
