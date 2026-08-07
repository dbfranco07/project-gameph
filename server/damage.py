"""The damage pipeline.

Resolving one hit used to be a single 70-line block inside
`system_damage_death` that did eleven unrelated jobs in sequence — and knew, by
name, about the Manananggal's detached body and about which rune buff needed
stripping when its bearer was hit. Every new mechanic that touched damage meant
another branch in the middle of that block.

Here a hit is a `DamageEvent` carried through an ordered list of small stages.
Each stage does one thing and may cancel the event outright. Statuses and (later)
items participate through their own hooks rather than by being special-cased, so
adding a mechanic means writing a status, not editing this file.

Stage order is gameplay-visible and deliberate:

    invulnerable -> evade -> crit -> defense -> reduction
                 -> absorb (status hooks: shields, cancel-on-hit)
                 -> apply -> lifesteal -> on-hit hooks

Mitigation runs before absorption so a shield soaks *post-armor* damage, and
lifesteal is computed from the damage actually dealt.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from shared.config import DEFENSE_K


@dataclass
class DamageEvent:
    """One hit in flight. Stages read and mutate it; `cancelled` stops the run."""

    state: object
    target: object
    source: object | None
    amount: float
    dtype: str = "physical"          # physical | special | true
    is_basic: bool = False           # an auto-attack rather than an ability
    crit_ok: bool = False            # an ability that opted into critting

    # Filled in as the event travels.
    crit: bool = False
    evaded: bool = False
    absorbed: float = 0.0
    cancelled: bool = False

    #: The raw amount before any mitigation, kept for effects that scale off it.
    raw: float = field(default=0.0)

    def cancel(self) -> None:
        self.cancelled = True

    @property
    def attacker(self):
        """The source, but only when it is a hero (the only kind that crits,
        lifesteals, and owns on-hit riders)."""
        from server.entity import Hero
        return self.source if isinstance(self.source, Hero) else None


def _fire_hero_hook(entity, name: str, *args) -> None:
    """Call a hero definition's lifecycle hook, if this entity is a hero that
    defines one. Kept local to avoid importing systems (which imports us)."""
    hd = getattr(entity, "hero_def", None)
    if hd is None:
        return
    hook = getattr(hd, name, None)
    if hook is not None:
        hook(*args)


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def stage_invulnerable(ev: DamageEvent) -> None:
    if ev.target.statuses.has("invuln"):
        ev.cancel()


def stage_evade(ev: DamageEvent) -> None:
    """Dodge an incoming basic physical attack. Abilities and non-physical
    damage cannot be dodged, and true-strike ignores evasion."""
    from server.entity import Hero
    if not (isinstance(ev.target, Hero) and ev.is_basic and ev.dtype == "physical"):
        return
    chance = ev.target.effective_evasion()
    if chance <= 0:
        return
    attacker = ev.attacker
    if attacker is not None and attacker.has_true_strike():
        return
    if random.random() < chance:
        ev.evaded = True
        ev.cancel()
        ev.state.combat_events.append(
            {"k": "miss", "x": round(ev.target.x, 1), "y": round(ev.target.y, 1),
             "eid": ev.target.entity_id})


def stage_crit(ev: DamageEvent) -> None:
    """Basic attacks always roll; abilities only when they opt in."""
    attacker = ev.attacker
    if attacker is None or not (ev.is_basic or ev.crit_ok):
        return
    if random.random() < attacker.effective_crit_chance():
        ev.crit = True
        ev.amount = int(ev.amount * attacker.effective_crit_mult())


def stage_defense(ev: DamageEvent) -> None:
    """The armor curve: DEF/(DEF+K) mitigation. True damage ignores it."""
    ev.amount = apply_defense(ev.target, ev.amount, ev.dtype)


def stage_reduction(ev: DamageEvent) -> None:
    """Flat percentage mitigation from statuses (capped by STAT_SPECS)."""
    from server.entity import Hero
    if isinstance(ev.target, Hero):
        ev.amount = int(ev.amount * (1.0 - ev.target.damage_reduction()))


def stage_absorb(ev: DamageEvent) -> None:
    """Hand the event to the target's statuses.

    This is where shields drain, damage amplifiers apply, and effects that
    fizzle when their bearer is hit end themselves — each in its own class,
    none of them known to this module.
    """
    ev.target.statuses.on_damage_taken(ev, ev.state)
    _fire_hero_hook(ev.target, "on_damage_taken", ev.state, ev.target, ev)


def stage_apply(ev: DamageEvent) -> None:
    ev.amount = max(0, int(ev.amount))
    ev.target.hp -= ev.amount


def stage_lifesteal(ev: DamageEvent) -> None:
    attacker = ev.attacker
    if attacker is None or ev.amount <= 0 or not attacker.alive:
        return
    ls = attacker.effective_lifesteal()
    if ls > 0:
        attacker.hp = min(attacker.effective_max_hp(),
                          attacker.hp + int(ev.amount * ls))


def stage_on_hit(ev: DamageEvent) -> None:
    """On-hit riders owned by the attacker (Kapre's slow, item procs)."""
    if ev.source is None or ev.amount <= 0:
        return
    statuses = getattr(ev.source, "statuses", None)
    if statuses is not None:
        statuses.on_hit_dealt(ev.target, ev.amount, ev.state)
    _fire_hero_hook(ev.source, "on_hit_dealt", ev.state, ev.source, ev.target,
                    ev.amount)


#: The pipeline. Order is gameplay-visible; see the module docstring.
STAGES = (
    stage_invulnerable,
    stage_evade,
    stage_crit,
    stage_defense,
    stage_reduction,
    stage_absorb,
    stage_apply,
    stage_lifesteal,
    stage_on_hit,
)


def resolve(ev: DamageEvent) -> DamageEvent:
    """Run `ev` through the pipeline, stopping early if a stage cancels it."""
    ev.raw = ev.amount
    for stage in STAGES:
        stage(ev)
        if ev.cancelled:
            break
    return ev


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def apply_defense(target, raw, dtype: str) -> int:
    """Reduce `raw` by the target's relevant defense using the armor curve."""
    if dtype == "true":
        return int(raw)
    if dtype == "special":
        defense = target.effective_sp_def()
    else:  # physical (default)
        defense = target.effective_phys_def()
    if defense <= 0:
        return int(raw)
    return int(raw * DEFENSE_K / (defense + DEFENSE_K))
