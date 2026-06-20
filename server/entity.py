"""Server-side entity classes. These hold the authoritative game state."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shared.game_types import EntityType, Team
from shared.config import (
    MINION_HP,
    MINION_DAMAGE,
    MINION_RANGE,
    MINION_INTERVAL,
    MINION_SPEED,
    MINION_RADIUS,
    TOWER_HP,
    TOWER_DAMAGE,
    TOWER_RANGE,
    TOWER_INTERVAL,
    TOWER_RADIUS,
    XP_BASE,
    XP_PER_LEVEL,
    MAX_LEVEL,
)


_next_id = 0


def _gen_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id


@dataclass
class Entity:
    entity_id: int = field(default_factory=_gen_id)
    entity_type: EntityType = EntityType.HERO
    team: Team = Team.NONE
    x: float = 0.0
    y: float = 0.0
    radius: float = 20.0
    hp: int = 600
    max_hp: int = 600
    alive: bool = True

    # Combat (attack_damage == 0 means this entity does not auto-attack)
    attack_damage: int = 0
    attack_range: float = 0.0
    attack_interval: float = 1.0
    attack_timer: float = 0.0  # seconds remaining until next attack is ready
    attack_type: str = "melee"  # "melee" = instant hit, "ranged" = fires a projectile
    attack_proj_speed: float = 1000.0

    def distance_to(self, other: Entity) -> float:
        """Euclidean distance to another entity."""
        return math.hypot(self.x - other.x, self.y - other.y)

    def to_snapshot(self) -> dict:
        """Minimal data sent to clients each tick."""
        return {
            "id": self.entity_id,
            "et": int(self.entity_type),
            "tm": int(self.team),
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "hp": self.hp,
            "mhp": self.max_hp,
            "r": self.radius,
            "a": self.alive,
        }


@dataclass
class Hero(Entity):
    entity_type: EntityType = EntityType.HERO
    name: str = ""
    hero_id: str = ""  # which hero definition this is
    move_speed: float = 250.0
    attack_damage: int = 55
    attack_range: float = 160.0
    attack_interval: float = 1.0
    attack_type: str = "melee"
    # Movement target (None = standing still)
    target_x: float | None = None
    target_y: float | None = None
    # Focus target from an "A + click enemy" command (chase + attack this entity)
    forced_target_id: int | None = None

    # Progression
    level: int = 1
    xp: int = 0
    gold: int = 0
    mana: int = 200
    max_mana: int = 200

    # Regeneration (per second). Defaults overridden from the hero definition.
    hp_regen: float = 0.0
    mana_regen: float = 5.0
    # Fractional carry so slow regen accrues correctly across ticks.
    regen_hp_acc: float = 0.0
    regen_mana_acc: float = 0.0

    # Abilities: loadout (list of metadata dicts) + per-key cooldown remaining.
    # `hero_def` is the HeroDef subclass holding the actual cast code.
    abilities: list[dict] = field(default_factory=list)
    cooldowns: dict[str, float] = field(default_factory=dict)
    hero_def: object | None = None

    # Temporary buffs: list of {speed_bonus, dmg_bonus, remaining}
    buffs: list[dict] = field(default_factory=list)

    # Inventory: list of item_id strings + per-slot active cooldown remaining.
    inventory: list[str] = field(default_factory=list)
    item_cooldowns: dict[str, float] = field(default_factory=dict)

    # Respawn
    respawn_timer: float = 0.0

    def ability_by_key(self, key: str) -> dict | None:
        for ab in self.abilities:
            if ab.get("key") == key:
                return ab
        return None

    def is_stunned(self) -> bool:
        return any(b.get("stun") for b in self.buffs)

    def bonus_speed(self) -> float:
        return sum(b.get("speed_bonus", 0) for b in self.buffs)

    def bonus_damage(self) -> int:
        return int(sum(b.get("dmg_bonus", 0) for b in self.buffs))

    def effective_damage(self) -> int:
        return self.attack_damage + self.bonus_damage()

    def move_toward_target(self, dt: float) -> None:
        if self.target_x is None or self.target_y is None:
            return
        speed = self.move_speed + self.bonus_speed()
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy)
        if dist < 0.5:
            self.x = self.target_x
            self.y = self.target_y
            self.target_x = None
            self.target_y = None
            return
        step = min(speed * dt, dist)
        self.x += (dx / dist) * step
        self.y += (dy / dist) * step

    def to_snapshot(self) -> dict:
        d = super().to_snapshot()
        d["name"] = self.name
        d["hid"] = self.hero_id
        d["lvl"] = self.level
        d["gold"] = self.gold
        d["mana"] = self.mana
        d["mmana"] = self.max_mana
        d["resp"] = round(self.respawn_timer, 1)
        # Extra stats for the HUD panel.
        d["ad"] = self.effective_damage()
        d["ms"] = int(self.move_speed + self.bonus_speed())
        d["xp"] = self.xp
        d["xpn"] = 0 if self.level >= MAX_LEVEL else XP_BASE + (self.level - 1) * XP_PER_LEVEL
        # Ability cooldown state for the owning client's HUD.
        d["cds"] = {k: round(v, 1) for k, v in self.cooldowns.items()}
        d["inv"] = list(self.inventory)
        d["icds"] = {k: round(v, 1) for k, v in self.item_cooldowns.items()}
        return d


@dataclass
class Minion(Entity):
    entity_type: EntityType = EntityType.MINION
    radius: float = MINION_RADIUS
    hp: int = MINION_HP
    max_hp: int = MINION_HP
    attack_damage: int = MINION_DAMAGE
    attack_range: float = MINION_RANGE
    attack_interval: float = MINION_INTERVAL
    move_speed: float = MINION_SPEED
    # Lane destination (enemy core position)
    dest_x: float = 0.0
    dest_y: float = 0.0

    def advance(self, dt: float) -> None:
        """Walk toward the lane destination (called when no enemy is in range)."""
        dx = self.dest_x - self.x
        dy = self.dest_y - self.y
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            return
        step = min(self.move_speed * dt, dist)
        self.x += (dx / dist) * step
        self.y += (dy / dist) * step


@dataclass
class Structure(Entity):
    """A tower or core. lane_order: outer=0, inner=1, core=2."""

    entity_type: EntityType = EntityType.TOWER
    radius: float = TOWER_RADIUS
    hp: int = TOWER_HP
    max_hp: int = TOWER_HP
    attack_damage: int = TOWER_DAMAGE
    attack_range: float = TOWER_RANGE
    attack_interval: float = TOWER_INTERVAL
    attack_type: str = "ranged"
    lane_order: int = 0
    is_core: bool = False

    def to_snapshot(self) -> dict:
        d = super().to_snapshot()
        d["core"] = self.is_core
        return d


@dataclass
class Projectile(Entity):
    entity_type: EntityType = EntityType.PROJECTILE
    radius: float = 18.0
    hp: int = 1
    max_hp: int = 1
    # Velocity (units/sec) and remaining travel distance.
    vx: float = 0.0
    vy: float = 0.0
    damage: int = 0
    owner_id: int = 0
    range_left: float = 0.0
    # Homing basic-attack projectiles steer toward a specific target each tick.
    homing: bool = False
    target_id: int = 0
    speed: float = 0.0
    is_basic: bool = False  # basic attack (team-colored) vs ability (bright)

    def to_snapshot(self) -> dict:
        d = super().to_snapshot()
        d["b"] = self.is_basic
        return d
