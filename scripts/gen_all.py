"""Regenerate every placeholder sprite asset in one go.

    uv run python scripts/gen_all.py

Discovers and runs every `gen_*.py` generator in this directory under a single
pygame init. Adding a generator is one new file — there is no import list and no
module tuple to keep in sync, which is the same papercut the hero and item
registries used to have.

Drop real PNGs with the same paths/names (see client/assets/README.md) to
replace any of these procedural placeholders without touching game code.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import spritelib as sl

_HERE = Path(__file__).resolve().parent

#: Generators are run in this order where it matters, then everything else
#: alphabetically. Entities/effects/terrain last so hero art lands first.
_ORDER_HINT = ("gen_sprite_", "gen_entities", "gen_effects", "gen_terrain")


def _discover():
    """Every `gen_*.py` module in this directory that exposes a `main()`."""
    names = []
    for info in pkgutil.iter_modules([str(_HERE)]):
        name = info.name
        if not name.startswith("gen_") or name == "gen_all":
            continue
        names.append(name)

    def rank(name: str) -> tuple[int, str]:
        for i, prefix in enumerate(_ORDER_HINT):
            if name.startswith(prefix):
                return (i, name)
        return (len(_ORDER_HINT), name)

    modules = []
    for name in sorted(names, key=rank):
        mod = importlib.import_module(name)
        if callable(getattr(mod, "main", None)):
            modules.append(mod)
    return modules


def main() -> None:
    sl._ensure_init()
    try:
        total = 0
        for mod in _discover():
            count = mod.main()
            total += count
            print(f"  {mod.__name__}: {count}")
        print(f"[gen_all] wrote {total} PNGs under {sl.ASSETS}")
    finally:
        import pygame
        pygame.quit()


if __name__ == "__main__":
    main()
