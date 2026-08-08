"""Aswang — a shapeshifting devourer that feeds to grow strong.

Kit:
  Q Devour     (unit)     eat an enemy minion/neutral whole for a timed buff;
                          against a hero it is a heavy bite instead, with a
                          slow.
  W Shapeshift (self)     morph into a random beast form — Dog (fast), Pig
                          (tanky), or Bat (phases terrain, slows on hit,
                          unobstructed vision).
  E Nightstalker(passive) lifesteal, and bonus damage while hunting alone.
  R True Aswang(passive)  rank 1: Devour on a hero extends Shapeshift's
                          duration; rank 2: Shapeshift grants 2 random
                          beasts' abilities at once; rank 3: all 3.
"""

from __future__ import annotations

import random

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.status import Aura, make_status
from server.entity import Hero
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_RANGE = 200
Q_BASE_DMG, Q_DMG_PER_RANK = 22, 6           # gorging on prey: bonus damage
Q_BASE_SPEED, Q_SPEED_PER_RANK = 30, 8       # ...and bonus speed
Q_BASE_DUR, Q_DUR_PER_RANK = 12.0, 1.5       # ...for a rank-scaled duration
Q_HERO_BITE, Q_HERO_BITE_PER_RANK = 120, 15
Q_HERO_SLOW, Q_HERO_SLOW_DUR = 0.3, 1.5

FORM_DUR = 12.0
DOG_SPEED, DOG_SPEED_PER_RANK = 110, 20
DOG_ATKSPD, DOG_ATKSPD_PER_RANK = 0.4, 0.08
PIG_DEF, PIG_DEF_PER_RANK = 24, 6
PIG_REDUCE, PIG_REDUCE_PER_RANK = 0.15, 0.03
BAT_SLOW, BAT_SLOW_PER_RANK = 0.25, 0.05
BAT_SLOW_DUR = 1.2
BAT_VISION, BAT_VISION_PER_RANK = 500, 100

E_LIFESTEAL_PER_RANK = 0.06
E_LONE_DMG_PER_RANK = 10
E_ALLY_RADIUS = 700

R_DEVOUR_EXTEND = 12.0


def _beast_mods(beast: str, rank: int) -> dict:
    """Stat modifiers for one beast form of Shapeshift at W's current rank."""
    if beast == "dog":
        return {"speed_bonus": DOG_SPEED + DOG_SPEED_PER_RANK * (rank - 1),
                "atkspd_pct": DOG_ATKSPD + DOG_ATKSPD_PER_RANK * (rank - 1)}
    if beast == "pig":
        d = PIG_DEF + PIG_DEF_PER_RANK * (rank - 1)
        return {"phys_def": d, "sp_def": d,
                "dmg_reduction": PIG_REDUCE + PIG_REDUCE_PER_RANK * (rank - 1)}
    # bat
    return {"phase": True, "unobstructed_vision": True,
            "attack_slow_pct": BAT_SLOW + BAT_SLOW_PER_RANK * (rank - 1),
            "attack_slow_dur": BAT_SLOW_DUR,
            "vision_bonus": BAT_VISION + BAT_VISION_PER_RANK * (rank - 1)}


class Nightstalker(Aura):
    """E passive: rank-scaled lifesteal, plus bonus damage while hunting alone.
    Dynamic — the rank and the solitude check both move under it."""

    status_id = "aswang:night"
    __slots__ = ("_alone",)
    dynamic = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Ally proximity needs the world; `condition` runs first and caches it.
        self._alone = False

    def condition(self, bearer, state) -> bool:
        if not (bearer.alive and bearer.ability_rank("E") > 0):
            return False
        allies = [e for e in skills.allies_in_radius(
            state, bearer.team, bearer.x, bearer.y, E_ALLY_RADIUS)
            if isinstance(e, Hero) and e is not bearer] if state else []
        self._alone = not allies
        return True

    @property
    def active_modifiers(self) -> dict:
        hero = self._bearer
        if hero is None:
            return {}
        rank = hero.ability_rank("E")
        if rank <= 0:
            return {}
        mods = {"lifesteal": E_LIFESTEAL_PER_RANK * rank}
        if self._alone:
            mods["dmg_bonus"] = E_LONE_DMG_PER_RANK * rank
        return mods


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

    @ability("Q", "Devour", cd=8, mana=60, cast=CastType.UNIT,
             desc="Eat an enemy minion or neutral whole for a timed buff. Heroes "
                  "take a heavy bite instead, and are slowed.")
    def devour(ctx):
        hero = ctx.caster
        rank = hero.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        speed = Q_BASE_SPEED + Q_SPEED_PER_RANK * (rank - 1)
        dur = Q_BASE_DUR + Q_DUR_PER_RANK * (rank - 1)
        bite = Q_HERO_BITE + Q_HERO_BITE_PER_RANK * (rank - 1)
        target = skills.devour(ctx, range=Q_RANGE, buff_dur=dur,
                               source="aswang:devour",
                               hero_bite=bite, dmg_bonus=dmg,
                               speed_bonus=speed)
        if isinstance(target, Hero):
            skills.slow(ctx, target, Q_HERO_SLOW, Q_HERO_SLOW_DUR)
            if hero.ability_rank("R") >= 1:
                for form_status in hero.statuses.by_source("aswang:form"):
                    form_status.remaining += R_DEVOUR_EXTEND

    @ability("W", "Shapeshift", cd=20, mana=70, cast=CastType.NONE,
             desc="Morph into a random beast: Dog (speed), Pig (tank), or Bat "
                  "(phase through terrain, slow on hit, unobstructed vision).")
    def shapeshift(ctx):
        hero = ctx.caster
        hero.statuses.remove_source("aswang:form", ctx.state)
        w_rank = hero.ability_rank("W")
        r_rank = hero.ability_rank("R")
        beasts = ("dog", "pig", "bat")
        if r_rank >= 3:
            chosen = beasts
        elif r_rank >= 2:
            chosen = random.choice((("dog", "pig"), ("pig", "bat"),
                                    ("bat", "dog")))
        else:
            chosen = (random.choice(beasts),)
        mods = {}
        for beast in chosen:
            mods.update(_beast_mods(beast, w_rank))
        hero.statuses.add(make_status(FORM_DUR, source="aswang:form", **mods),
                          ctx.state)
        hero.ability_state["form"] = "+".join(chosen)

    @ability("E", "Nightstalker", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: gain lifesteal, plus bonus damage while no allied "
                  "hero is near.")
    def nightstalker(ctx):
        pass  # passive — refreshed in on_tick

    @ability("R", "True Aswang", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: rank 1 makes Devour on a hero extend Shapeshift's "
                  "duration; rank 2 makes Shapeshift grant 2 random beasts' "
                  "abilities at once; rank 3 grants all 3.")
    def true_aswang(ctx):
        pass  # passive — read by rank in devour() and shapeshift()

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        if (hero.ability_state.get("form")
                and not hero.statuses.by_source("aswang:form")):
            hero.ability_state.pop("form", None)
        # Attach the passive once; it tracks rank and solitude itself.
        if hero.statuses.get("aswang:night") is None:
            hero.statuses.add(Nightstalker(), state)
