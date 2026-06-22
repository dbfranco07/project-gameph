"""Procedural placeholder sprites for the Tiktik: idle/move/attack + Q/W/E/R
(Tongue Hook / Wallrun / Barbed Tongue / Frenzy) and its tongue projectile head.
The Q pose shows the long tongue lashing out so it reads as a tongue, not a dot.

    uv run python scripts/gen_sprite_tiktik.py
"""

from __future__ import annotations

import spritelib as sl
import pygame

PAL = {
    "skin": (120, 150, 110), "hair": (40, 50, 34),
    "cloth": (70, 64, 96), "cloth_dk": (48, 44, 70),
    "eye": (240, 230, 120),
}


def skill_fx(s, key, frame):
    if key == "q":  # Tongue Hook: the tongue lashes forward from the mouth
        reach = 22 + 6 * frame
        sl.tongue_strip(s, sl.CX + 4, 18, sl.CX + reach, 16)
    elif key == "w":  # Wallrun: wall shimmer at the side
        for dy in (-8, 0, 8):
            pygame.draw.line(s, (150, 150, 190),
                             (sl.CX + 12, 24 + dy), (sl.CX + 16, 24 + dy), 2)
    elif key == "e":  # Barbed Tongue: a barbed tip
        sl.tongue_strip(s, sl.CX + 4, 18, sl.CX + 16, 16)
        pygame.draw.line(s, (120, 24, 48), (sl.CX + 16, 16), (sl.CX + 20, 12), 2)
        pygame.draw.line(s, (120, 24, 48), (sl.CX + 16, 16), (sl.CX + 20, 20), 2)
    else:  # r Frenzy: red speed aura
        sl.glow(s, sl.CX, 30, 17, (230, 90, 70), alpha=120)


def projectile() -> int:
    # The renderer draws the tongue body as a primitive band and caps it with
    # this head sprite (so missing art still looks like a tongue).
    s = sl.surf(24)
    pygame.draw.circle(s, (210, 80, 104), (12, 12), 7)
    pygame.draw.circle(s, (120, 24, 48), (12, 12), 7, 2)
    pygame.draw.line(s, (236, 132, 150), (8, 12), (16, 12), 2)
    sl.save(s, "projectiles", "tiktik_q", "tongue_head")
    return 1


def main() -> int:
    n = sl.emit_hero("tiktik", PAL, skill_fx=skill_fx)
    n += projectile()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
