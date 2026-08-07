"""`make_status` — build the right status from a bag of properties.

Hero and skill code reads most naturally as "apply this effect with these
properties" rather than "instantiate this class":

    apply_effect(target, 3.0, phys_def=-15)
    apply_effect(caster, 5.0, source="pedro:blue", phase=True, speed_bonus=90)

This routes each property to where it belongs — stat modifiers into the
`StatBlock`, boolean assertions into flags, and the few properties that imply
*behaviour* (a shield pool, an on-hit slow rider) into the dedicated status
class that implements them. Anything unrecognised raises, which is the whole
point: the dict system accepted every keyword silently, so a misspelled
property was a no-op nobody noticed until the effect visibly did nothing.
"""

from __future__ import annotations

from server.stats import STAT_SPECS, UnknownStatError
from server.status.base import FLAGS, Status
from server.status.library import (
    AttackSlow, Disarm, Invisible, Invulnerable, Phased, Shield, Silence,
    StatBuff, Stun, TrueSight,
)

# When a flag names a well-known effect, use that class rather than a generic
# stat bundle — it carries the right HUD label, icon and buff/debuff category.
# Highest-priority match wins; every flag still rides along on the instance, so
# a status that both stuns and phases keeps both behaviours.
_PRIMARY_BY_FLAG = (
    ("stun", Stun),
    ("silence", Silence),
    ("disarm", Disarm),
    ("invuln", Invulnerable),
    ("invisible", Invisible),
    ("phase", Phased),
    ("unobstructed_vision", TrueSight),
)

# Properties that are neither a stat nor a flag: they parameterise a behavioural
# status rather than being applied directly.
_BEHAVIOUR_KEYS = {
    "shield",           # -> Shield(amount=...)
    "attack_slow_pct",  # -> AttackSlow(pct=...)
    "attack_slow_dur",  # -> AttackSlow(slow_duration=...)
}


def make_status(duration: float, source: str | None = None,
                nohud: bool = False, **props) -> Status:
    """Build a status carrying `props`.

    Falsy values are kept rather than dropped — `slow_pct=0` now means "a slow
    of zero", not "no slow at all". The old constructor filtered them out, which
    made the truthiness contract implicit and occasionally surprising.
    """
    unknown = [k for k in props
               if k not in STAT_SPECS and k not in FLAGS and k not in _BEHAVIOUR_KEYS]
    if unknown:
        raise UnknownStatError(
            f"unknown effect propert{'y' if len(unknown) == 1 else 'ies'} "
            f"{sorted(unknown)} — declare a stat in server/stats.STAT_SPECS "
            f"or a flag in server.status.base.FLAGS")

    mods = {k: v for k, v in props.items() if k in STAT_SPECS}
    flags = frozenset(k for k in props if k in FLAGS and props[k])

    # A shield is a draining pool, not a static number: give it its own class so
    # the mitigation logic lives in the effect instead of the damage system.
    if props.get("shield"):
        status = Shield(duration, props["shield"], source=source,
                        modifiers=mods, flags=flags)
    # An on-hit slow is a hook, not a stat the combat system has to look up.
    elif props.get("attack_slow_pct"):
        status = AttackSlow(duration, pct=props["attack_slow_pct"],
                            slow_duration=props.get("attack_slow_dur", 1.0),
                            source=source, modifiers=mods, flags=flags)
    else:
        primary = next((cls for flag, cls in _PRIMARY_BY_FLAG if flag in flags),
                       None)
        if primary is not None:
            status = primary(duration, source=source, modifiers=mods,
                             flags=flags)
        else:
            status = StatBuff(duration, source=source, modifiers=mods,
                              flags=flags)

    if nohud:
        status.hidden = True
    return status
