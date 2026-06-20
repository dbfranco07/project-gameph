"""Starter item set. Each item is a small ItemDef subclass.

Kept in one file for the initial roster; split into one-file-per-item as the
catalog grows (the registry auto-collects either way).
"""

from __future__ import annotations

from shared.game_types import CastType
from server.items.base import ItemDef, item_active
from server import skills


class LongSword(ItemDef):
    item_id = "long_sword"
    name = "Long Sword"
    cost = 900
    bonuses = {"atk_dmg": 30}


class VitalityGem(ItemDef):
    item_id = "vitality_gem"
    name = "Vitality Gem"
    cost = 1100
    bonuses = {"hp": 250, "hp_regen": 4}


class ManaCrystal(ItemDef):
    item_id = "mana_crystal"
    name = "Mana Crystal"
    cost = 800
    bonuses = {"mana": 200, "mana_regen": 4}


class SwiftBoots(ItemDef):
    item_id = "swift_boots"
    name = "Swift Boots"
    cost = 500
    bonuses = {"move_speed": 55}


class HealthFlask(ItemDef):
    item_id = "health_flask"
    name = "Health Flask"
    cost = 450
    bonuses = {"hp": 80}

    @item_active("Quaff", cd=25, mana=0, cast=CastType.NONE)
    def quaff(ctx):
        # Instant self-heal; reuses the shared heal building block on the caster.
        ctx.state.damage_events.append(
            {"tgt": ctx.caster.entity_id, "heal": 200})
