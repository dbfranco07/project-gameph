"""The status (buff / debuff) system.

A status is an object, not a dict. It owns its own identity, HUD presentation,
stacking policy, stat modifiers, boolean flags, and — the part dicts could never
express — **lifecycle hooks**. A shield that absorbs damage, a rune buff that
drops when you are hit, an item that procs on kill, and a passive that toggles
with terrain are all ordinary subclasses here rather than special cases wired
into the combat systems.

The previous design stored effects as `list[dict]` and reconstructed meaning by
inspecting keys: four hand-maintained tables in `effects.py` classified an
effect as buff or debuff, named it, and picked its icon, while the systems
pipeline carried explicit branches for the handful of effects that needed to
*do* something. Statuses answer all of that themselves.

Duration is in seconds; `math.inf` means "until explicitly removed", which is
what auras and toggled abilities use.
"""

from __future__ import annotations

import itertools
import math
from enum import Enum

from server.stats import STAT_SPECS, StatBlock, UnknownStatError


class StackPolicy(Enum):
    """What happens when a status is applied to a bearer that already has one
    with the same `status_id`."""

    REFRESH = "refresh"    # keep one, extend to the longer remaining duration
    STACK = "stack"        # accumulate stacks, modifiers scale with count
    IGNORE = "ignore"      # the existing one stands; the new application is lost
    STRONGEST = "strongest"  # keep whichever has the larger magnitude


# Boolean states a status can assert. Unlike stat modifiers these do not
# aggregate — presence is what matters — so the container keeps a reference
# count per flag and answers `has()` in O(1) instead of scanning a list.
FLAGS = frozenset({
    # --- crowd control ---
    "stun",        # cannot move, attack or cast
    "silence",     # cannot cast abilities
    "disarm",      # cannot auto-attack (may still move and cast)
    # --- defensive ---
    "invuln",      # takes no damage
    # --- movement / terrain ---
    "phase",       # ignores wall and tree collision
    # --- stealth and vision ---
    "invisible",           # hidden from enemies (allies still see)
    "unobstructed_vision",  # this unit's sight ignores line-of-sight blockers
    # --- combat riders ---
    "true_strike",      # this unit's basic attacks ignore enemy evasion
    "guaranteed_crit",  # every eligible hit crits
    "cancel_on_hit",    # this status drops when its bearer takes damage
    # --- shared hero mechanics ---
    # Boolean markers that more than one system or hero has to agree on. They
    # were undocumented ad-hoc keys in the dict system; naming them here makes
    # the set of "things a status can assert" closed and checkable.
    "bind",    # lodged inside terrain (Kapre R, Tiktik W)
    "split",   # upper half detached from its body (Manananggal R)
    "frenzy",  # Tiktik's empowered window
})


_anon_counter = itertools.count()


def _anon_source(status_id: str) -> str:
    """A unique source tag for a status applied without one."""
    return f"{status_id}#{next(_anon_counter)}"


class Status:
    """Base class for a buff or debuff. Subclass it; one concept per class.

    Class attributes are the defaults; anything passed to `__init__` overrides
    them per instance (so a single `Slow` class covers a 20% and a 60% slow).
    """

    # --- identity ---
    status_id: str = ""
    label: str = ""            # short HUD text
    icon: str = ""             # stable art id, so sprites can be swapped in later
    category: str = "buff"     # "buff" or "debuff" — drives HUD colouring

    # --- stacking ---
    stack_policy: StackPolicy = StackPolicy.REFRESH
    max_stacks: int = 1

    #: Survives `clear()` — i.e. is not stripped by death. Equipped items and
    #: their passives are the reason this exists: they are a property of the
    #: hero's inventory, not a temporary effect that dying should remove.
    persistent: bool = False

    # --- presentation ---
    # Subclasses set `default_hidden`, not `hidden`: the latter is a slot below
    # so individual instances can be hidden, and a subclass class attribute of
    # the same name would shadow the slot descriptor and make it read-only.
    default_hidden: bool = False

    # --- payload ---
    # Declared as class defaults; copied per instance so mutation is safe.
    modifiers: dict[str, float] = {}
    flags: frozenset[str] = frozenset()

    # Set by a status whose modifier *values* change while it stays attached
    # (e.g. a passive that scales with its ability's rank). The container then
    # re-pushes its payload when the numbers actually move, instead of assuming
    # they were fixed at application time.
    dynamic: bool = False

    __slots__ = ("remaining", "duration", "source", "stacks", "hidden",
                 "_modifiers", "_flags", "_bearer", "_applied", "_last_mods")

    def __init__(self, duration: float = math.inf, source: str | None = None,
                 stacks: int = 1, modifiers: dict[str, float] | None = None,
                 flags: frozenset[str] | None = None,
                 hidden: bool | None = None, **overrides) -> None:
        self.duration = duration
        self.remaining = duration
        # An unsourced status is independent: two slows from two different
        # abilities must stack toward the cap rather than one refreshing the
        # other. Stacking policy is scoped to a *source* (see `dedupe_key`), so
        # anonymous effects get a unique one.
        self.source = source if source is not None else _anon_source(self.status_id)
        self.stacks = stacks
        self.hidden = type(self).default_hidden if hidden is None else hidden
        self._bearer = None
        self._applied = False  # are our modifiers currently in the StatBlock?
        self._last_mods: dict[str, float] | None = None

        # Per-instance payload, seeded from the class defaults.
        mods = dict(self.modifiers)
        if modifiers:
            mods.update(modifiers)
        # Bare keyword overrides are a convenience for one-off statuses:
        # `Slow(2.0, slow_pct=0.3)` rather than `Slow(2.0, {"slow_pct": 0.3})`.
        for key, value in overrides.items():
            if key not in STAT_SPECS:
                raise UnknownStatError(
                    f"{type(self).__name__} got unknown stat '{key}' "
                    f"(declare it in server/stats.STAT_SPECS)")
            mods[key] = value
        self._modifiers = mods
        self._flags = frozenset(flags) if flags is not None else self.flags
        _validate_flags(self._flags, type(self).__name__)

    # ----- payload views ----------------------------------------------------
    @property
    def active_modifiers(self) -> dict[str, float]:
        """Modifiers as currently contributed, scaled by stack count."""
        if self.stacks == 1:
            return self._modifiers
        return {k: v * self.stacks for k, v in self._modifiers.items()}

    @property
    def active_flags(self) -> frozenset[str]:
        return self._flags

    @property
    def dedupe_key(self) -> tuple[str, str]:
        """What the stacking policy is scoped to.

        Refreshing, ignoring and strongest-wins all compare a new application
        against the *same effect from the same source*. Two different abilities
        that both slow are independent and stack toward the cap; casting one of
        them twice refreshes it.
        """
        return (self.status_id, self.source)

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    @property
    def magnitude(self) -> float:
        """Rough strength, used by `StackPolicy.STRONGEST` to pick a winner."""
        return sum(abs(v) for v in self._modifiers.values())

    def is_active(self, bearer, state) -> bool:
        """Whether the payload should currently apply. Always true for a plain
        status; `Aura` overrides this with a condition."""
        return True

    # ----- lifecycle hooks (override as needed) -----------------------------
    def on_apply(self, bearer, state) -> None:
        """Called once when the status first attaches to `bearer`."""

    def on_expire(self, bearer, state) -> None:
        """Called once when the status is removed, by timeout or explicitly."""

    def on_tick(self, bearer, state, dt: float) -> None:
        """Called every simulation tick while attached. Damage-over-time,
        leashing and periodic pulses live here."""

    def on_damage_taken(self, bearer, event, state) -> None:
        """Called as the bearer is about to take damage, during the shield stage
        of the damage pipeline. Mutate `event.amount` to mitigate."""

    def on_hit_dealt(self, bearer, victim, amount: int, state) -> None:
        """Called after the bearer deals damage. On-hit procs live here."""

    def on_kill(self, bearer, victim, state) -> None:
        """Called when the bearer lands a killing blow."""

    # ----- HUD --------------------------------------------------------------
    def describe(self) -> dict | None:
        """Summary for the HUD effect row, or None to stay hidden.

        Wire shape is unchanged from the old `effects.describe_effect` so the
        renderer needs no edit: label, category, icon id, and remaining/original
        duration for the timer ring.
        """
        if self.hidden or self.remaining <= 0:
            return None
        # An endless status has no meaningful ring; show it as full.
        rem = self.remaining if math.isfinite(self.remaining) else 1.0
        dur = self.duration if math.isfinite(self.duration) else 1.0
        d = {
            "lbl": self.label or self.status_id[:6].title(),
            "cat": self.category,
            "icon": self.icon or self.status_id,
            "rem": round(rem, 1),
            "dur": round(dur or rem, 1),
        }
        if self.stacks > 1:
            d["n"] = self.stacks
        return d

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        rem = "inf" if math.isinf(self.remaining) else f"{self.remaining:.2f}"
        n = f" x{self.stacks}" if self.stacks > 1 else ""
        return f"<{type(self).__name__}{n} rem={rem}>"


class Aura(Status):
    """A status whose payload switches on and off with a condition.

    Eight heroes previously emulated a conditional passive by stripping their
    own tagged effect out of `hero.buffs` and appending a freshly allocated
    0.5-second replacement *every tick*, forever. An `Aura` is attached once and
    simply toggles: no per-tick allocation, no flicker, and the HUD sees a stable
    effect instead of one that is constantly torn down and rebuilt.
    """

    default_hidden = True  # conditional passives are ambient, not timed pickups
    stack_policy = StackPolicy.IGNORE

    __slots__ = ()

    def __init__(self, duration: float = math.inf, **kwargs) -> None:
        super().__init__(duration, **kwargs)

    def condition(self, bearer, state) -> bool:
        """Override: whether the aura's payload currently applies."""
        return True

    def is_active(self, bearer, state) -> bool:
        return self.condition(bearer, state)


def _validate_flags(flags, owner: str) -> None:
    unknown = set(flags) - FLAGS
    if unknown:
        raise ValueError(
            f"{owner} declares unknown status flag(s) {sorted(unknown)}; "
            f"add them to server.status.base.FLAGS")


class StatusContainer:
    """Every status attached to one entity.

    Keeps three indices so the hot paths are all O(1): a reference count per
    flag (`is_stunned` was a list scan on every movement and cast check), a map
    by `status_id`, and a map by `source` tag for the strip-and-reapply patterns.
    """

    __slots__ = ("_statuses", "_flag_counts", "_by_id", "_by_key",
                 "_stats", "_owner")

    def __init__(self, stats: StatBlock, owner=None) -> None:
        self._statuses: list[Status] = []
        self._flag_counts: dict[str, int] = {}
        self._by_id: dict[str, list[Status]] = {}
        # Stacking is resolved against (status_id, source) — see `dedupe_key`.
        self._by_key: dict[tuple[str, str], Status] = {}
        self._stats = stats
        self._owner = owner

    # ----- queries ----------------------------------------------------------
    def has(self, flag: str) -> bool:
        """O(1) flag test."""
        return self._flag_counts.get(flag, 0) > 0

    def get(self, status_id: str) -> Status | None:
        found = self._by_id.get(status_id)
        return found[0] if found else None

    def all_of(self, status_id: str) -> list[Status]:
        return list(self._by_id.get(status_id, ()))

    def by_source(self, source: str) -> list[Status]:
        return [s for s in self._statuses if s.source == source]

    def __iter__(self):
        return iter(self._statuses)

    def __len__(self) -> int:
        return len(self._statuses)

    def __bool__(self) -> bool:
        return bool(self._statuses)

    # ----- mutation ---------------------------------------------------------
    def add(self, status: Status, state=None) -> Status | None:
        """Attach `status`, honouring its stacking policy.

        Returns the status that ended up attached (which may be a pre-existing
        one that was refreshed or stacked instead), or None if the application
        was discarded by `IGNORE`.
        """
        bearer = self._owner
        current = self._by_key.get(status.dedupe_key)
        if current is not None:
            policy = status.stack_policy
            if policy is StackPolicy.IGNORE:
                return None
            if policy is StackPolicy.REFRESH:
                # Never shorten an effect by re-applying a weaker instance.
                current.remaining = max(current.remaining, status.remaining)
                current.duration = max(current.duration, status.duration)
                return current
            if policy is StackPolicy.STACK:
                if current.stacks < current.max_stacks:
                    current.stacks += 1
                    self._refresh_modifiers(current, state)
                current.remaining = max(current.remaining, status.remaining)
                return current
            if policy is StackPolicy.STRONGEST:
                if status.magnitude <= current.magnitude:
                    current.remaining = max(current.remaining, status.remaining)
                    return current
                self.remove(current, state)

        status._bearer = bearer
        self._statuses.append(status)
        self._by_id.setdefault(status.status_id, []).append(status)
        self._by_key[status.dedupe_key] = status
        for flag in status.active_flags:
            self._flag_counts[flag] = self._flag_counts.get(flag, 0) + 1
        self._apply_payload(status, state)
        status.on_apply(bearer, state)
        return status

    def remove(self, status: Status, state=None) -> None:
        """Detach `status`, firing `on_expire`. A no-op if already detached."""
        try:
            self._statuses.remove(status)
        except ValueError:
            return
        bucket = self._by_id.get(status.status_id)
        if bucket:
            if status in bucket:
                bucket.remove(status)
            if not bucket:
                del self._by_id[status.status_id]
        if self._by_key.get(status.dedupe_key) is status:
            del self._by_key[status.dedupe_key]
        for flag in status.active_flags:
            count = self._flag_counts.get(flag, 0) - 1
            if count > 0:
                self._flag_counts[flag] = count
            else:
                self._flag_counts.pop(flag, None)
        self._stats.remove(status)
        status._applied = False
        status.on_expire(self._owner, state)
        status._bearer = None

    def remove_id(self, status_id: str, state=None) -> None:
        for status in self.all_of(status_id):
            self.remove(status, state)

    def remove_source(self, source: str, state=None) -> None:
        for status in self.by_source(source):
            self.remove(status, state)

    def clear(self, state=None, keep_persistent: bool = True) -> None:
        """Drop every non-persistent status (death). Hooks still fire so nothing
        leaks. Equipped items are `persistent` and survive — dying costs you
        your buffs, not your inventory."""
        for status in list(self._statuses):
            if keep_persistent and status.persistent:
                continue
            self.remove(status, state)

    # ----- per-tick ---------------------------------------------------------
    def tick(self, dt: float, state=None) -> None:
        """Advance durations, re-evaluate auras, fire `on_tick`, drop expired."""
        if not self._statuses:
            return
        bearer = self._owner
        expired: list[Status] = []
        for status in self._statuses:
            if math.isfinite(status.remaining):
                status.remaining -= dt
                if status.remaining <= 0:
                    expired.append(status)
                    continue
            # An aura's payload follows its condition without re-allocating.
            self._apply_payload(status, state)
            status.on_tick(bearer, state, dt)
        for status in expired:
            self.remove(status, state)

    # ----- damage pipeline participation ------------------------------------
    def on_damage_taken(self, event, state=None) -> None:
        bearer = self._owner
        for status in list(self._statuses):
            status.on_damage_taken(bearer, event, state)

    def on_hit_dealt(self, victim, amount: int, state=None) -> None:
        bearer = self._owner
        for status in list(self._statuses):
            status.on_hit_dealt(bearer, victim, amount, state)

    def on_kill(self, victim, state=None) -> None:
        bearer = self._owner
        for status in list(self._statuses):
            status.on_kill(bearer, victim, state)

    # ----- internals --------------------------------------------------------
    def _apply_payload(self, status: Status, state) -> None:
        """Sync the status' modifiers into the StatBlock, honouring `is_active`.

        Only touches the block when the active state actually changes, so a
        steady aura costs one boolean check per tick rather than a rebuild.
        """
        mods = status.active_modifiers
        should = bool(mods) and status.is_active(self._owner, state)
        if should:
            # A steady status costs one boolean check per tick; a dynamic one
            # additionally compares its numbers and re-pushes only on a change.
            if not status._applied:
                self._stats.add(status, mods)
                status._applied = True
                status._last_mods = dict(mods)
            elif status.dynamic and mods != status._last_mods:
                self._stats.add(status, mods)
                status._last_mods = dict(mods)
        elif status._applied:
            self._stats.remove(status)
            status._applied = False
            status._last_mods = None

    def _refresh_modifiers(self, status: Status, state) -> None:
        """Re-push a status' modifiers after its stack count changed."""
        if status._applied:
            self._stats.add(status, status.active_modifiers)
