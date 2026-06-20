"""Validation + lookup for data-driven hero definitions.

Kept UI-agnostic so both server (applies stats/abilities) and client (hero-select
screen) can import it. The actual data lives in `data/heroes.py`.
"""

from __future__ import annotations

from data.heroes import HERO_DEFS, DEFAULT_HERO

# Required base-stat keys on every hero.
_REQUIRED_STATS = ("name", 
                   "hp", "mana", 
                   "move_speed", 
                   "atk_dmg", "atk_range", "atk_interval")

# Required parameter keys per ability kind (beyond the common key/kind/name/cd/mana).
_ABILITY_KINDS: dict[str, tuple[str, ...]] = {
    "projectile": ("dmg", "speed", "radius", "range"),
    "dash": ("dist",),
    "area_dmg": ("dmg", "radius"),
    "area_heal": ("heal", "radius"),
    "target_dmg": ("dmg", "range"),
    "buff": ("duration",),
}


def validate_hero(hero_id: str, hero: dict) -> None:
    """Raise ValueError if a hero definition is malformed."""
    for key in _REQUIRED_STATS:
        if key not in hero:
            raise ValueError(f"hero '{hero_id}' missing stat '{key}'")
        
    atk_type = hero.get("atk_type", "melee")
    if atk_type not in ("melee", "ranged"):
        raise ValueError(f"hero '{hero_id}' has invalid atk_type '{atk_type}'")
    
    abilities = hero.get("abilities", [])
    if not isinstance(abilities, list):
        raise ValueError(f"hero '{hero_id}' abilities must be a list")
    
    for ab in abilities:
        for key in ("key", "kind", "name", "cd", "mana"):
            if key not in ab:
                raise ValueError(f"hero '{hero_id}' ability missing '{key}': {ab}")
            
        kind = ab["kind"]
        if kind not in _ABILITY_KINDS:
            raise ValueError(f"hero '{hero_id}' has unknown ability kind '{kind}'")
        
        for key in _ABILITY_KINDS[kind]:
            if key not in ab:
                raise ValueError(
                    f"hero '{hero_id}' ability '{ab['key']}' ({kind}) missing '{key}'"
                )


def validate_all() -> None:
    """Validate every hero definition. Called once at server startup."""
    for hero_id, hero in HERO_DEFS.items():
        validate_hero(hero_id, hero)


def get_hero_def(hero_id: str | None) -> dict:
    """Return a hero definition, falling back to the default hero."""
    if hero_id and hero_id in HERO_DEFS:
        return HERO_DEFS[hero_id]
    return HERO_DEFS[DEFAULT_HERO]


def list_hero_ids() -> list[str]:
    return list(HERO_DEFS.keys())
