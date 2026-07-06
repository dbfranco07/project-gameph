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


def make_effect(duration: float, source: str | None = None,
                nohud: bool = False, **mods) -> dict:
    """Build an effect dict. Pass any recognized modifier keys as kwargs.

    ``duration`` is remembered as ``dur`` (alongside the ticking ``remaining``)
    so the HUD can draw a timer ring as ``remaining / dur``. Pass ``nohud=True``
    to keep an internal / passive-refresh effect (e.g. one re-applied every tick)
    out of the HUD's buff/debuff row so it doesn't flicker.
    """
    eff = {k: v for k, v in mods.items() if v}
    eff["remaining"] = duration
    eff["dur"] = duration
    if source is not None:
        eff["source"] = source
    if nohud:
        eff["nohud"] = True
    return eff


# --- HUD buff/debuff description -------------------------------------------
# Ordered crowd-control / flag effects: (effect key, label, icon id, category).
# These dominate the display when present (a stun matters more than its stats).
_FLAG_EFFECTS = [
    ("stun", "Stun", "stun", "debuff"),
    ("silence", "Silence", "silence", "debuff"),
    ("disarm", "Disarm", "disarm", "debuff"),
    ("slow_pct", "Slow", "slow", "debuff"),
    ("invuln", "Invuln", "invuln", "buff"),
    ("shield", "Shield", "shield", "buff"),
]

# Stat keys that name a nondescript effect when no flag/source matched.
_STAT_LABELS = {
    "dmg_bonus": ("ATK", "dmg"),
    "sp_atk": ("SP", "sp_atk"),
    "phys_def": ("DEF", "def"),
    "sp_def": ("SPDEF", "sp_def"),
    "speed_bonus": ("MS", "speed"),
    "atkspd_pct": ("AS", "atkspd"),
    "range_bonus": ("RNG", "range"),
    "crit_chance": ("Crit", "crit"),
    "lifesteal": ("Life", "lifesteal"),
    "evasion": ("Dodge", "evasion"),
    "dmg_reduction": ("Armor", "reduce"),
    "hp_regen_bonus": ("Regen", "regen"),
}

# Signed stat keys used to decide buff vs debuff.
_SIGNED_KEYS = (
    "dmg_bonus", "sp_atk", "phys_def", "sp_def", "range_bonus", "speed_bonus",
    "atkspd_pct", "hp_regen_bonus", "mana_regen_bonus", "vision_bonus",
    "crit_chance", "crit_mult", "lifesteal", "evasion", "dmg_reduction", "shield",
)
# Truthy buff flags with no numeric sign.
_BUFF_FLAGS = ("invisible", "unobstructed_vision", "phase", "true_strike",
               "guaranteed_crit")
# Friendly names for known effect sources ("tag" -> label).
_SOURCE_LABELS = {"frenzy": "Frenzy", "haste": "Haste", "elastic": "Elastic"}


def _category(eff: dict) -> str | None:
    """buff / debuff / None (nothing worth showing) from an effect's modifiers."""
    if eff.get("slow_pct"):
        return "debuff"
    neg = any(eff.get(k, 0) < 0 for k in _SIGNED_KEYS)
    pos = any(eff.get(k, 0) > 0 for k in _SIGNED_KEYS)
    if pos:
        return "buff"
    if neg:
        return "debuff"
    if any(eff.get(k) for k in _BUFF_FLAGS):
        return "buff"
    return None


def _named(eff: dict):
    """(label, icon) for a source-tagged or stat-dominant effect."""
    tag = eff.get("source", "").split(":")[-1]
    if tag:
        return (_SOURCE_LABELS.get(tag, tag[:6].title()), tag)
    for key, (lbl, icon) in _STAT_LABELS.items():
        if eff.get(key):
            return (lbl, icon)
    return ("Buff", "buff")


def describe_effect(eff: dict) -> dict | None:
    """Summarize an effect for the HUD, or None to hide it.

    Returns ``{"lbl", "cat", "icon", "rem", "dur"}``: a short label, category
    ("buff"/"debuff"), a stable icon id (so art can be swapped in later, keyed
    off this string), and the remaining / original duration for the timer ring.
    """
    if eff.get("nohud"):
        return None
    rem = eff.get("remaining", 0.0)
    if rem <= 0:
        return None
    dur = eff.get("dur") or rem
    for key, lbl, icon, cat in _FLAG_EFFECTS:
        if eff.get(key):
            return {"lbl": lbl, "cat": cat, "icon": icon,
                    "rem": round(rem, 1), "dur": round(dur, 1)}
    cat = _category(eff)
    if cat is None:
        # A source-tagged effect with a custom mechanic key (e.g. frenzy=True):
        # not a plain stat mod, but still a real named buff worth showing.
        extra = [k for k in eff if k not in ("remaining", "dur", "source", "nohud")]
        if eff.get("source") and extra:
            cat = "buff"
        else:
            return None
    lbl, icon = _named(eff)
    return {"lbl": lbl, "cat": cat, "icon": icon,
            "rem": round(rem, 1), "dur": round(dur, 1)}
