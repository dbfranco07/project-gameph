"""TEMPLATE — copy this file to add a new item.

Steps:
  1. Copy this file to `server/items/<your_item>.py`.
  2. Rename the class and set `item_id` (unique, lowercase), `name`, `cost`.
  3. Fill in `bonuses`. Any stat in `server/stats.STAT_SPECS` works, plus the
     friendly aliases in `items/base._BONUS_ALIASES`: hp, mana, atk_dmg,
     move_speed, hp_regen, mana_regen, atk_speed, atk_range. A misspelled key
     raises at import rather than silently doing nothing.
  4. (Optional) `components` + `recipe_cost` to make it an upgrade. Keep `cost`
     equal to the components' costs plus `recipe_cost` — a test enforces it.
  5. (Optional) `passive` — a `Status` subclass (see `items/passives.py`) for a
     unique passive or an on-hit / on-kill proc.
  6. (Optional) one or more `@item_active` methods; their bodies compose the
     same `server/skills.py` building blocks heroes use.

There is no registry to edit: `server/items/__init__.py` discovers every module
in this package automatically. Modules starting with `_` (like this one) are
skipped, so this file stays a template rather than a playable item.

Bonuses are granted as modifiers on the hero's StatBlock when equipped and
withdrawn when sold, so they need not be static across a match and selling can
never drift the hero's stats.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.items.base import ItemDef, item_active
from server.status.base import Status
from server import skills


class TemplateProc(Status):
    """Optional: a unique passive. Delete if the item has none.

    Any of the status lifecycle hooks work here — `on_hit_dealt`, `on_kill`,
    `on_damage_taken`, `on_tick` — because item passives are ordinary statuses.
    """

    status_id = "item:template_proc"
    label = "Template"
    icon = "template"
    default_hidden = True
    persistent = True      # equipped items are not stripped by death

    __slots__ = ()

    def on_hit_dealt(self, bearer, victim, amount, state) -> None:
        pass  # e.g. apply a Slow, queue bonus damage, add a stack


class TemplateItem(ItemDef):
    item_id = "template_item"     # MUST be unique; rename when you copy
    name = "Template Item"
    cost = 1000
    bonuses = {"atk_dmg": 20, "hp": 100}

    # Optional: make it an upgrade. `cost` must equal parts + recipe_cost.
    # components = ("long_sword",)
    # recipe_cost = 100

    # Optional: a unique passive (only one copy's passive applies).
    # passive = TemplateProc

    # Optional actives. Remove for a purely passive item. The first is cast
    # with its inventory slot key ("I3"); further ones as "I3#1", "I3#2".
    @item_active("Surge", cd=30, mana=0, cast=CastType.NONE)
    def surge(ctx):
        # Self-buff on use; reuses the shared buff building block.
        skills.buff(ctx, duration=4, speed_bonus=80, dmg_bonus=20,
                    source="item:template_item")
