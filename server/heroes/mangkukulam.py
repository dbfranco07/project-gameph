"""Mangkukulam — a witch who curses foes while mending allies.

Kit:
  Q Hex Aura   (point)    burst an area: special damage to enemies, healing to
                          allies. With Evil Eye learned it also shreds sp. def.
  W Worm Curse (unit)     curse a target: a writhing brood of worms spawns and
                          gnaws the victim (summoned pets) and slows it.
  E Evil Eye   (passive)  her hexes (Q/R) tear at enemy special defense.
  R Pangkukulam(point)    a great curse: heavy special damage + silence in a zone.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_BASE_DMG, Q_DMG_PER_RANK = 70, 13
Q_BASE_HEAL, Q_HEAL_PER_RANK = 55, 10
Q_RADIUS = 280

W_RANGE = 600
W_WORMS, W_WORM_LIFE = 3, 7.0
W_BASE_WORM_DMG, W_WORM_DMG_PER_RANK = 12, 2
W_SLOW, W_SLOW_DUR = 0.25, 3.0

E_SHRED_PER_RANK, E_SHRED_DUR = 5, 4.0   # sp_def reduction applied by hexes per cast

R_BASE_DMG, R_DMG_PER_RANK = 180, 32
R_RADIUS = 360
R_SILENCE = 1.6


def _evil_eye(ctx, targets) -> None:
    rank = ctx.caster.ability_rank("E")
    if rank > 0:
        shred = E_SHRED_PER_RANK * rank
        for e in targets:
            skills.shred_sp_def(ctx, e, shred, E_SHRED_DUR)


class Mangkukulam(HeroDef):
    hero_id = "mangkukulam"
    name = "Mangkukulam"

    hp = 570
    mana = 370
    move_speed = 248
    atk_dmg = 40
    sp_atk = 54
    phys_def = 17
    sp_def = 23
    atk_range = 310
    atk_interval = 1.05
    atk_type = "ranged"
    hp_regen = 2.6
    sp_atk_per_level = 6.0
    phys_def_per_level = 2.0
    sp_def_per_level = 3.0

    @ability("Q", "Hex Aura", cd=7, mana=70, cast=CastType.POINT, radius=Q_RADIUS,
             desc="Curse an area: special damage to enemies and healing to "
                  "allies. With Evil Eye, also reduces enemy special defense.")
    def hex_aura(ctx):
        rank = ctx.caster.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        heal = Q_BASE_HEAL + Q_HEAL_PER_RANK * (rank - 1)
        hit = skills.area_dmg(ctx, dmg=dmg, radius=Q_RADIUS, dtype="special",
                              fx="hexaura")
        skills.area_heal(ctx, heal=heal, radius=Q_RADIUS, fx="hexheal")
        _evil_eye(ctx, hit)

    @ability("W", "Worm Curse", cd=14, mana=80, cast=CastType.UNIT,
             target="enemy", range=W_RANGE,
             desc="Curse a target: a brood of worms spawns to gnaw it, and it is "
                  "slowed.")
    def worm_curse(ctx):
        caster = ctx.caster
        target = ctx.state.entities.get(ctx.tid) if ctx.tid else None
        if target is None or not target.alive or target.team == caster.team:
            target = skills.nearest_enemy(ctx.state, caster.team, caster.x,
                                          caster.y, W_RANGE, toward=(ctx.tx, ctx.ty))
        if target is None or caster.distance_to(target) > W_RANGE + target.radius:
            return
        rank = caster.ability_rank("W")
        worm_dmg = W_BASE_WORM_DMG + W_WORM_DMG_PER_RANK * (rank - 1)
        skills.slow(ctx, target, pct=W_SLOW, duration=W_SLOW_DUR)
        skills.summon(ctx, count=W_WORMS, lifetime=W_WORM_LIFE,
                      target_id=target.entity_id, attack_damage=worm_dmg)

    @ability("E", "Evil Eye", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: your hexes (Hex Aura, Pangkukulam) shred the special "
                  "defense of enemies they strike.")
    def evil_eye(ctx):
        pass  # passive — read by Q/R via _evil_eye

    @ability("R", "Pangkukulam", cd=80, mana=130, cast=CastType.POINT,
             radius=R_RADIUS,
             desc="Unleash a great curse: heavy special damage and a silence to "
                  "all enemies in a large area.")
    def pangkukulam(ctx):
        rank = ctx.caster.ability_rank("R")
        dmg = R_BASE_DMG + R_DMG_PER_RANK * (rank - 1)
        hit = skills.area_dmg(ctx, dmg=dmg, radius=R_RADIUS, dtype="special",
                              fx="pangkukulam")
        for e in hit:
            skills.silence(ctx, e, R_SILENCE)
        _evil_eye(ctx, hit)
