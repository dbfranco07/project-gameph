"""Manananggal — a Filipino mythological aswang that detaches its upper body.

Kit:
  Q Scratch    (unit)    ranged claw: damage + movement slow.
  W Pounce     (unit)    dash to a target.
  E Bloodlust  (passive) every skill use grants stacking move + attack speed.
  R Split      (self)    detach: upper half becomes an invulnerable, harder-
                         hitting, longer-ranged flyer leashed to the lower body;
                         the grounded lower body is vulnerable and takes DOUBLE
                         damage. If it is destroyed, you die. Press R again near
                         the body to recombine (gaining a burst of regen); the
                         split also auto-recombines when its timer runs out.
"""

from __future__ import annotations

import math

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.entity import Hero, SplitBody
from server.status import DamageAmplify, Split, make_status
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_RANGE = 450
Q_BASE_DMG, Q_DMG_PER_RANK = 86, 15
Q_SLOW, Q_SLOW_DUR = 0.35, 2.0

POUNCE_DIST = 650

BLOODLUST_BASE_SPEED, BLOODLUST_SPEED_PER_RANK = 27, 5
BLOODLUST_BASE_ATKSPD, BLOODLUST_ATKSPD_PER_RANK = 0.14, 0.03
BLOODLUST_DUR = 4.0

SPLIT_TOGGLE_CD = 0.75     # min time between split <-> recombine presses
SPLIT_REAL_CD = 55.0       # cooldown applied once you recombine
SPLIT_MANA = 100
SPLIT_DURATION = 8.0       # timed auto-recombine
SPLIT_BASE_DMG_BONUS, SPLIT_DMG_BONUS_PER_RANK = 35, 6
SPLIT_BASE_RANGE_BONUS, SPLIT_RANGE_BONUS_PER_RANK = 172, 30
SPLIT_VISION_BONUS = 400    # extra sight radius while the upper half is flying
SPLIT_LEASH = 900          # max distance the upper half may roam from the body
RECOMBINE_RANGE = 260      # must be this close to the body to recombine
BODY_HP_FRAC = 0.6         # body hp as a fraction of max hp
BODY_DMG_MULT = 2.0        # body takes double damage
REGEN_HP, REGEN_MP, REGEN_DUR = 35, 12, 6.0


class _Split(Split):
    """The detached state, which owns its own teardown.

    Recombining is just this status ending — whether the player presses R near
    the body or the timer lapses — so the body cleanup and the reunion regen
    live in `on_expire` instead of being duplicated across a manual path and a
    timed path that had to notice the buff had silently vanished.
    """

    __slots__ = ()

    def on_expire(self, bearer, state) -> None:
        if state is None:
            return
        body = state.entities.get(self.body_id)
        if body is not None:
            body.alive = False
            state.entities.pop(body.entity_id, None)
        bearer.statuses.add(make_status(REGEN_DUR, source="manananggal:reform",
                                        hp_regen_bonus=REGEN_HP,
                                        mana_regen_bonus=REGEN_MP), state)
        bearer.cooldowns["R"] = SPLIT_REAL_CD


def _begin_split(ctx) -> None:
    hero, state = ctx.caster, ctx.state
    if hero.mana < SPLIT_MANA:
        return
    hero.mana -= SPLIT_MANA
    body = SplitBody(team=hero.team, x=hero.x, y=hero.y, radius=hero.radius,
                     owner_id=hero.entity_id, dmg_mult=BODY_DMG_MULT)
    body.hp = body.max_hp = max(1, int(hero.max_hp * BODY_HP_FRAC))
    state.entities[body.entity_id] = body
    # The body is deliberately fragile; the amplification rides on it as a
    # status instead of being a field the damage pipeline checks for by type.
    body.statuses.add(DamageAmplify(multiplier=BODY_DMG_MULT), state)
    rank = hero.ability_rank("R")
    dmg_bonus = SPLIT_BASE_DMG_BONUS + SPLIT_DMG_BONUS_PER_RANK * (rank - 1)
    range_bonus = SPLIT_BASE_RANGE_BONUS + SPLIT_RANGE_BONUS_PER_RANK * (rank - 1)
    hero.statuses.add(_Split(
        SPLIT_DURATION, body_id=body.entity_id,
        flags=Split.flags | frozenset({"invuln"}),
        modifiers={"dmg_bonus": dmg_bonus,
                   "range_bonus": range_bonus,
                   "vision_bonus": SPLIT_VISION_BONUS}), state)


def _recombine(state, hero: Hero, body) -> None:
    """Reunite the halves. Removing the status fires its on_expire, which does
    the body cleanup, the regen burst and the real cooldown."""
    hero.statuses.remove_id("split", state)


class Manananggal(HeroDef):
    hero_id = "manananggal"
    name = "Manananggal"

    hp = 600
    mana = 330
    move_speed = 278
    atk_dmg = 60
    sp_atk = 22
    phys_def = 19
    sp_def = 19
    atk_range = 158
    atk_interval = 0.95
    atk_type = "melee"
    hp_regen = 2.8
    phys_def_per_level = 3.0
    sp_def_per_level = 2.5

    @ability("Q", "Scratch", cd=7, mana=60, cast=CastType.UNIT,
             target="enemy", range=Q_RANGE,
             desc="Claw an enemy for damage and a movement slow.")
    def scratch(ctx):
        rank = ctx.caster.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        target = skills.target_dmg(ctx, dmg=dmg, range=Q_RANGE)
        if target is None:
            # No valid unit was clicked (near-miss): claw the enemy nearest the
            # cursor that is within range, so Scratch reliably connects.
            target = skills.nearest_enemy(
                ctx.state, ctx.caster.team, ctx.caster.x, ctx.caster.y,
                Q_RANGE, toward=(ctx.tx, ctx.ty))
            if target is not None:
                ctx.state.damage_events.append(
                    {"src": ctx.caster.entity_id, "tgt": target.entity_id,
                     "amt": dmg, "dtype": "physical"})
        if target is not None:
            skills.slow(ctx, target, pct=Q_SLOW, duration=Q_SLOW_DUR)

    @ability("W", "Pounce", cd=12, mana=50, cast=CastType.UNIT,
             desc="Leap to a targeted unit.")
    def pounce(ctx):
        skills.dash_to_target(ctx, dist=POUNCE_DIST)

    @ability("E", "Bloodlust", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: each ability cast grants stacking move + attack speed.")
    def bloodlust(ctx):
        pass  # passive — effect lives in on_ability_cast

    @ability("R", "Split", cd=SPLIT_TOGGLE_CD, mana=0, cast=CastType.NONE,
             desc="Detach your invulnerable upper half; recombine near the body to heal.")
    def split(ctx):
        hero = ctx.caster
        split = hero.statuses.get("split")
        if split is None:
            _begin_split(ctx)
        else:
            body = ctx.state.entities.get(split.body_id)
            if (body is not None and body.alive
                    and hero.distance_to(body) <= RECOMBINE_RANGE):
                _recombine(ctx.state, hero, body)
            # too far from the body: nothing happens (fly back first)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_ability_cast(ctx, key):
        # Bloodlust: every skill cast adds a short, stacking haste.
        hero = ctx.caster
        rank = max(hero.ability_rank("E"), 1)
        speed = BLOODLUST_BASE_SPEED + BLOODLUST_SPEED_PER_RANK * (rank - 1)
        atkspd = BLOODLUST_BASE_ATKSPD + BLOODLUST_ATKSPD_PER_RANK * (rank - 1)
        hero.statuses.add(make_status(
            BLOODLUST_DUR, source="manananggal:bloodlust",
            speed_bonus=speed,
            atkspd_pct=atkspd), ctx.state)

    @staticmethod
    def on_tick(state, hero, dt):
        split = hero.statuses.get("split")
        if split is None:
            return
        body = state.entities.get(split.body_id)
        if body is None or not body.alive:
            hero.statuses.remove_id("split", state)
            return
        # Leash the flying upper half to within range of the lower body.
        dx, dy = hero.x - body.x, hero.y - body.y
        d = math.hypot(dx, dy)
        if d > SPLIT_LEASH:
            hero.x = body.x + dx / d * SPLIT_LEASH
            hero.y = body.y + dy / d * SPLIT_LEASH
            hero.target_x = hero.target_y = None
