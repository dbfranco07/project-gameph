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
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_RANGE, Q_DMG = 450, 110
Q_SLOW, Q_SLOW_DUR = 0.35, 2.0

POUNCE_DIST = 650

BLOODLUST_SPEED, BLOODLUST_ATKSPD, BLOODLUST_DUR = 35, 0.18, 4.0

SPLIT_TOGGLE_CD = 0.75     # min time between split <-> recombine presses
SPLIT_REAL_CD = 55.0       # cooldown applied once you recombine
SPLIT_MANA = 100
SPLIT_DURATION = 8.0       # timed auto-recombine
SPLIT_DMG_BONUS = 45
SPLIT_RANGE_BONUS = 220
SPLIT_LEASH = 900          # max distance the upper half may roam from the body
RECOMBINE_RANGE = 260      # must be this close to the body to recombine
BODY_HP_FRAC = 0.6         # body hp as a fraction of max hp
BODY_DMG_MULT = 2.0        # body takes double damage
REGEN_HP, REGEN_MP, REGEN_DUR = 35, 12, 6.0


def _begin_split(ctx) -> None:
    hero, state = ctx.caster, ctx.state
    if hero.mana < SPLIT_MANA:
        return
    hero.mana -= SPLIT_MANA
    body = SplitBody(team=hero.team, x=hero.x, y=hero.y, radius=hero.radius,
                     owner_id=hero.entity_id, dmg_mult=BODY_DMG_MULT)
    body.hp = body.max_hp = max(1, int(hero.max_hp * BODY_HP_FRAC))
    state.entities[body.entity_id] = body
    hero.buffs.append({
        "split": True, "invuln": True,
        "dmg_bonus": SPLIT_DMG_BONUS, "range_bonus": SPLIT_RANGE_BONUS,
        "remaining": SPLIT_DURATION,
    })
    hero.ability_state["split"] = {"body_id": body.entity_id}


def _recombine(state, hero: Hero, body) -> None:
    hero.buffs[:] = [b for b in hero.buffs if not b.get("split")]
    hero.ability_state.pop("split", None)
    if body is not None:
        body.alive = False
        state.entities.pop(body.entity_id, None)
    # Reuniting grants a short surge of regeneration (and the bonus dmg/range
    # from the split buff is now gone).
    hero.buffs.append({"hp_regen_bonus": REGEN_HP, "mana_regen_bonus": REGEN_MP,
                       "remaining": REGEN_DUR})
    hero.cooldowns["R"] = SPLIT_REAL_CD


class Manananggal(HeroDef):
    hero_id = "manananggal"
    name = "Manananggal"

    hp = 620
    mana = 350
    move_speed = 270
    atk_dmg = 58
    atk_range = 160
    atk_interval = 0.95
    atk_type = "melee"
    hp_regen = 3.0

    @ability("Q", "Scratch", cd=7, mana=60, cast=CastType.UNIT)
    def scratch(ctx):
        target = skills.target_dmg(ctx, dmg=Q_DMG, range=Q_RANGE)
        if target is not None:
            skills.slow(ctx, target, pct=Q_SLOW, duration=Q_SLOW_DUR)

    @ability("W", "Pounce", cd=12, mana=50, cast=CastType.UNIT)
    def pounce(ctx):
        skills.dash_to_target(ctx, dist=POUNCE_DIST)

    @ability("E", "Bloodlust", cd=0, mana=0, cast=CastType.PASSIVE)
    def bloodlust(ctx):
        pass  # passive — effect lives in on_ability_cast

    @ability("R", "Split", cd=SPLIT_TOGGLE_CD, mana=0, cast=CastType.NONE)
    def split(ctx):
        hero = ctx.caster
        st = hero.ability_state.get("split")
        if st is None:
            _begin_split(ctx)
        else:
            body = ctx.state.entities.get(st["body_id"])
            if (body is not None and body.alive
                    and hero.distance_to(body) <= RECOMBINE_RANGE):
                _recombine(ctx.state, hero, body)
            # too far from the body: nothing happens (fly back first)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_ability_cast(ctx, key):
        # Bloodlust: every skill cast adds a short, stacking haste.
        ctx.caster.buffs.append({
            "speed_bonus": BLOODLUST_SPEED, "atkspd_pct": BLOODLUST_ATKSPD,
            "remaining": BLOODLUST_DUR,
        })

    @staticmethod
    def on_tick(state, hero, dt):
        st = hero.ability_state.get("split")
        if not st:
            return
        body = state.entities.get(st["body_id"])
        if body is None or not body.alive:
            hero.ability_state.pop("split", None)
            hero.buffs[:] = [b for b in hero.buffs if not b.get("split")]
            return
        # Timed auto-recombine once the split buff expires.
        if not any(b.get("split") for b in hero.buffs):
            _recombine(state, hero, body)
            return
        # Leash the flying upper half to within range of the lower body.
        dx, dy = hero.x - body.x, hero.y - body.y
        d = math.hypot(dx, dy)
        if d > SPLIT_LEASH:
            hero.x = body.x + dx / d * SPLIT_LEASH
            hero.y = body.y + dy / d * SPLIT_LEASH
            hero.target_x = hero.target_y = None
