"""Procedural placeholder sprites for non-hero entities: lane minions (melee /
ranged / cart), neutral jungle monsters, towers, the core, and runes.

    uv run python scripts/gen_entities.py
"""

from __future__ import annotations

import random

import spritelib as sl
import pygame


def wall_seg() -> pygame.Surface:
    """A horizontally-tileable stone-brick segment (tiled along a wall capsule)."""
    s = pygame.Surface((48, 48))
    s.fill((96, 94, 104))
    mortar, hi = (58, 56, 64), (120, 118, 128)
    rh = 12
    for r in range(4):
        y = r * rh
        pygame.draw.line(s, mortar, (0, y), (48, y), 2)
        off = (r % 2) * 12
        for x in range(off, 48 + 24, 24):
            for ox in (0, -48, 48):
                pygame.draw.line(s, mortar, (x + ox, y), (x + ox, y + rh), 2)
                pygame.draw.line(s, hi, (x + ox + 1, y + 2),
                                 (x + ox + 1, y + rh - 1), 1)
    return s


def tree_seg() -> pygame.Surface:
    """A horizontally-tileable leafy segment (tiled along a tree capsule)."""
    s = sl.tileable_noise(48, 48, (38, 82, 44), 140, seed=7)
    rng = random.Random(7)
    for _ in range(16):
        x, y, rr = rng.randint(0, 47), rng.randint(6, 42), rng.randint(4, 7)
        col = (rng.randint(46, 72), rng.randint(96, 132), rng.randint(52, 74))
        for ox in (0, -48, 48):
            pygame.draw.circle(s, col, (x + ox, y), rr)
    return s


def _minion(key, body, dark, accent=None) -> int:
    """idle (4 facings) + a 2-frame bob for `move`."""
    n = 0
    for facing in sl.FACINGS:
        idle = sl.blob(body, dark, r=12, outline=accent)
        sl.save(sl.oriented(idle, facing), "entities", key, f"idle_{facing}")
        n += 1
        for fr in (0, 1):
            mv = sl.blob(body, dark, r=12, outline=accent)
            if fr == 1:
                mv.scroll(0, -1)
            sl.save(sl.oriented(mv, facing), "entities", key, f"move_{facing}_{fr}")
            n += 1
    return n


def _cart() -> int:
    """A boxy siege cart instead of a blob."""
    n = 0
    for facing in sl.FACINGS:
        s = sl.surf()
        sl.shadow(s)
        pygame.draw.rect(s, (120, 96, 60), (sl.CX - 12, 26, 24, 18),
                         border_radius=3)
        pygame.draw.rect(s, (80, 62, 36), (sl.CX - 12, 26, 24, 18), 2,
                         border_radius=3)
        pygame.draw.circle(s, (40, 36, 30), (sl.CX - 7, 46), 4)
        pygame.draw.circle(s, (40, 36, 30), (sl.CX + 7, 46), 4)
        sl.save(sl.oriented(s, facing), "entities", "minion_cart", f"idle_{facing}")
        n += 1
    return n


def main() -> int:
    n = 0
    n += _minion("minion_melee", (150, 150, 160), (90, 90, 100))
    n += _minion("minion_ranged", (140, 170, 150), (84, 110, 92),
                 accent=(200, 230, 200))
    n += _cart()
    n += _minion("minion_neutral", (160, 130, 90), (100, 80, 54),
                 accent=(210, 180, 120))
    # Runes: a glowing diamond.
    for fr in (0, 1):
        s = sl.surf()
        sl.glow(s, sl.CX, sl.CX, 12 + fr, (180, 120, 230), alpha=130)
        pygame.draw.polygon(s, (210, 170, 250),
                            [(sl.CX, sl.CX - 9), (sl.CX + 8, sl.CX),
                             (sl.CX, sl.CX + 9), (sl.CX - 8, sl.CX)])
        pygame.draw.polygon(s, (250, 230, 255),
                            [(sl.CX, sl.CX - 9), (sl.CX + 8, sl.CX),
                             (sl.CX, sl.CX + 9), (sl.CX - 8, sl.CX)], 2)
        sl.save(s, "entities", "rune", f"idle_{fr}")
        n += 1
    # Towers + core (team-neutral grey; the client tints HP, the sprite reads as
    # a structure). Provide idle / core / dead.
    sl.save(sl.building((150, 150, 165), (90, 90, 105),
                        accent=(220, 220, 235)), "entities", "tower", "idle")
    sl.save(sl.building((150, 150, 165), (90, 90, 105), dead=True),
            "entities", "tower", "dead")
    sl.save(sl.building((170, 160, 120), (110, 100, 70),
                        accent=(255, 240, 180), core=True),
            "entities", "base", "core")
    sl.save(sl.building((170, 160, 120), (110, 100, 70),
                        accent=(255, 240, 180), core=True),
            "entities", "base", "idle")
    sl.save(sl.building((170, 160, 120), (110, 100, 70), dead=True),
            "entities", "base", "dead")
    n += 5
    # Wall + tree capsule segments (tiled along the obstacle by the renderer).
    sl.save(wall_seg(), "entities", "wall", "seg")
    sl.save(tree_seg(), "entities", "tree", "seg")
    n += 2
    return n


if __name__ == "__main__":
    sl.main_guard(main)
