"""Item registry.

Importing this package imports every item module, which defines and validates
each item via `ItemDef.__init_subclass__`. To add an item, drop a new module in
this package and import it below (or add a class to `starters.py`).

`_template.py` is intentionally NOT imported — it is a starting point to copy.
"""

from __future__ import annotations

from server.items.base import ItemDef, ItemActive, item_active
from server.items.starters import (
    LongSword, VitalityGem, ManaCrystal, SwiftBoots, HealthFlask,
)
from server.items.tp_scroll import TpScroll

ITEM_REGISTRY: dict[str, type[ItemDef]] = {
    cls.item_id: cls
    for cls in (LongSword, VitalityGem, ManaCrystal, SwiftBoots, HealthFlask,
                TpScroll)
}


def get_item_def(item_id: str | None) -> type[ItemDef] | None:
    return ITEM_REGISTRY.get(item_id) if item_id else None


def list_item_ids() -> list[str]:
    return list(ITEM_REGISTRY.keys())


def item_catalog() -> list[dict]:
    """Shop catalog (wire metadata) for the client, in registry order."""
    return [cls.describe() for cls in ITEM_REGISTRY.values()]


def validate_all() -> None:
    for cls in ITEM_REGISTRY.values():
        cls._validate()


__all__ = [
    "ItemDef", "ItemActive", "item_active", "ITEM_REGISTRY",
    "get_item_def", "list_item_ids", "item_catalog", "validate_all",
]
