"""Game systems — plain functions called each server tick."""

from __future__ import annotations

from shared.config import MAP_WIDTH, MAP_HEIGHT
from server.game_state import GameState
from server.entity import Hero


def system_movement(state: GameState, dt: float) -> None:
    """Move all heroes toward their movement targets."""
    for entity in state.entities.values():
        if not entity.alive:
            continue
        if isinstance(entity, Hero):
            entity.move_toward_target(dt)
            # Clamp to map bounds
            entity.x = max(entity.radius, min(MAP_WIDTH - entity.radius, entity.x))
            entity.y = max(entity.radius, min(MAP_HEIGHT - entity.radius, entity.y))
