"""The standard status catalog.

Everything the old dict-based effects vocabulary could express, as classes. A
hero, item or system applies these instead of hand-building a dict, which means
the label, icon, buff/debuff category and stacking behaviour travel *with* the
effect rather than being reverse-engineered from its keys by a lookup table.
"""

from __future__ import annotations

from server.status.base import Aura, StackPolicy, Status


# ---------------------------------------------------------------------------
# Crowd control
# ---------------------------------------------------------------------------

class Stun(Status):
    """Cannot move, attack or cast. Implies silence and disarm — those are
    derived at the read sites rather than duplicated as flags here."""

    status_id = "stun"
    label = "Stun"
    icon = "stun"
    category = "debuff"
    flags = frozenset({"stun"})
    # A second stun should not shorten the first, nor compound into a chain.
    stack_policy = StackPolicy.REFRESH


class Silence(Status):
    status_id = "silence"
    label = "Silence"
    icon = "silence"
    category = "debuff"
    flags = frozenset({"silence"})


class Disarm(Status):
    status_id = "disarm"
    label = "Disarm"
    icon = "disarm"
    category = "debuff"
    flags = frozenset({"disarm"})


class Slow(Status):
    """Movement slow. Multiple slows stack additively but clamp at the
    `slow_pct` cap in `STAT_SPECS`, so a unit is never fully rooted by slows."""

    status_id = "slow"
    label = "Slow"
    icon = "slow"
    category = "debuff"

    def __init__(self, duration: float, pct: float = 0.3, **kwargs) -> None:
        kwargs.setdefault("slow_pct", pct)
        super().__init__(duration, **kwargs)


# ---------------------------------------------------------------------------
# Defensive
# ---------------------------------------------------------------------------

class Invulnerable(Status):
    status_id = "invuln"
    label = "Invuln"
    icon = "invuln"
    flags = frozenset({"invuln"})


class Shield(Status):
    """An absorb pool that soaks incoming damage before it reaches HP.

    The pool is mutable instance state and drains through `on_damage_taken`.
    Previously this was a `shield` number inside an effect dict that the damage
    system reached in and decremented, then swept the buff list for emptied
    entries — the mitigation logic lived in the combat code rather than in the
    effect.
    """

    status_id = "shield"
    label = "Shield"
    icon = "shield"
    stack_policy = StackPolicy.STRONGEST

    __slots__ = ("pool", "initial")

    def __init__(self, duration: float, amount: float, **kwargs) -> None:
        super().__init__(duration, **kwargs)
        self.pool = float(amount)
        self.initial = float(amount)

    @property
    def magnitude(self) -> float:
        return self.pool

    def on_damage_taken(self, bearer, event, state) -> None:
        if self.pool <= 0 or event.amount <= 0:
            return
        used = min(self.pool, event.amount)
        self.pool -= used
        event.amount -= used
        event.absorbed += used
        if self.pool <= 0:
            # Spent shields disappear immediately rather than lingering as an
            # empty entry on the HUD.
            self.remaining = 0.0


class DamageReduction(Status):
    status_id = "dmg_reduction"
    label = "Armor"
    icon = "reduce"

    def __init__(self, duration: float, pct: float, **kwargs) -> None:
        kwargs.setdefault("dmg_reduction", pct)
        super().__init__(duration, **kwargs)


# ---------------------------------------------------------------------------
# Movement / terrain / stealth
# ---------------------------------------------------------------------------

class Phased(Status):
    """Ignores wall and tree collision."""

    status_id = "phase"
    label = "Phase"
    icon = "phase"
    flags = frozenset({"phase"})


class Invisible(Status):
    """Hidden from enemies; allies still see. Attacking briefly reveals the
    bearer via `Hero.reveal_timer`, which the vision code checks separately."""

    status_id = "invisible"
    label = "Invis"
    icon = "invisible"
    flags = frozenset({"invisible"})


class TrueSight(Status):
    """This unit's sight ignores wall/tree line-of-sight blockers."""

    status_id = "unobstructed_vision"
    label = "Sight"
    icon = "sight"
    flags = frozenset({"unobstructed_vision"})


# ---------------------------------------------------------------------------
# Generic stat buff / debuff
# ---------------------------------------------------------------------------

class StatBuff(Status):
    """A plain bundle of stat modifiers with no special behaviour.

    The catch-all replacing `make_effect(...)` for effects that only move
    numbers. Its HUD category is inferred from the sign of its modifiers, which
    is the one piece of the old dict classification worth keeping — a +15
    phys_def is a buff and a -15 is a debuff, and a single class covers both.
    """

    # NB: `status_id` is deliberately *not* set as a class variable here — it
    # lives in __slots__ below (each instance gets its own id derived from its
    # source), and Python rejects a name that is both.

    # Preferred labels when a caller does not supply one, most-specific first.
    _LABELS = (
        ("dmg_bonus", "ATK", "dmg"),
        ("sp_atk", "SP", "sp_atk"),
        ("phys_def", "DEF", "def"),
        ("sp_def", "SPDEF", "sp_def"),
        ("speed_bonus", "MS", "speed"),
        ("atkspd_pct", "AS", "atkspd"),
        ("range_bonus", "RNG", "range"),
        ("crit_chance", "Crit", "crit"),
        ("lifesteal", "Life", "lifesteal"),
        ("evasion", "Dodge", "evasion"),
        ("hp_regen_bonus", "Regen", "regen"),
    )

    # Subclasses name themselves through these rather than by overriding
    # `label`/`icon` directly: those are slots here, and a subclass class
    # attribute of the same name would shadow the slot descriptor and make the
    # assignment in __init__ fail with "attribute is read-only".
    default_label: str = ""
    default_icon: str = ""

    # These shadow the class attributes of the same name on `Status`: resolved
    # once in __init__ rather than on every HUD read.
    __slots__ = ("status_id", "label", "icon", "category")

    def __init__(self, duration: float, source: str | None = None,
                 label: str = "", icon: str = "", category: str = "",
                 **kwargs) -> None:
        # Set before super().__init__, which reads `self.status_id` to default
        # the source. A distinct id per source keeps unrelated stat buffs from
        # refreshing or displacing one another under one shared identity.
        self.status_id = f"statbuff:{source}" if source else "statbuff"
        super().__init__(duration, source=source, **kwargs)
        cls = type(self)
        # Precedence: explicit argument, then the subclass' declared default
        # (how the rune buffs below name themselves), then inference.
        self.label = label or cls.default_label or self._derive_label()
        self.icon = icon or cls.default_icon or self._derive_icon()
        self.category = category or self._derive_category()

    def _derive_label(self) -> str:
        for key, lbl, _icon in self._LABELS:
            if self._modifiers.get(key):
                return lbl
        tag = (self.source or "").split(":")[-1]
        return tag[:6].title() if tag else "Buff"

    def _derive_icon(self) -> str:
        for key, _lbl, icon in self._LABELS:
            if self._modifiers.get(key):
                return icon
        return (self.source or "buff").split(":")[-1]

    def _derive_category(self) -> str:
        # Sign decides: a +15 phys_def is a buff, a -15 is a debuff.
        if self._modifiers.get("slow_pct"):
            return "debuff"
        if any(v < 0 for v in self._modifiers.values()):
            return "debuff"
        return "buff"


# ---------------------------------------------------------------------------
# On-hit riders
# ---------------------------------------------------------------------------

class AttackSlow(Status):
    """The bearer's auto-attacks apply a movement slow to whatever they hit.

    Previously the combat system read a `(pct, duration)` pair off the bearer's
    buff list and applied the slow itself. As a hook the rider carries its own
    effect, so the combat system no longer knows this mechanic exists.
    """

    status_id = "attack_slow"
    label = "Chill"
    icon = "attack_slow"

    __slots__ = ("slow_pct_on_hit", "slow_duration")

    def __init__(self, duration: float, pct: float = 0.3,
                 slow_duration: float = 1.0, **kwargs) -> None:
        super().__init__(duration, **kwargs)
        self.slow_pct_on_hit = pct
        self.slow_duration = slow_duration

    def on_hit_dealt(self, bearer, victim, amount, state) -> None:
        statuses = getattr(victim, "statuses", None)
        if statuses is not None:
            statuses.add(Slow(self.slow_duration, self.slow_pct_on_hit), state)


class Lifesteal(Status):
    status_id = "lifesteal"
    label = "Life"
    icon = "lifesteal"

    def __init__(self, duration: float, pct: float, **kwargs) -> None:
        kwargs.setdefault("lifesteal", pct)
        super().__init__(duration, **kwargs)


# ---------------------------------------------------------------------------
# Rune buffs
# ---------------------------------------------------------------------------
# Runes were a hardcoded if/elif catalog inside `systems.apply_rune_buff`.
# Each drop is now a status, and the rune system just looks one up by name.

class RuneHaste(StatBuff):
    __slots__ = ()
    default_label = "Haste"
    default_icon = "haste"


class RuneDoubleDamage(StatBuff):
    __slots__ = ()
    default_label = "2x Dmg"
    default_icon = "double_damage"


class RuneCooldown(StatBuff):
    __slots__ = ()
    default_label = "CDR"
    default_icon = "cdr_50"


class RuneRegen(StatBuff):
    """10x regen that fizzles the moment the bearer takes damage.

    `cancel_on_hit` used to be an undocumented key the damage system special-
    cased; here the status simply ends itself in its own damage hook.
    """

    __slots__ = ()
    default_label = "Regen"
    default_icon = "regen_10x"

    def on_damage_taken(self, bearer, event, state) -> None:
        if event.amount > 0:
            self.remaining = 0.0


__all__ = [
    "Stun", "Silence", "Disarm", "Slow",
    "Invulnerable", "Shield", "DamageReduction",
    "Phased", "Invisible", "TrueSight",
    "StatBuff", "AttackSlow", "Lifesteal",
    "RuneHaste", "RuneDoubleDamage", "RuneCooldown", "RuneRegen",
    "Aura", "Status", "StackPolicy",
]
