"""The stat modifier layer.

Every temporary numeric change to a unit — from a status, an item, a rune or an
aura — is a *modifier contribution* aggregated here, rather than a value summed
by hand at each read site.

Two problems this solves:

1. **Stacking policy lived in six places.** `slow_pct` was capped-additive,
   `cd_mult` was min-wins, `dmg_mult` was a product, `crit_chance` was
   capped-additive at 1.0, `evasion` capped at 0.95, `dmg_reduction` capped at
   0.8 — each hand-coded inside its own accessor on `Hero`. Now each stat
   declares its rule once in `STAT_SPECS` and `StatBlock` applies it uniformly.
2. **Every read was a scan.** Each of the ~30 `effective_*` / `bonus_*` methods
   ran `sum(b.get(key, 0) for b in self.buffs)` on every access, several times
   per entity per tick. `StatBlock` caches the aggregate behind a dirty flag, so
   a read is a dict lookup and the recompute happens once per mutation.

Base stats deliberately stay as plain dataclass fields on the entity (leveling
and permanent item bonuses write them directly). `StatBlock` owns only the
*temporary* layer, and `total()` combines the two under the stat's rule — which
is why caps are applied to base+bonus rather than to the bonus alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StackRule(Enum):
    """How multiple simultaneous modifiers to one stat combine."""

    ADD = "add"                # sum them            (dmg_bonus, phys_def, ...)
    MULT = "mult"              # multiply them       (dmg_mult)
    MIN_WINS = "min_wins"      # smallest wins       (cd_mult — best CDR applies)
    CAPPED_ADD = "capped_add"  # sum, clamped to cap (slow_pct, evasion, ...)
    MAX_WINS = "max_wins"      # largest single wins (attack_slow_pct)


# The identity element for each rule: the value `total()` returns when nothing
# is contributing, and the seed the aggregate folds from.
_IDENTITY = {
    StackRule.ADD: 0.0,
    StackRule.MULT: 1.0,
    StackRule.MIN_WINS: 1.0,
    StackRule.CAPPED_ADD: 0.0,
    StackRule.MAX_WINS: 0.0,
}


@dataclass(frozen=True)
class StatSpec:
    """Declares how one stat aggregates. `cap` applies to the combined
    base+bonus total, not to the bonus alone — a 0.6 base evasion plus a 0.5
    buff must clamp to 0.95, not reach 1.1."""

    name: str
    rule: StackRule
    cap: float | None = None


def _spec(name: str, rule: StackRule, cap: float | None = None) -> StatSpec:
    return StatSpec(name, rule, cap)


# Single source of truth. Adding a stat here is the *only* edit needed for the
# aggregation side of a new modifier — no new accessor, no new table.
STAT_SPECS: dict[str, StatSpec] = {
    s.name: s for s in (
        # --- flat additive stat gains -------------------------------------
        _spec("dmg_bonus", StackRule.ADD),
        _spec("sp_atk", StackRule.ADD),
        _spec("phys_def", StackRule.ADD),
        _spec("sp_def", StackRule.ADD),
        _spec("range_bonus", StackRule.ADD),
        _spec("speed_bonus", StackRule.ADD),
        _spec("atkspd_pct", StackRule.ADD),
        _spec("hp_regen_bonus", StackRule.ADD),
        _spec("mana_regen_bonus", StackRule.ADD),
        _spec("vision_bonus", StackRule.ADD),
        _spec("crit_mult", StackRule.ADD),
        _spec("lifesteal", StackRule.ADD),
        _spec("max_hp_bonus", StackRule.ADD),
        _spec("max_mana_bonus", StackRule.ADD),
        # --- capped fractions ---------------------------------------------
        # Never fully rooted by slows alone; hard CC is a separate flag.
        _spec("slow_pct", StackRule.CAPPED_ADD, cap=0.8),
        _spec("crit_chance", StackRule.CAPPED_ADD, cap=1.0),
        _spec("evasion", StackRule.CAPPED_ADD, cap=0.95),
        _spec("dmg_reduction", StackRule.CAPPED_ADD, cap=0.8),
        # --- multiplicative ------------------------------------------------
        _spec("dmg_mult", StackRule.MULT),
        # Best cooldown reduction wins rather than compounding to near-zero.
        _spec("cd_mult", StackRule.MIN_WINS),
        # --- strongest-wins riders -----------------------------------------
        _spec("attack_slow_pct", StackRule.MAX_WINS),
    )
}


def is_stat(key: str) -> bool:
    return key in STAT_SPECS


class UnknownStatError(KeyError):
    """Raised when a modifier names a stat that does not exist.

    The dict-based effects system silently accepted any keyword, so a typo was a
    no-op that failed quietly and was found only by noticing the buff did
    nothing in game. Modifiers are validated on the way in now.
    """


class StatBlock:
    """The temporary modifier layer for one entity.

    Contributions are keyed by an opaque `source` token (a `Status` instance, an
    item id) so they can be withdrawn again without disturbing anything else.
    Reads are served from a cache rebuilt only after a mutation.
    """

    __slots__ = ("_mods", "_agg", "_dirty")

    def __init__(self) -> None:
        # source token -> {stat key: value}
        self._mods: dict[object, dict[str, float]] = {}
        self._agg: dict[str, float] = {}
        self._dirty = True

    # ----- mutation ---------------------------------------------------------
    def add(self, source: object, mods: dict[str, float]) -> None:
        """Register (or replace) `source`'s contributions.

        Raises `UnknownStatError` if any key is not a declared stat — this is
        the check that turns a silent typo into an immediate, located failure.
        """
        if not mods:
            return
        for key in mods:
            if key not in STAT_SPECS:
                raise UnknownStatError(
                    f"unknown stat '{key}' (declare it in server/stats.STAT_SPECS)")
        self._mods[source] = dict(mods)
        self._dirty = True

    def remove(self, source: object) -> None:
        """Withdraw `source`'s contributions. Removing an absent source is a
        no-op, so expiry paths need not track whether they applied anything."""
        if self._mods.pop(source, None) is not None:
            self._dirty = True

    def clear(self) -> None:
        if self._mods:
            self._mods.clear()
            self._dirty = True

    def touch(self) -> None:
        """Force a recompute. For a source that mutates its own values in place
        (a draining shield pool) rather than being added and removed."""
        self._dirty = True

    # ----- reads ------------------------------------------------------------
    def _rebuild(self) -> None:
        agg: dict[str, float] = {}
        for mods in self._mods.values():
            for key, value in mods.items():
                spec = STAT_SPECS[key]
                rule = spec.rule
                if key not in agg:
                    agg[key] = _IDENTITY[rule]
                if rule is StackRule.ADD or rule is StackRule.CAPPED_ADD:
                    agg[key] += value
                elif rule is StackRule.MULT:
                    agg[key] *= value
                elif rule is StackRule.MIN_WINS:
                    agg[key] = min(agg[key], value)
                else:  # MAX_WINS
                    agg[key] = max(agg[key], value)
        self._agg = agg
        self._dirty = False

    def bonus(self, key: str) -> float:
        """The aggregated modifier contribution alone, without any base value.

        For MULT/MIN_WINS this is a multiplier (identity 1.0); for the additive
        rules it is a delta (identity 0.0). This is what the HUD's green/red
        temporary-delta row wants.
        """
        if self._dirty:
            self._rebuild()
        spec = STAT_SPECS.get(key)
        if spec is None:
            raise UnknownStatError(f"unknown stat '{key}'")
        return self._agg.get(key, _IDENTITY[spec.rule])

    def total(self, key: str, base: float = 0.0) -> float:
        """Combine `base` with the modifier aggregate under the stat's rule,
        applying the cap to the result."""
        spec = STAT_SPECS.get(key)
        if spec is None:
            raise UnknownStatError(f"unknown stat '{key}'")
        agg = self.bonus(key)
        rule = spec.rule
        if rule is StackRule.ADD:
            out = base + agg
        elif rule is StackRule.CAPPED_ADD:
            out = base + agg
        elif rule is StackRule.MULT:
            out = (base if base else 1.0) * agg
        elif rule is StackRule.MIN_WINS:
            out = min(base if base else 1.0, agg)
        else:  # MAX_WINS
            out = max(base, agg)
        if spec.cap is not None:
            out = min(spec.cap, out)
        return out

    def sources_for(self, key: str) -> list[object]:
        """Every source currently contributing to `key`. Used by riders that
        need a paired value (e.g. the duration alongside `attack_slow_pct`)."""
        return [src for src, mods in self._mods.items() if key in mods]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self._dirty:
            self._rebuild()
        return f"StatBlock({self._agg!r})"
