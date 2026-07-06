"""Foundation for code-driven items.

Like heroes, each item is its own Python class (one file per item) subclassing
`ItemDef`. An item declares a `cost` and a `bonuses` dict of flat stat gains, and
may optionally define a single active ability via `@item_active`.

Buying an item calls `apply(hero)` (adds the bonuses); selling calls
`remove(hero)` (subtracts them). Only item **metadata** crosses the wire to the
client (via the catalog in JOIN_ACK); the active's cast code stays server-side
and reuses the hero `CastContext` cast path.
"""

from __future__ import annotations

from shared.game_types import CastType

# Stat keys an item may grant. Mapped onto the live Hero entity in apply/remove.
_STAT_FIELDS = {
    "hp": "max_hp",
    "mana": "max_mana",
    "atk_dmg": "attack_damage",
    "move_speed": "move_speed",
    "hp_regen": "hp_regen",
    "mana_regen": "mana_regen",
}


class ItemActive:
    """An optional on-use ability attached to an item."""

    def __init__(self, name: str, cd: float, mana: int, cast: CastType, fn) -> None:
        self.name = name
        self.cd = cd
        self.mana = mana
        self.cast_type = cast
        self.fn = fn  # function taking a single CastContext

    def describe(self) -> dict:
        return {"name": self.name, "cd": self.cd, "mana": self.mana,
                "cast": int(self.cast_type)}


def item_active(name: str, cd: float, mana: int = 0,
                cast: CastType = CastType.NONE):
    """Decorator tagging an `ItemDef` method as the item's active ability."""

    def deco(fn):
        fn._item_active_meta = (name, cd, mana, cast)
        return fn

    return deco


class ItemDef:
    """Base class for an item definition. Subclass it, one file per item."""

    item_id: str = ""
    name: str = ""
    cost: int = 0
    bonuses: dict = {}              # e.g. {"atk_dmg": 25, "hp": 150}
    active: ItemActive | None = None
    # A "charge" item (e.g. the TP scroll) is bought into a dedicated slot rather
    # than the inventory grid: buying stacks a charge instead of applying stats.
    is_charge: bool = False

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls.active = None
        for value in cls.__dict__.values():
            meta = getattr(value, "_item_active_meta", None)
            if meta is not None:
                name, cd, mana, cast = meta
                cls.active = ItemActive(name, cd, mana, cast, value)
                break
        cls._validate()

    # ----- Buy / sell stat application --------------------------------------
    @classmethod
    def apply(cls, hero) -> None:
        """Grant this item's stat bonuses to a hero (on purchase)."""
        for key, delta in cls.bonuses.items():
            field = _STAT_FIELDS[key]
            setattr(hero, field, getattr(hero, field) + delta)
        # Gaining max hp/mana also heals/refills by that amount (MOBA convention).
        if cls.bonuses.get("hp"):
            hero.hp += cls.bonuses["hp"]
        if cls.bonuses.get("mana"):
            hero.mana += cls.bonuses["mana"]

    @classmethod
    def remove(cls, hero) -> None:
        """Strip this item's stat bonuses from a hero (on sell)."""
        for key, delta in cls.bonuses.items():
            field = _STAT_FIELDS[key]
            setattr(hero, field, getattr(hero, field) - delta)
        hero.hp = min(hero.hp, hero.max_hp)
        hero.mana = min(hero.mana, hero.max_mana)

    # ----- Wire / validation ------------------------------------------------
    @classmethod
    def describe(cls) -> dict:
        d = {"item_id": cls.item_id, "name": cls.name, "cost": cls.cost,
             "bonuses": dict(cls.bonuses)}
        if cls.active is not None:
            d["active"] = cls.active.describe()
        if cls.is_charge:
            d["charge"] = True  # client: a dedicated-slot charge item, cast via Z
        return d

    @classmethod
    def _validate(cls) -> None:
        if not cls.item_id:
            raise ValueError(f"{cls.__name__} must set item_id")
        if not cls.name:
            raise ValueError(f"item '{cls.item_id}' must set name")
        for key in cls.bonuses:
            if key not in _STAT_FIELDS:
                raise ValueError(
                    f"item '{cls.item_id}' has unknown bonus '{key}'")
