"""Andres Bonifacio — the Supremo: a frontline fighter who rallies the Katipunan.

Kit:
  Q Bolo Cleave   (point)  a sweeping bolo strike: physical damage in an arc in
                           front of you.
  W Rip the Cedula(self)   tear the cedula in defiance: bonus damage, lifesteal,
                           and toughness.
  E Katipunero   (passive) grow stronger for each nearby allied hero.
  R KKK Warcry    (self)   with at least two allies near, every ally gains
                           damage, speed, and defense (a weaker self-rally alone).
"""

from __future__ import annotations

import math

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.status import Aura, make_status
from server.entity import Hero
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_DMG, Q_RADIUS, Q_OFFSET = 110, 220, 180

W_DUR = 6.0
W_DMG, W_LIFESTEAL, W_PDEF, W_SDEF = 40, 0.2, 16, 16

E_RADIUS = 600
E_DMG_PER_ALLY, E_PDEF_PER_ALLY, E_MAX_ALLIES = 14, 6, 3

R_RADIUS, R_DUR = 700, 7.0
R_DMG, R_SPEED, R_PDEF, R_SDEF = 45, 70, 16, 16
R_SOLO_DMG, R_SOLO_SPEED = 20, 35   # weaker buff when you rally alone


class Katipunero(Aura):
    """E passive: damage and defense scaling with the number of allied heroes
    nearby. Dynamic — the ally count changes constantly in a teamfight."""

    status_id = "bonifacio:kkk"
    __slots__ = ("_allies",)
    dynamic = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Ally count needs the world; `condition` runs first and caches it.
        self._allies = 0

    def condition(self, bearer, state) -> bool:
        if not (bearer.alive and bearer.ability_rank("E") > 0 and state):
            return False
        others = [e for e in skills.allies_in_radius(
            state, bearer.team, bearer.x, bearer.y, E_RADIUS)
            if isinstance(e, Hero) and e is not bearer]
        self._allies = min(len(others), E_MAX_ALLIES)
        return self._allies > 0

    @property
    def active_modifiers(self) -> dict:
        n = self._allies
        if n <= 0:
            return {}
        return {"dmg_bonus": E_DMG_PER_ALLY * n,
                "phys_def": E_PDEF_PER_ALLY * n}


class Bonifacio(HeroDef):
    hero_id = "bonifacio"
    name = "Andres Bonifacio"

    hp = 720
    mana = 280
    move_speed = 265
    atk_dmg = 66
    sp_atk = 5
    phys_def = 24
    sp_def = 20
    atk_range = 165
    atk_interval = 0.95
    atk_type = "melee"
    hp_regen = 3.5
    phys_def_per_level = 3.5
    sp_def_per_level = 2.5

    @ability("Q", "Bolo Cleave", cd=6, mana=45, cast=CastType.POINT,
             desc="Sweep your bolo, dealing physical damage to enemies in front "
                  "of you.")
    def bolo_cleave(ctx):
        caster = ctx.caster
        dx, dy = ctx.tx - caster.x, ctx.ty - caster.y
        d = math.hypot(dx, dy) or 1.0
        ctx.tx = caster.x + dx / d * Q_OFFSET
        ctx.ty = caster.y + dy / d * Q_OFFSET
        skills.area_dmg(ctx, dmg=Q_DMG, radius=Q_RADIUS, fx="bolocleave")

    @ability("W", "Rip the Cedula", cd=14, mana=55, cast=CastType.NONE,
             desc="Tear the cedula: gain bonus damage, lifesteal, and defenses.")
    def rip_the_cedula(ctx):
        ctx.caster.statuses.add(make_status(
            W_DUR, source="bonifacio:cedula", dmg_bonus=W_DMG,
            lifesteal=W_LIFESTEAL, phys_def=W_PDEF, sp_def=W_SDEF), ctx.state)

    @ability("E", "Katipunero", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: gain bonus damage and defense for each nearby allied "
                  "hero.")
    def katipunero(ctx):
        pass  # passive — refreshed in on_tick

    @ability("R", "KKK Warcry", cd=70, mana=100, cast=CastType.NONE,
             desc="Rally the Katipunan: with two or more allies near, all allies "
                  "gain damage, speed, and defense.")
    def kkk_warcry(ctx):
        caster = ctx.caster
        allies = [e for e in skills.allies_in_radius(
            ctx.state, caster.team, caster.x, caster.y, R_RADIUS)
            if isinstance(e, Hero)]
        others = [e for e in allies if e is not caster]
        skills._emit_fx(ctx, "warcry", caster.x, caster.y, R_RADIUS)
        if len(others) >= 2:
            for e in allies:
                e.statuses.add(make_status(
                    R_DUR, source="bonifacio:warcry", dmg_bonus=R_DMG,
                    speed_bonus=R_SPEED, phys_def=R_PDEF, sp_def=R_SDEF),
                    ctx.state)
        else:
            caster.statuses.add(make_status(
                R_DUR, source="bonifacio:warcry", dmg_bonus=R_SOLO_DMG,
                speed_bonus=R_SOLO_SPEED), ctx.state)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        # Attach the passive once; it counts nearby allies itself.
        if hero.statuses.get("bonifacio:kkk") is None:
            hero.statuses.add(Katipunero(), state)
