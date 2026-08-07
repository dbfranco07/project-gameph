"""Statuses for mechanics that more than one hero or system has to agree on.

These were the undocumented ad-hoc keys of the dict era — `bind`, `split`,
`frenzy` — read by name from inside `systems.py`, `bind.py` and individual hero
modules with nothing tying the writers and readers together. As classes they are
declared once and asserted through the flag registry, so a reader can no longer
silently disagree with a writer about the spelling.
"""

from __future__ import annotations

import math

from server.status.base import StackPolicy, Status


class Bound(Status):
    """Lodged inside a wall or tree (Kapre R, Tiktik W).

    While bound the hero phases through terrain and sees past it. The owning
    obstacle and the ability key that produced the bind travel on the status so
    the release path does not need a parallel bookkeeping dict.
    """

    status_id = "bind"
    label = "Bound"
    icon = "bind"
    flags = frozenset({"bind", "phase", "unobstructed_vision"})
    stack_policy = StackPolicy.REFRESH

    __slots__ = ("obstacle_id", "ability_key", "kind", "cluster_ids", "rider")

    def __init__(self, duration: float = math.inf, obstacle_id: int = 0,
                 ability_key: str = "", kind: str = "", **kwargs) -> None:
        super().__init__(duration, **kwargs)
        self.obstacle_id = obstacle_id
        self.ability_key = ability_key
        self.kind = kind
        # The connected cluster of capsules the hero may move along, and an
        # optional companion status carrying per-hero riders (Kapre's on-hit
        # slow). Both are set by `server.bind` right after construction.
        self.cluster_ids: list[int] = []
        self.rider = None


class Split(Status):
    """Upper half detached from its body (Manananggal R).

    The body entity's id rides on the status so the recombine and death paths
    can find it without reaching into a free-form per-hero state dict.
    """

    status_id = "split"
    label = "Split"
    icon = "split"
    flags = frozenset({"split", "phase"})
    stack_policy = StackPolicy.IGNORE

    __slots__ = ("body_id",)

    def __init__(self, duration: float = math.inf, body_id: int = 0,
                 **kwargs) -> None:
        super().__init__(duration, **kwargs)
        self.body_id = body_id


class DamageAmplify(Status):
    """The bearer takes multiplied damage.

    Carried by the Manananggal's detached lower body, which is deliberately
    fragile. The damage pipeline used to check `isinstance(tgt, SplitBody)` and
    read a `dmg_mult` field off it; now the vulnerability belongs to the body as
    a status, and any future mechanic can reuse it.
    """

    status_id = "dmg_amplify"
    label = "Exposed"
    icon = "exposed"
    category = "debuff"
    default_hidden = True

    __slots__ = ("multiplier",)

    def __init__(self, duration: float = math.inf, multiplier: float = 2.0,
                 **kwargs) -> None:
        super().__init__(duration, **kwargs)
        self.multiplier = multiplier

    def on_damage_taken(self, bearer, event, state) -> None:
        event.amount *= self.multiplier


class Frenzy(Status):
    """Tiktik's empowered window: its abilities gain riders while this is up."""

    status_id = "frenzy"
    label = "Frenzy"
    icon = "frenzy"
    flags = frozenset({"frenzy"})


__all__ = ["Bound", "Split", "Frenzy", "DamageAmplify"]
