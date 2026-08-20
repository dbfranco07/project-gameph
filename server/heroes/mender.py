"""Mender — ranged support that pokes, heals, repositions, and zones with an ult."""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_BASE_DMG, Q_DMG_PER_RANK = 62, 11
W_BASE_HEAL, W_HEAL_PER_RANK = 109, 20
R_BASE_HEAL, R_HEAL_PER_RANK = 250, 44


class Mender(HeroDef):
    hero_id = "mender"
    name = "Mender"

    hp = 590
    mana = 330
    move_speed = 252
    atk_dmg = 40
    sp_atk = 48               # spellcaster: leans on special attack
    phys_def = 15
    sp_def = 25
    atk_range = 305
    atk_interval = 1.0
    atk_type = "ranged"
    hp_regen = 2.5
    sp_atk_per_level = 6.0
    phys_def_per_level = 2.0
    sp_def_per_level = 3.0

    @ability("Q", "Spirit Bolt", cd=4, mana=40, cast=CastType.POINT,
             desc="Fire a spirit bolt dealing special damage to the first enemy hit.")
    def spirit_bolt(ctx):
        rank = ctx.caster.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        skills.projectile(ctx, dmg=dmg, speed=850, range=800, radius=18,
                          dtype="special", kind="mender_q")

    @ability("W", "Renewing Wave", cd=12, mana=70, cast=CastType.POINT,
             desc="Heal allies in a target area.")
    def renewing_wave(ctx):
        rank = ctx.caster.ability_rank("W")
        heal = W_BASE_HEAL + W_HEAL_PER_RANK * (rank - 1)
        skills.area_heal(ctx, heal=heal, radius=300, fx="renewwave")

    @ability("E", "Blink", cd=13, mana=50, cast=CastType.POINT,
             desc="Teleport a short distance toward the cursor.")
    def blink(ctx):
        skills.blink(ctx, dist=340)

    @ability("R", "Sanctuary", cd=80, mana=120, cast=CastType.POINT,
             desc="Bless a large area, healing all allies within it.")
    def sanctuary(ctx):
        rank = ctx.caster.ability_rank("R")
        heal = R_BASE_HEAL + R_HEAL_PER_RANK * (rank - 1)
        skills.area_heal(ctx, heal=heal, radius=420, fx="sanctuary")
