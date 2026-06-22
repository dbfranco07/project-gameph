"""Procedural placeholder sprites for the Mender (idle/move/attack + Q/W/E/R) and
its Spirit Bolt projectile.

    uv run python scripts/gen_sprite_mender.py
"""

from __future__ import annotations

import spritelib as sl
import pygame

PAL = {
    "skin": (220, 200, 180), "hair": (210, 210, 220),
    "cloth": (90, 130, 200), "cloth_dk": (60, 92, 150),
    "eye": (60, 90, 140),
}


def skill_fx(s, key, frame):
    if key == "q":  # Spirit Bolt: a glowing orb forming at the hand
        sl.glow(s, sl.CX + 16, 30, 9, (150, 210, 255), alpha=160)
        pygame.draw.circle(s, (235, 245, 255), (sl.CX + 16, 30), 4)
    elif key == "w":  # Renewing Wave: green healing sparkles
        for dx, dy in ((-8, 20), (0, 14), (10, 22), (6, 12)):
            pygame.draw.circle(s, (150, 240, 170),
                               (sl.CX + dx, 30 + dy - (3 if frame else 0)), 2)
    elif key == "e":  # Blink: teleport shimmer
        for i, r in enumerate((8, 13, 18)):
            sl.ring(s, sl.CX, sl.CX, r, (190, 210, 255),
                    width=2, alpha=170 - i * 50)
    else:  # r Sanctuary: a radiant halo
        sl.glow(s, sl.CX, 26, 18, (240, 235, 170), alpha=120)
        sl.ring(s, sl.CX, 26, 16, (255, 250, 210), width=2, alpha=200)


def projectile() -> int:
    s = sl.surf(40)
    sl.glow(s, 20, 20, 12, (130, 200, 255), alpha=150)
    pygame.draw.circle(s, (235, 245, 255), (20, 20), 6)
    pygame.draw.circle(s, (180, 220, 255), (20, 20), 6, 2)
    sl.save(s, "projectiles", "mender_q", "fly")
    return 1


def main() -> int:
    n = sl.emit_hero("mender", PAL, skill_fx=skill_fx)
    n += projectile()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
