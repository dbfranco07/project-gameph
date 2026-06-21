"""Master game state — single source of truth on the server."""

from __future__ import annotations

import math

from shared.config import (
    SPAWN_POSITIONS,
    HERO_RADIUS,
    STARTING_GOLD,
    DEFAULT_KILL_TARGET,
    LANE_PATHS,
    LANE_TOWERS,
    CORE_HP,
    CORE_DAMAGE,
    CORE_RADIUS,
    CREEP_WAVE_INTERVAL,
    BASIC_PROJECTILE_SPEED,
    TOWER_PROJECTILE_SPEED,
    HERO_VISION_RADIUS,
    MINION_VISION_RADIUS,
    TOWER_VISION_RADIUS,
    WALLS,
    TREES,
    PREGAME_COUNTDOWN,
)
from shared.config import MAX_PLAYERS
from shared.geometry import point_along, segment_intersects_rect
from shared.game_types import GamePhase, Team, EntityType
from server.heroes import get_hero_def, DEFAULT_HERO, list_hero_ids, hero_catalog
from server.entity import Entity, Hero, Minion, Structure, Wall, Tree, Obstacle


def enemy_team(team: Team) -> Team:
    return Team.TEAM2 if team == Team.TEAM1 else Team.TEAM1


class GameState:
    def __init__(self) -> None:
        self.phase: GamePhase = GamePhase.WAITING
        self.tick: int = 0
        self.entities: dict[int, Entity] = {}  # entity_id -> Entity
        self.player_heroes: dict[int, int] = {}  # client_id -> entity_id
        self.player_hero_choice: dict[int, str] = {}  # client_id -> hero_id
        # Pre-game lobby: client_id -> {"name", "team", "is_host"}. Heroes are
        # not spawned until the host starts the match.
        self.lobby: dict[int, dict] = {}

        # Match / scoring
        self.kill_target: int = DEFAULT_KILL_TARGET
        self.team_kills: dict[Team, int] = {Team.TEAM1: 0, Team.TEAM2: 0}
        self.winner: Team | None = None

        # Per-tick queues processed by the systems pipeline
        self.damage_events: list[dict] = []   # {"src", "tgt", "amt"} or {"tgt","heal"}
        self.ability_casts: list[dict] = []    # {"caster", "key", "tx", "ty", "tid"}
        # One-shot reward popups for the client (gold/xp gained). Rebuilt each
        # tick; broadcast in the snapshot, filtered by team vision.
        self.combat_events: list[dict] = []   # {"k", "amt", "x", "y", "eid"}

        # Timers
        self.creep_timer: float = 0.0
        self.econ_accum: float = 0.0
        self.wave_count: int = 0

        # Jungle camps: camp_id -> {"timer": seconds until respawn or 0.0 if up}.
        self.neutral_camps: dict[int, dict] = {}
        # Runes: rune_index -> {"timer": seconds until respawn or 0.0 if up}.
        self.rune_state: dict[int, dict] = {}
        # Match clock: starts at +PREGAME_COUNTDOWN counting DOWN to 0 (when the
        # first wave + neutrals + runes appear), then counts UP as elapsed time.
        self.match_clock: float = 0.0

    # ----- Lobby ------------------------------------------------------------
    def add_to_lobby(self, client_id: int, name: str) -> dict:
        """Register a player in the pre-game lobby (no hero spawned yet).

        The first player to join becomes the host. New players land on whichever
        team currently has fewer lobby members.
        """
        is_host = not self.lobby
        team = self._balanced_lobby_team()
        self.lobby[client_id] = {"name": name, "team": int(team),
                                 "is_host": is_host}
        self.player_hero_choice.setdefault(client_id, DEFAULT_HERO)
        return self.lobby[client_id]

    def remove_from_lobby(self, client_id: int) -> None:
        was_host = self.lobby.get(client_id, {}).get("is_host", False)
        self.lobby.pop(client_id, None)
        # Promote the earliest remaining player if the host left.
        if was_host and self.lobby:
            first = next(iter(self.lobby))
            self.lobby[first]["is_host"] = True

    def _balanced_lobby_team(self) -> Team:
        t1 = sum(1 for p in self.lobby.values() if p["team"] == int(Team.TEAM1))
        t2 = sum(1 for p in self.lobby.values() if p["team"] == int(Team.TEAM2))
        return Team.TEAM1 if t1 <= t2 else Team.TEAM2

    def set_lobby_team(self, client_id: int, team: int) -> bool:
        """Move a lobby player to team 1/2 unless that side is full."""
        if client_id not in self.lobby or team not in (1, 2):
            return False
        cap = max(1, MAX_PLAYERS // 2)
        count = sum(1 for cid, p in self.lobby.items()
                    if cid != client_id and p["team"] == team)
        if count >= cap:
            return False
        self.lobby[client_id]["team"] = team
        return True

    def set_lobby_hero(self, client_id: int, hero_id: str) -> bool:
        if client_id not in self.lobby or hero_id not in list_hero_ids():
            return False
        self.player_hero_choice[client_id] = hero_id
        return True

    def is_host(self, client_id: int) -> bool:
        return self.lobby.get(client_id, {}).get("is_host", False)

    def lobby_roster(self) -> list[dict]:
        """Wire-friendly roster for the LOBBY_STATE broadcast."""
        return [
            {"cid": cid, "name": p["name"], "team": p["team"],
             "hero": self.player_hero_choice.get(cid, DEFAULT_HERO),
             "host": p["is_host"]}
            for cid, p in self.lobby.items()
        ]

    def available_heroes(self) -> list[dict]:
        """[{id, name}] for the lobby hero picker."""
        cat = hero_catalog()
        return [{"id": hid, "name": meta.get("name", hid)}
                for hid, meta in cat.items()]

    def spawn_from_lobby(self) -> None:
        """Create a hero for every lobby player on their chosen team/hero."""
        for cid, p in self.lobby.items():
            self.add_hero(cid, p["name"], Team(p["team"]),
                          hero_id=self.player_hero_choice.get(cid))

    # ----- Heroes -----------------------------------------------------------
    def set_hero_choice(self, client_id: int, hero_id: str) -> None:
        self.player_hero_choice[client_id] = hero_id

    def add_hero(self, client_id: int, name: str, team: Team,
                 hero_id: str | None = None) -> Hero:
        hero_id = hero_id or self.player_hero_choice.get(client_id)
        hdef = get_hero_def(hero_id)
        spawn = SPAWN_POSITIONS[int(team)]
        abilities = [ab.describe() for ab in hdef.abilities]
        hero = Hero(
            team=team,
            name=name,
            hero_id=hdef.hero_id,
            x=spawn[0],
            y=spawn[1],
            radius=HERO_RADIUS,
            hp=hdef.hp,
            max_hp=hdef.hp,
            mana=hdef.mana,
            max_mana=hdef.mana,
            move_speed=hdef.move_speed,
            attack_damage=hdef.atk_dmg,
            sp_atk=hdef.sp_atk,
            phys_def=hdef.phys_def,
            sp_def=hdef.sp_def,
            attack_range=hdef.atk_range,
            attack_interval=hdef.atk_interval,
            attack_type=hdef.atk_type,
            attack_proj_speed=BASIC_PROJECTILE_SPEED,
            gold=STARTING_GOLD,
            hp_regen=hdef.hp_regen,
            mana_regen=hdef.mana_regen,
            sp_atk_per_level=hdef.sp_atk_per_level,
            phys_def_per_level=hdef.phys_def_per_level,
            sp_def_per_level=hdef.sp_def_per_level,
            abilities=abilities,
            cooldowns={ab.key: 0.0 for ab in hdef.abilities},
            ability_levels={ab.key: 0 for ab in hdef.abilities},
            skill_points=1,  # one point granted at level 1
            hero_def=hdef,
        )
        self.entities[hero.entity_id] = hero
        self.player_heroes[client_id] = hero.entity_id
        return hero

    def remove_hero(self, client_id: int) -> None:
        eid = self.player_heroes.pop(client_id, None)
        if eid is not None:
            self.entities.pop(eid, None)
        self.player_hero_choice.pop(client_id, None)

    # Per-key rank caps and the hero-level gate for raising the ultimate.
    ULT_KEY = "R"
    ULT_RANK_CAP = 3
    BASIC_RANK_CAP = 4
    ULT_LEVEL_GATES = (4, 8, 12)  # hero level needed for R ranks 1/2/3

    def level_ability(self, client_id: int, key: str) -> bool:
        """Spend a skill point to raise an ability's rank, honoring caps and the
        ultimate's level gates. Returns True on success."""
        hero = self.get_hero(client_id)
        if hero is None or key not in hero.ability_levels:
            return False
        if hero.skill_points <= 0:
            return False
        cur = hero.ability_levels[key]
        cap = self.ULT_RANK_CAP if key == self.ULT_KEY else self.BASIC_RANK_CAP
        if cur >= cap:
            return False
        if key == self.ULT_KEY and hero.level < self.ULT_LEVEL_GATES[cur]:
            return False  # not high enough level for the next ultimate rank
        hero.ability_levels[key] = cur + 1
        hero.skill_points -= 1
        return True

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
        self.wave_count = 0
        self.neutral_camps = {}
        self.rune_state = {}
        # Negative clock = pre-game countdown; it ticks up to 0 (spawns) then on.
        self.match_clock = -PREGAME_COUNTDOWN
        self._spawn_structures()
        self._spawn_map()
        self.phase = GamePhase.PLAYING

    def _spawn_structures(self) -> None:
        # Lane towers: three per lane per team, positioned along each lane
        # polyline by arc-length fraction.
        for team_int, towers in LANE_TOWERS.items():
            team = Team(team_int)
            for lane in LANE_PATHS:
                path = LANE_PATHS[lane]
                for lane_order, t, _kind in towers:
                    x, y = point_along(path, t)
                    struct = Structure(
                        team=team,
                        x=x,
                        y=y,
                        lane_order=lane_order,
                        lane=lane,
                        attack_proj_speed=TOWER_PROJECTILE_SPEED,
                    )
                    self.entities[struct.entity_id] = struct
        # One core per team at its base corner.
        for team_int, (cx, cy) in SPAWN_POSITIONS.items():
            team = Team(team_int)
            core = Structure(
                team=team,
                x=cx,
                y=cy,
                lane_order=99,
                is_core=True,
                hp=CORE_HP,
                max_hp=CORE_HP,
                attack_damage=CORE_DAMAGE,
                radius=CORE_RADIUS,
                entity_type=EntityType.BASE,
                attack_proj_speed=TOWER_PROJECTILE_SPEED,
            )
            self.entities[core.entity_id] = core

    def _spawn_map(self) -> None:
        """Spawn static obstacles (walls + destructible trees) from the config."""
        for (x, y, w, h) in WALLS:
            wall = Wall(x=x, y=y, w=w, h=h,
                        radius=math.hypot(w, h) / 2)
            self.entities[wall.entity_id] = wall
        for (x, y, w, h) in TREES:
            tree = Tree(x=x, y=y, w=w, h=h,
                        radius=math.hypot(w, h) / 2)
            self.entities[tree.entity_id] = tree

    def obstacle_rects(self) -> list[tuple[float, float, float, float]]:
        """Rects that block walking (walls + alive trees)."""
        return [e.rect() for e in self.entities.values()
                if isinstance(e, Obstacle) and e.alive]

    def vision_blocker_rects(self) -> list[tuple[float, float, float, float]]:
        """Rects that block line-of-sight (walls + alive trees)."""
        return [e.rect() for e in self.entities.values()
                if isinstance(e, Obstacle) and e.alive and e.blocks_vision]

    def lane_cleared(self, team: Team, lane: str) -> bool:
        """True if every one of `team`'s towers in `lane` has been destroyed."""
        for e in self.entities.values():
            if (isinstance(e, Structure) and e.team == team
                    and e.lane == lane and e.alive):
                return False
        return True

    def core_exposed(self, team: Team) -> bool:
        """A team's core is attackable once any one of its lanes is fully cleared."""
        return any(self.lane_cleared(team, lane) for lane in LANE_PATHS)

    def is_structure_vulnerable(self, struct: Structure) -> bool:
        """Lane towers fall outer -> inner -> base within their own lane. The
        core is attackable only once some lane is fully cleared."""
        if struct.is_core:
            return self.core_exposed(struct.team)
        for e in self.entities.values():
            if (
                isinstance(e, Structure)
                and e.team == struct.team
                and e.lane == struct.lane
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

    # ----- Snapshot / vision ------------------------------------------------
    def build_snapshot(self) -> list[dict]:
        """Build a list of entity snapshots for broadcast (no fog)."""
        return [e.to_snapshot() for e in self.entities.values()]

    def _vision_sources(self, team: Team):
        """Yield (x, y, radius) for each alive vision-granting unit of `team`."""
        for e in self.entities.values():
            if not e.alive or e.team != team:
                continue
            if isinstance(e, Hero):
                yield e.x, e.y, HERO_VISION_RADIUS
            elif isinstance(e, Minion):
                yield e.x, e.y, MINION_VISION_RADIUS
            elif isinstance(e, Structure):
                yield e.x, e.y, TOWER_VISION_RADIUS

    def visible_entity_ids_for(self, team: Team) -> set[int]:
        """Ids visible to `team`: own units + all static map features, plus
        enemy/neutral units within unobstructed line-of-sight of one of the
        team's vision sources (walls and alive trees block the sight line)."""
        sources = list(self._vision_sources(team))
        blockers = self.vision_blocker_rects()
        visible: set[int] = set()
        for e in self.entities.values():
            # Own units + static map features (structures, walls, trees) are
            # always sent so the client can draw the world.
            if e.team == team or isinstance(e, (Structure, Obstacle)):
                visible.add(e.entity_id)
                continue
            for sx, sy, r in sources:
                if math.hypot(e.x - sx, e.y - sy) > r + e.radius:
                    continue
                if any(segment_intersects_rect(sx, sy, e.x, e.y, rect)
                       for rect in blockers):
                    continue  # sight line is blocked by a wall/tree
                visible.add(e.entity_id)
                break
        return visible

    def build_snapshot_for(self, team: Team) -> list[dict]:
        """Fog-of-war snapshot: only entities `team` can currently see."""
        visible = self.visible_entity_ids_for(team)
        return [e.to_snapshot() for e in self.entities.values()
                if e.entity_id in visible]

    def assign_team(self) -> Team:
        """Assign the team with fewer heroes."""
        t1 = sum(1 for e in self.heroes() if e.team == Team.TEAM1)
        t2 = sum(1 for e in self.heroes() if e.team == Team.TEAM2)
        return Team.TEAM1 if t1 <= t2 else Team.TEAM2
