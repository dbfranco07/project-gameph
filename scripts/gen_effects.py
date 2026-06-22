"""Procedural placeholder AoE/impact effect sprites (one-shot frame sequences):
smash, earthshatter, arrowstorm, sanctuary, renewwave (ground decals) and
hit_phys / hit_special (impact sparks). The client scales ground decals to the
ability radius and cycles the frames over the effect's lifetime.

    uv run python scripts/gen_effects.py
"""

from __future__ import annotations

import math
import spritelib as sl
import pygame

FRAMES = 5          # one-shot sequence length
DECAL = 96          # ground decal reference size (scaled to AoE radius client-side)


def _decal_sequence(name, col, builder) -> int:
    for i in range(FRAMES):
        frac = i / (FRAMES - 1)
        s = sl.surf(DECAL)
        builder(s, frac, col)
        sl.save(s, "effects", name, f"play_{i}")
    return FRAMES


def _shock(s, frac, col):
    c = DECAL // 2
    sl.ring(s, c, c, int((c - 4) * frac), col,
            width=max(2, int(6 * (1 - frac))), alpha=int(230 * (1 - frac)))
    sl.ring(s, c, c, int((c - 4) * frac * 0.6), col, width=2,
            alpha=int(150 * (1 - frac)))


def _cracks(s, frac, col):
    c = DECAL // 2
    a = int(230 * (1 - frac))
    for k in range(8):
        ang = k * math.tau / 8
        r = int((c - 4) * frac)
        pygame.draw.line(s, (*col, a), (c, c),
                         (c + math.cos(ang) * r, c + math.sin(ang) * r), 3)


def _rain(s, frac, col):
    c = DECAL // 2
    a = int(230 * (1 - frac))
    for k in range(10):
        ang = k * math.tau / 10
        rr = (c - 6)
        x = c + math.cos(ang) * rr
        y0 = c + math.sin(ang) * rr - 18
        pygame.draw.line(s, (*col, a), (x, y0 + frac * 18), (x, y0 + 8 + frac * 18), 2)
    sl.ring(s, c, c, int((c - 4) * frac), col, width=2, alpha=a // 2)


def _bloom(s, frac, col):
    c = DECAL // 2
    a = int(200 * (1 - frac * 0.7))
    sl.glow(s, c, c, int((c - 6) * (0.4 + 0.6 * frac)), col, alpha=a // 2)
    sl.ring(s, c, c, int((c - 4) * frac), col, width=3, alpha=a)


def _spark_seq(name, col) -> int:
    for i in range(FRAMES):
        frac = i / (FRAMES - 1)
        sl.save(sl.spark(40, frac, col), "effects", name, f"play_{i}")
    return FRAMES


def main() -> int:
    n = 0
    n += _decal_sequence("smash", (235, 150, 60), _shock)
    n += _decal_sequence("earthshatter", (210, 120, 50), _cracks)
    n += _decal_sequence("arrowstorm", (240, 220, 120), _rain)
    n += _decal_sequence("sanctuary", (240, 235, 170), _bloom)
    n += _decal_sequence("renewwave", (130, 230, 160), _bloom)
    n += _spark_seq("hit_phys", (255, 220, 150))
    n += _spark_seq("hit_special", (160, 200, 255))
    return n


if __name__ == "__main__":
    sl.main_guard(main)
