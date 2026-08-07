"""Statuses: the OOP buff / debuff layer.

Replaces the old `server/effects.py`, where an effect was a plain dict and four
hand-maintained tables in that module reverse-engineered its label, icon and
buff/debuff category from which keys it happened to contain. A status now
carries its own presentation and — crucially — its own behaviour, through
lifecycle hooks the damage pipeline and systems dispatch generically.

Typical use from a hero or item:

    from server.status import Slow, Stun, Shield
    target.statuses.add(Slow(2.0, pct=0.35), state)

Adding a new kind of effect means writing a class here (or beside the hero that
owns it), not editing a shared table.
"""

from server.status.base import (
    FLAGS,
    Aura,
    StackPolicy,
    Status,
    StatusContainer,
)
from server.status.factory import make_status
from server.status.mechanics import Bound, DamageAmplify, Frenzy, Split
from server.status.library import (
    AttackSlow,
    DamageReduction,
    Disarm,
    Invisible,
    Invulnerable,
    Lifesteal,
    Phased,
    RuneCooldown,
    RuneDoubleDamage,
    RuneHaste,
    RuneRegen,
    Shield,
    Silence,
    Slow,
    StatBuff,
    Stun,
    TrueSight,
)

__all__ = [
    # base
    "Status", "Aura", "StatusContainer", "StackPolicy", "FLAGS", "make_status",
    # shared hero mechanics
    "Bound", "Split", "Frenzy", "DamageAmplify",
    # crowd control
    "Stun", "Silence", "Disarm", "Slow",
    # defensive
    "Invulnerable", "Shield", "DamageReduction",
    # movement / stealth / vision
    "Phased", "Invisible", "TrueSight",
    # generic + riders
    "StatBuff", "AttackSlow", "Lifesteal",
    # runes
    "RuneHaste", "RuneDoubleDamage", "RuneCooldown", "RuneRegen",
]
