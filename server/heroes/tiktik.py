"""Tiktik — a stealthy aswang that strikes from walls and reels victims in.

Kit:
  Q Tongue Hook (point)   skillshot: the first enemy unit it touches takes
                          damage and is dragged to melee range. With Barbed
                          Tongue (E) learned, the victim is stunned, then slowed.
  W Wallrun     (point)   target a wall to live inside it: invisible to enemies
                          (allies still see), increased + unobstructed vision,
                          confined to that connected wall. Cannot attack. Recast
                          on another wall to hop to it; recast on open ground to
                          climb out.
  E Barbed Tongue(passive)the hook's hits stun, then slow (scales with rank).
  R Frenzy      (self)    for a few seconds the hook is spammable (slashed
                          cooldown) and hits harder + reaches farther.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.entity import Wall
from server.status import Frenzy
from server import skills, terrain, bind

# --- Tuning ----------------------------------------------------------------
HOOK_BASE_DMG, HOOK_DMG_PER_RANK = 74, 13
HOOK_SPEED = 1250
HOOK_RANGE = 800
HOOK_RADIUS = 24
HOOK_STOP = 140
HOOK_PULL_SPEED = 1150

E_STUN_BASE = 0.4
E_STUN_PER_RANK = 0.2   # stun seconds (rank 1..4 -> 0.6..1.2)
E_SLOW_PCT = 0.4
E_SLOW_DUR = 1.6          # lingering slow after the stun

FRENZY_BASE_DUR, FRENZY_DUR_PER_RANK = 7.0, 1.0
FRENZY_HOOK_DMG = 135
FRENZY_HOOK_RANGE = 1100
FRENZY_HOOK_CD = 1.5

W_TOGGLE_CD = 1.0
W_JUMP_CD = 1.0 
W_REAL_CD = 14.0

W_GRAB = 160
W_VISION_BONUS = 400


def _frenzied(hero) -> bool:
    return hero.statuses.has("frenzy")


class Tiktik(HeroDef):
    hero_id = "tiktik"
    name = "Tiktik"

    hp = 590
    mana = 320
    move_speed = 285
    atk_dmg = 64
    sp_atk = 14
    phys_def = 17
    sp_def = 17
    atk_range = 165
    atk_interval = 0.9
    atk_type = "melee"
    hp_regen = 2.7
    phys_def_per_level = 3.0
    sp_def_per_level = 2.5

    @ability("Q", "Tongue Hook", cd=11, mana=60, cast=CastType.POINT,
             desc="Skillshot: damage the first enemy hit and reel it to you. "
                  "With Barbed Tongue, also stun then slow.")
    def tongue_hook(ctx):
        hero = ctx.caster
        frenzy = _frenzied(hero)
        qrank = hero.ability_rank("Q")
        hook_dmg = HOOK_BASE_DMG + HOOK_DMG_PER_RANK * (qrank - 1)
        dmg = FRENZY_HOOK_DMG if frenzy else hook_dmg
        rng = FRENZY_HOOK_RANGE if frenzy else HOOK_RANGE
        erank = hero.ability_rank("E")
        stun = (E_STUN_BASE + erank * E_STUN_PER_RANK) if erank > 0 else 0.0
        slow_dur = E_SLOW_DUR if erank > 0 else 0.0
        slow_pct = E_SLOW_PCT if erank > 0 else 0.0
        skills.hook(ctx, 
                    dmg=dmg, 
                    speed=HOOK_SPEED, 
                    range=rng, 
                    radius=HOOK_RADIUS,
                    stop_dist=HOOK_STOP, 
                    pull_speed=HOOK_PULL_SPEED,
                    stun_dur=stun, 
                    slow_dur=slow_dur, 
                    slow_pct=slow_pct,
                    kind="tiktik_q")
        if frenzy:
            hero.cooldowns["Q"] = FRENZY_HOOK_CD  # spammable during Frenzy

    @ability("W", "Wallrun", cd=W_TOGGLE_CD, mana=35, cast=CastType.POINT,
             desc="Live inside a targeted wall: invisible, see far, hop between "
                  "walls. Can't attack. Recast on open ground to exit.")
    def wallrun(ctx):
        hero, state = ctx.caster, ctx.state
        wall = terrain.obstacle_at(state, ctx.tx, ctx.ty, Wall, grab=W_GRAB)
        if bind.is_bound(hero):
            if wall is not None:
                bind.enter_bind(state, hero, wall, kind="wall", ability_key="W",
                                vision_bonus=W_VISION_BONUS,
                                extra={"disarm": True})
                hero.cooldowns["W"] = W_JUMP_CD  # hopped to another wall
            else:
                bind.release_bind(hero, state)   # open ground: climb out
                hero.cooldowns["W"] = W_REAL_CD
            return
        if wall is None:
            hero.cooldowns["W"] = 0.0            # no wall under the cursor
            return
        bind.enter_bind(state, hero, wall, kind="wall", ability_key="W",
                        vision_bonus=W_VISION_BONUS, extra={"disarm": True})

    @ability("E", "Barbed Tongue", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: enemies hit by the hook are stunned, then slowed.")
    def barbed_tongue(ctx):
        pass  # passive — read by the hook (Q) when applying its on-hit effects

    @ability("R", "Frenzy", cd=70, mana=100, cast=CastType.NONE,
             desc="For a few seconds the hook is spammable and hits harder and "
                  "farther.")
    def frenzy(ctx):
        rank = ctx.caster.ability_rank("R")
        dur = FRENZY_BASE_DUR + FRENZY_DUR_PER_RANK * (rank - 1)
        ctx.caster.statuses.add(Frenzy(dur, source="tiktik:frenzy"),
                                ctx.state)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        bind.tick_bind(state, hero)  # clamp to the wall cluster while bound
