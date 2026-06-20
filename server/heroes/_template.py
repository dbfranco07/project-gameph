"""TEMPLATE — copy this file to add a new hero.

Steps:
  1. Copy this file to `server/heroes/<your_hero>.py`.
  2. Rename the class and set `hero_id` (unique, lowercase) + `name`.
  3. Tune the base stats.
  4. Write the four ability bodies using the building blocks in `server/skills.py`
     (projectile, dash/blink, area_dmg, area_heal, target_dmg, buff, stun_nearby).
     Combine and tweak them freely — that is what makes each hero unique.
  5. That's it: the registry auto-discovers any HeroDef subclass in this package,
     and the client learns the ability bar from metadata over the wire.

`@ability(key, name, cd, mana, cast=...)` declares an ability. `cast` controls the
client's targeting UX:
  - CastType.NONE  -> fires immediately (self/auto buffs, on-self effects)
  - CastType.POINT -> click a ground location; body reads ctx.tx / ctx.ty
  - CastType.UNIT  -> click an enemy; body reads ctx.tid
  - CastType.VECTOR-> click to pick a direction from the caster (ctx.tx/ctx.ty)

Each ability body takes a single `ctx` (CastContext) with:
  ctx.state   - the GameState
  ctx.caster  - the live Hero entity casting
  ctx.tx, ctx.ty - targeted world point
  ctx.tid     - targeted entity id (unit-target)
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server import skills


class TemplateHero(HeroDef):
    hero_id = "template"      # MUST be unique; rename when you copy this file
    name = "Template Hero"

    # Base stats
    hp = 600
    mana = 250
    move_speed = 250
    atk_dmg = 55
    atk_range = 200
    atk_interval = 1.0
    atk_type = "melee"        # "melee" (instant hit) or "ranged" (projectile)
    hp_regen = 2.0            # slow passive hp/sec
    # mana_regen defaults to the global MANA_REGEN_PER_SEC; override if desired

    @ability("Q", "Bolt", cd=5, mana=50, cast=CastType.POINT)
    def q_bolt(ctx):
        # A point-targeted projectile. Tweak the returned entity for flair.
        skills.projectile(ctx, dmg=90, speed=900, range=850)

    @ability("W", "Hex", cd=8, mana=45, cast=CastType.UNIT)
    def w_hex(ctx):
        # A unit-targeted nuke.
        skills.target_dmg(ctx, dmg=120, range=300)

    @ability("E", "Phase", cd=12, mana=40, cast=CastType.POINT)
    def e_phase(ctx):
        # Example of making a shared block unique: blink AND stun on arrival.
        skills.blink(ctx, dist=350)
        skills.stun_nearby(ctx, radius=160, duration=0.6)

    @ability("R", "Cataclysm", cd=60, mana=100, cast=CastType.POINT)
    def r_cataclysm(ctx):
        skills.area_dmg(ctx, dmg=240, radius=340)
