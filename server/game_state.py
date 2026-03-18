"""Master game state — single source of truth on the server."""

from __future__ import annotations

from shared.config import SPAWN_POSITIONS, HERO_BASE_HP, HERO_BASE_MANA, HERO_RADIUS
from shared.game_types import GamePhase, Team
from server.entity import Hero


class GameState:
    def __init__(self) -> None:
        self.phase: GamePhase = GamePhase.WAITING
        self.tick: int = 0
        self.entities: dict[int, Hero] = {}  # entity_id -> Entity
        self.player_heroes: dict[int, int] = {}  # client_id -> entity_id

    def add_hero(self, client_id: int, name: str, team: Team) -> Hero:
        spawn = SPAWN_POSITIONS[int(team)]
        hero = Hero(
            team=team,
            name=name,
            x=spawn[0],
            y=spawn[1],
            radius=HERO_RADIUS,
            hp=HERO_BASE_HP,
            max_hp=HERO_BASE_HP,
            mana=HERO_BASE_MANA,
            max_mana=HERO_BASE_MANA,
        )
        self.entities[hero.entity_id] = hero
        self.player_heroes[client_id] = hero.entity_id
        return hero

    def remove_hero(self, client_id: int) -> None:
        eid = self.player_heroes.pop(client_id, None)
        if eid is not None:
            self.entities.pop(eid, None)

    def get_hero(self, client_id: int) -> Hero | None:
        eid = self.player_heroes.get(client_id)
        if eid is None:
            return None
        return self.entities.get(eid)

    def build_snapshot(self) -> list[dict]:
        """Build a list of entity snapshots for broadcast."""
        return [e.to_snapshot() for e in self.entities.values()]

    def assign_team(self) -> Team:
        """Assign the team with fewer players."""
        t1 = sum(1 for e in self.entities.values() if e.team == Team.TEAM1)
        t2 = sum(1 for e in self.entities.values() if e.team == Team.TEAM2)
        return Team.TEAM1 if t1 <= t2 else Team.TEAM2
