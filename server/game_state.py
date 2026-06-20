"""Master game state — single source of truth on the server."""

from __future__ import annotations

from shared.config import (
    SPAWN_POSITIONS,
    LANE_Y,
    HERO_RADIUS,
    HERO_MOVE_SPEED,
    DEFAULT_KILL_TARGET,
    STRUCTURES,
    CORE_HP,
    CORE_DAMAGE,
    CORE_RADIUS,
    CREEP_WAVE_INTERVAL,
    BASIC_PROJECTILE_SPEED,
    TOWER_PROJECTILE_SPEED,
)
from shared.game_types import GamePhase, Team, EntityType
from shared.hero_schema import get_hero_def
from server.entity import Entity, Hero, Structure


def enemy_team(team: Team) -> Team:
    return Team.TEAM2 if team == Team.TEAM1 else Team.TEAM1


class GameState:
    def __init__(self) -> None:
        self.phase: GamePhase = GamePhase.WAITING
        self.tick: int = 0
        self.entities: dict[int, Entity] = {}  # entity_id -> Entity
        self.player_heroes: dict[int, int] = {}  # client_id -> entity_id
        self.player_hero_choice: dict[int, str] = {}  # client_id -> hero_id

        # Match / scoring
        self.kill_target: int = DEFAULT_KILL_TARGET
        self.team_kills: dict[Team, int] = {Team.TEAM1: 0, Team.TEAM2: 0}
        self.winner: Team | None = None

        # Per-tick queues processed by the systems pipeline
        self.damage_events: list[dict] = []   # {"src", "tgt", "amt"} or {"tgt","heal"}
        self.ability_casts: list[dict] = []    # {"caster", "key", "tx", "ty", "tid"}

        # Timers
        self.creep_timer: float = 0.0
        self.econ_accum: float = 0.0

    # ----- Heroes -----------------------------------------------------------
    def set_hero_choice(self, client_id: int, hero_id: str) -> None:
        self.player_hero_choice[client_id] = hero_id

    def add_hero(self, client_id: int, name: str, team: Team,
                 hero_id: str | None = None) -> Hero:
        hero_id = hero_id or self.player_hero_choice.get(client_id)
        hdef = get_hero_def(hero_id)
        spawn = SPAWN_POSITIONS[int(team)]
        abilities = [dict(a) for a in hdef.get("abilities", [])]
        hero = Hero(
            team=team,
            name=name,
            hero_id=hero_id or hdef["name"].lower(),
            x=spawn[0],
            y=spawn[1],
            radius=HERO_RADIUS,
            hp=hdef["hp"],
            max_hp=hdef["hp"],
            mana=hdef["mana"],
            max_mana=hdef["mana"],
            move_speed=hdef.get("move_speed", HERO_MOVE_SPEED),
            attack_damage=hdef["atk_dmg"],
            attack_range=hdef["atk_range"],
            attack_interval=hdef["atk_interval"],
            attack_type=hdef.get("atk_type", "melee"),
            attack_proj_speed=BASIC_PROJECTILE_SPEED,
            abilities=abilities,
            cooldowns={a["key"]: 0.0 for a in abilities},
        )
        self.entities[hero.entity_id] = hero
        self.player_heroes[client_id] = hero.entity_id
        return hero

    def remove_hero(self, client_id: int) -> None:
        eid = self.player_heroes.pop(client_id, None)
        if eid is not None:
            self.entities.pop(eid, None)
        self.player_hero_choice.pop(client_id, None)

    def get_hero(self, client_id: int) -> Hero | None:
        eid = self.player_heroes.get(client_id)
        if eid is None:
            return None
        ent = self.entities.get(eid)
        return ent if isinstance(ent, Hero) else None

    def heroes(self) -> list[Hero]:
        return [e for e in self.entities.values() if isinstance(e, Hero)]

    # ----- Match lifecycle --------------------------------------------------
    def start_match(self, kill_target: int | None = None) -> None:
        """Transition WAITING -> PLAYING and spawn the lane structures."""
        if kill_target is not None:
            self.kill_target = max(1, int(kill_target))
        self.team_kills = {Team.TEAM1: 0, Team.TEAM2: 0}
        self.winner = None
        self.creep_timer = 0.0
        self.econ_accum = 0.0
        self._spawn_structures()
        self.phase = GamePhase.PLAYING

    def _spawn_structures(self) -> None:
        for team_int, layout in STRUCTURES.items():
            team = Team(team_int)
            for lane_order, x, kind in layout:
                is_core = kind == "core"
                struct = Structure(
                    team=team,
                    x=x,
                    y=LANE_Y,
                    lane_order=lane_order,
                    is_core=is_core,
                    attack_proj_speed=TOWER_PROJECTILE_SPEED,
                )
                if is_core:
                    struct.hp = struct.max_hp = CORE_HP
                    struct.attack_damage = CORE_DAMAGE
                    struct.radius = CORE_RADIUS
                    struct.entity_type = EntityType.BASE
                self.entities[struct.entity_id] = struct

    def is_structure_vulnerable(self, struct: Structure) -> bool:
        """A structure can only be damaged once all more-outer same-team
        structures are destroyed (outer -> inner -> core)."""
        for e in self.entities.values():
            if (
                isinstance(e, Structure)
                and e.team == struct.team
                and e.alive
                and e.lane_order < struct.lane_order
            ):
                return False
        return True

    def core_of(self, team: Team) -> Structure | None:
        for e in self.entities.values():
            if isinstance(e, Structure) and e.is_core and e.team == team:
                return e
        return None

    # ----- Snapshot ---------------------------------------------------------
    def build_snapshot(self) -> list[dict]:
        """Build a list of entity snapshots for broadcast."""
        return [e.to_snapshot() for e in self.entities.values()]

    def assign_team(self) -> Team:
        """Assign the team with fewer heroes."""
        t1 = sum(1 for e in self.heroes() if e.team == Team.TEAM1)
        t2 = sum(1 for e in self.heroes() if e.team == Team.TEAM2)
        return Team.TEAM1 if t1 <= t2 else Team.TEAM2
