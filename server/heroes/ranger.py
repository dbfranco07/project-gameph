"""Ranger — long-range marksman with poke, mobility, and a teamfight ult."""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server import skills


class Ranger(HeroDef):
    hero_id = "ranger"
    name = "Ranger"

    hp = 560
    mana = 280
    move_speed = 250
    atk_dmg = 50
    sp_atk = 0                # pure physical marksman
    phys_def = 16
    sp_def = 18
    atk_range = 520
    atk_interval = 0.9
    atk_type = "ranged"
    hp_regen = 2.0
    phys_def_per_level = 2.5
    sp_def_per_level = 2.0

    @ability("Q", "Piercing Shot", cd=5, mana=50, cast=CastType.POINT,
             desc="Fire a long-range shot that damages the first enemy hit.")
    def piercing_shot(ctx):
        skills.projectile(ctx, dmg=95, speed=950, range=900, radius=18)

    @ability("W", "Tumble", cd=11, mana=40, cast=CastType.POINT,
             desc="Roll a short distance toward the cursor.")
    def tumble(ctx):
        skills.dash(ctx, dist=320)

    @ability("E", "Hunter's Focus", cd=16, mana=60, cast=CastType.NONE,
             desc="Temporarily gain bonus movement speed and attack damage.")
    def hunters_focus(ctx):
        skills.buff(ctx, duration=5, speed_bonus=90, dmg_bonus=25)

    @ability("R", "Arrow Storm", cd=60, mana=100, cast=CastType.POINT,
             desc="Rain arrows over a target area, damaging all enemies.")
    def arrow_storm(ctx):
        skills.area_dmg(ctx, dmg=230, radius=360)
