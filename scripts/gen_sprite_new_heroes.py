"""Procedural placeholder sprites for the eight newer heroes:

    Tiyanak · Mangkukulam · Aswang · Jose Rizal · Apolinario Mabini ·
    Melchora Aquino · Andres Bonifacio · Lastikman

Each gets the standard set (idle/move/attack + Q/W/E/R cast poses + a `face`
portrait for hero-select) via ``spritelib.emit_hero``, plus the few line/hook
projectiles their kits fire (rizal_q / mabini_q / lastikman_q). Like the other
generators these are placeholders — drop real PNGs with the same paths to
upgrade without code changes.

    uv run python scripts/gen_sprite_new_heroes.py
"""

from __future__ import annotations

import math

import spritelib as sl
import pygame

CX = sl.CX


# ---------------------------------------------------------------------------
# Tiyanak — blood-hungry demon-infant assassin
# ---------------------------------------------------------------------------
TIYANAK_PAL = {
    "skin": (172, 166, 170), "hair": (30, 24, 28),
    "cloth": (124, 40, 46), "cloth_dk": (84, 26, 32),
    "eye": (236, 60, 55), "claw": sl.WHITE,
}


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


# ---------------------------------------------------------------------------
# Mangkukulam — curse-weaving witch
# ---------------------------------------------------------------------------
MANGKUKULAM_PAL = {
    "skin": (202, 182, 172), "hair": (40, 30, 46),
    "cloth": (104, 64, 150), "cloth_dk": (66, 40, 98),
    "eye": (120, 230, 140),
}


def mangkukulam_fx(s, key, frame):
    if key == "q":  # Hex Aura: a swirling violet ring + motes
        sl.ring(s, CX, 32, 16 + 2 * frame, (180, 120, 230), width=3, alpha=200)
        for ang in range(0, 360, 60):
            a = math.radians(ang + frame * 20)
            pygame.draw.circle(s, (210, 160, 250),
                               (CX + int(math.cos(a) * 18),
                                32 + int(math.sin(a) * 18)), 2)
    elif key == "w":  # Worm Curse: a wriggling green worm
        pts = [(CX + 10, 26), (CX + 15, 22), (CX + 19, 28), (CX + 24, 24)]
        pygame.draw.lines(s, (150, 190, 90), False, pts, 4)
        pygame.draw.circle(s, (90, 130, 60), (CX + 24, 24), 3)
    elif key == "e":  # Evil Eye: a watching eye glyph
        pygame.draw.ellipse(s, sl.WHITE, (CX - 7, 6, 14, 9))
        pygame.draw.circle(s, (140, 60, 200), (CX, 11), 3)
        pygame.draw.circle(s, sl.BLACK, (CX, 11), 1)
    else:  # r Pangkukulam: a great curse, rings bursting outward
        for i, r in enumerate((10, 17, 24)):
            sl.ring(s, CX, 30, r + 3 * frame, (150, 70, 200),
                    width=2, alpha=200 - i * 50)


# ---------------------------------------------------------------------------
# Aswang — shapeshifting devourer
# ---------------------------------------------------------------------------
ASWANG_PAL = {
    "skin": (150, 140, 130), "hair": (24, 20, 24),
    "cloth": (72, 40, 46), "cloth_dk": (48, 28, 32),
    "eye": (240, 200, 80), "claw": (232, 230, 224),
}


def aswang_fx(s, key, frame):
    if key == "q":  # Devour: gaping toothed maw
        mx = CX + 13
        pygame.draw.circle(s, (40, 16, 18), (mx, 18), 6)
        for t in range(-4, 5, 4):
            pygame.draw.polygon(s, sl.WHITE,
                                [(mx + t - 2, 13), (mx + t + 2, 13), (mx + t, 18)])
            pygame.draw.polygon(s, sl.WHITE,
                                [(mx + t - 2, 23), (mx + t + 2, 23), (mx + t, 18)])
    elif key == "w":  # Shapeshift: morphing swirl
        for i, col in enumerate(((220, 200, 120), (160, 120, 90),
                                 (110, 150, 110))):
            a = math.radians(frame * 40 + i * 120)
            pygame.draw.arc(s, col, (CX - 16, 14, 32, 32), a, a + 2.0, 3)
    elif key == "e":  # Nightstalker: fang + a blood drop
        pygame.draw.polygon(s, sl.WHITE,
                            [(CX + 8, 16), (CX + 12, 16), (CX + 10, 23)])
        pygame.draw.circle(s, (170, 30, 36), (CX + 10, 27 + frame), 2)
    else:  # r True Aswang: dark winged terror
        sl.glow(s, CX, 30, 18, (120, 30, 40), alpha=130)
        for side in (-1, 1):
            pygame.draw.arc(s, (30, 20, 26),
                            (CX + side * 4 - 14, 18, 28, 22),
                            0.2, 2.9, 3)


# ---------------------------------------------------------------------------
# Jose Rizal — scholar-hero with pen and word
# ---------------------------------------------------------------------------
RIZAL_PAL = {
    "skin": (214, 184, 150), "hair": (28, 22, 20),
    "cloth": (40, 46, 78), "cloth_dk": (26, 30, 54),
    "eye": (60, 44, 30),
}


def rizal_fx(s, key, frame):
    if key == "q":  # Pluma Throw: a quill pen cast forward
        _quill(s, CX + 8, 30, CX + 26, 22)
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
        sl.glow(s, CX, 14, 14, (245, 220, 120), alpha=130)
        sl.ring(s, CX, 14, 12, (255, 240, 180), width=2, alpha=210)


def _quill(s, x0, y0, x1, y1):
    pygame.draw.line(s, (40, 40, 48), (x0, y0), (x1, y1), 2)     # shaft
    pygame.draw.polygon(s, (235, 235, 240),                      # feather
                        [(x1, y1), (x1 - 6, y1 - 2), (x1 - 4, y1 - 7),
                         (x1 + 1, y1 - 3)])
    pygame.draw.circle(s, (30, 30, 40), (x0, y0), 2)             # nib end


# ---------------------------------------------------------------------------
# Apolinario Mabini — the Sublime Paralytic (a seated control mage)
# ---------------------------------------------------------------------------
MABINI_PAL = {
    "skin": (210, 180, 150), "hair": (26, 22, 20),
    "cloth": (98, 60, 52), "cloth_dk": (66, 40, 34),
    "eye": (50, 40, 30),
}


def mabini_overlay(s, action, facing, frame):
    # His wheelchair: a pair of wheels flanking the lower body.
    for side in (-1, 1):
        wx = CX + side * 9
        pygame.draw.circle(s, (40, 36, 40), (wx, 50), 6)
        pygame.draw.circle(s, (90, 84, 90), (wx, 50), 6, 2)
        pygame.draw.circle(s, (120, 114, 120), (wx, 50), 1)


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
# Lastikman — elastic stretch-fighter
# ---------------------------------------------------------------------------
LASTIKMAN_PAL = {
    "skin": (212, 178, 150), "hair": (30, 26, 40),
    "cloth": (60, 110, 200), "cloth_dk": (40, 76, 150),
    "eye": (40, 60, 110),
}


def lastikman_fx(s, key, frame):
    if key == "q":  # Stretch Punch: a fist flung out on a rubbery arm
        reach = 22 + 4 * frame
        pygame.draw.line(s, (212, 178, 150), (CX + 6, 30), (CX + reach, 28), 4)
        pygame.draw.circle(s, (60, 110, 200), (CX + reach, 28), 5)
        pygame.draw.circle(s, (40, 76, 150), (CX + reach, 28), 5, 2)
    elif key == "w":  # Grapple: an elastic hook-line to the side
        pygame.draw.line(s, (90, 140, 220), (CX + 6, 28), (CX + 22, 16), 2)
        pygame.draw.circle(s, (200, 210, 230), (CX + 22, 16), 3)
    elif key == "e":  # Elastic Body: bouncy resilience rings
        for i, r in enumerate((10, 15, 20)):
            sl.ring(s, CX, 32, r, (120, 170, 240), width=2, alpha=170 - i * 45)
    else:  # r Rubber Storm: flailing stretched limbs all around
        for ang in range(0, 360, 60):
            a = math.radians(ang + frame * 25)
            ex, ey = CX + math.cos(a) * 20, 32 + math.sin(a) * 18
            pygame.draw.line(s, (212, 178, 150), (CX, 32), (ex, ey), 3)
            pygame.draw.circle(s, (60, 110, 200), (int(ex), int(ey)), 3)


# ---------------------------------------------------------------------------
# Projectiles (only the kits that fire one)
# ---------------------------------------------------------------------------
def _projectiles() -> int:
    n = 0
    # Rizal's pen boomerang.
    s = sl.surf(40)
    _quill(s, 8, 28, 32, 14)
    sl.save(s, "projectiles", "rizal_q", "fly")
    n += 1
    # Mabini's Constitution Bolt: a glowing special bolt.
    s = sl.surf(40)
    sl.glow(s, 20, 20, 12, (130, 180, 255), alpha=160)
    pygame.draw.circle(s, (225, 238, 255), (20, 20), 6)
    pygame.draw.circle(s, (150, 195, 255), (20, 20), 6, 2)
    sl.save(s, "projectiles", "mabini_q", "fly")
    n += 1
    # Lastikman's Stretch Punch: a flying fist trailing a rubbery band.
    s = sl.surf(40)
    pygame.draw.line(s, (212, 178, 150), (4, 22), (24, 20), 4)
    pygame.draw.circle(s, (60, 110, 200), (28, 20), 8)
    pygame.draw.circle(s, (40, 76, 150), (28, 20), 8, 2)
    pygame.draw.line(s, (90, 130, 180), (25, 16), (31, 16), 2)
    sl.save(s, "projectiles", "lastikman_q", "fly")
    n += 1
    return n


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
_HEROES = [
    ("tiyanak", TIYANAK_PAL, {"skill_fx": tiyanak_fx}),
    ("mangkukulam", MANGKUKULAM_PAL, {"skill_fx": mangkukulam_fx}),
    ("aswang", ASWANG_PAL, {"skill_fx": aswang_fx}),
    ("rizal", RIZAL_PAL, {"skill_fx": rizal_fx}),
    ("mabini", MABINI_PAL,
     {"skill_fx": mabini_fx, "overlay": mabini_overlay}),
    ("melchora", MELCHORA_PAL, {"skill_fx": melchora_fx}),
    ("bonifacio", BONIFACIO_PAL, {"skill_fx": bonifacio_fx}),
    ("lastikman", LASTIKMAN_PAL, {"skill_fx": lastikman_fx}),
]


def main() -> int:
    n = 0
    for hero_id, pal, hooks in _HEROES:
        n += sl.emit_hero(hero_id, pal, **hooks)
    n += _projectiles()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
