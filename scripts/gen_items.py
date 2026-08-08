"""Procedural placeholder icons for shop/inventory items: one static,
non-directional 64x64 gem per item in the registry, colored by its dominant
stat bonus so the shop reads at a glance (red = damage, green = vitality,
blue = mana/magic, grey = armor, yellow = utility/speed).

    uv run python scripts/gen_items.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Run from anywhere: put the repo root on the path so ``server`` imports
# resolve whether launched as ``python scripts/gen_items.py`` or via
# ``gen_all.py`` / ``uv run``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import spritelib as sl  # noqa: E402
import pygame  # noqa: E402

from server.items import ITEM_REGISTRY  # noqa: E402

# Bonus key -> (fill, edge). Checked in priority order so a multi-stat item
# (e.g. Spirit Charm: sp_def + sp_atk) still picks one clear identity color.
_CATEGORY_COLORS = (
    ("atk_dmg", ((200, 70, 70), (255, 140, 130))),
    ("hp", ((70, 160, 90), (150, 230, 160))),
    ("mana", ((70, 110, 200), (140, 180, 250))),
    ("sp_atk", ((130, 90, 200), (200, 160, 250))),
    ("phys_def", ((140, 140, 150), (210, 210, 220))),
    ("sp_def", ((110, 130, 160), (180, 200, 230))),
    ("atk_speed", ((200, 160, 70), (250, 220, 140))),
    ("move_speed", ((90, 190, 190), (160, 240, 240))),
)
_DEFAULT_COLOR = ((160, 150, 120), (230, 220, 190))


def _color_for(bonuses: dict) -> tuple[tuple, tuple]:
    for key, colors in _CATEGORY_COLORS:
        if key in bonuses:
            return colors
    return _DEFAULT_COLOR


def _icon(name: str, fill, edge, recipe: bool) -> pygame.Surface:
    s = sl.surf()
    cx = sl.CX
    pts = [(cx, cx - 20), (cx + 16, cx), (cx, cx + 20), (cx - 16, cx)]
    sl.glow(s, cx, cx, 16, fill, alpha=90)
    pygame.draw.polygon(s, fill, pts)
    pygame.draw.polygon(s, edge, pts, 2)
    # A small inner facet mark distinguishes built (recipe) items from basics.
    if recipe:
        pygame.draw.polygon(
            s, edge,
            [(cx, cx - 9), (cx + 7, cx), (cx, cx + 9), (cx - 7, cx)], 1)
    else:
        pygame.draw.circle(s, edge, (cx, cx - 3), 3)
    return s


def main() -> int:
    n = 0
    for item_id, cls in ITEM_REGISTRY.items():
        fill, edge = _color_for(cls.bonuses)
        icon = _icon(cls.name, fill, edge, bool(cls.components))
        sl.save(icon, "items", item_id, "icon")
        n += 1
    return n


if __name__ == "__main__":
    sl.main_guard(main)
