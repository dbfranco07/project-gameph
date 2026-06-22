"""Hero registry.

Importing this package imports every concrete hero module, which (via
`HeroDef.__init_subclass__`) defines and validates each hero. The registry maps
`hero_id -> HeroDef` subclass. To add a hero, drop a new module in this package
and import it below (or rely on the copy-the-template workflow + adding the line).

`_template.py` is intentionally NOT imported — it is a starting point to copy, not
a playable hero.
"""

from __future__ import annotations

from server.heroes.base import HeroDef, Ability, CastContext, ability

# Import concrete heroes so their subclasses register.
from server.heroes.ranger import Ranger
from server.heroes.brawler import Brawler
from server.heroes.mender import Mender
from server.heroes.manananggal import Manananggal
from server.heroes.kapre import Kapre
from server.heroes.tiktik import Tiktik

HERO_REGISTRY: dict[str, type[HeroDef]] = {
    cls.hero_id: cls
    for cls in (Ranger, Brawler, Mender, Manananggal, Kapre, Tiktik)
}

DEFAULT_HERO = "ranger"


def get_hero_def(hero_id: str | None) -> type[HeroDef]:
    """Return a hero class, falling back to the default hero."""
    if hero_id and hero_id in HERO_REGISTRY:
        return HERO_REGISTRY[hero_id]
    return HERO_REGISTRY[DEFAULT_HERO]


def list_hero_ids() -> list[str]:
    return list(HERO_REGISTRY.keys())


def hero_catalog() -> dict[str, dict]:
    """Every hero's wire metadata, keyed by hero_id (for client hero-select)."""
    return {hid: cls.describe() for hid, cls in HERO_REGISTRY.items()}


def validate_all() -> None:
    """Heroes self-validate at import time; this is the explicit fail-fast call.

    Re-runs each hero's validation so a malformed hero raises at server startup
    with a clear message (mirrors the previous shared.hero_schema.validate_all).
    """
    for cls in HERO_REGISTRY.values():
        cls._validate()


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
