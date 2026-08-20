"""Brawler — melee bruiser that gap-closes, bursts a single target, and slams."""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_BASE_DMG, Q_DMG_PER_RANK = 101, 18
Q_RANGE = 220

E_BASE_SPEED, E_SPEED_PER_RANK = 47, 8
E_BASE_DMG, E_DMG_PER_RANK = 27, 5
E_DUR = 6

R_BASE_DMG, R_DMG_PER_RANK = 203, 36
R_RADIUS = 320


class Brawler(HeroDef):
    hero_id = "brawler"
    name = "Brawler"

    hp = 700
    mana = 170
    move_speed = 270
    atk_dmg = 64
    sp_atk = 0
    phys_def = 26           # tanky bruiser
    sp_def = 20
    atk_range = 150
    atk_interval = 1.0
    atk_type = "melee"
    hp_regen = 3.0
    phys_def_per_level = 4.0
    sp_def_per_level = 2.5

    @ability("Q", "Crushing Blow", cd=6, mana=35, cast=CastType.UNIT,
             target="enemy", range=Q_RANGE,
             desc="Strike a single target for heavy physical damage.")
    def crushing_blow(ctx):
        rank = ctx.caster.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        skills.target_dmg(ctx, dmg=dmg, range=Q_RANGE)

    @ability("W", "Charge", cd=10, mana=45, cast=CastType.POINT,
             desc="Dash a long distance toward the cursor.")
    def charge(ctx):
        skills.dash(ctx, dist=380)

    @ability("E", "Battle Fury", cd=18, mana=50, cast=CastType.NONE,
             desc="Temporarily gain bonus movement speed and attack damage.")
    def battle_fury(ctx):
        rank = ctx.caster.ability_rank("E")
        speed = E_BASE_SPEED + E_SPEED_PER_RANK * (rank - 1)
        dmg = E_BASE_DMG + E_DMG_PER_RANK * (rank - 1)
        skills.buff(ctx, duration=E_DUR, speed_bonus=speed, dmg_bonus=dmg)

    @ability("R", "Earthshatter", cd=70, mana=90, cast=CastType.POINT,
             desc="Slam the ground, damaging all enemies in a wide area.")
    def earthshatter(ctx):
        rank = ctx.caster.ability_rank("R")
        dmg = R_BASE_DMG + R_DMG_PER_RANK * (rank - 1)
        skills.area_dmg(ctx, dmg=dmg, radius=R_RADIUS, fx="earthshatter")
