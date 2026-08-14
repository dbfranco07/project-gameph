"""Panday — a blacksmith-swordsman who forges his blade into the battlefield.

Kit:
  Q Sword of Panday (point)   forge a sword into a targeted wall: damage and
                              stun enemies near the strike, and leave the sword
                              standing at the wall. Walking up to it claims it
                              (recasting Q replaces any sword still unclaimed).
  W Weakness Reader (self)    automatic: a smith's eye for flaws disarms
                              nearby enemies for a moment.
  E Panday's Throw (unit/self) without the sword in hand: a light burst of
                              speed. Carrying it: hurl the sword at an enemy
                              for heavy damage — if a wall stands close behind
                              them, they're pinned to it and stunned, and
                              Panday blinks to their side.
  R Master's Slash  (point)   a two-range sweep of his blade dealing huge
                              damage and slowing everyone it catches.

Losing the sword (thrown by E, or never claimed) means fighting bare-handed
again until Q forges a new one and Panday walks up to claim it.
"""

from __future__ import annotations

import math

from shared.game_types import CastType
from server.heroes.base import CastContext, HeroDef, ability
from server.entity import Hero, Minion, Wall
from server.status import Aura, Disarm, Stun
from server import skills, terrain

# --- Tuning ----------------------------------------------------------------
Q_DMG, Q_RADIUS, Q_STUN = 130, 210, 0.9
Q_WALL_GRAB = 110          # how close a click must be to a wall to count
Q_ITEM_RADIUS = 26         # the dropped sword's pickup collision size
Q_SWORD_KIND = "panday_sword_ground"
Q_SWORD_LIFETIME = 20.0    # seconds an unclaimed sword lasts on the ground
PICKUP_RADIUS = 110        # how close Panday must walk to claim it

CARRY_RANGE_BONUS, CARRY_DMG_BONUS = 45, 30   # bonus while the sword is held

W_RADIUS, W_DISARM_DUR = 260, 2.6

E_NO_SWORD_SPEED, E_NO_SWORD_DUR = 45, 3.0
E_THROW_DMG, E_THROW_RANGE = 150, 700
E_PIN_CHECK = 90    # how far past the enemy to look for a wall
E_PIN_GRAB = 70
E_PIN_STUN = 1.3
E_BLINK_MAX = 700

# Two windup slashes 0.2s apart, each dealing its own damage + slow.
R_DMG, R_WIDTH, R_SLOW_PCT, R_SLOW_DUR = 130, 170, 0.35, 2.0
R_SLASH_INTERVAL = 0.2


class SwordCarry(Aura):
    """Passive: while Panday holds the forged sword (claimed after Q), his
    reach and damage grow. Thrown away by E, or never claimed before it
    expires, and the bonus is gone until he forges and claims another."""

    status_id = "panday:sword"
    __slots__ = ()
    modifiers = {"range_bonus": CARRY_RANGE_BONUS, "dmg_bonus": CARRY_DMG_BONUS}

    def condition(self, bearer, state) -> bool:
        return bool(bearer.alive and bearer.ability_state.get("carries_sword"))


def _replace_sword(ctx, x, y) -> None:
    """Drop a fresh sword at (x, y), clearing any unclaimed one Panday already
    has on the ground (a recast replaces it rather than stacking swords)."""
    hero, state = ctx.caster, ctx.state
    old_id = hero.ability_state.get("sword_id")
    if old_id is not None:
        state.entities.pop(old_id, None)
    item = skills.drop_item(ctx, x, y, kind=Q_SWORD_KIND,
                            radius=Q_ITEM_RADIUS, lifetime=Q_SWORD_LIFETIME)
    hero.ability_state["sword_id"] = item.entity_id


class Panday(HeroDef):
    hero_id = "panday"
    name = "Panday"

    hp = 700
    mana = 260
    move_speed = 260
    atk_dmg = 68
    sp_atk = 0
    phys_def = 26
    sp_def = 20
    atk_range = 155
    atk_interval = 0.95
    atk_type = "melee"
    hp_regen = 4.0
    phys_def_per_level = 3.5
    sp_def_per_level = 2.0

    @ability("Q", "Sword of Panday", cd=12, mana=60, cast=CastType.POINT,
             radius=Q_RADIUS,
             desc="Forge a sword into a targeted wall: damage and stun "
                  "enemies near the strike. Walk up to the sword to claim it "
                  "for bonus range and damage.")
    def sword_of_panday(ctx):
        state, hero = ctx.state, ctx.caster
        wall = terrain.obstacle_at(state, ctx.tx, ctx.ty, Wall, grab=Q_WALL_GRAB)
        if wall is None:
            hero.cooldowns["Q"] = 0.0  # must target a wall
            return
        cluster = terrain.connected_cluster(state, wall)
        capsules = [w.capsule() for w in cluster]
        px, py = terrain.clamp_to_cluster(ctx.tx, ctx.ty, capsules)
        ctx.tx, ctx.ty = px, py
        hit = skills.area_dmg(ctx, dmg=Q_DMG, radius=Q_RADIUS, fx="smash")
        for e in hit:
            skills.apply_status(e, Stun(Q_STUN), state)
        _replace_sword(ctx, px, py)

    @ability("W", "Weakness Reader", cd=11, mana=45, cast=CastType.NONE,
             desc="A smith's eye for flaws: automatically disarm nearby "
                  "enemies for a moment.")
    def weakness_reader(ctx):
        hero, state = ctx.caster, ctx.state
        skills._emit_fx(ctx, "panday_disarm", hero.x, hero.y, W_RADIUS)
        for e in skills.enemies_in_radius(state, hero.team, hero.x, hero.y,
                                          W_RADIUS):
            if isinstance(e, (Hero, Minion)):
                skills.apply_status(e, Disarm(W_DISARM_DUR), state)

    @ability("E", "Panday's Throw", cd=13, mana=55, cast=CastType.UNIT,
             target="enemy", range=E_THROW_RANGE,
             desc="Without the sword: a burst of speed. Carrying it: throw "
                  "the sword for heavy damage — if a wall is close behind the "
                  "target, they're pinned and stunned, and you blink to them.")
    def pandays_throw(ctx):
        hero, state = ctx.caster, ctx.state
        if not hero.ability_state.get("carries_sword"):
            skills.buff(ctx, E_NO_SWORD_DUR, speed_bonus=E_NO_SWORD_SPEED,
                       source="panday:step")
            return
        target = skills.target_dmg(ctx, dmg=E_THROW_DMG, range=E_THROW_RANGE,
                                   dtype="physical")
        if target is None:
            hero.cooldowns["E"] = 0.0  # no legal target: refund
            return
        hero.ability_state["carries_sword"] = False  # the sword leaves his hand
        dx, dy = target.x - hero.x, target.y - hero.y
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        check_x = target.x + ux * E_PIN_CHECK
        check_y = target.y + uy * E_PIN_CHECK
        wall = terrain.obstacle_at(state, check_x, check_y, Wall, grab=E_PIN_GRAB)
        if wall is None:
            return  # nothing to pin them against: just a heavy hit
        cluster = terrain.connected_cluster(state, wall)
        capsules = [w.capsule() for w in cluster]
        px, py = terrain.clamp_to_cluster(check_x, check_y, capsules)
        target.x, target.y = px, py
        target.target_x = target.target_y = None
        skills.apply_status(target, Stun(E_PIN_STUN), state)
        skills._emit_fx(ctx, "panday_pin", px, py, 40)
        approach = hero.radius + target.radius + 30
        ctx.tx, ctx.ty = px - ux * approach, py - uy * approach
        skills.blink(ctx, dist=E_BLINK_MAX)

    @ability("R", "Master's Slash", cd=65, mana=100, cast=CastType.POINT,
             desc="Two sweeps of your blade, 0.2s apart, each twice your "
                  "melee reach in front of you: damage and slow, twice over.")
    def masters_slash(ctx):
        hero, state = ctx.caster, ctx.state
        tx, ty, rank = ctx.tx, ctx.ty, ctx.rank

        def _slash(state, hero):
            slash_ctx = CastContext(state, hero, tx, ty, None, rank)
            length = hero.effective_attack_range() * 2.0
            hit = skills.line_aoe(slash_ctx, dmg=R_DMG, length=length,
                                  width=R_WIDTH, fx="bolocleave")
            for e in hit:
                skills.slow(slash_ctx, e, R_SLOW_PCT, R_SLOW_DUR)

        skills.pulse(ctx, "r_slash", duration=2 * R_SLASH_INTERVAL,
                    interval=R_SLASH_INTERVAL, on_pulse=_slash)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        skills.tick_pulses(state, hero, dt)  # advances Master's Slash's 2 hits
        if hero.statuses.get("panday:sword") is None:
            hero.statuses.add(SwordCarry(), state)
        if not hero.ability_state.get("carries_sword"):
            item = skills.nearby_ground_item(state, hero, PICKUP_RADIUS,
                                             kind=Q_SWORD_KIND)
            if item is not None:
                state.entities.pop(item.entity_id, None)
                hero.ability_state["carries_sword"] = True
                hero.ability_state.pop("sword_id", None)

    @staticmethod
    def on_death(state, hero, killer):
        hero.ability_state["carries_sword"] = False  # fight bare-handed until reforged
