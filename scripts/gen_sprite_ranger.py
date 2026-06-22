"""Procedural placeholder sprites for the Ranger (idle/move/attack + Q/W/E/R cast
poses) and its Piercing Shot projectile. Run via gen_all.py or directly:

    uv run python scripts/gen_sprite_ranger.py
"""

from __future__ import annotations

import math
import spritelib as sl
import pygame

PAL = {
    "skin": (214, 184, 150), "hair": (60, 40, 24),
    "cloth": (46, 104, 70), "cloth_dk": (30, 70, 48),
    "eye": (30, 60, 40),
}


def skill_fx(s, key, frame):
    if key == "q":  # Piercing Shot: a long arrow loosed forward
        y = 30
        pygame.draw.line(s, (230, 220, 180), (sl.CX + 6, y), (sl.CX + 26, y), 2)
        pygame.draw.polygon(s, (240, 235, 200),
                            [(sl.CX + 26, y), (sl.CX + 22, y - 3),
                             (sl.CX + 22, y + 3)])
    elif key == "w":  # Tumble: roll motion arcs
        for i, r in enumerate((10, 14, 18)):
            sl.ring(s, sl.CX, sl.CX, r, (180, 220, 190),
                    width=2, alpha=150 - i * 40)
    elif key == "e":  # Hunter's Focus: keen-eye glow
        sl.glow(s, sl.CX, 28, 16, (240, 220, 120), alpha=120)
    else:  # r Arrow Storm: arrows raining down
        for dx in (-10, 0, 10):
            x = sl.CX + dx + (2 if frame else 0)
            pygame.draw.line(s, (235, 225, 190), (x, 6), (x, 16), 2)


def projectile() -> int:
    s = sl.surf(40)
    pygame.draw.line(s, (235, 225, 190), (6, 20), (30, 20), 3)
    pygame.draw.polygon(s, (245, 240, 210),
                        [(34, 20), (28, 16), (28, 24)])
    pygame.draw.line(s, (160, 130, 90), (6, 20), (10, 17), 2)
    pygame.draw.line(s, (160, 130, 90), (6, 20), (10, 23), 2)
    sl.save(s, "projectiles", "ranger_q", "fly")
    return 1


def main() -> int:
    n = sl.emit_hero("ranger", PAL, skill_fx=skill_fx)
    n += projectile()
    return n


if __name__ == "__main__":
    sl.main_guard(main)
