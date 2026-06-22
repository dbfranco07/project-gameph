"""Brawler — melee bruiser that gap-closes, bursts a single target, and slams."""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server import skills


class Brawler(HeroDef):
    hero_id = "brawler"
    name = "Brawler"

    hp = 720
    mana = 180
    move_speed = 260
    atk_dmg = 62
    sp_atk = 0
    phys_def = 28           # tanky bruiser
    sp_def = 22
    atk_range = 150
    atk_interval = 1.0
    atk_type = "melee"
    hp_regen = 3.0
    phys_def_per_level = 4.0
    sp_def_per_level = 2.5

    @ability("Q", "Crushing Blow", cd=6, mana=35, cast=CastType.UNIT,
             desc="Strike a single target for heavy physical damage.")
    def crushing_blow(ctx):
        skills.target_dmg(ctx, dmg=130, range=220)

    @ability("W", "Charge", cd=10, mana=45, cast=CastType.POINT,
             desc="Dash a long distance toward the cursor.")
    def charge(ctx):
        skills.dash(ctx, dist=380)

    @ability("E", "Battle Fury", cd=18, mana=50, cast=CastType.NONE,
             desc="Temporarily gain bonus movement speed and attack damage.")
    def battle_fury(ctx):
        skills.buff(ctx, duration=6, speed_bonus=60, dmg_bonus=35)

    @ability("R", "Earthshatter", cd=70, mana=90, cast=CastType.POINT,
             desc="Slam the ground, damaging all enemies in a wide area.")
    def earthshatter(ctx):
        skills.area_dmg(ctx, dmg=260, radius=320, fx="earthshatter")
