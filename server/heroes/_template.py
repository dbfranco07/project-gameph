"""TEMPLATE — copy this file to add a new hero.

Steps:
  1. Copy this file to `server/heroes/<your_hero>.py`.
  2. Rename the class and set `hero_id` (unique, lowercase) + `name`.
  3. Tune the base stats.
  4. Write the ability bodies using the building blocks in `server/skills.py`
     (projectile, dash/blink, hook, grapple, area_dmg, area_heal, target_dmg,
     cone, line_aoe, knockback, shield, stun_nearby, summon, pulse, toggle).
     Combine and tweak them freely — that is what makes each hero unique.
  5. Drop sprites in `client/assets/heroes/<your_hero>/`, or run
     `uv run python scripts/gen_all.py` for procedural placeholders.

**There is no registry to edit.** `server/heroes/__init__.py` discovers every
module in this package automatically, and modules starting with `_` (like this
one) are skipped, so this file stays a template rather than a playable hero.
The client learns the whole ability bar from metadata over the wire, so adding
a hero needs no client changes at all.

`@ability(key, name, cd, mana, cast=...)` declares an ability. `cast` controls
the client's targeting UX:
  - CastType.NONE   -> fires immediately (self/auto buffs, on-self effects)
  - CastType.POINT  -> click a ground location; body reads ctx.tx / ctx.ty
  - CastType.UNIT   -> click an enemy; body reads ctx.tid
  - CastType.VECTOR -> click to pick a direction from the caster (ctx.tx/ctx.ty)
  - CastType.PASSIVE-> not castable; implement it in a hook or an Aura

Each ability body takes a single `ctx` (CastContext) with:
  ctx.state   - the GameState
  ctx.caster  - the live Hero entity casting
  ctx.tx, ctx.ty - targeted world point
  ctx.tid     - targeted entity id (unit-target)
  ctx.rank    - the current rank of the ability being cast

Passives: prefer an `Aura` (server/status) over recomputing an effect each
tick. Attach it once from `on_tick` and let its `condition()` toggle it; set
`dynamic = True` and override `active_modifiers` when the numbers scale with
rank or the battlefield.

Optional lifecycle hooks (declare as @staticmethod; full list in
`HeroDef.HERO_HOOKS`): on_tick, on_ability_cast, on_spawn, on_death, on_level,
on_attack, on_hit_dealt, on_damage_taken, on_kill.

`kind=` and `fx=` name client art under `client/assets/projectiles/<kind>/` and
`client/assets/effects/<fx>/`. Both are checked at server startup, so a typo is
reported instead of silently drawing nothing.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.status import Aura
from server import skills


# --- Tuning ----------------------------------------------------------------
# Keep magic numbers up here as named constants: tests import them, so a
# rebalance does not mean rewriting assertions too.
Q_DMG, Q_SPEED, Q_RANGE = 90, 900, 850
W_DMG, W_RANGE = 120, 300
E_BLINK, E_STUN_RADIUS, E_STUN = 350, 160, 0.6
R_DMG, R_RADIUS = 240, 340

E_DEF_PER_RANK = 6


class TemplatePassive(Aura):
    """Optional: a conditional passive. Delete if the hero has none."""

    status_id = "template:passive"
    __slots__ = ()
    dynamic = True      # its numbers follow the ability's rank

    def condition(self, bearer, state) -> bool:
        return bool(bearer.alive and bearer.ability_rank("E") > 0)

    @property
    def active_modifiers(self) -> dict:
        hero = self._bearer
        rank = hero.ability_rank("E") if hero else 0
        return {"phys_def": E_DEF_PER_RANK * rank} if rank else {}


class TemplateHero(HeroDef):
    hero_id = "template"      # MUST be unique; rename when you copy this file
    name = "Template Hero"

    # Base stats
    hp = 600
    mana = 250
    move_speed = 250
    atk_dmg = 55
    sp_atk = 0
    phys_def = 20
    sp_def = 20
    atk_range = 200
    atk_interval = 1.0
    atk_type = "melee"        # "melee" (instant hit) or "ranged" (projectile)
    hp_regen = 2.0            # slow passive hp/sec
    # mana_regen defaults to the global MANA_REGEN_PER_SEC; override if desired

    # Per-level growth
    sp_atk_per_level = 0.0
    phys_def_per_level = 3.0
    sp_def_per_level = 2.0

    @ability("Q", "Bolt", cd=5, mana=50, cast=CastType.POINT,
             desc="Fire a bolt that damages the first enemy it hits.")
    def q_bolt(ctx):
        # A point-targeted projectile. Tweak the returned entity for flair.
        skills.projectile(ctx, dmg=Q_DMG, speed=Q_SPEED, range=Q_RANGE)

    @ability("W", "Hex", cd=8, mana=45, cast=CastType.UNIT,
             target="enemy", range=W_RANGE,
             desc="Hex a single enemy for heavy special damage.")
    def w_hex(ctx):
        skills.target_dmg(ctx, dmg=W_DMG, range=W_RANGE, dtype="special")

    @ability("E", "Phase", cd=12, mana=40, cast=CastType.POINT,
             desc="Blink to a point, stunning enemies where you land. "
                  "Passive: bonus armor per rank.")
    def e_phase(ctx):
        # Example of making a shared block unique: blink AND stun on arrival.
        skills.blink(ctx, dist=E_BLINK)
        skills.stun_nearby(ctx, radius=E_STUN_RADIUS, duration=E_STUN)

    @ability("R", "Cataclysm", cd=60, mana=100, cast=CastType.POINT,
             desc="Detonate a burst of damage at the target point.")
    def r_cataclysm(ctx):
        skills.area_dmg(ctx, dmg=R_DMG, radius=R_RADIUS, fx="smash")

    # ----- lifecycle hooks (delete the ones you don't need) ----------------
    @staticmethod
    def on_tick(state, hero, dt):
        # Attach conditional passives once; they toggle themselves afterwards.
        if hero.statuses.get("template:passive") is None:
            hero.statuses.add(TemplatePassive(), state)
        # Advance any repeating effects started with skills.pulse().
        skills.tick_pulses(state, hero, dt)
