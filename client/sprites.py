"""Sprite loading for the client.

Sprites are optional, drop-in PNGs under ``client/assets``. The renderer asks
this manager for an entity's current frame; when no matching image exists it
returns ``None`` and the renderer falls back to its primitive-shape drawing, so
heroes/minions without art keep working.

Folder + naming convention (see client/assets/README.md):

    client/assets/heroes/<hero_id>/<action>_<facing>.png
    client/assets/heroes/<hero_id>/<action>_<facing>_<frame>.png   # animated
    client/assets/heroes/<hero_id>/<action>.png                    # non-directional

``facing`` is one of n/e/s/w. Animated actions number frames from 0. Lookups
fall back from the most specific name to the least (directional+frame ->
directional -> bare action -> idle), so a folder with only ``idle_s.png`` still
renders something for every action/facing.
"""

from __future__ import annotations

import os
import pygame

_ASSET_ROOT = os.path.join(os.path.dirname(__file__), "assets")
_HERO_DIR = os.path.join(_ASSET_ROOT, "heroes")

FACINGS = ("n", "e", "s", "w")


def facing_from_delta(dx: float, dy: float) -> str:
    """Map a movement vector to one of the four cardinal facings."""
    if abs(dx) >= abs(dy):
        return "e" if dx >= 0 else "w"
    return "s" if dy >= 0 else "n"


class SpriteManager:
    """Loads and caches per-hero sprite frames, with graceful fallback."""

    def __init__(self) -> None:
        # hero_id -> {stem: [Surface, ...]} ; loaded lazily on first request.
        self._heroes: dict[str, dict[str, list[pygame.Surface]]] = {}

    def _load_hero(self, hero_id: str) -> dict[str, list[pygame.Surface]]:
        cached = self._heroes.get(hero_id)
        if cached is not None:
            return cached

        frames: dict[str, list[pygame.Surface]] = {}
        folder = os.path.join(_HERO_DIR, hero_id)
        if os.path.isdir(folder):
            # Group files by their non-frame stem. "move_s_0.png" and
            # "move_s_1.png" both land under the "move_s" key, ordered by frame.
            buckets: dict[str, list[tuple[int, str]]] = {}
            for fname in os.listdir(folder):
                if not fname.lower().endswith(".png"):
                    continue
                stem = fname[:-4]
                parts = stem.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    key, frame = parts[0], int(parts[1])
                else:
                    key, frame = stem, 0
                buckets.setdefault(key, []).append((frame, fname))
            for key, items in buckets.items():
                items.sort()
                frames[key] = [
                    pygame.image.load(os.path.join(folder, fn)).convert_alpha()
                    for _, fn in items
                ]

        self._heroes[hero_id] = frames
        return frames

    def hero_frame(self, hero_id: str, action: str, facing: str,
                   anim_t: float, fps: float = 6.0) -> pygame.Surface | None:
        """Return the sprite frame for a hero, or ``None`` if it has no art.

        Tries the most specific name first and falls back gradually so a sparse
        sprite folder still renders. ``anim_t`` (seconds) drives frame cycling.
        """
        if not hero_id:
            return None
        frames = self._load_hero(hero_id)
        if not frames:
            return None
        for key in (f"{action}_{facing}", action, f"idle_{facing}", "idle"):
            seq = frames.get(key)
            if seq:
                idx = int(anim_t * fps) % len(seq)
                return seq[idx]
        return None
