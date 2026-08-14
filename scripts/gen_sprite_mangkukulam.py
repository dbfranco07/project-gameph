"""Procedural sprites for Mangkukulam: a curse-weaving witch.

Reads as an actual witch — a pointed hat (head_fn), a ragged jagged-hemmed
robe (torso_fn), and a stooped hunched posture (chibi_body_raw's `hunch`),
all shaded on sprite_engine's SS canvas. Her Worm Curse (W) summons keep
their existing small-creature look (pixelart's worm_body), written to
client/assets/entities/minion_worm/ — the exact path server/entity.py's
SummonedMinion._sub="worm" already expects, so no server/client changes.

    uv run python scripts/gen_sprite_mangkukulam.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import pixelart as px
import sprite_engine as se

CX = se.CX

MANGKUKULAM_PAL = {
    "skin": (196, 178, 168), "hair": (40, 30, 46),
    "cloth": (104, 64, 150), "cloth_dk": (66, 40, 98),
    "eye": (120, 230, 140),
}

WORM_PAL = {
    "cloth": (150, 190, 90), "cloth_dk": (90, 130, 60), "eye": (20, 20, 20),
}


def _no_hair(s, skin, hair, facing):
    pass  # the pointed hat replaces the hairline entirely


def mangkukulam_head(s, pal, facing):
    se.chibi_head(s, pal.get("skin", (200, 180, 160)), pal.get("hair", sl.BLACK),
                 facing, pal.get("eye", (40, 30, 30)), hair_fn=_no_hair)
    cx, cy = CX, 15.0
    hat_col = pal.get("cloth", (104, 64, 150))
    hat_dk = pal.get("cloth_dk", (66, 40, 98))
    se.ellipse(s, hat_dk, (cx - 14, cy - 15, 28, 6), highlight=False)
    se.poly(s, hat_col, [(cx - 8, cy - 13), (cx + 8, cy - 13), (cx, cy - 31)],
           sh=hat_dk)


def mangkukulam_torso(s, pal, action, facing, frame, lean, bob):
    col, dark = pal["cloth"], pal["cloth_dk"]
    w, h = 18, 18
    x = CX - w / 2 + lean
    y = 20 + bob
    pts = [(x, y), (x + w, y), (x + w, y + h - 4), (x + w - 4, y + h),
           (x + w - 9, y + h - 4), (x + w / 2, y + h), (x + 9, y + h - 4),
           (x + 4, y + h), (x, y + h - 4)]
    se.poly(s, col, pts, sh=dark)


def witch_body(s, pal, action, facing, frame):
    se.chibi_body_raw(s, pal, action, facing, frame, head_fn=mangkukulam_head,
                      torso_fn=mangkukulam_torso, hunch=2.0)


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


def _projectiles() -> int:
    # Basic attack: a small hex bolt — a violet motelet trailing a curved wisp.
    s = sl.surf(40)
    pygame.draw.line(s, (150, 70, 200), (6, 26), (30, 16), 3)
    pygame.draw.line(s, (110, 40, 160), (6, 26), (30, 16), 1)
    pygame.draw.circle(s, (210, 160, 250), (30, 16), 5)
    pygame.draw.circle(s, (140, 60, 200), (30, 16), 5, 2)
    for ang in (200, 260, 320):
        a = math.radians(ang)
        pygame.draw.circle(s, (190, 130, 240),
                           (30 + int(math.cos(a) * 8), 16 + int(math.sin(a) * 8)), 1)
    sl.save(s, "projectiles", "mangkukulam_atk", "fly")
    return 1


def main() -> int:
    n = se.emit_hero("mangkukulam", MANGKUKULAM_PAL, body_fn=witch_body,
                     skill_fx=mangkukulam_fx)
    n += px.emit_pixel_creature("minion_worm", WORM_PAL, px.worm_body)
    n += _projectiles()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
