"""Melchora Aquino — "Tandang Sora", the Mother of the Revolution: a guardian
support who shelters her allies from harm.

Kit:
  Q Sheltering Hand(unit)  grant an ally a damage-absorbing shield.
  W Rallying Words (point) embolden nearby allies: move speed + defenses.
  E Matriarch     (passive)aura: nearby allies take reduced damage.
  R Refuge        (point)  a sanctuary: allies inside are healed, heavily
                           mitigated, and briefly made invulnerable.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.status import Aura, make_status
from server.entity import Hero
from server import skills

# --- Tuning ----------------------------------------------------------------
Q_RANGE, Q_SHIELD, Q_SHIELD_DUR = 600, 180, 6.0

W_RADIUS, W_DUR = 360, 5.0
W_SPEED, W_PDEF, W_SDEF = 60, 18, 18

E_RADIUS, E_REDUCE = 450, 0.12
E_AURA_LINGER = 0.4         # how long the projected aura outlives leaving range

R_RADIUS, R_DUR = 400, 5.0
R_HEAL, R_REDUCE, R_INVULN = 160, 0.5, 0.8


class Melchora(HeroDef):
    hero_id = "melchora"
    name = "Melchora Aquino"

    hp = 620
    mana = 380
    move_speed = 245
    atk_dmg = 42
    sp_atk = 40
    phys_def = 22
    sp_def = 26
    atk_range = 460
    atk_interval = 1.1
    atk_type = "ranged"
    hp_regen = 3.5
    sp_atk_per_level = 4.0
    phys_def_per_level = 3.0
    sp_def_per_level = 3.0

    @ability("Q", "Sheltering Hand", cd=8, mana=60, cast=CastType.UNIT,
             desc="Shield an ally, absorbing incoming damage for a few seconds.")
    def sheltering_hand(ctx):
        caster = ctx.caster
        target = ctx.state.entities.get(ctx.tid) if ctx.tid else None
        if not (isinstance(target, Hero) and target.alive
                and target.team == caster.team
                and caster.distance_to(target) <= Q_RANGE + target.radius):
            target = caster  # default to self if no valid ally was clicked
        target.statuses.add(make_status(Q_SHIELD_DUR, source="melchora:shield",
                                        shield=Q_SHIELD), ctx.state)

    @ability("W", "Rallying Words", cd=12, mana=70, cast=CastType.POINT,
             desc="Embolden nearby allies with bonus move speed and defenses.")
    def rallying_words(ctx):
        allies = skills.allies_in_radius(ctx.state, ctx.caster.team,
                                         ctx.caster.x, ctx.caster.y, W_RADIUS)
        for e in allies:
            if isinstance(e, Hero):
                e.statuses.add(make_status(W_DUR, source="melchora:rally",
                                           speed_bonus=W_SPEED, phys_def=W_PDEF,
                                           sp_def=W_SDEF), ctx.state)

    @ability("E", "Matriarch", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive aura: nearby allies take reduced damage.")
    def matriarch(ctx):
        pass  # passive — refreshed in on_tick

    @ability("R", "Refuge", cd=90, mana=130, cast=CastType.POINT,
             desc="Raise a sanctuary: allies within are healed, heavily mitigated, "
                  "and briefly made invulnerable.")
    def refuge(ctx):
        allies = skills.allies_in_radius(ctx.state, ctx.caster.team,
                                         ctx.tx, ctx.ty, R_RADIUS)
        skills._emit_fx(ctx, "refuge", ctx.tx, ctx.ty, R_RADIUS)
        for e in allies:
            if isinstance(e, Hero):
                e.statuses.add(make_status(R_DUR, source="melchora:refuge",
                                           dmg_reduction=R_REDUCE), ctx.state)
                e.statuses.add(make_status(R_INVULN, source="melchora:refuge",
                                           invuln=True), ctx.state)
                ctx.state.damage_events.append({"tgt": e.entity_id, "heal": R_HEAL})

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        # A projected aura: it lives on each *ally* in range, not on Melchora,
        # so it is refreshed outward rather than attached once. Allies who walk
        # out keep it only until it lapses.
        if not hero.alive or hero.ability_rank("E") <= 0:
            return
        for e in skills.allies_in_radius(state, hero.team, hero.x, hero.y,
                                         E_RADIUS):
            if not isinstance(e, Hero):
                continue
            held = e.statuses.get("statbuff:melchora:matriarch")
            if held is not None:
                held.remaining = E_AURA_LINGER   # refresh, don't stack
            else:
                e.statuses.add(make_status(E_AURA_LINGER,
                                           source="melchora:matriarch",
                                           nohud=True,
                                           dmg_reduction=E_REDUCE), state)
