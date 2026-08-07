"""Foundation for code-driven items.

Like heroes, each item is a Python class subclassing `ItemDef`. An item declares
a cost, a `bonuses` dict of stat gains, optionally the components it builds out
of, an optional `passive` status, and any number of actives.

**Items are modifier sources, not stat mutations.** Equipping grants a hidden,
endless `ItemStatus` whose modifiers flow into the hero's `StatBlock`; selling
removes that status and withdraws exactly what it added. The previous design
added the numbers straight onto the hero's base fields and subtracted them on
sell, which meant item stats were invisible to the HUD's buff deltas and any
asymmetry between apply and remove silently corrupted the hero's stats.

That change is what makes real item depth possible:

* any stat in `STAT_SPECS` can be granted (the old design allowed exactly six);
* a **unique passive** is just a `Status` subclass, so on-hit / on-kill procs
  reuse the hooks the damage pipeline already dispatches;
* **recipes** work because component stats are withdrawn and the upgrade's are
  granted, with no double-counting.

Only item metadata crosses the wire (the catalog in JOIN_ACK); active cast code
stays server-side and reuses the hero `CastContext` path.
"""

from __future__ import annotations

import math

from shared.game_types import CastType
from server.stats import STAT_SPECS, UnknownStatError
from server.status.base import Status

# Friendly aliases so item definitions can keep reading in gameplay terms
# ("atk_dmg") while the modifier layer sees its canonical stat key.
_BONUS_ALIASES = {
    "hp": "max_hp_bonus",
    "mana": "max_mana_bonus",
    "atk_dmg": "dmg_bonus",
    "move_speed": "speed_bonus",
    "hp_regen": "hp_regen_bonus",
    "mana_regen": "mana_regen_bonus",
    "atk_speed": "atkspd_pct",
    "atk_range": "range_bonus",
}


def canonical_bonuses(bonuses: dict) -> dict:
    """Map an item's declared bonuses onto canonical stat keys."""
    out: dict[str, float] = {}
    for key, value in bonuses.items():
        stat = _BONUS_ALIASES.get(key, key)
        if stat not in STAT_SPECS:
            raise UnknownStatError(
                f"unknown item bonus '{key}' (declare the stat in "
                f"server/stats.STAT_SPECS or add an alias in items/base.py)")
        out[stat] = out.get(stat, 0) + value
    return out


class ItemStatus(Status):
    """The carrier for an equipped item's flat stat bonuses.

    Hidden from the HUD effect row (an item is not a timed buff), endless, and
    keyed per inventory instance so two copies of the same item each contribute.
    """

    status_id = "item"
    default_hidden = True
    persistent = True      # an equipped item is not stripped by death

    __slots__ = ("item_id",)

    def __init__(self, item_id: str, bonuses: dict, instance: int = 0) -> None:
        super().__init__(math.inf, source=f"item:{item_id}#{instance}",
                         modifiers=canonical_bonuses(bonuses))
        self.item_id = item_id


class ItemActive:
    """An on-use ability attached to an item.

    Items are not spells: a silence stops you casting abilities but not using
    an item, so `through_silence` defaults to True. A stun stops everything —
    unless the active exists precisely to answer being stunned (a cleanse), in
    which case it opts in with `through_stun`.
    """

    def __init__(self, name: str, cd: float, mana: int, cast: CastType,
                 fn, through_silence: bool = True,
                 through_stun: bool = False) -> None:
        self.name = name
        self.cd = cd
        self.mana = mana
        self.cast_type = cast
        self.fn = fn  # function taking a single CastContext
        self.through_silence = through_silence
        self.through_stun = through_stun

    def usable_under_cc(self, hero) -> bool:
        if hero.statuses.has("stun"):
            return self.through_stun
        if hero.is_silenced():
            return self.through_silence
        return True

    def describe(self) -> dict:
        return {"name": self.name, "cd": self.cd, "mana": self.mana,
                "cast": int(self.cast_type)}


def item_active(name: str, cd: float, mana: int = 0,
                cast: CastType = CastType.NONE,
                through_silence: bool = True, through_stun: bool = False):
    """Decorator tagging an `ItemDef` method as one of the item's actives."""

    def deco(fn):
        fn._item_active_meta = (name, cd, mana, cast, through_silence,
                                through_stun)
        return fn

    return deco


class ItemDef:
    """Base class for an item definition."""

    item_id: str = ""
    name: str = ""
    cost: int = 0                       # total gold cost (see `recipe_cost`)
    bonuses: dict = {}                  # e.g. {"atk_dmg": 25, "hp": 150}

    #: Item ids this builds out of. Owning them all lets you buy this for only
    #: `recipe_cost`, consuming the components.
    components: tuple[str, ...] = ()
    #: Extra gold to combine the components. `cost` is kept as the from-scratch
    #: price and is validated against the components' costs plus this.
    recipe_cost: int = 0

    #: A `Status` subclass granted while equipped — where unique passives and
    #: on-hit / on-kill procs live.
    passive: type[Status] | None = None
    #: With a unique passive, a second copy grants stats but not the passive.
    unique: bool = True

    #: Consumables live in a dedicated slot and stack charges instead of
    #: occupying an inventory square (the TP scroll is the first of these).
    is_charge: bool = False

    # Populated by __init_subclass__ from decorated methods.
    actives: list[ItemActive] = []

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        collected: list[ItemActive] = []
        for value in cls.__dict__.values():
            meta = getattr(value, "_item_active_meta", None)
            if meta is not None:
                name, cd, mana, cast, thru_sil, thru_stun = meta
                collected.append(ItemActive(name, cd, mana, cast, value,
                                            thru_sil, thru_stun))
        cls.actives = collected
        cls._validate()

    # ----- convenience ------------------------------------------------------
    @classmethod
    def active(cls) -> ItemActive | None:
        """The item's first active, or None. Most items have at most one."""
        return cls.actives[0] if cls.actives else None

    @classmethod
    def component_cost(cls) -> int:
        """What the components are worth, for recipe pricing/validation."""
        from server.items import get_item_def
        total = 0
        for cid in cls.components:
            sub = get_item_def(cid)
            if sub is not None:
                total += sub.cost
        return total

    # ----- equip / unequip --------------------------------------------------
    @classmethod
    def equip(cls, hero, state=None, instance: int = 0) -> None:
        """Grant this item's bonuses and passive to `hero`.

        `instance` distinguishes multiple copies so each contributes its own
        stats; the passive is granted only once when the item is `unique`.
        """
        if cls.bonuses:
            hero.statuses.add(ItemStatus(cls.item_id, cls.bonuses, instance),
                              state)
        if cls.passive is not None:
            source = f"item:{cls.item_id}:passive"
            if cls.unique and hero.statuses.by_source(source):
                return  # unique passives do not stack with a second copy
            status = cls.passive(math.inf, source=source)
            hero.statuses.add(status, state)

    @classmethod
    def unequip(cls, hero, state=None, instance: int = 0) -> None:
        """Withdraw this item's bonuses and passive from `hero`."""
        hero.statuses.remove_source(f"item:{cls.item_id}#{instance}", state)
        if cls.passive is not None:
            hero.statuses.remove_source(f"item:{cls.item_id}:passive", state)

    # ----- wire / validation ------------------------------------------------
    @classmethod
    def describe(cls) -> dict:
        d = {"item_id": cls.item_id, "name": cls.name, "cost": cls.cost,
             "bonuses": dict(cls.bonuses)}
        if cls.actives:
            d["actives"] = [a.describe() for a in cls.actives]
            # Back-compat with the single-active HUD slot.
            d["active"] = cls.actives[0].describe()
        if cls.components:
            d["components"] = list(cls.components)
            d["recipe_cost"] = cls.recipe_cost
        if cls.passive is not None:
            d["passive"] = getattr(cls.passive, "label", "") or "Passive"
        if cls.is_charge:
            d["charge"] = True  # client: a dedicated-slot charge item, cast via Z
        return d

    @classmethod
    def _validate(cls) -> None:
        if not cls.item_id:
            raise ValueError(f"{cls.__name__} must set item_id")
        if not cls.name:
            raise ValueError(f"item '{cls.item_id}' must set name")
        # Fails at import on a misspelled bonus rather than silently no-opping.
        canonical_bonuses(cls.bonuses)
        if cls.passive is not None and not issubclass(cls.passive, Status):
            raise ValueError(
                f"item '{cls.item_id}' passive must be a Status subclass")
        if cls.components and cls.recipe_cost < 0:
            raise ValueError(f"item '{cls.item_id}' has negative recipe_cost")
