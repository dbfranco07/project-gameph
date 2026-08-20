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
from server.status import Aura, make_status
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_RANGE = 360
Q_BASE_DMG, Q_DMG_PER_RANK = 100, 18

TANTRUM_BASE_DUR, TANTRUM_DUR_PER_RANK = 3.0, 0.5
TANTRUM_BASE_ATKSPD, TANTRUM_ATKSPD_PER_RANK = 0.45, 0.08

E_CRIT_PER_RANK = 0.06      # rank 1..4 -> 6%..24% crit
E_LIFESTEAL_PER_RANK = 0.05 # rank 1..4 -> 5%..20% lifesteal
E_SWIFT_SPEED = 90          # extra speed when no enemy is near
E_DANGER_RADIUS = 650       # "in combat" if an enemy is within this distance

CORD_DUR = 6.0
CORD_SPEED = 160
CORD_REAL_CD = 22.0


class FeralHunger(Aura):
    """E passive: rank-scaled crit chance and lifesteal, plus swiftness while no
    enemy is near. Dynamic — its numbers follow the rank, and the swiftness
    component toggles with proximity."""

    status_id = "tiyanak:feral"
    __slots__ = ("_swift",)
    dynamic = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Enemy proximity needs the world, which `active_modifiers` cannot see;
        # `condition` runs first each tick and stashes the answer here.
        self._swift = False

    def condition(self, bearer, state) -> bool:
        if not (bearer.alive and bearer.ability_rank("E") > 0):
            return False
        self._swift = (state is not None and skills.nearest_enemy(
            state, bearer.team, bearer.x, bearer.y, E_DANGER_RADIUS) is None)
        return True

    @property
    def active_modifiers(self) -> dict:
        hero = self._bearer
        if hero is None:
            return {}
        rank = hero.ability_rank("E")
        if rank <= 0:
            return {}
        mods = {"crit_chance": E_CRIT_PER_RANK * rank,
                "lifesteal": E_LIFESTEAL_PER_RANK * rank}
        if self._swift:
            mods["speed_bonus"] = E_SWIFT_SPEED
        return mods


def _anchor_snap(hero, state=None) -> None:
    st = hero.ability_state.pop("cord", None)
    hero.statuses.remove_source("tiyanak:cord", state)
    if st is not None:
        hero.x, hero.y = st["x"], st["y"]
        hero.target_x = hero.target_y = None
        hero.attack_move = False
        hero.attack_move_x = hero.attack_move_y = None
    hero.cooldowns["R"] = CORD_REAL_CD


class Tiyanak(HeroDef):
    hero_id = "tiyanak"
    name = "Tiyanak"

    hp = 540
    mana = 290
    move_speed = 295
    atk_dmg = 62
    sp_atk = 9
    phys_def = 15
    sp_def = 15
    atk_range = 152
    atk_interval = 0.85
    atk_type = "melee"
    hp_regen = 2.2
    crit_chance = 0.05
    crit_mult = 2.0
    phys_def_per_level = 2.5
    sp_def_per_level = 2.0

    @ability("Q", "Cradle Bite", cd=6, mana=45, cast=CastType.UNIT,
             target="enemy", range=Q_RANGE,
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
        rank = caster.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        # crit_ok lets this ability roll the caster's crit; lifesteal applies via
        # the resolver because the source hero carries lifesteal.
        ctx.state.damage_events.append(
            {"src": caster.entity_id, "tgt": target.entity_id, "amt": dmg,
             "dtype": "physical", "crit_ok": True})

    @ability("W", "Tantrum", cd=16, mana=60, cast=CastType.NONE,
             desc="Fly into a frenzy: bonus attack speed and guaranteed critical "
                  "strikes for a few seconds.")
    def tantrum(ctx):
        rank = ctx.caster.ability_rank("W")
        dur = TANTRUM_BASE_DUR + TANTRUM_DUR_PER_RANK * (rank - 1)
        atkspd = TANTRUM_BASE_ATKSPD + TANTRUM_ATKSPD_PER_RANK * (rank - 1)
        ctx.caster.statuses.add(
            make_status(dur, source="tiyanak:tantrum",
                        atkspd_pct=atkspd, guaranteed_crit=True),
            ctx.state)

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
            hero.statuses.add(make_status(CORD_DUR, source="tiyanak:cord",
                                          speed_bonus=CORD_SPEED), ctx.state)
        else:
            _anchor_snap(hero, ctx.state)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        # Auto-snap when the cord buff has lapsed but the anchor still stands.
        if (hero.ability_state.get("cord") is not None
                and not hero.statuses.by_source("tiyanak:cord")):
            _anchor_snap(hero, state)
        # Attach the passive once; it tracks rank and proximity itself.
        if hero.statuses.get("tiyanak:feral") is None:
            hero.statuses.add(FeralHunger(), state)
