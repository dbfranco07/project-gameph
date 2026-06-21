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
    MINION_GOLD,
    MINION_XP,

    RANGED_MINION_HP,
    RANGED_MINION_DAMAGE,
    RANGED_MINION_RANGE,
    RANGED_MINION_GOLD,
    RANGED_MINION_XP,
    RANGED_MINION_PROJECTILE_SPEED,

    CART_MINION_HP,
    CART_MINION_DAMAGE,
    CART_MINION_RANGE,
    CART_MINION_SPEED,
    CART_MINION_RADIUS,
    CART_MINION_GOLD,
    CART_MINION_XP,

    NEUTRAL_HP,
    NEUTRAL_DAMAGE,
    NEUTRAL_RANGE,
    NEUTRAL_INTERVAL,
    NEUTRAL_RADIUS,
    NEUTRAL_GOLD,
    NEUTRAL_XP,

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

    # Combat (attack_damage == 0 means this entity does not auto-attack).
    # attack_damage is the PHYSICAL attack; sp_atk is the SPECIAL (magic) attack
    # used by abilities. Incoming physical damage is reduced by phys_def and
    # special damage by sp_def (see system_damage_death's armor curve).
    attack_damage: int = 0
    sp_atk: int = 0
    phys_def: int = 0
    sp_def: int = 0
    attack_range: float = 0.0
    attack_interval: float = 1.0
    attack_timer: float = 0.0  # seconds remaining until next attack is ready
    attack_type: str = "melee"  # "melee" = instant hit, "ranged" = fires a projectile
    attack_proj_speed: float = 1000.0

    def distance_to(self, other: Entity) -> float:
        """Euclidean distance to another entity."""
        return math.hypot(self.x - other.x, self.y - other.y)

    def effective_attack_range(self) -> float:
        """Attack range including any bonuses (base entities have none)."""
        return self.attack_range

    # Defenses including any temporary modifiers (base entities have none).
    def effective_phys_def(self) -> float:
        return self.phys_def

    def effective_sp_def(self) -> float:
        return self.sp_def

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
    sp_atk: int = 0
    phys_def: int = 20
    sp_def: int = 20
    attack_range: float = 160.0
    attack_interval: float = 1.0
    attack_type: str = "melee"

    # Per-level stat growth (copied from the HeroDef on spawn).
    sp_atk_per_level: float = 0.0
    phys_def_per_level: float = 3.0
    sp_def_per_level: float = 2.0
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
    # Skill leveling: per-key rank (0 = not learned yet) + unspent skill points.
    # Q/W/E cap at 4, R at 3 (R only at hero levels 4/8/12).
    ability_levels: dict[str, int] = field(default_factory=dict)
    skill_points: int = 0

    # Temporary buffs: list of {speed_bonus, dmg_bonus, remaining}
    buffs: list[dict] = field(default_factory=list)

    # Inventory: list of item_id strings + per-slot active cooldown remaining.
    inventory: list[str] = field(default_factory=list)
    item_cooldowns: dict[str, float] = field(default_factory=dict)

    # Free-form per-hero ability state (e.g. Manananggal split). Not networked.
    ability_state: dict = field(default_factory=dict)

    # Respawn
    respawn_timer: float = 0.0

    # Scoreboard: kills / deaths / assists + last-hit counters (enemy minions /
    # neutral monsters this hero killed).
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    minion_kills: int = 0
    neutral_kills: int = 0

    def ability_rank(self, key: str) -> int:
        return self.ability_levels.get(key, 0)

    def ability_by_key(self, key: str) -> dict | None:
        for ab in self.abilities:
            if ab.get("key") == key:
                return ab
        return None

    def is_stunned(self) -> bool:
        return any(b.get("stun") for b in self.buffs)

    def is_silenced(self) -> bool:
        # A stun also silences (can't act at all).
        return any(b.get("silence") or b.get("stun") for b in self.buffs)

    def is_invulnerable(self) -> bool:
        return any(b.get("invuln") for b in self.buffs)

    def bonus_speed(self) -> float:
        return sum(b.get("speed_bonus", 0) for b in self.buffs)

    def slow_pct(self) -> float:
        # Slows stack additively, capped so a unit is never fully rooted by them.
        return min(0.8, sum(b.get("slow_pct", 0) for b in self.buffs))

    def effective_move_speed(self) -> float:
        return (self.move_speed + self.bonus_speed()) * (1.0 - self.slow_pct())

    def bonus_damage(self) -> int:
        return int(sum(b.get("dmg_bonus", 0) for b in self.buffs))

    def damage_mult(self) -> float:
        """Product of multiplicative damage buffs (e.g. the double-damage rune)."""
        mult = 1.0
        for b in self.buffs:
            mult *= b.get("dmg_mult", 1.0)
        return mult

    def effective_damage(self) -> int:
        return int((self.attack_damage + self.bonus_damage()) * self.damage_mult())

    def cooldown_mult(self) -> float:
        """Smallest cooldown multiplier among active CDR buffs (best one wins)."""
        mult = 1.0
        for b in self.buffs:
            mult = min(mult, b.get("cd_mult", 1.0))
        return mult

    def bonus_range(self) -> float:
        return sum(b.get("range_bonus", 0) for b in self.buffs)

    def effective_attack_range(self) -> float:
        return self.attack_range + self.bonus_range()

    # Special attack + both defenses, including temporary buff/debuff deltas.
    def bonus_sp_atk(self) -> float:
        return sum(b.get("sp_atk", 0) for b in self.buffs)

    def effective_sp_atk(self) -> int:
        return int(self.sp_atk + self.bonus_sp_atk())

    def bonus_phys_def(self) -> float:
        return sum(b.get("phys_def", 0) for b in self.buffs)

    def effective_phys_def(self) -> float:
        return self.phys_def + self.bonus_phys_def()

    def bonus_sp_def(self) -> float:
        return sum(b.get("sp_def", 0) for b in self.buffs)

    def effective_sp_def(self) -> float:
        return self.sp_def + self.bonus_sp_def()

    def attack_speed_bonus(self) -> float:
        return sum(b.get("atkspd_pct", 0) for b in self.buffs)

    def effective_attack_interval(self) -> float:
        return self.attack_interval / (1.0 + self.attack_speed_bonus())

    def move_toward_target(self, dt: float) -> None:
        if self.target_x is None or self.target_y is None:
            return
        speed = self.effective_move_speed()
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
        # Lightweight render hint: True while the upper half is detached (R Split)
        # so the client can swap to the flying-torso sprite. Cheap one-bit flag.
        if self.ability_state.get("split"):
            d["split"] = True
        # Extra stats for the HUD panel.
        d["ad"] = self.effective_damage()
        d["spa"] = self.effective_sp_atk()
        d["pdef"] = round(self.effective_phys_def(), 1)
        d["sdef"] = round(self.effective_sp_def(), 1)
        d["rng"] = round(self.effective_attack_range())
        d["aspd"] = round(1.0 / self.effective_attack_interval(), 2)
        d["ms"] = int(self.effective_move_speed())
        d["hpr"] = round(self.hp_regen
                         + sum(b.get("hp_regen_bonus", 0) for b in self.buffs), 1)
        d["mpr"] = round(self.mana_regen
                         + sum(b.get("mana_regen_bonus", 0) for b in self.buffs), 1)
        d["xp"] = self.xp
        d["xpn"] = 0 if self.level >= MAX_LEVEL else XP_BASE + (self.level - 1) * XP_PER_LEVEL
        # Temporary stat deltas (from buffs/debuffs only) so the HUD can render
        # green (+) / red (-) numbers. Only nonzero entries are sent.
        deltas = {
            "ad": self.bonus_damage(),
            "spa": int(self.bonus_sp_atk()),
            "pdef": round(self.bonus_phys_def(), 1),
            "sdef": round(self.bonus_sp_def(), 1),
            "rng": round(self.bonus_range(), 1),
            "ms": round(self.effective_move_speed() - self.move_speed, 1),
            "aspd": round(1.0 / self.effective_attack_interval()
                          - 1.0 / self.attack_interval, 2),
            "hpr": round(sum(b.get("hp_regen_bonus", 0) for b in self.buffs), 1),
            "mpr": round(sum(b.get("mana_regen_bonus", 0) for b in self.buffs), 1),
        }
        d["dlt"] = {k: v for k, v in deltas.items() if v}
        # Active crowd-control flags for HUD/feedback.
        cc = []
        if self.is_stunned():
            cc.append("stun")
        if self.is_silenced() and not self.is_stunned():
            cc.append("silence")
        if self.slow_pct() > 0:
            cc.append("slow")
        if cc:
            d["cc"] = cc
        # Ability cooldown state for the owning client's HUD.
        d["cds"] = {k: round(v, 1) for k, v in self.cooldowns.items()}
        d["alvl"] = dict(self.ability_levels)
        d["sp"] = self.skill_points
        d["inv"] = list(self.inventory)
        d["icds"] = {k: round(v, 1) for k, v in self.item_cooldowns.items()}
        # Scoreboard.
        d["kills"] = self.kills
        d["deaths"] = self.deaths
        d["assists"] = self.assists
        d["mk"] = self.minion_kills
        d["nk"] = self.neutral_kills
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
    # Bounty granted when this minion dies (subtypes override).
    gold_value: int = MINION_GOLD
    xp_value: int = MINION_XP
    # Current waypoint the minion walks toward, plus any remaining waypoints.
    dest_x: float = 0.0
    dest_y: float = 0.0
    path: list[tuple[float, float]] = field(default_factory=list)
    # Neutral jungle monsters are teamless, stationary, and only fight back once
    # provoked (i.e. after taking damage).
    is_neutral: bool = False
    provoked: bool = False
    camp_id: int = -1  # index into JUNGLE_CAMPS for neutral monsters
    # Wave-1 "meet point": until reached, the minion walks at meet_speed, then
    # reverts to its default move_speed. meet_speed == 0 means inactive.
    meet_x: float = 0.0
    meet_y: float = 0.0
    meet_speed: float = 0.0

    def advance(self, dt: float) -> None:
        """Walk toward the current waypoint, advancing along the path as each is
        reached (called when no enemy is in range)."""
        dx = self.dest_x - self.x
        dy = self.dest_y - self.y
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            self._next_waypoint()
            return
        step = min(self.move_speed * dt, dist)
        self.x += (dx / dist) * step
        self.y += (dy / dist) * step

    def _next_waypoint(self) -> None:
        """Advance dest to the next waypoint in the path, if any remain."""
        if self.path:
            self.dest_x, self.dest_y = self.path.pop(0)


@dataclass
class MeleeMinion(Minion):
    """The default frontline minion (uses the base Minion stats)."""


@dataclass
class RangedMinion(Minion):
    radius: float = MINION_RADIUS
    hp: int = RANGED_MINION_HP
    max_hp: int = RANGED_MINION_HP
    attack_damage: int = RANGED_MINION_DAMAGE
    attack_range: float = RANGED_MINION_RANGE
    attack_type: str = "ranged"
    attack_proj_speed: float = RANGED_MINION_PROJECTILE_SPEED
    gold_value: int = RANGED_MINION_GOLD
    xp_value: int = RANGED_MINION_XP


@dataclass
class CartMinion(Minion):
    radius: float = CART_MINION_RADIUS
    hp: int = CART_MINION_HP
    max_hp: int = CART_MINION_HP
    attack_damage: int = CART_MINION_DAMAGE
    attack_range: float = CART_MINION_RANGE
    move_speed: float = CART_MINION_SPEED
    gold_value: int = CART_MINION_GOLD
    xp_value: int = CART_MINION_XP


@dataclass
class NeutralMinion(Minion):
    team: Team = Team.NONE
    radius: float = NEUTRAL_RADIUS
    hp: int = NEUTRAL_HP
    max_hp: int = NEUTRAL_HP
    attack_damage: int = NEUTRAL_DAMAGE
    attack_range: float = NEUTRAL_RANGE
    attack_interval: float = NEUTRAL_INTERVAL
    gold_value: int = NEUTRAL_GOLD
    xp_value: int = NEUTRAL_XP
    is_neutral: bool = True


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
    lane: str = ""        # "top"/"mid"/"bot"; empty for the (laneless) core
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
    damage_type: str = "physical"  # physical | special | true (armor curve)
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


@dataclass
class Obstacle(Entity):
    """A static, axis-aligned rectangle (top-left at x, y) that blocks walking
    and (optionally) vision. ``radius`` is set to the half-diagonal so the
    client's circular cull keeps it on screen."""

    entity_type: EntityType = EntityType.WALL
    team: Team = Team.NONE
    w: float = 100.0
    h: float = 100.0
    blocks_vision: bool = True

    def rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    def to_snapshot(self) -> dict:
        d = super().to_snapshot()
        d["w"] = self.w
        d["h"] = self.h
        return d


@dataclass
class Wall(Obstacle):
    """Permanent, indestructible. Blocks walking + vision."""

    entity_type: EntityType = EntityType.WALL


@dataclass
class Tree(Obstacle):
    """Like a wall but destructible: takes damage and, when killed, stops
    blocking walking and vision."""

    entity_type: EntityType = EntityType.TREE
    hp: int = 200
    max_hp: int = 200


@dataclass
class RuneCreature(NeutralMinion):
    """A roaming neutral that patrols near its spawn, attacks nearby enemies, and
    on death grants the killer a timed buff (haste / double_damage / cdr_50 /
    regen_10x). Unlike jungle camps it is aggressive by default."""

    provoked: bool = True          # always willing to fight
    rune_buff: str = "haste"
    home_x: float = 0.0
    home_y: float = 0.0
    patrol_radius: float = 400.0
    rune_index: int = -1

    def to_snapshot(self) -> dict:
        d = super().to_snapshot()
        d["rune"] = True  # let the client tint/label it
        return d


@dataclass
class SplitBody(Entity):
    """A hero's detached lower body (Manananggal ult). Stationary and vulnerable:
    it does not move or attack, takes `dmg_mult` times damage, and if destroyed
    the owning hero dies. Rendered as a MINION-type blip on the client."""

    entity_type: EntityType = EntityType.MINION
    owner_id: int = 0
    dmg_mult: float = 2.0

    def to_snapshot(self) -> dict:
        d = super().to_snapshot()
        d["body"] = True  # let the client tint it as a hero body
        return d
