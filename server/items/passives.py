"""Unique item passives.

Each is an ordinary `Status`, so it participates in the damage pipeline through
the same hooks heroes and buffs use. That is the whole payoff of the status
rewrite: an on-hit slow, a stacking-on-kill bonus and a damage-reflect need no
new machinery in the combat systems — they are three small classes here.

Passives are granted endlessly while the item is equipped and withdrawn when it
is sold, so none of them manage their own lifetime.
"""

from __future__ import annotations

from server.status.base import StackPolicy, Status
from server.status.library import Slow


class ChillingTouch(Status):
    """On-hit: slow whatever you damage."""

    status_id = "item:chill"
    label = "Chill"
    icon = "attack_slow"
    default_hidden = True
    persistent = True

    SLOW_PCT = 0.25
    SLOW_DUR = 1.2

    __slots__ = ()

    def on_hit_dealt(self, bearer, victim, amount, state) -> None:
        statuses = getattr(victim, "statuses", None)
        if statuses is not None:
            statuses.add(Slow(self.SLOW_DUR, self.SLOW_PCT,
                              source=self.status_id), state)


class Bloodthirst(Status):
    """On-kill: a stacking attack-damage bonus that decays on death.

    Stacks are held on this status rather than on the hero, so they vanish with
    the item automatically when it is sold.
    """

    status_id = "item:bloodthirst"
    label = "Bloodthirst"
    icon = "bloodthirst"
    default_hidden = False
    persistent = True
    stack_policy = StackPolicy.IGNORE
    dynamic = True

    DMG_PER_STACK = 6
    MAX_KILL_STACKS = 10

    __slots__ = ("kills",)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.kills = 0

    @property
    def active_modifiers(self) -> dict:
        return {"dmg_bonus": self.DMG_PER_STACK * self.kills} if self.kills else {}

    def describe(self) -> dict | None:
        d = super().describe()
        if d is not None and self.kills:
            d["n"] = self.kills
        return d

    def on_kill(self, bearer, victim, state) -> None:
        from server.entity import Hero
        # Only real kills count — farming lane creeps would trivialise it.
        if isinstance(victim, Hero):
            self.kills = min(self.MAX_KILL_STACKS, self.kills + 1)

    def on_tick(self, bearer, state, dt) -> None:
        # Stacks are lost on death (the status itself persists with the item).
        if not bearer.alive and self.kills:
            self.kills = 0

    def on_expire(self, bearer, state) -> None:
        self.kills = 0


class Thorns(Status):
    """Reflect a fraction of incoming damage back at the attacker.

    Reflected damage is queued as a normal damage event rather than applied
    directly, so it goes through the pipeline (armor, shields, death handling)
    like any other hit — and cannot recurse, because it is not a basic attack
    and the reflector is the source.
    """

    status_id = "item:thorns"
    label = "Thorns"
    icon = "thorns"
    default_hidden = True
    persistent = True

    REFLECT = 0.18

    __slots__ = ()

    def on_damage_taken(self, bearer, event, state) -> None:
        attacker = getattr(event, "source", None)
        if attacker is None or state is None or event.amount <= 0:
            return
        if attacker is bearer or not getattr(attacker, "alive", False):
            return
        # Reflect off the *incoming* amount, as true damage so the loop cannot
        # be amplified by the attacker's own defenses being ignored twice.
        state.damage_events.append({
            "src": bearer.entity_id, "tgt": attacker.entity_id,
            "amt": int(event.amount * self.REFLECT), "dtype": "true"})


class SecondWind(Status):
    """Once per life, survive a lethal blow at a sliver of health."""

    status_id = "item:second_wind"
    label = "2nd Wind"
    icon = "second_wind"
    persistent = True

    SURVIVE_HP = 1

    __slots__ = ("spent",)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.spent = False

    def on_damage_taken(self, bearer, event, state) -> None:
        if self.spent or event.amount < bearer.hp:
            return
        self.spent = True
        # Leave exactly enough to survive; the apply stage subtracts the rest.
        event.amount = max(0, bearer.hp - self.SURVIVE_HP)

    def on_tick(self, bearer, state, dt) -> None:
        # Recharges on death, so it is once per life rather than once per game.
        if not bearer.alive and self.spent:
            self.spent = False

    def on_expire(self, bearer, state) -> None:
        self.spent = False


__all__ = ["ChillingTouch", "Bloodthirst", "Thorns", "SecondWind"]
