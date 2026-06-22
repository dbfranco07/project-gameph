"""Jose Rizal — a scholar-hero who fights with pen and word.

Kit:
  Q Pluma Throw  (point)   hurl the pen as a boomerang: special damage out and
                           back along its flight.
  W Words of Reform(point) hypnotic oratory: silence enemies in an area (a brief
                           stun at higher ranks).
  E Polymath     (passive) his intellect grants bonus special attack and reduced
                           cooldowns.
  R Mi Ultimo Adios(self)  a final inspiration: all allies gain special attack
                           and speed and are healed.
"""

from __future__ import annotations

import math

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.effects import make_effect
from server.entity import Hero
from server import skills
from shared.config import MAP_WIDTH, MAP_HEIGHT

# --- Tuning ----------------------------------------------------------------
Q_DMG, Q_SPEED, Q_RANGE = 95, 950, 700

W_RADIUS, W_SILENCE = 320, 1.8
W_STUN_RANK, W_STUN = 3, 0.7   # at rank >= 3 the silence also briefly stuns

E_SPATK_PER_RANK = 6
E_CDR_PER_RANK = 0.04          # rank 1..4 -> 4%..16% cooldown reduction

R_DUR = 8.0
R_SPATK, R_SPEED, R_HEAL = 45, 70, 120
_MAP_DIAG = math.hypot(MAP_WIDTH, MAP_HEIGHT)


class Rizal(HeroDef):
    hero_id = "rizal"
    name = "Jose Rizal"

    hp = 540
    mana = 380
    move_speed = 250
    atk_dmg = 46
    sp_atk = 52
    phys_def = 16
    sp_def = 22
    atk_range = 520
    atk_interval = 1.0
    atk_type = "ranged"
    hp_regen = 2.5
    sp_atk_per_level = 6.0
    phys_def_per_level = 2.0
    sp_def_per_level = 3.0

    @ability("Q", "Pluma Throw", cd=6, mana=55, cast=CastType.POINT,
             desc="Hurl your pen as a boomerang, dealing special damage to "
                  "enemies along its path out and back.")
    def pluma_throw(ctx):
        caster = ctx.caster
        # Outward throw.
        skills.projectile(ctx, dmg=Q_DMG, speed=Q_SPEED, range=Q_RANGE,
                          radius=20, dtype="special", kind="rizal_q")
        # Return pass: spawn a second bolt from the far end back toward the caster.
        dx, dy = ctx.tx - caster.x, ctx.ty - caster.y
        dist = math.hypot(dx, dy) or 1.0
        reach = min(Q_RANGE, dist)
        far_x = caster.x + dx / dist * reach
        far_y = caster.y + dy / dist * reach
        ret = skills.projectile(ctx, dmg=Q_DMG, speed=Q_SPEED, range=reach,
                                radius=20, dtype="special", kind="rizal_q")
        ret.x, ret.y = far_x, far_y
        rdx, rdy = caster.x - far_x, caster.y - far_y
        rd = math.hypot(rdx, rdy) or 1.0
        ret.vx, ret.vy = rdx / rd * Q_SPEED, rdy / rd * Q_SPEED

    @ability("W", "Words of Reform", cd=12, mana=70, cast=CastType.POINT,
             desc="Hypnotic words silence enemies in an area (and briefly stun "
                  "them at higher ranks).")
    def words_of_reform(ctx):
        hit = skills.area_dmg(ctx, dmg=0, radius=W_RADIUS, dtype="special",
                              fx="reform")
        stun = ctx.rank >= W_STUN_RANK
        for e in hit:
            skills.silence(ctx, e, W_SILENCE)
            if stun:
                skills.stun_target(ctx, e, W_STUN)

    @ability("E", "Polymath", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: gain bonus special attack and reduced cooldowns.")
    def polymath(ctx):
        pass  # passive — refreshed in on_tick

    @ability("R", "Mi Ultimo Adios", cd=90, mana=130, cast=CastType.NONE,
             desc="Inspire every ally: bonus special attack and move speed, plus "
                  "an immediate heal.")
    def mi_ultimo_adios(ctx):
        allies = skills.allies_in_radius(ctx.state, ctx.caster.team,
                                         ctx.caster.x, ctx.caster.y, _MAP_DIAG)
        for e in allies:
            if isinstance(e, Hero):
                e.buffs.append(make_effect(R_DUR, source="rizal:adios",
                                           sp_atk=R_SPATK, speed_bonus=R_SPEED))
                ctx.state.damage_events.append({"tgt": e.entity_id, "heal": R_HEAL})

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        hero.buffs[:] = [b for b in hero.buffs
                         if b.get("source") != "rizal:polymath"]
        if not hero.alive:
            return
        erank = hero.ability_rank("E")
        if erank <= 0:
            return
        hero.buffs.append(make_effect(
            0.5, source="rizal:polymath", sp_atk=E_SPATK_PER_RANK * erank,
            cd_mult=1.0 - E_CDR_PER_RANK * erank))
