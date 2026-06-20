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
    atk_range = 150
    atk_interval = 1.0
    atk_type = "melee"
    hp_regen = 3.0

    @ability("Q", "Crushing Blow", cd=6, mana=35, cast=CastType.UNIT)
    def crushing_blow(ctx):
        skills.target_dmg(ctx, dmg=130, range=220)

    @ability("W", "Charge", cd=10, mana=45, cast=CastType.POINT)
    def charge(ctx):
        skills.dash(ctx, dist=380)

    @ability("E", "Battle Fury", cd=18, mana=50, cast=CastType.NONE)
    def battle_fury(ctx):
        skills.buff(ctx, duration=6, speed_bonus=60, dmg_bonus=35)

    @ability("R", "Earthshatter", cd=70, mana=90, cast=CastType.POINT)
    def earthshatter(ctx):
        skills.area_dmg(ctx, dmg=260, radius=320)
