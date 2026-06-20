"""Foundation for code-driven heroes.

Each hero is its own Python class (one file per hero in this package) subclassing
`HeroDef`. Stats are class attributes; each ability is a method tagged with the
`@ability(...)` decorator whose body is plain Python that composes the reusable
building blocks in `server/skills.py`. This is the "every hero is unique code"
design: a hero can blink *and* stun, fire a piercing projectile, etc., just by
writing the method body — no central data table to thread parameters through.

Only ability **metadata** (key/name/cooldown/mana/cast-type) crosses the wire to
the client via `describe()`; the cast **code** stays server-side.
"""

from __future__ import annotations

from shared.config import (
    HERO_MOVE_SPEED, MANA_REGEN_PER_SEC, HERO_HP_REGEN_PER_SEC)
from shared.game_types import CastType


class CastContext:
    """Everything an ability body needs when it fires.

    `caster` is the live `Hero` entity (runtime state), not the `HeroDef` class.
    `tx`/`ty` is the targeted world point; `tid` is the targeted entity id (if
    the ability is unit-targeted). Skill helpers in `server/skills.py` take one
    of these and mutate `state`.
    """

    __slots__ = ("state", "caster", "tx", "ty", "tid")

    def __init__(self, state, caster, tx: float, ty: float, tid: int | None) -> None:
        self.state = state
        self.caster = caster
        self.tx = tx
        self.ty = ty
        self.tid = tid


class Ability:
    """A single ability: its gameplay metadata + the function that casts it."""

    def __init__(self, key: str, name: str, cd: float, mana: int,
                 cast: CastType, fn) -> None:
        self.key = key
        self.name = name
        self.cd = cd
        self.mana = mana
        self.cast_type = cast
        self.fn = fn  # plain function taking a single CastContext argument

    def describe(self) -> dict:
        """UI-agnostic metadata sent to the client (no cast code)."""
        return {
            "key": self.key,
            "name": self.name,
            "cd": self.cd,
            "mana": self.mana,
            "cast": int(self.cast_type),
        }


def ability(key: str, name: str, cd: float, mana: int,
            cast: CastType = CastType.POINT):
    """Decorator tagging a `HeroDef` method as an ability.

    The decorated method takes a single `CastContext` (`ctx`). It is collected
    into `cls.abilities` by `HeroDef.__init_subclass__` in definition order, so
    declare abilities Q, W, E, R top-to-bottom.
    """

    def deco(fn):
        fn._ability_meta = (key, name, cd, mana, cast)
        return fn

    return deco


class HeroDef:
    """Base class for a hero definition. Subclass it, one file per hero."""

    hero_id: str = ""
    name: str = ""

    # Base stats (override per hero)
    hp: int = 600
    mana: int = 200
    move_speed: float = HERO_MOVE_SPEED
    atk_dmg: int = 55
    atk_range: float = 160.0
    atk_interval: float = 1.0
    atk_type: str = "melee"        # "melee" (instant) or "ranged" (projectile)
    hp_regen: float = HERO_HP_REGEN_PER_SEC  # hp per second (slow passive)
    mana_regen: float = MANA_REGEN_PER_SEC

    # Populated by __init_subclass__ from decorated methods.
    abilities: list[Ability] = []

    # Optional lifecycle hooks (override in a hero as @staticmethod):
    #   on_ability_cast(ctx, key) -> called after any active ability this hero
    #       casts (drives "on skill use" passives).
    #   on_tick(state, hero, dt)  -> called every simulation tick for stateful
    #       heroes (e.g. the Manananggal split: leash + auto-recombine).
    on_ability_cast = None
    on_tick = None

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        collected: list[Ability] = []
        # cls.__dict__ preserves definition order (Python 3.7+).
        for value in cls.__dict__.values():
            meta = getattr(value, "_ability_meta", None)
            if meta is None:
                continue
            key, name, cd, mana, cast = meta
            collected.append(Ability(key, name, cd, mana, cast, value))
        cls.abilities = collected
        cls._validate()

    # ----- Lookup / wire ----------------------------------------------------
    @classmethod
    def ability(cls, key: str) -> Ability | None:
        for ab in cls.abilities:
            if ab.key == key:
                return ab
        return None

    @classmethod
    def describe(cls) -> dict:
        """Plain dict of stats + ability metadata for the client / wire."""
        return {
            "hero_id": cls.hero_id,
            "name": cls.name,
            "hp": cls.hp,
            "mana": cls.mana,
            "move_speed": cls.move_speed,
            "atk_dmg": cls.atk_dmg,
            "atk_range": cls.atk_range,
            "atk_interval": cls.atk_interval,
            "atk_type": cls.atk_type,
            "abilities": [ab.describe() for ab in cls.abilities],
        }

    # ----- Validation (runs at class-definition / import time) --------------
    @classmethod
    def _validate(cls) -> None:
        if not cls.hero_id:
            raise ValueError(f"{cls.__name__} must set hero_id")
        if not cls.name:
            raise ValueError(f"hero '{cls.hero_id}' must set name")
        if cls.atk_type not in ("melee", "ranged"):
            raise ValueError(
                f"hero '{cls.hero_id}' has invalid atk_type '{cls.atk_type}'")
        seen: set[str] = set()
        for ab in cls.abilities:
            if ab.key in seen:
                raise ValueError(
                    f"hero '{cls.hero_id}' has duplicate ability key '{ab.key}'")
            seen.add(ab.key)
