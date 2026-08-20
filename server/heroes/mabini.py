"""Apolinario Mabini — the Sublime Paralytic: a slow but brilliant control mage.

Kit:
  Q Constitution Bolt(point) long-range special nuke that shreds special defense.
  W Decalogue        (point) lay down a binding edict: special damage + a heavy
                             slow (a brief root at higher ranks).
  E Brains over Brawn(passive)bonus special attack; even greater power while
                             holding position (he fights from his wheelchair).
  R Paralysis        (point) paralyze every enemy in a large area (mass stun).
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.status import Aura, make_status
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_BASE_DMG, Q_DMG_PER_RANK = 101, 18
Q_SPEED, Q_RANGE = 1000, 950
Q_BASE_SHRED, Q_SHRED_PER_RANK = 11, 2
Q_SHRED_DUR = 4.0

W_BASE_DMG, W_DMG_PER_RANK = 70, 13
W_RADIUS = 300
W_SLOW, W_SLOW_DUR = 0.5, 2.5
W_ROOT_RANK, W_ROOT = 3, 0.6

E_SPATK_PER_RANK = 7
E_STILL_SPATK_PER_RANK = 6     # extra sp_atk while stationary
E_STILL_REDUCE = 0.12          # damage reduction while holding position

R_BASE_DMG, R_DMG_PER_RANK = 140, 25
R_RADIUS, R_STUN = 380, 1.6


class SereneWits(Aura):
    """E passive: special attack that scales with rank, plus extra power and
    mitigation while holding position. Dynamic because both the rank and the
    stationary check move while it stays attached."""

    status_id = "mabini:wits"
    __slots__ = ()
    dynamic = True

    def condition(self, bearer, state) -> bool:
        return bool(bearer.alive and bearer.ability_rank("E") > 0)

    @property
    def active_modifiers(self) -> dict:
        hero = self._bearer
        if hero is None:
            return {}
        rank = hero.ability_rank("E")
        if rank <= 0:
            return {}
        mods = {"sp_atk": E_SPATK_PER_RANK * rank}
        stationary = (hero.target_x is None and hero.target_y is None
                      and not hero.attack_move)
        if stationary:
            mods["sp_atk"] += E_STILL_SPATK_PER_RANK * rank
            mods["dmg_reduction"] = E_STILL_REDUCE
        return mods


class Mabini(HeroDef):
    hero_id = "mabini"
    name = "Apolinario Mabini"

    hp = 560
    mana = 420
    move_speed = 205            # the wheelchair: slow on foot
    atk_dmg = 40
    sp_atk = 62
    phys_def = 15
    sp_def = 26
    atk_range = 325
    atk_interval = 1.1
    atk_type = "ranged"
    hp_regen = 2.3
    sp_atk_per_level = 7.0
    phys_def_per_level = 2.0
    sp_def_per_level = 3.0

    @ability("Q", "Constitution Bolt", cd=6, mana=60, cast=CastType.POINT,
             desc="Fire a long-range bolt dealing special damage and reducing the "
                  "first enemy's special defense.")
    def constitution_bolt(ctx):
        rank = ctx.caster.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        shred = Q_BASE_SHRED + Q_SHRED_PER_RANK * (rank - 1)
        skills.projectile(ctx, dmg=dmg, speed=Q_SPEED, range=Q_RANGE,
                          radius=18, dtype="special", kind="mabini_q")
        # Land the special-defense shred on the enemy nearest the aim point so the
        # debuff applies even though the projectile's own hit resolves later.
        t = skills.nearest_enemy(ctx.state, ctx.caster.team, ctx.tx, ctx.ty, 120)
        if t is not None:
            skills.shred_sp_def(ctx, t, shred, Q_SHRED_DUR)

    @ability("W", "Decalogue", cd=12, mana=75, cast=CastType.POINT,
             radius=W_RADIUS,
             desc="Bind an area with an edict: special damage and a heavy slow "
                  "(a brief root at higher ranks).")
    def decalogue(ctx):
        dmg = W_BASE_DMG + W_DMG_PER_RANK * (ctx.rank - 1)
        hit = skills.area_dmg(ctx, dmg=dmg, radius=W_RADIUS, dtype="special",
                              fx="decalogue")
        root = ctx.rank >= W_ROOT_RANK
        for e in hit:
            skills.slow(ctx, e, pct=W_SLOW, duration=W_SLOW_DUR)
            if root:
                skills.stun_target(ctx, e, W_ROOT)

    @ability("E", "Brains over Brawn", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: bonus special attack, increased further while holding "
                  "position.")
    def brains_over_brawn(ctx):
        pass  # passive — refreshed in on_tick

    @ability("R", "Paralysis", cd=85, mana=130, cast=CastType.POINT,
             radius=R_RADIUS,
             desc="Paralyze all enemies in a large area, stunning them.")
    def paralysis(ctx):
        dmg = R_BASE_DMG + R_DMG_PER_RANK * (ctx.rank - 1)
        hit = skills.area_dmg(ctx, dmg=dmg, radius=R_RADIUS, dtype="special",
                              fx="paralysis")
        for e in hit:
            skills.stun_target(ctx, e, R_STUN)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        # Attach the passive once; it then tracks rank and stillness itself.
        if hero.statuses.get("mabini:wits") is None:
            hero.statuses.add(SereneWits(), state)
