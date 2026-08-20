"""Ranger — long-range marksman with poke, mobility, and a teamfight ult."""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_BASE_DMG, Q_DMG_PER_RANK = 74, 13
Q_SPEED, Q_RANGE = 950, 900

E_BASE_SPEED, E_SPEED_PER_RANK = 70, 12
E_BASE_DMG, E_DMG_PER_RANK = 20, 3
E_DUR = 5

R_BASE_DMG, R_DMG_PER_RANK = 180, 32
R_RADIUS = 360


class Ranger(HeroDef):
    hero_id = "ranger"
    name = "Ranger"

    hp = 550
    mana = 260
    move_speed = 258
    atk_dmg = 56
    sp_atk = 0                # pure physical marksman
    phys_def = 14
    sp_def = 16
    atk_range = 330
    atk_interval = 0.9
    atk_type = "ranged"
    hp_regen = 1.8
    phys_def_per_level = 2.5
    sp_def_per_level = 2.0

    @ability("Q", "Piercing Shot", cd=5, mana=50, cast=CastType.POINT,
             desc="Fire a long-range shot that damages the first enemy hit.")
    def piercing_shot(ctx):
        rank = ctx.caster.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        skills.projectile(ctx, dmg=dmg, speed=Q_SPEED, range=Q_RANGE, radius=18,
                          kind="ranger_q")

    @ability("W", "Tumble", cd=11, mana=40, cast=CastType.POINT,
             desc="Roll a short distance toward the cursor.")
    def tumble(ctx):
        skills.dash(ctx, dist=320)

    @ability("E", "Hunter's Focus", cd=16, mana=60, cast=CastType.NONE,
             desc="Temporarily gain bonus movement speed and attack damage.")
    def hunters_focus(ctx):
        rank = ctx.caster.ability_rank("E")
        speed = E_BASE_SPEED + E_SPEED_PER_RANK * (rank - 1)
        dmg = E_BASE_DMG + E_DMG_PER_RANK * (rank - 1)
        skills.buff(ctx, duration=E_DUR, speed_bonus=speed, dmg_bonus=dmg)

    @ability("R", "Arrow Storm", cd=60, mana=100, cast=CastType.POINT,
             desc="Rain arrows over a target area, damaging all enemies.")
    def arrow_storm(ctx):
        rank = ctx.caster.ability_rank("R")
        dmg = R_BASE_DMG + R_DMG_PER_RANK * (rank - 1)
        skills.area_dmg(ctx, dmg=dmg, radius=R_RADIUS, fx="arrowstorm")
