"""Master game state — single source of truth on the server."""

from __future__ import annotations

import math

from shared.config import (
    SPAWN_POSITIONS,
    CORE_POSITIONS,
    HERO_RADIUS,
    STARTING_GOLD,
    DEFAULT_KILL_TARGET,
    LANE_PATHS,
    LANE_TOWERS,
    CORE_HP,
    CORE_DAMAGE,
    CORE_RADIUS,
    BASIC_PROJECTILE_SPEED,
    TOWER_PROJECTILE_SPEED,
    HERO_VISION_RADIUS,
    MINION_VISION_RADIUS,
    TOWER_VISION_RADIUS,
    WALLS,
    TREES,
    RIVER,
    PREGAME_COUNTDOWN,
    GRID_CELL,
    GRID_MARGIN
)
from shared.config import MAX_PLAYERS
from shared.geometry import point_along, segment_capsule_intersect
from shared.game_types import GamePhase, Team, EntityType
from server.heroes import get_hero_def, DEFAULT_HERO, list_hero_ids, hero_catalog
from server.entity import (
    Entity, Hero, Minion, Projectile, Structure, Wall, Tree, Obstacle)


def enemy_team(team: Team) -> Team:
    return Team.TEAM2 if team == Team.TEAM1 else Team.TEAM1


class GameState:
    """Holds information about the lobby, heroes, per-tick spatial index, match 
    lifecycle, and snapshot/vision.

    The game state also holds the phase of the game, the tick count, entities in
    the game, mapping of the client ID to the hero ID.
    
    The server's single source of truth on the game world."""

    def __init__(self) -> None:
        self.phase: GamePhase = GamePhase.WAITING
        self.tick: int = 0

        # Sandbox / hero-testing mode: when True the server accepts chat
        # slash-commands (/gold, /level, ...) that mutate the caller's hero
        # Enabled with the server's --sandbox flag; off by default.
        self.sandbox: bool = False

        # Contains all entities in the game, keyed by entity_id. Includes 
        # heroes, minions, etc. Structures are also entities, but they are not 
        # mobile and do not have a client_id.  
        # entity_id -> Entity
        self.entities: dict[int, Entity] = {}

        # Maps client IDs to the entity ID of the hero they control. This allows 
        # the server to quickly look up player's hero based on their client ID.
        # client_id -> entity_id
        self.player_heroes: dict[int, int] = {}

        # Heroes parked for a reconnecting player, by player name. See
        # `remove_hero(keep_for_reconnect=...)`.
        # player name -> entity_id
        self.disconnected: dict[str, int] = {} 

        # Maps client IDs to the hero ID they have chosen in the lobby. This is 
        # used to determine which hero to spawn when the match starts.
        # client_id -> hero_id
        self.player_hero_choice: dict[int, str] = {} 

        # Pre-game lobby: client_id -> {"name", "team", "is_host"}. Heroes are
        # not spawned until the host starts the match.
        self.lobby: dict[int, dict[str, str | int | bool]] = {}

        # Match / scoring
        self.kill_target: int = DEFAULT_KILL_TARGET
        self.team_kills: dict[Team, int] = {Team.TEAM1: 0, Team.TEAM2: 0}
        self.winner: Team | None = None

        # Per-tick queues processed by the systems pipeline
        # src means source; tgt means target
        # {"src", "tgt", "amt"} or {"tgt","heal"}
        self.damage_events: list[dict] = []
        # {"caster", "key", "tx", "ty", "tid"}
        self.ability_casts: list[dict] = []

        # Active pulls/displacements: {"tgt", "to", "speed", "stop"}. A unit is
        # dragged toward another (e.g. Tiktik's hook) until within `stop`.
        self.pulls: list[dict] = []

        # One-shot reward popups for the client (gold/xp gained). Rebuilt each
        # tick; broadcast in the snapshot, filtered by team vision.
        self.combat_events: list[dict] = []   # {"k", "amt", "x", "y", "eid"}

        # Timers
        self.creep_timer: float = 0.0
        # Accumulated gold for the next wave, which is distributed to all heroes
        self.econ_accum: float = 0.0
        # Number of waves spawned so far. Used to scale creep stats and gold.
        self.wave_count: int = 0

        # Per-tick memoized team-visibility sets for in-tick targeting (see
        # visible_ids_cached). The snapshot broadcast computes fresh sets.
        self._vis_cache: dict[Team, set[int]] = {}

        # The vision cache is keyed on a simulation epoch rather than `tick`,
        # because the server increments `tick` between running the systems and
        # broadcasting. Keyed on tick, the broadcast always missed and every
        # team's line-of-sight was computed twice per frame — and it is the most
        # expensive query in the game.
        self._vis_epoch: int = 0
        self._vis_cache_epoch: int = -1

        # Per-tick spatial index (see rebuild_spatial_index). Empty until the
        # first tick; `nearby()` then simply returns the structure list.
        self._grid: dict[tuple[int, int], list] = {}
        self._grid_structures: list = []
        self._grid_tick: int = -1


        # Jungle camps: camp_id -> {"timer": seconds until respawn or 0.0 if up}.
        self.neutral_camps: dict[int, dict[str, float]] = {}

        # Runes: rune_index -> {"timer": seconds until respawn or 0.0 if up}.
        self.rune_state: dict[int, dict[str, float]] = {}

        # Match clock: starts at +PREGAME_COUNTDOWN counting DOWN to 0 (when the
        # first wave + neutrals + runes appear), then counts UP as elapsed time.
        self.match_clock: float = 0.0

    # --------------------------------------------------------------------------
    # Lobby
    # --------------------------------------------------------------------------
    def add_to_lobby(self, client_id: int, 
                     name: str) -> dict[str, str | int | bool]:
        """Register a player in the pre-game lobby (no hero spawned yet).

        The first player to join becomes the host. New players land on whichever
        team currently has fewer lobby members.
        """
        is_host = not self.lobby
        team = self._balanced_lobby_team()
        self.lobby[client_id] = {"name": name, 
                                 "team": int(team),
                                 "is_host": is_host}
        self.player_hero_choice.setdefault(client_id, DEFAULT_HERO)
        return self.lobby[client_id]

    def remove_from_lobby(self, client_id: int) -> None:
        """Remove a player from the lobby. If they were the host, promote the
        earliest remaining player to host."""
        was_host = self.lobby.get(client_id, {}).get("is_host", False)
        self.lobby.pop(client_id, None)
        # Promote the earliest remaining player if the host left.
        if was_host and self.lobby:
            next_first_player = next(iter(self.lobby))
            self.lobby[next_first_player]["is_host"] = True

    def _balanced_lobby_team(self) -> Team:
        """Gives the team that has fewer players."""
        t1 = sum(1 for p in self.lobby.values() if p["team"] == int(Team.TEAM1))
        t2 = sum(1 for p in self.lobby.values() if p["team"] == int(Team.TEAM2))
        return Team.TEAM1 if t1 <= t2 else Team.TEAM2

    def set_lobby_team(self, client_id: int, team: int) -> bool:
        """Move a lobby player to team 1/2 unless that side is full.
        Returns True if success, otherwise False."""
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
        """Sets the hero choice for a lobby player.
        Returns True if success, otherwise False."""
        if client_id not in self.lobby or hero_id not in list_hero_ids():
            return False
        self.player_hero_choice[client_id] = hero_id
        return True

    def is_host(self, client_id: int) -> bool:
        """Returns True if the given client is the lobby host."""
        return self.lobby.get(client_id, {}).get("is_host", False)

    def lobby_roster(self) -> list[dict[str, str | int | bool]]:
        """Wire-friendly roster for the LOBBY_STATE broadcast."""
        return [
            {"cid": cid, # client id
             "name": p["name"], 
             "team": p["team"],
             "hero": self.player_hero_choice.get(cid, DEFAULT_HERO),
             "host": p["is_host"]}
            for cid, p in self.lobby.items()
        ]

    def available_heroes(self) -> list[dict[str, str]]:
        """[{id, name}] for the lobby hero picker."""
        cat = hero_catalog()
        return [{"id": hid, 
                 "name": meta.get("name", hid)}
                for hid, meta in cat.items()]

    def spawn_from_lobby(self) -> None:
        """Create a hero for every lobby player on their chosen team/hero."""
        for cid, p in self.lobby.items():
            self.add_hero(cid, 
                          p["name"], 
                          Team(p["team"]),
                          hero_id=self.player_hero_choice.get(cid))

    # --------------------------------------------------------------------------
    # Heroes
    # --------------------------------------------------------------------------
    def set_hero_choice(self, client_id: int, hero_id: str) -> None:
        """Sets the hero for the given client."""
        self.player_hero_choice[client_id] = hero_id

    def add_hero(self, client_id: int, name: str, team: Team,
                 hero_id: str | None = None) -> Hero:
        """Defines the hero"""
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
            crit_chance=hdef.crit_chance,
            crit_mult=hdef.crit_mult,
            lifesteal=hdef.lifesteal,
            evasion=hdef.evasion,
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

    def remove_hero(self, client_id: int, keep_for_reconnect: str = "") -> None:
        """Detach a player's hero.

        With `keep_for_reconnect` set to the player's name during a live match,
        the hero entity stays in the world and is parked so the same player can
        reclaim it. Previously a dropped connection deleted the hero outright,
        so a few seconds of bad wifi cost you your level, gold and items and
        handed you a fresh level-1 hero on rejoin.
        """
        eid = self.player_heroes.pop(client_id, None)
        if eid is None:
            self.player_hero_choice.pop(client_id, None)
            return
        if keep_for_reconnect and self.phase == GamePhase.PLAYING:
            hero = self.entities.get(eid)
            if hero is not None:
                self.disconnected[keep_for_reconnect] = eid
                # Park it: no lingering move order to walk it into a tower.
                hero.target_x = hero.target_y = None
                hero.attack_move = False
                hero.attack_move_x = hero.attack_move_y = None
                hero.forced_target_id = None
                return
        self.entities.pop(eid, None)
        self.player_hero_choice.pop(client_id, None)

    def reclaim_hero(self, client_id: int, name: str) -> Hero | None:
        """Rebind a parked hero to a reconnecting player, or None if there is
        no hero waiting under that name."""
        eid = self.disconnected.pop(name, None)
        if eid is None:
            return None
        hero = self.entities.get(eid)
        if hero is None:
            return None
        self.player_heroes[client_id] = eid
        return hero

    def level_ability(self, client_id: int, key: str) -> bool:
        """Spend a skill point to raise an ability's rank, honoring caps and the
        ultimate's level gates. Returns True on success.

        Rank caps and which key is "the ultimate" both come from the hero
        definition (per-ability ``max_rank`` + ``ult_key``/``ult_level_gates``),
        so non-standard kits work: a normal hero ults on "R" (cap 3, gates
        4/8/12), while e.g. Pedro Penduko ults on "I" and his "R" is an ordinary
        skill."""
        hero = self.get_hero(client_id)

        if hero is None or key not in hero.ability_levels:
            return False
        
        if hero.skill_points <= 0:
            return False
        
        hdef = hero.hero_def
        adef = hdef.ability(key) if hdef is not None else None
        if adef is None:
            return False
        
        cur = hero.ability_levels[key]
        if cur >= adef.max_rank:
            return False
        
        ult_key = getattr(hdef, "ult_key", "R")
        if key == ult_key:
            gates = getattr(hdef, "ult_level_gates", (4, 8, 12))
            if cur < len(gates) and hero.level < gates[cur]:
                return False  # not high enough level for the next ultimate rank
            
        hero.ability_levels[key] = cur + 1
        hero.skill_points -= 1
        return True

    def get_hero(self, client_id: int) -> Hero | None:
        """Return the Hero entity for the given client, or None if not found."""
        eid = self.player_heroes.get(client_id)
        if eid is None:
            return None
        ent = self.entities.get(eid)
        return ent if isinstance(ent, Hero) else None

    def heroes(self) -> list[Hero]:
        """Return a list of all Hero entities in the game."""
        return [e for e in self.entities.values() if isinstance(e, Hero)]

    # --------------------------------------------------------------------------
    # Per-tick spatial index
    # --------------------------------------------------------------------------
    #: Grid cell size. Comfortably larger than any attack range, so a query
    #: touches a small, bounded number of cells.
    # GRID_CELL = 512
    #: Slack added to every query radius. The index is built once at the top of
    #: the tick, but units keep moving through it, and an entity's own radius
    #: counts toward "in range". Generous enough that the grid can only ever
    #: return a superset — callers still do the exact distance test.
    # GRID_MARGIN = 200.0
    # NOTE: values for GRID_CELL and GRID_MARGIN are now in config/game.yaml

    def rebuild_spatial_index(self) -> None:
        """Bucket mobile entities by grid cell for the coming tick.

        `find_attack_target` was the single most expensive thing in the
        simulation — roughly a third of all time — because every attacker
        scanned every entity, every tick. Structures are kept in a separate flat
        list rather than the grid: there are only a couple of dozen, they never
        move, and their radii are large enough that gridding them would just
        spread each one over many cells.
        """
        grid: dict[tuple[int, int], list] = {}
        structures: list = []
        cell = GRID_CELL
        self._grid_tick = self.tick
        for e in self.entities.values():
            if not e.alive:
                continue
            if isinstance(e, Structure):
                structures.append(e)
                continue
            if isinstance(e, (Projectile, Obstacle)):
                # never auto-attack targets
                continue 
            grid.setdefault((int(e.x // cell), int(e.y // cell)), []).append(e)
        self._grid = grid
        self._grid_structures = structures

    def nearby(self, x: float, y: float, radius: float,
               include_structures: bool = True) -> list:
        """Candidate entities near a point: a superset of what is truly in
        range, cheap to produce. Callers apply their own exact test.

        Builds the index on demand if this tick has not built one yet, so the
        query never depends on a caller having remembered to rebuild first —
        `step()` does it explicitly at the top of each tick, but tests (and any
        future caller) that drive a single system in isolation still work.
        """
        if self._grid_tick != self.tick:
            self.rebuild_spatial_index()
        reach = radius + GRID_MARGIN
        cell = GRID_CELL
        cx0, cx1 = int((x - reach) // cell), int((x + reach) // cell)
        cy0, cy1 = int((y - reach) // cell), int((y + reach) // cell)
        out: list = []
        grid = self._grid
        for gx in range(cx0, cx1 + 1):
            for gy in range(cy0, cy1 + 1):
                bucket = grid.get((gx, gy))
                if bucket:
                    out.extend(bucket)
        if include_structures:
            # Structures are few and static but large, so they are distance-
            # filtered here rather than bucketed (a core would span several
            # cells and need de-duplicating). Squared compare: no sqrt.
            for st in self._grid_structures:
                dx, dy = st.x - x, st.y - y
                limit = reach + st.radius
                if dx * dx + dy * dy <= limit * limit:
                    out.append(st)
        return out

    # --------------------------------------------------------------------------
    # Match lifecycle
    # --------------------------------------------------------------------------
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
        # One core per team, inland between its fountain and mid base tower.
        for team_int, (cx, cy) in CORE_POSITIONS.items():
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
        """Spawn static obstacles (walls + destructible trees) from the config.
        Each obstacle is an oriented capsule (p1, p2, thickness)."""
        for cap in WALLS:
            p1, p2 = cap["p1"], cap["p2"]
            wall = Wall(x1=p1[0], y1=p1[1], x2=p2[0], y2=p2[1],
                        thickness=cap["thickness"])
            self.entities[wall.entity_id] = wall
        for cap in TREES:
            p1, p2 = cap["p1"], cap["p2"]
            tree = Tree(x1=p1[0], y1=p1[1], x2=p2[0], y2=p2[1],
                        thickness=cap["thickness"])
            self.entities[tree.entity_id] = tree

    def invalidate_terrain(self) -> None:
        """Hook for when the walkable/sight-blocking geometry changes (a tree
        dying or regrowing). Currently a no-op: the capsule lists are rebuilt on
        demand, which profiling showed is not a hot path. Kept as the single
        place to hang a cache if that ever changes, so callers already announce
        the invalidation."""

    def obstacle_capsules(self) -> list[tuple[float, float, float, float, float]]:
        """Capsules that block walking (walls + alive trees)."""
        return [e.capsule() for e in self.entities.values()
                if isinstance(e, Obstacle) and e.alive]

    def vision_blocker_capsules(self) -> list[tuple[float, float, float, float, float]]:
        """Capsules that block line-of-sight (walls + alive trees)."""
        return [e.capsule() for e in self.entities.values()
                if isinstance(e, Obstacle) and e.alive and e.blocks_vision]

    def in_river(self, x: float, y: float) -> bool:
        """True if (x, y) lies in the walkable river band (for river effects)."""
        return RIVER is not None and RIVER.contains(x, y)

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

    # --------------------------------------------------------------------------
    # Snapshot / vision
    # --------------------------------------------------------------------------
    def build_snapshot(self) -> list[dict]:
        """Build a list of entity snapshots for broadcast (no fog)."""
        return [e.to_snapshot() for e in self.entities.values()]

    def _vision_sources(self, team: Team):
        """Yield (x, y, radius, unobstructed) for each alive vision-granting unit
        of `team`. `unobstructed` sight ignores wall/tree line-of-sight blocks."""
        for e in self.entities.values():
            if not e.alive or e.team != team:
                continue
            if isinstance(e, Hero):
                yield (e.x, e.y, HERO_VISION_RADIUS + e.bonus_vision(),
                       e.has_unobstructed_vision())
            elif isinstance(e, Minion):
                yield e.x, e.y, MINION_VISION_RADIUS, False
            elif isinstance(e, Structure):
                yield e.x, e.y, TOWER_VISION_RADIUS, False

    def visible_entity_ids_for(self, team: Team) -> set[int]:
        """Ids visible to `team`: own units + all static map features, plus
        enemy/neutral units within unobstructed line-of-sight of one of the
        team's vision sources (walls and alive trees block the sight line).
        Invisible enemy heroes are hidden unless briefly revealed (attacking)."""
        sources = list(self._vision_sources(team))
        blockers = self.vision_blocker_capsules()
        visible: set[int] = set()
        for e in self.entities.values():
            # Own units + static map features (structures, walls, trees) are
            # always sent so the client can draw the world.
            if e.team == team or isinstance(e, (Structure, Obstacle)):
                visible.add(e.entity_id)
                continue
            # A stealthed enemy hero is unseen until it reveals itself (attacks).
            if isinstance(e, Hero) and e.is_invisible() and e.reveal_timer <= 0:
                continue
            for sx, sy, r, unob in sources:
                if math.hypot(e.x - sx, e.y - sy) > r + e.radius:
                    continue
                if not unob and any(
                        segment_capsule_intersect(sx, sy, e.x, e.y,
                                                  cx0, cy0, cx1, cy1, th)
                        for (cx0, cy0, cx1, cy1, th) in blockers):
                    continue  # sight line is blocked by a wall/tree
                visible.add(e.entity_id)
                break
        return visible

    def visible_ids_cached(self, team: Team) -> set[int]:
        """Per-tick memoized `visible_entity_ids_for`, used by combat targeting
        (heroes can't acquire fogged targets) without recomputing line-of-sight
        for every targeting call in the same tick."""
        if self._vis_cache_epoch != self._vis_epoch:
            self._vis_cache = {}
            self._vis_cache_epoch = self._vis_epoch
        s = self._vis_cache.get(team)
        if s is None:
            s = self._vis_cache[team] = self.visible_entity_ids_for(team)
        return s

    def point_visible_for(self, team: Team, x: float, y: float) -> bool:
        """True if `team` has line-of-sight to the world point (x, y). Used to
        reveal AoE/hit effect telegraphs even when their source unit is fogged."""
        blockers = self.vision_blocker_capsules()
        for sx, sy, r, unob in self._vision_sources(team):
            if math.hypot(x - sx, y - sy) > r:
                continue
            if not unob and any(
                    segment_capsule_intersect(sx, sy, x, y,
                                              cx0, cy0, cx1, cy1, th)
                    for (cx0, cy0, cx1, cy1, th) in blockers):
                continue
            return True
        return False

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
