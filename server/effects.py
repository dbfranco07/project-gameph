"""Unified buff / debuff effects.

A single concept covers buffs and debuffs — the *sign* of each number decides
whether it helps or hurts (a +15 phys_def is a buff, a -15 is a debuff). Effects
are plain dicts stored on ``Hero.buffs`` (kept that way for back-compatibility
with the hand-written effect dicts in existing heroes); this module just gives a
named constructor plus the catalog of recognized modifier keys so the HUD can
report temporary stat deltas.

Recognized keys:
  Stat modifiers (added to the matching base stat):
    dmg_bonus, sp_atk, phys_def, sp_def, range_bonus, speed_bonus,
    atkspd_pct, hp_regen_bonus, mana_regen_bonus, vision_bonus
  Multiplicative:
    slow_pct       (movement slow, 0..1; stacks additively, capped)
  Combat modifiers (resolved in system_damage_death):
    crit_chance      (added dodge-able crit chance, 0..1)
    crit_mult        (added to base crit multiplier)
    guaranteed_crit  (truthy; forces every eligible hit to crit)
    lifesteal        (fraction of damage dealt healed back to the attacker)
    evasion          (chance to dodge an incoming basic physical hit, 0..1)
    true_strike      (truthy; this unit's basic hits ignore enemy evasion)
    dmg_reduction    (flat incoming-damage mitigation fraction, 0..1, capped)
    shield           (HP-absorb pool; depleted before damage reaches HP)
  Crowd-control flags (truthy):
    stun           (cannot move / attack / cast)
    silence        (cannot cast abilities)
    disarm         (cannot auto-attack, but may still move / cast)
    invuln         (takes no damage)
    phase          (ignores wall/tree terrain collision)
  Stealth / vision flags (truthy):
    invisible          (hidden from enemies; allies still see; revealed while
                        attacking via Hero.reveal_timer)
    unobstructed_vision(this unit's sight ignores wall/tree line-of-sight blocks)
  On-hit rider:
    attack_slow_pct(this unit's auto-attacks apply a movement slow to the victim)
  Bookkeeping:
    remaining      (seconds left; ticked down by system_status)
    source         (optional tag, e.g. "rune:haste", for cancel-on-hit logic)
"""
from __future__ import annotations

# Effect keys that map directly onto a HUD stat row, with the snapshot field the
# client reads for the green(+)/red(-) temporary delta. (move/atkspd handled
# specially because they are multiplicative / interact with slow.)
STAT_KEYS = {
    "dmg_bonus": "ad",
    "sp_atk": "spa",
    "phys_def": "pdef",
    "sp_def": "sdef",
    "range_bonus": "rng",
    "hp_regen_bonus": "hpr",
    "mana_regen_bonus": "mpr",
}


def make_effect(duration: float, source: str | None = None, **mods) -> dict:
    """Build an effect dict. Pass any recognized modifier keys as kwargs."""
    eff = {k: v for k, v in mods.items() if v}
    eff["remaining"] = duration
    if source is not None:
        eff["source"] = source
    return eff
