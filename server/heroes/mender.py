"""Mender — ranged support that pokes, heals, repositions, and zones with an ult."""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server import skills


class Mender(HeroDef):
    hero_id = "mender"
    name = "Mender"

    hp = 600
    mana = 320
    move_speed = 245
    atk_dmg = 44
    atk_range = 480
    atk_interval = 1.0
    atk_type = "ranged"
    hp_regen = 2.5

    @ability("Q", "Spirit Bolt", cd=4, mana=40, cast=CastType.POINT)
    def spirit_bolt(ctx):
        skills.projectile(ctx, dmg=80, speed=850, range=800, radius=18)

    @ability("W", "Renewing Wave", cd=12, mana=70, cast=CastType.POINT)
    def renewing_wave(ctx):
        skills.area_heal(ctx, heal=140, radius=300)

    @ability("E", "Blink", cd=13, mana=50, cast=CastType.POINT)
    def blink(ctx):
        skills.blink(ctx, dist=340)

    @ability("R", "Sanctuary", cd=80, mana=120, cast=CastType.POINT)
    def sanctuary(ctx):
        skills.area_heal(ctx, heal=320, radius=420)
