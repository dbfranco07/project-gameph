"""Server-side entity classes. These hold the authoritative game state."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shared.game_types import EntityType, Team


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
    move_speed: float = 250.0
    # Movement target (None = standing still)
    target_x: float | None = None
    target_y: float | None = None

    # Future phases
    level: int = 1
    xp: int = 0
    gold: int = 0
    mana: int = 200
    max_mana: int = 200

    # Respawn
    respawn_timer: float = 0.0

    def move_toward_target(self, dt: float) -> None:
        if self.target_x is None or self.target_y is None:
            return
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy)
        if dist < 0.5:
            self.x = self.target_x
            self.y = self.target_y
            self.target_x = None
            self.target_y = None
            return
        step = min(self.move_speed * dt, dist)
        self.x += (dx / dist) * step
        self.y += (dy / dist) * step

    def to_snapshot(self) -> dict:
        d = super().to_snapshot()
        d["name"] = self.name
        d["lvl"] = self.level
        d["gold"] = self.gold
        d["mana"] = self.mana
        d["mmana"] = self.max_mana
        return d
