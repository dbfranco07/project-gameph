"""Procedural sprites for Pedro Penduko, wielder of the Mutya.

He wears orange, carries a wooden stick (a hand-anchored prop, tracking his
arm pose via sprite_engine's chibi_prop), and the seven-colored gem on his
chest (an `overlay`, drawn on the SS canvas before downsampling). Each of his
eight cast poses lights his whole body in that skill's Mutya color — a
`tint_body` rim-light wash on top of the shaded chibi body, not just the
chest gem — plus a matching glow behind him:

    Q Red · W Orange · E Yellow (song) · R Green · T Blue (leap) ·
    Y Indigo (sight) · U Violet · I White (the radiant nuke).

The White ultimate is unit-targeted/instant, so no projectile is needed.

    uv run python scripts/gen_sprite_pedro.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

PAL = {
    "skin": (206, 168, 132), "hair": (28, 22, 18),
    "cloth": (214, 122, 40), "cloth_dk": (150, 82, 26),  # orange garb
    "eye": (60, 40, 26),
}

# The seven Mutya colors, keyed by the cast key they belong to.
MUTYA = {
    "q": (224, 60, 52),     # red
    "w": (236, 140, 48),    # orange
    "e": (244, 214, 70),    # yellow
    "r": (90, 196, 96),     # green
    "t": (70, 130, 230),    # blue
    "y": (92, 80, 190),     # indigo
    "u": (170, 92, 214),    # violet
    "i": (245, 245, 250),   # white
}
SKILL_KEYS = ("q", "w", "e", "r", "t", "y", "u", "i")


def amulet(s, action, facing, frame):
    """The Mutya: a small gem on the chest that shifts through its seven
    colors, drawn on the SS canvas."""
    if facing == "n":
        return  # back turned: gem hidden
    cols = list(MUTYA.values())[:7]
    col = cols[frame % len(cols)] if action in ("idle", "move") else cols[2]
    se.circle(s, col, (CX, 26), 2.4, ow=1.2)


def _stick(s, x, y, angle):
    dx, dy = math.cos(angle), math.sin(angle)
    tip = (x + dx * 9, y + dy * 9)
    top = (x - dx * 15, y - dy * 15 - 4)
    se.poly(s, (92, 66, 38), se.capsule_pts(top[0], top[1], tip[0], tip[1], 2.6),
           ow=1.1)


def overlay(s, action, facing, frame):
    amulet(s, action, facing, frame)
    phase = se._phase_for(action, frame)
    se.chibi_prop(s, action, facing, phase, 1, _stick)
    if action in MUTYA:
        se.tint_body(s, MUTYA[action], amount=0.4)


def skill_fx(s, key, frame):
    col = MUTYA.get(key, sl.WHITE)
    sl.glow(s, CX, 34, 20, col, alpha=110)
    if key == "e":          # Yellow — Awit: musical notes + sound rings
        for dx, dy in ((-12, 10), (10, 6), (16, 14)):
            x, y = CX + dx, 26 + dy - (2 if frame else 0)
            pygame.draw.circle(s, col, (x, y), 2)
            pygame.draw.line(s, col, (x + 2, y), (x + 2, y - 6), 1)
        for i, r in enumerate((10, 15, 20)):
            sl.ring(s, CX, 26, r + frame, col, width=1, alpha=200 - i * 55)
    elif key == "t":        # Blue — Lukso: an upward leap arc + dust
        pygame.draw.arc(s, col, (CX - 18, 14, 36, 36), 0.3, 2.84, 3)
        for dx in (-10, 0, 10):
            pygame.draw.circle(s, (210, 200, 180), (CX + dx, 54), 2)
    elif key == "y":        # Indigo — Mata: an all-seeing eye
        pygame.draw.ellipse(s, (235, 235, 245), (CX - 9, 8, 18, 11))
        pygame.draw.circle(s, col, (CX, 13), 4)
        pygame.draw.circle(s, sl.BLACK, (CX, 13), 2)
        for ang in range(0, 360, 45):
            a = math.radians(ang)
            pygame.draw.line(s, col, (CX + math.cos(a) * 11, 13 + math.sin(a) * 11),
                             (CX + math.cos(a) * 14, 13 + math.sin(a) * 14), 1)
    elif key == "u":        # Violet — Ilag: dodgy after-images
        for off in (-7, 7):
            pygame.draw.ellipse(s, col, (CX + off - 6, 26, 12, 18), 1)
    elif key == "i":        # White — Puti: a radiant burst
        sl.glow(s, CX, 30, 22, (245, 245, 255), alpha=170)
        for ang in range(0, 360, 30):
            a = math.radians(ang + frame * 12)
            pygame.draw.line(s, (255, 255, 255), (CX, 30),
                             (CX + math.cos(a) * (16 + 4 * frame),
                              30 + math.sin(a) * (16 + 4 * frame)), 2)
    else:                   # Red / Orange / Green — a held-power aura + gem flare
        pygame.draw.circle(s, col, (CX + 15, 30), 5)
        pygame.draw.circle(s, (250, 250, 255), (CX + 13, 28), 2)


def face_fx(s):
    # A small rainbow arc above the portrait to mark the Mutya-bearer.
    cols = list(MUTYA.values())[:7]
    for i, col in enumerate(cols):
        pygame.draw.arc(s, col, (CX - 18 + i, 40 - i, 36 - 2 * i, 36 - 2 * i),
                        0.5, 2.64, 2)


def main() -> int:
    return se.emit_hero("pedro", PAL, overlay=overlay, skill_fx=skill_fx,
                        face_fx=face_fx, skill_keys=SKILL_KEYS)


if __name__ == "__main__":
    sl.main_guard(main)
