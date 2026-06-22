"""Tiyanak — a swift, blood-hungry assassin that strikes from an anchor.

Kit:
  Q Cradle Bite (unit)    a single-target bite that can crit and lifesteals.
  W Tantrum     (self)    brief frenzy: bonus attack speed + guaranteed crits.
  E Feral Hunger(passive) crit chance + lifesteal (scale with rank); extra move
                          speed while no enemy is near (swift out of combat).
  R Umbilical Cord(self)  anchor to the current spot and gain haste to roam;
                          recast — or when the timer expires — snaps you back to
                          the anchor (dive in, then yank out / escape).
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.effects import make_effect
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_RANGE, Q_DMG = 360, 130

TANTRUM_DUR, TANTRUM_ATKSPD = 4.0, 0.6

E_CRIT_PER_RANK = 0.06      # rank 1..4 -> 6%..24% crit
E_LIFESTEAL_PER_RANK = 0.05 # rank 1..4 -> 5%..20% lifesteal
E_SWIFT_SPEED = 90          # extra speed when no enemy is near
E_DANGER_RADIUS = 650       # "in combat" if an enemy is within this distance

CORD_DUR = 6.0
CORD_SPEED = 160
CORD_REAL_CD = 22.0


def _anchor_snap(hero) -> None:
    st = hero.ability_state.pop("cord", None)
    hero.buffs[:] = [b for b in hero.buffs if b.get("source") != "tiyanak:cord"]
    if st is not None:
        hero.x, hero.y = st["x"], st["y"]
        hero.target_x = hero.target_y = None
        hero.attack_move = False
        hero.attack_move_x = hero.attack_move_y = None
    hero.cooldowns["R"] = CORD_REAL_CD


class Tiyanak(HeroDef):
    hero_id = "tiyanak"
    name = "Tiyanak"

    hp = 560
    mana = 300
    move_speed = 290
    atk_dmg = 60
    sp_atk = 10
    phys_def = 18
    sp_def = 18
    atk_range = 150
    atk_interval = 0.85
    atk_type = "melee"
    hp_regen = 2.5
    crit_chance = 0.05
    crit_mult = 2.0
    phys_def_per_level = 2.5
    sp_def_per_level = 2.0

    @ability("Q", "Cradle Bite", cd=6, mana=45, cast=CastType.UNIT,
             desc="Bite an enemy for heavy damage. Can crit and heals you for a "
                  "portion of the damage dealt.")
    def cradle_bite(ctx):
        caster = ctx.caster
        target = ctx.state.entities.get(ctx.tid) if ctx.tid else None
        if target is None or not target.alive or target.team == caster.team:
            target = skills.nearest_enemy(ctx.state, caster.team, caster.x,
                                          caster.y, Q_RANGE, toward=(ctx.tx, ctx.ty))
        if target is None or caster.distance_to(target) > Q_RANGE + target.radius:
            return
        # crit_ok lets this ability roll the caster's crit; lifesteal applies via
        # the resolver because the source hero carries lifesteal.
        ctx.state.damage_events.append(
            {"src": caster.entity_id, "tgt": target.entity_id, "amt": Q_DMG,
             "dtype": "physical", "crit_ok": True})

    @ability("W", "Tantrum", cd=16, mana=60, cast=CastType.NONE,
             desc="Fly into a frenzy: bonus attack speed and guaranteed critical "
                  "strikes for a few seconds.")
    def tantrum(ctx):
        ctx.caster.buffs.append(
            make_effect(TANTRUM_DUR, source="tiyanak:tantrum",
                        atkspd_pct=TANTRUM_ATKSPD, guaranteed_crit=True))

    @ability("E", "Feral Hunger", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: gain crit chance and lifesteal; move faster while no "
                  "enemy is nearby.")
    def feral_hunger(ctx):
        pass  # passive — refreshed in on_tick

    @ability("R", "Umbilical Cord", cd=2.0, mana=80, cast=CastType.NONE,
             desc="Anchor here and gain haste to roam. Recast, or let the timer "
                  "lapse, to snap back to the anchor.")
    def umbilical_cord(ctx):
        hero = ctx.caster
        if hero.ability_state.get("cord") is None:
            hero.ability_state["cord"] = {"x": hero.x, "y": hero.y}
            hero.buffs.append(make_effect(CORD_DUR, source="tiyanak:cord",
                                          speed_bonus=CORD_SPEED))
        else:
            _anchor_snap(hero)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        # Auto-snap when the cord buff has lapsed but the anchor still stands.
        if (hero.ability_state.get("cord") is not None
                and not any(b.get("source") == "tiyanak:cord" for b in hero.buffs)):
            _anchor_snap(hero)

        # Refresh the Feral Hunger passive (rank-scaled crit + lifesteal, plus
        # out-of-combat swiftness).
        hero.buffs[:] = [b for b in hero.buffs
                         if b.get("source") != "tiyanak:feral"]
        if not hero.alive:
            return
        erank = hero.ability_rank("E")
        if erank <= 0:
            return
        mods = {"crit_chance": E_CRIT_PER_RANK * erank,
                "lifesteal": E_LIFESTEAL_PER_RANK * erank}
        if skills.nearest_enemy(state, hero.team, hero.x, hero.y,
                                E_DANGER_RADIUS) is None:
            mods["speed_bonus"] = E_SWIFT_SPEED
        hero.buffs.append(make_effect(0.5, source="tiyanak:feral", **mods))
