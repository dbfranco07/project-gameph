"""Sprite loading for the client.

Sprites are optional, drop-in PNGs under ``client/assets``. The renderer asks
this manager for an entity's current frame; when no matching image exists it
returns ``None`` and the renderer falls back to its primitive-shape drawing, so
heroes/minions/terrain without art keep working.

Folder + naming convention (see client/assets/README.md):

    client/assets/<category>/<key>/<action>_<facing>.png
    client/assets/<category>/<key>/<action>_<facing>_<frame>.png   # animated
    client/assets/<category>/<key>/<action>.png                    # non-directional

``facing`` is one of n/e/s/w (or "" for non-directional categories). Animated
actions number frames from 0. Lookups fall back from the most specific name to
the least (directional+frame -> directional -> bare action -> idle), so a sparse
folder still renders something for every action/facing.

Categories the renderer uses: ``heroes``, ``projectiles``, ``effects``,
``entities``, ``terrain``.
"""

from __future__ import annotations

import os
import pygame

_ASSET_ROOT = os.path.join(os.path.dirname(__file__), "assets")
_TERRAIN_DIR = os.path.join(_ASSET_ROOT, "terrain")

FACINGS = ("n", "e", "s", "w")


def facing_from_delta(dx: float, dy: float) -> str:
    """Map a movement vector to one of the four cardinal facings."""
    if abs(dx) >= abs(dy):
        return "e" if dx >= 0 else "w"
    return "s" if dy >= 0 else "n"


class SpriteManager:
    """Loads and caches sprite frames per (category, key), with graceful fallback."""

    def __init__(self) -> None:
        # (category, key) -> {stem: [Surface, ...]} ; loaded lazily on first request.
        self._dirs: dict[tuple[str, str], dict[str, list[pygame.Surface]]] = {}
        # terrain name -> Surface|None ; single (non-animated) tiles.
        self._tiles: dict[str, pygame.Surface | None] = {}

    def _load_dir(self, category: str,
                  key: str) -> dict[str, list[pygame.Surface]]:
        """Load+cache every PNG under assets/<category>/<key>/, grouped by stem."""
        cache_key = (category, key)
        cached = self._dirs.get(cache_key)
        if cached is not None:
            return cached

        frames: dict[str, list[pygame.Surface]] = {}
        folder = os.path.join(_ASSET_ROOT, category, key)
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
                    skey, frame = parts[0], int(parts[1])
                else:
                    skey, frame = stem, 0
                buckets.setdefault(skey, []).append((frame, fname))
            for skey, items in buckets.items():
                items.sort()
                frames[skey] = [
                    pygame.image.load(os.path.join(folder, fn)).convert_alpha()
                    for _, fn in items
                ]

        self._dirs[cache_key] = frames
        return frames

    def frame(self, category: str, key: str, action: str, facing: str,
              anim_t: float, fps: float = 6.0) -> pygame.Surface | None:
        """Generic frame lookup with graceful fallback. ``facing`` may be "".

        Tries the most specific name first and falls back gradually so a sparse
        folder still renders. ``anim_t`` (seconds) drives frame cycling.
        """
        if not key:
            return None
        frames = self._load_dir(category, key)
        if not frames:
            return None
        candidates = (f"{action}_{facing}" if facing else action,
                      action,
                      f"idle_{facing}" if facing else "idle",
                      "idle")
        for stem in candidates:
            seq = frames.get(stem)
            if seq:
                idx = int(anim_t * fps) % len(seq)
                return seq[idx]
        return None

    def frame_count(self, category: str, key: str, stem: str) -> int:
        """Number of frames available for a given stem (0 if absent)."""
        return len(self._load_dir(category, key).get(stem, ()))

    # ----- convenience wrappers per category --------------------------------
    def hero_frame(self, hero_id: str, action: str, facing: str,
                   anim_t: float, fps: float = 6.0) -> pygame.Surface | None:
        return self.frame("heroes", hero_id, action, facing, anim_t, fps)

    def projectile_frame(self, kind: str, facing: str,
                         anim_t: float, fps: float = 10.0) -> pygame.Surface | None:
        return self.frame("projectiles", kind, "fly", facing, anim_t, fps)

    def effect_frame(self, name: str, anim_t: float,
                     fps: float = 12.0) -> pygame.Surface | None:
        return self.frame("effects", name, "play", "", anim_t, fps)

    def entity_frame(self, type_key: str, sub: str, facing: str,
                     anim_t: float, fps: float = 6.0) -> pygame.Surface | None:
        return self.frame("entities", type_key, sub or "idle", facing,
                          anim_t, fps)

    def terrain_tile(self, name: str) -> pygame.Surface | None:
        """A single (non-animated) terrain tile, cached. None if missing."""
        if name in self._tiles:
            return self._tiles[name]
        path = os.path.join(_TERRAIN_DIR, f"{name}.png")
        tile = None
        if os.path.isfile(path):
            tile = pygame.image.load(path).convert_alpha()
        self._tiles[name] = tile
        return tile
