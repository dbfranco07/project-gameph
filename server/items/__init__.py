"""Item registry — auto-discovered.

Every module in this package is imported at load, and every `ItemDef` subclass
it defines registers itself. Adding an item is one new file (or one new class in
an existing file); there is no list to keep in sync, which is the papercut the
hand-maintained tuple here used to be.

Modules whose name starts with `_` are skipped, so `_template.py` stays a
starting point to copy rather than a playable item.
"""

from __future__ import annotations

import importlib
import pkgutil

from server.items.base import (
    ItemActive,
    ItemDef,
    ItemStatus,
    canonical_bonuses,
    item_active,
)


def _discover() -> dict[str, type[ItemDef]]:
    """Import every item module in this package and collect what they define.

    Collection walks the imported modules' namespaces rather than
    `ItemDef.__subclasses__()`, so a throwaway ItemDef defined in a test never
    lands in the shop (see the matching note in `server/heroes/__init__.py`).
    """
    found: dict[str, type[ItemDef]] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_") or info.name in ("base", "passives"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        for value in vars(module).values():
            if not (isinstance(value, type) and issubclass(value, ItemDef)):
                continue
            if value is ItemDef or not value.item_id:
                continue
            # Only the defining module registers an item, so importing one item
            # into another's file cannot register it twice.
            if value.__module__ != module.__name__:
                continue
            if value.item_id in found and found[value.item_id] is not value:
                raise ValueError(
                    f"duplicate item_id '{value.item_id}': "
                    f"{found[value.item_id].__name__} and {value.__name__}")
            found[value.item_id] = value
    return found


ITEM_REGISTRY: dict[str, type[ItemDef]] = _discover()


def get_item_def(item_id: str | None) -> type[ItemDef] | None:
    return ITEM_REGISTRY.get(item_id) if item_id else None


def list_item_ids() -> list[str]:
    return list(ITEM_REGISTRY.keys())


def item_catalog() -> list[dict]:
    """Shop catalog (wire metadata) for the client, cheapest first."""
    return [cls.describe()
            for cls in sorted(ITEM_REGISTRY.values(), key=lambda c: c.cost)]


def upgrades_from(item_id: str) -> list[type[ItemDef]]:
    """Items that list `item_id` as one of their components."""
    return [cls for cls in ITEM_REGISTRY.values() if item_id in cls.components]


def purchase_plan(hero, item: type[ItemDef]) -> tuple[int, list[int]] | None:
    """What buying `item` would cost `hero`, and which inventory slots it eats.

    Owning a component means paying only the recipe cost for it. Returns
    ``(gold_needed, component_slots)``, or None if the hero cannot hold the
    result. Each owned component is consumed at most once, so two copies of a
    component correctly fund two separate upgrades rather than one twice.
    """
    from shared.config import ITEM_SLOTS

    slots: list[int] = []
    price = item.cost
    if item.components:
        price = item.recipe_cost
        remaining = list(item.components)
        for idx, owned in enumerate(hero.inventory):
            if owned in remaining:
                remaining.remove(owned)
                slots.append(idx)
        # Components still missing are bought at their own price.
        for missing in remaining:
            sub = get_item_def(missing)
            if sub is None:
                return None
            price += sub.cost

    # The upgrade takes one slot; the components it consumes free theirs.
    free_after = ITEM_SLOTS - len(hero.inventory) + len(slots)
    if free_after < 1:
        return None
    return price, slots


def resync(hero, state=None) -> None:
    """Rebuild every item status on `hero` from its inventory list.

    Called after *any* inventory change. Rebuilding from scratch is O(6) and
    makes it structurally impossible for the granted modifiers to drift out of
    step with what the hero is actually carrying — which is the failure mode
    incremental apply/remove bookkeeping is prone to, especially with duplicate
    copies and recipes consuming components.
    """
    for status in list(hero.statuses):
        source = status.source or ""
        if source.startswith("item:"):
            hero.statuses.remove(status, state)
    seen: dict[str, int] = {}
    for item_id in hero.inventory:
        item = get_item_def(item_id)
        if item is None:
            continue
        instance = seen.get(item_id, 0)
        seen[item_id] = instance + 1
        item.equip(hero, state, instance=instance)


def apply_inventory_change(hero, state, mutate) -> None:
    """Run `mutate()` on the inventory, resync statuses, and carry the change in
    maximum health/mana into the current pools.

    Gaining max HP should heal you by that much (MOBA convention) and losing it
    must not leave you above the new ceiling. Doing it from the before/after
    difference handles plain buys, sells and recipe combines — where components
    are removed and an upgrade added in one step — without any per-item
    bookkeeping.
    """
    hp_before = hero.effective_max_hp()
    mana_before = hero.effective_max_mana()
    mutate()
    resync(hero, state)
    hero.hp = max(1, hero.hp + hero.effective_max_hp() - hp_before)
    hero.mana = max(0, hero.mana + hero.effective_max_mana() - mana_before)
    hero.hp = min(hero.hp, hero.effective_max_hp())
    hero.mana = min(hero.mana, hero.effective_max_mana())


def validate_all() -> None:
    """Explicit fail-fast call: items self-validate at import, this re-runs it
    and additionally checks that every referenced component exists."""
    for cls in ITEM_REGISTRY.values():
        cls._validate()
        for cid in cls.components:
            if cid not in ITEM_REGISTRY:
                raise ValueError(
                    f"item '{cls.item_id}' lists unknown component '{cid}'")


__all__ = [
    "ItemDef", 
    "ItemActive", 
    "ItemStatus", 
    "item_active", 
    "canonical_bonuses",
    "ITEM_REGISTRY", 
    "get_item_def", 
    "list_item_ids", 
    "item_catalog",
    "upgrades_from", 
    "purchase_plan", 
    "resync", 
    "apply_inventory_change",
    "validate_all",
]
