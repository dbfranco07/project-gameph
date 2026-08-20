"""Lastikman — an elastic hero who punches from afar and slings to cover.

Kit:
  Q Stretch Punch(point)  stretch a fist out in a line, damaging the first enemy.
  W Grapple      (point)  hook a wall or tree and sling yourself to it (crosses
                          terrain).
  E Elastic Body(passive) rubbery resilience: evasion and damage reduction.
  R Rubber Storm (self)   flail your stretched limbs, dealing repeated damage to
                          everything around you for a few seconds.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.status import Aura, make_status
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_BASE_DMG, Q_DMG_PER_RANK = 94, 17
Q_SPEED, Q_RANGE = 1400, 780
Q_SLOW, Q_SLOW_DUR = 0.25, 1.2

# Grapple: a hook that reels the caster to the first wall/tree/structure it hits.
W_MAX_DIST = 900
W_SPEED = 1600
W_RADIUS = 22
W_PULL_SPEED = 1500
W_STOP = 70          # stop this far from the anchor (clears the wall surface)

E_EVASION_PER_RANK = 0.05      # rank 1..4 -> 5%..20% dodge
E_REDUCE_PER_RANK = 0.03       # rank 1..4 -> 3%..12% mitigation

R_DUR, R_INTERVAL = 6.0, 0.5
R_BASE_TICK_DMG, R_TICK_DMG_PER_RANK = 35, 6
R_RADIUS = 280


class ElasticBody(Aura):
    """E passive: rank-scaled evasion and flat damage reduction."""

    status_id = "lastik:elastic"
    __slots__ = ()
    dynamic = True

    def condition(self, bearer, state) -> bool:
        return bool(bearer.alive and bearer.ability_rank("E") > 0)

    @property
    def active_modifiers(self) -> dict:
        hero = self._bearer
        rank = hero.ability_rank("E") if hero else 0
        if rank <= 0:
            return {}
        return {"evasion": E_EVASION_PER_RANK * rank,
                "dmg_reduction": E_REDUCE_PER_RANK * rank}


class Lastikman(HeroDef):
    hero_id = "lastikman"
    name = "Lastikman"

    hp = 650
    mana = 290
    move_speed = 275
    atk_dmg = 58
    sp_atk = 12
    phys_def = 19
    sp_def = 20
    atk_range = 165
    atk_interval = 0.95
    atk_type = "melee"
    hp_regen = 3.0
    phys_def_per_level = 3.0
    sp_def_per_level = 2.5

    @ability("Q", "Stretch Punch", cd=6, mana=45, cast=CastType.POINT,
             desc="Stretch a fist in a line, damaging and slowing the first enemy "
                  "it strikes.")
    def stretch_punch(ctx):
        rank = ctx.caster.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        skills.hook(ctx, dmg=dmg, speed=Q_SPEED, range=Q_RANGE, radius=22,
                    pull=False, slow_dur=Q_SLOW_DUR, slow_pct=Q_SLOW,
                    kind="lastikman_q")

    @ability("W", "Grapple", cd=10, mana=40, cast=CastType.POINT,
             target="obstacle", range=W_MAX_DIST,
             desc="Fling a grapple line; when it strikes a wall, tree or "
                  "structure you are reeled to it.")
    def grapple(ctx):
        skills.grapple(ctx, speed=W_SPEED, range=W_MAX_DIST, radius=W_RADIUS,
                       pull_speed=W_PULL_SPEED, stop_dist=W_STOP,
                       kind="lastikman_w")

    @ability("E", "Elastic Body", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: rubbery body grants evasion and damage reduction.")
    def elastic_body(ctx):
        pass  # passive — refreshed in on_tick

    @ability("R", "Rubber Storm", cd=70, mana=110, cast=CastType.NONE,
             desc="Flail wildly: deal repeated physical damage to all enemies "
                  "around you for several seconds.")
    def rubber_storm(ctx):
        ctx.caster.ability_state["storm"] = {"t": R_DUR, "acc": 0.0}

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        # Attach the Elastic Body passive once; it tracks its own rank.
        if hero.statuses.get("lastik:elastic") is None:
            hero.statuses.add(ElasticBody(), state)

        # Rubber Storm: tick AoE on an interval while active.
        storm = hero.ability_state.get("storm")
        if not storm:
            return
        if not hero.alive:
            hero.ability_state.pop("storm", None)
            return
        storm["t"] -= dt
        storm["acc"] += dt
        rank = hero.ability_rank("R")
        tick_dmg = R_BASE_TICK_DMG + R_TICK_DMG_PER_RANK * (rank - 1)
        while storm["acc"] >= R_INTERVAL:
            storm["acc"] -= R_INTERVAL
            for e in skills.enemies_in_radius(state, hero.team, hero.x, hero.y,
                                              R_RADIUS):
                state.damage_events.append(
                    {"src": hero.entity_id, "tgt": e.entity_id,
                     "amt": tick_dmg, "dtype": "physical"})
        if storm["t"] <= 0:
            hero.ability_state.pop("storm", None)