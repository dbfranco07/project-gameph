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
from server.effects import make_effect
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_DMG, Q_SPEED, Q_RANGE = 130, 1000, 950
Q_SHRED, Q_SHRED_DUR = 14, 4.0

W_DMG, W_RADIUS = 90, 300
W_SLOW, W_SLOW_DUR = 0.5, 2.5
W_ROOT_RANK, W_ROOT = 3, 0.6

E_SPATK_PER_RANK = 7
E_STILL_SPATK_PER_RANK = 6     # extra sp_atk while stationary
E_STILL_REDUCE = 0.12          # damage reduction while holding position

R_DMG, R_RADIUS, R_STUN = 180, 380, 1.6


class Mabini(HeroDef):
    hero_id = "mabini"
    name = "Apolinario Mabini"

    hp = 540
    mana = 400
    move_speed = 215            # the wheelchair: slow on foot
    atk_dmg = 44
    sp_atk = 58
    phys_def = 16
    sp_def = 24
    atk_range = 540
    atk_interval = 1.1
    atk_type = "ranged"
    hp_regen = 2.5
    sp_atk_per_level = 7.0
    phys_def_per_level = 2.0
    sp_def_per_level = 3.0

    @ability("Q", "Constitution Bolt", cd=6, mana=60, cast=CastType.POINT,
             desc="Fire a long-range bolt dealing special damage and reducing the "
                  "first enemy's special defense.")
    def constitution_bolt(ctx):
        skills.projectile(ctx, dmg=Q_DMG, speed=Q_SPEED, range=Q_RANGE,
                          radius=18, dtype="special", kind="mabini_q")
        # Land the special-defense shred on the enemy nearest the aim point so the
        # debuff applies even though the projectile's own hit resolves later.
        t = skills.nearest_enemy(ctx.state, ctx.caster.team, ctx.tx, ctx.ty, 120)
        if t is not None:
            skills.shred_sp_def(ctx, t, Q_SHRED, Q_SHRED_DUR)

    @ability("W", "Decalogue", cd=12, mana=75, cast=CastType.POINT,
             desc="Bind an area with an edict: special damage and a heavy slow "
                  "(a brief root at higher ranks).")
    def decalogue(ctx):
        hit = skills.area_dmg(ctx, dmg=W_DMG, radius=W_RADIUS, dtype="special",
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
             desc="Paralyze all enemies in a large area, stunning them.")
    def paralysis(ctx):
        hit = skills.area_dmg(ctx, dmg=R_DMG, radius=R_RADIUS, dtype="special",
                              fx="paralysis")
        for e in hit:
            skills.stun_target(ctx, e, R_STUN)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        hero.buffs[:] = [b for b in hero.buffs
                         if b.get("source") != "mabini:wits"]
        if not hero.alive:
            return
        erank = hero.ability_rank("E")
        if erank <= 0:
            return
        mods = {"sp_atk": E_SPATK_PER_RANK * erank}
        stationary = hero.target_x is None and hero.target_y is None and not hero.attack_move
        if stationary:
            mods["sp_atk"] += E_STILL_SPATK_PER_RANK * erank
            mods["dmg_reduction"] = E_STILL_REDUCE
        hero.buffs.append(make_effect(0.5, source="mabini:wits", **mods))
