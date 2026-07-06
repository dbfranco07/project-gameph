"""TP Scroll — a bought teleport consumable in its own dedicated slot.

Unlike the stat items, the TP scroll is a *charge* item: buying it stacks a
charge onto the hero's dedicated TP slot (see `Hero.tp_charges`) instead of
occupying an inventory slot or granting stats. It is cast with the ``Z`` key to
teleport near an alive allied structure (resolved server-side in
`systems._cast_tp`), consuming one charge and starting a shared cooldown that
persists across rebuys.
"""

from __future__ import annotations

from server.items.base import ItemDef
from shared.config import TP_COST


class TpScroll(ItemDef):
    item_id = "tp_scroll"
    name = "TP Scroll"
    cost = TP_COST
    bonuses = {}
    is_charge = True
