"""Procedural placeholder sprites for the Manananggal: idle/move/attack, the
Q/W/E/R cast poses (Scratch / Pounce / Bloodlust / Split), the detached flying
upper half with emphasized flapping bat wings, the grounded lower body, and the
recombine/death effects. Supersedes the old scripts/gen_sprites.py.

    uv run python scripts/gen_sprite_manananggal.py
"""

from __future__ import annotations

import math
import spritelib as sl
import pygame

WING = (52, 30, 40)
WING_EDGE = (110, 60, 78)
GUT = (158, 48, 58)
GUT_DK = (112, 32, 44)

PAL = {
    "skin": (216, 186, 162), "hair": (22, 18, 26),
    "cloth": (116, 30, 44), "cloth_dk": (84, 20, 32),
    "claw": sl.WHITE, "eye": (220, 70, 60),
}


def _spread(action, frame):
    return {"idle": 0.3 + 0.1 * frame, "move": 0.6 + 0.3 * frame,
            "attack": 0.5, "q": 0.6, "w": 0.95, "split_flyer": 0.7 + 0.3 * frame
            }.get(action, 0.4)


def back_wings(s, action, facing, frame):
    sp = _spread(action, frame)
    sl.bat_wing(s, -1, sp, WING, WING_EDGE)
    sl.bat_wing(s, 1, sp, WING, WING_EDGE)


def skill_fx(s, key, frame):
    if key == "q":  # Scratch: a claw-slash arc
        for k in (-4, 0, 4):
            pygame.draw.arc(s, (245, 230, 235),
                            (sl.CX + 4, 18 + k, 22, 22), -0.8, 0.8, 2)
    elif key == "w":  # Pounce: leap motion blur below
        for i, r in enumerate((8, 13, 18)):
            sl.ring(s, sl.CX, 50, r, (200, 120, 140), width=2, alpha=150 - i * 45)
    elif key == "e":  # Bloodlust: red aura + drip
        sl.glow(s, sl.CX, 30, 17, (200, 50, 60), alpha=130)
        pygame.draw.circle(s, GUT, (sl.CX, 46 + (2 if frame else 0)), 2)
    else:  # r Split: detach line across the waist
        pygame.draw.line(s, GUT, (sl.CX - 9, 40), (sl.CX + 9, 40), 3)
        for dx in (-6, 0, 6):
            pygame.draw.circle(s, GUT_DK, (sl.CX + dx, 44), 2)


def _entrails(s, n, frame):
    x, y = sl.CX, 40
    for i in range(n):
        nx = sl.CX + int(3.2 * math.sin(i * 0.7 + frame))
        pygame.draw.line(s, GUT_DK, (x, y), (nx, y + 3), 3)
        x, y = nx, y + 3
    pygame.draw.circle(s, GUT, (x, y), 3)


def split_flyer(facing, frame) -> pygame.Surface:
    s = sl.surf()
    back_wings(s, "split_flyer", facing, frame)
    sl.torso(s, PAL["cloth"], PAL["cloth_dk"])
    sl.arms(s, PAL["skin"], "split_flyer", PAL["claw"])
    sl.head(s, PAL["skin"], PAL["hair"], facing, PAL["eye"])
    _entrails(s, 6, frame)
    return sl.oriented(s, facing)


def split_body() -> pygame.Surface:
    s = sl.surf()
    sl.shadow(s)
    pygame.draw.ellipse(s, GUT, (sl.CX - 8, 22, 16, 8))
    pygame.draw.ellipse(s, GUT_DK, (sl.CX - 8, 22, 16, 8), 1)
    pygame.draw.rect(s, PAL["cloth"], (sl.CX - 8, 26, 16, 12), border_radius=3)
    sl.legs(s, PAL["cloth"], PAL["cloth_dk"])
    return s


def main() -> int:
    n = sl.emit_hero("manananggal", PAL, back=back_wings, skill_fx=skill_fx)
    for f in sl.FACINGS:
        for fr in (0, 1):
            sl.save(split_flyer(f, fr), "heroes", "manananggal",
                    f"split_flyer_{f}_{fr}")
            n += 1
    sl.save(split_body(), "heroes", "manananggal", "split_body")
    n += 1
    return n


if __name__ == "__main__":
    sl.main_guard(main)
