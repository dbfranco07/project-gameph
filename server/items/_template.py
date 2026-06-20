"""TEMPLATE — copy this file to add a new item.

Steps:
  1. Copy this file to `server/items/<your_item>.py`.
  2. Rename the class and set `item_id` (unique, lowercase), `name`, `cost`.
  3. Fill in `bonuses` with any of: hp, mana, atk_dmg, move_speed, hp_regen,
     mana_regen.
  4. (Optional) give the item an active with `@item_active`, body composes the
     same `server/skills.py` building blocks heroes use.
  5. Import it in `server/items/__init__.py` (registry).

Bonuses are applied on purchase and reverted on sell, so they must be static.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.items.base import ItemDef, item_active
from server import skills


class TemplateItem(ItemDef):
    item_id = "template_item"     # MUST be unique; rename when you copy
    name = "Template Item"
    cost = 1000
    bonuses = {"atk_dmg": 20, "hp": 100}

    # Optional active. Remove this method for a purely passive item.
    @item_active("Surge", cd=30, mana=0, cast=CastType.NONE)
    def surge(ctx):
        # Self-buff on use; reuses the shared buff building block.
        skills.buff(ctx, duration=4, speed_bonus=80, dmg_bonus=20)
