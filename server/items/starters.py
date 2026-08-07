"""The item catalog: basic components and the items they build into.

Basics are cheap, single-stat, and exist to be combined. Upgrades list their
`components` and a `recipe_cost`, so owning the parts means paying only the
difference — the shop resolves that in `items.purchase_plan`.

`cost` is always the full from-scratch price; a test asserts it equals the
components' costs plus `recipe_cost`, so a mispriced recipe cannot ship.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.items.base import ItemDef, item_active
from server.items.passives import Bloodthirst, ChillingTouch, SecondWind, Thorns
from server import skills


# ---------------------------------------------------------------------------
# Basics — single-stat components
# ---------------------------------------------------------------------------

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


class IronPlate(ItemDef):
    item_id = "iron_plate"
    name = "Iron Plate"
    cost = 700
    bonuses = {"phys_def": 22}


class SpiritCharm(ItemDef):
    item_id = "spirit_charm"
    name = "Spirit Charm"
    cost = 700
    bonuses = {"sp_def": 20, "sp_atk": 12}


class HuntingKnife(ItemDef):
    item_id = "hunting_knife"
    name = "Hunting Knife"
    cost = 650
    bonuses = {"atk_speed": 0.22}


# ---------------------------------------------------------------------------
# Upgrades — built from the basics above
# ---------------------------------------------------------------------------

class Bloodblade(ItemDef):
    """Long Sword + Hunting Knife: the carry's snowball item."""

    item_id = "bloodblade"
    name = "Bloodblade"
    components = ("long_sword", "hunting_knife")
    recipe_cost = 750
    cost = 900 + 650 + 750
    bonuses = {"atk_dmg": 45, "atk_speed": 0.25, "lifesteal": 0.12}
    passive = Bloodthirst


class FrostMaul(ItemDef):
    """Long Sword + Vitality Gem: bruiser item that kites what it hits."""

    item_id = "frost_maul"
    name = "Frost Maul"
    components = ("long_sword", "vitality_gem")
    recipe_cost = 800
    cost = 900 + 1100 + 800
    bonuses = {"atk_dmg": 35, "hp": 300}
    passive = ChillingTouch


class ThornMail(ItemDef):
    """Iron Plate + Vitality Gem: punishes auto-attackers."""

    item_id = "thorn_mail"
    name = "Thorn Mail"
    components = ("iron_plate", "vitality_gem")
    recipe_cost = 600
    cost = 700 + 1100 + 600
    bonuses = {"phys_def": 40, "hp": 250}
    passive = Thorns


class GuardianAmulet(ItemDef):
    """Spirit Charm + Iron Plate: one cheat-death per life, plus an active
    shield. Two actives on one item, which the old single-active design could
    not express."""

    item_id = "guardian_amulet"
    name = "Guardian Amulet"
    components = ("spirit_charm", "iron_plate")
    recipe_cost = 900
    cost = 700 + 700 + 900
    bonuses = {"sp_def": 35, "phys_def": 20, "hp": 200}
    passive = SecondWind

    @item_active("Barrier", cd=45, mana=50, cast=CastType.NONE)
    def barrier(ctx):
        from server.status import Shield
        ctx.caster.statuses.add(
            Shield(5.0, 350, source="item:guardian_amulet"), ctx.state)

    @item_active("Cleanse", cd=60, mana=40, cast=CastType.NONE,
                 through_stun=True)
    def cleanse(ctx):
        # Strip crowd control from the caster: every debuff asserting a CC flag.
        hero = ctx.caster
        for status in list(hero.statuses):
            if status.active_flags & {"stun", "silence", "disarm"}:
                hero.statuses.remove(status, ctx.state)


class TravelBoots(ItemDef):
    """Swift Boots upgrade with a burst of speed on use."""

    item_id = "travel_boots"
    name = "Boots of Travel"
    components = ("swift_boots",)
    recipe_cost = 1100
    cost = 500 + 1100
    bonuses = {"move_speed": 95}

    @item_active("Surge", cd=35, mana=25, cast=CastType.NONE)
    def surge(ctx):
        skills.buff(ctx, duration=4, speed_bonus=120,
                    source="item:travel_boots")
