"""Hero registry — auto-discovered.

Every module in this package is imported at load, and every `HeroDef` subclass
it defines registers itself (and validates itself via `__init_subclass__`). The
registry maps `hero_id -> HeroDef`.

**To add a hero: drop one file in this package.** There is no import list and no
class tuple to keep in sync — this used to be two hand-maintained lists in two
non-adjacent places, and forgetting either made the hero silently not exist.

Modules whose name starts with `_` are skipped, so `_template.py` stays a
starting point to copy rather than a playable hero.
"""

from __future__ import annotations

import importlib
import pkgutil

from server.heroes.base import HeroDef, Ability, CastContext, ability


def _discover() -> dict[str, type[HeroDef]]:
    """Import every hero module in this package and collect what they define.

    Collection walks the imported modules' namespaces rather than
    `HeroDef.__subclasses__()`. That matters: `__subclasses__` returns every
    subclass alive anywhere in the process, which would register a throwaway
    HeroDef defined in a test — and would keep a deleted hero registered for as
    long as anything still referenced its class.
    """
    found: dict[str, type[HeroDef]] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_") or info.name in ("base", "validation"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        for value in vars(module).values():
            if not (isinstance(value, type) and issubclass(value, HeroDef)):
                continue
            if value is HeroDef or not value.hero_id:
                continue
            # Only the module that defines a hero registers it, so importing a
            # hero into another hero's file cannot register it twice.
            if value.__module__ != module.__name__:
                continue
            if value.hero_id in found and found[value.hero_id] is not value:
                raise ValueError(
                    f"duplicate hero_id '{value.hero_id}': "
                    f"{found[value.hero_id].__name__} and {value.__name__}")
            found[value.hero_id] = value
    return found


HERO_REGISTRY: dict[str, type[HeroDef]] = _discover()

DEFAULT_HERO = "ranger"


def get_hero_def(hero_id: str | None) -> type[HeroDef]:
    """Return a hero class, falling back to the default hero."""
    if hero_id and hero_id in HERO_REGISTRY:
        return HERO_REGISTRY[hero_id]
    return HERO_REGISTRY[DEFAULT_HERO]


def list_hero_ids() -> list[str]:
    return sorted(HERO_REGISTRY)


def hero_catalog() -> dict[str, dict]:
    """Every hero's wire metadata, keyed by hero_id (for client hero-select)."""
    return {hid: cls.describe() for hid, cls in HERO_REGISTRY.items()}


def validate_all() -> None:
    """Heroes self-validate at import time; this is the explicit fail-fast call.

    Re-runs each hero's validation so a malformed hero raises at server startup
    with a clear message, and additionally checks the art contracts that a
    single class cannot verify on its own (see `server.heroes.validation`).
    """
    from server.heroes.validation import validate_art_references

    if DEFAULT_HERO not in HERO_REGISTRY:
        raise ValueError(f"DEFAULT_HERO '{DEFAULT_HERO}' is not a known hero")
    for cls in HERO_REGISTRY.values():
        cls._validate()
    validate_art_references()


__all__ = [
    "HeroDef",
    "Ability",
    "CastContext",
    "ability",
    "HERO_REGISTRY",
    "DEFAULT_HERO",
    "get_hero_def",
    "list_hero_ids",
    "hero_catalog",
    "validate_all",
]
