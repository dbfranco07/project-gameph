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

import math

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.effects import make_effect
from server.entity import Obstacle
from server import skills, terrain
from shared.geometry import closest_point_on_segment

# --- Tuning ----------------------------------------------------------------
Q_DMG, Q_SPEED, Q_RANGE = 120, 1400, 780
Q_SLOW, Q_SLOW_DUR = 0.25, 1.2

W_MAX_DIST, W_GRAB = 900, 130

E_EVASION_PER_RANK = 0.05      # rank 1..4 -> 5%..20% dodge
E_REDUCE_PER_RANK = 0.03       # rank 1..4 -> 3%..12% mitigation

R_DUR, R_INTERVAL = 6.0, 0.5
R_TICK_DMG, R_RADIUS = 45, 280


class Lastikman(HeroDef):
    hero_id = "lastikman"
    name = "Lastikman"

    hp = 640
    mana = 300
    move_speed = 270
    atk_dmg = 60
    sp_atk = 10
    phys_def = 20
    sp_def = 20
    atk_range = 180
    atk_interval = 0.95
    atk_type = "melee"
    hp_regen = 3.0
    phys_def_per_level = 3.0
    sp_def_per_level = 2.5

    @ability("Q", "Stretch Punch", cd=6, mana=45, cast=CastType.POINT,
             desc="Stretch a fist in a line, damaging and slowing the first enemy "
                  "it strikes.")
    def stretch_punch(ctx):
        skills.hook(ctx, dmg=Q_DMG, speed=Q_SPEED, range=Q_RANGE, radius=22,
                    pull=False, slow_dur=Q_SLOW_DUR, slow_pct=Q_SLOW,
                    kind="lastikman_q")

    @ability("W", "Grapple", cd=10, mana=40, cast=CastType.POINT,
             desc="Grab a wall or tree and sling yourself to it.")
    def grapple(ctx):
        hero = ctx.caster
        obstacle = terrain.obstacle_at(ctx.state, ctx.tx, ctx.ty, Obstacle,
                                       grab=W_GRAB)
        if obstacle is None:
            hero.cooldowns["W"] = 0.0   # nothing to grapple: refund the cast
            return
        x0, y0, x1, y1, _ = obstacle.capsule()
        cx, cy = closest_point_on_segment(hero.x, hero.y, x0, y0, x1, y1)
        ctx.tx, ctx.ty = cx, cy
        skills.dash(ctx, dist=W_MAX_DIST)

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
        # Elastic Body passive.
        hero.buffs[:] = [b for b in hero.buffs
                         if b.get("source") != "lastik:elastic"]
        if hero.alive:
            erank = hero.ability_rank("E")
            if erank > 0:
                hero.buffs.append(make_effect(
                    0.5, source="lastik:elastic",
                    evasion=E_EVASION_PER_RANK * erank,
                    dmg_reduction=E_REDUCE_PER_RANK * erank))

        # Rubber Storm: tick AoE on an interval while active.
        storm = hero.ability_state.get("storm")
        if not storm:
            return
        if not hero.alive:
            hero.ability_state.pop("storm", None)
            return
        storm["t"] -= dt
        storm["acc"] += dt
        while storm["acc"] >= R_INTERVAL:
            storm["acc"] -= R_INTERVAL
            for e in skills.enemies_in_radius(state, hero.team, hero.x, hero.y,
                                              R_RADIUS):
                state.damage_events.append(
                    {"src": hero.entity_id, "tgt": e.entity_id,
                     "amt": R_TICK_DMG, "dtype": "physical"})
        if storm["t"] <= 0:
            hero.ability_state.pop("storm", None)