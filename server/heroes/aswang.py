"""Aswang — a shapeshifting devourer that feeds to grow strong.

Kit:
  Q Devour     (unit)     eat an enemy minion/neutral whole for a timed buff;
                          against a hero it is a heavy bite instead.
  W Shapeshift (self)     morph into a random beast form — Dog (fast), Pig
                          (tanky), or Snake (phases terrain, slows on hit).
  E Nightstalker(passive) lifesteal, and bonus damage while hunting alone.
  R True Aswang(self)     drop the disguise: a winged terror that flies over
                          terrain with bonus damage and heavy lifesteal.
"""

from __future__ import annotations

import random

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.effects import make_effect
from server.entity import Hero
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_RANGE = 200
Q_HERO_BITE = 120
Q_BUFF_DUR = 14.0
Q_BUFF_DMG, Q_BUFF_SPEED = 22, 30   # gorging on prey: bonus damage + speed

FORM_DUR = 12.0
DOG_SPEED, DOG_ATKSPD = 110, 0.4
PIG_PDEF, PIG_SDEF, PIG_REDUCE = 24, 24, 0.15
SNAKE_SLOW, SNAKE_SLOW_DUR = 0.3, 1.2

E_LIFESTEAL_PER_RANK = 0.06
E_LONE_DMG_PER_RANK = 10
E_ALLY_RADIUS = 700

R_DUR = 9.0
R_DMG_BONUS, R_SPEED, R_LIFESTEAL = 55, 80, 0.25


class Aswang(HeroDef):
    hero_id = "aswang"
    name = "Aswang"

    hp = 640
    mana = 300
    move_speed = 280
    atk_dmg = 64
    sp_atk = 10
    phys_def = 20
    sp_def = 18
    atk_range = 160
    atk_interval = 0.9
    atk_type = "melee"
    hp_regen = 3.5
    phys_def_per_level = 3.0
    sp_def_per_level = 2.0

    @ability("Q", "Devour", cd=10, mana=60, cast=CastType.UNIT,
             desc="Eat an enemy minion or neutral whole for a timed buff. Heroes "
                  "take a heavy bite instead.")
    def devour(ctx):
        skills.devour(ctx, range=Q_RANGE, buff_dur=Q_BUFF_DUR,
                      hero_bite=Q_HERO_BITE, dmg_bonus=Q_BUFF_DMG,
                      speed_bonus=Q_BUFF_SPEED)

    @ability("W", "Shapeshift", cd=13, mana=50, cast=CastType.NONE,
             desc="Morph into a random beast: Dog (speed), Pig (tank), or Snake "
                  "(phase through terrain, slow on hit).")
    def shapeshift(ctx):
        hero = ctx.caster
        hero.buffs[:] = [b for b in hero.buffs
                         if b.get("source") != "aswang:form"]
        form = random.choice(("dog", "pig", "snake"))
        if form == "dog":
            mods = {"speed_bonus": DOG_SPEED, "atkspd_pct": DOG_ATKSPD}
        elif form == "pig":
            mods = {"phys_def": PIG_PDEF, "sp_def": PIG_SDEF,
                    "dmg_reduction": PIG_REDUCE}
        else:  # snake
            mods = {"phase": True, "attack_slow_pct": SNAKE_SLOW,
                    "attack_slow_dur": SNAKE_SLOW_DUR}
        hero.buffs.append(make_effect(FORM_DUR, source="aswang:form", **mods))
        hero.ability_state["form"] = form

    @ability("E", "Nightstalker", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: gain lifesteal, plus bonus damage while no allied "
                  "hero is near.")
    def nightstalker(ctx):
        pass  # passive — refreshed in on_tick

    @ability("R", "True Aswang", cd=75, mana=120, cast=CastType.NONE,
             desc="Reveal your winged true form: fly over terrain with bonus "
                  "damage and heavy lifesteal.")
    def true_aswang(ctx):
        ctx.caster.buffs.append(
            make_effect(R_DUR, source="aswang:true", phase=True,
                        dmg_bonus=R_DMG_BONUS, speed_bonus=R_SPEED,
                        lifesteal=R_LIFESTEAL))

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        if hero.ability_state.get("form") and not any(
                b.get("source") == "aswang:form" for b in hero.buffs):
            hero.ability_state.pop("form", None)
        hero.buffs[:] = [b for b in hero.buffs
                         if b.get("source") != "aswang:night"]
        if not hero.alive:
            return
        erank = hero.ability_rank("E")
        if erank <= 0:
            return
        mods = {"lifesteal": E_LIFESTEAL_PER_RANK * erank}
        allies = [e for e in skills.allies_in_radius(
            state, hero.team, hero.x, hero.y, E_ALLY_RADIUS)
            if isinstance(e, Hero) and e is not hero]
        if not allies:
            mods["dmg_bonus"] = E_LONE_DMG_PER_RANK * erank
        hero.buffs.append(make_effect(0.5, source="aswang:night", **mods))
