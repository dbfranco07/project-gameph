"""Game systems — plain functions called each server tick.

The whole simulation is an ordered pipeline of pure-ish functions over GameState.
`step()` runs them in order; adding a mechanic means adding a function and slotting
it into `step()`. This is the extension point the whole design leans on.
"""

from __future__ import annotations

import math
import random

from shared.config import (
    MAP_WIDTH,
    MAP_HEIGHT,
    SPAWN_POSITIONS,
    LANE_PATHS,
    HERO_RESPAWN_BASE,
    HERO_RESPAWN_PER_LEVEL,
    HERO_KILL_GOLD,
    HERO_KILL_XP,
    STRUCTURE_GOLD,
    PASSIVE_GOLD_PER_SEC,
    MINION_ASSIST_GOLD_FRACTION,
    GOLD_SHARE_RADIUS,
    XP_SHARE_RADIUS,
    MAX_LEVEL,
    XP_BASE,
    XP_PER_LEVEL,
    HP_PER_LEVEL,
    DAMAGE_PER_LEVEL,
    CREEP_WAVE_INTERVAL,
    CREEP_MELEE_PER_WAVE,
    CREEP_RANGED_PER_WAVE,
    CREEP_CART_EVERY,
    JUNGLE_CAMPS,
    NEUTRAL_RESPAWN,
    BASIC_PROJECTILE_RADIUS,
    DEFENSE_K,
    RUNES,
    MEET_POINTS,
    SPAWN_ZONE_RADIUS,
    BASE_TOWER_T,
)
from shared.geometry import point_along, closest_point_on_segment
from shared.game_types import EntityType, Team, GamePhase
from server.entity import (
    Hero, Minion, MeleeMinion, RangedMinion, CartMinion, NeutralMinion,
    Structure, Projectile, HookProjectile, SplitBody, RuneCreature,
    SummonedMinion,
)
from server.effects import make_effect
from server.bind import release_bind
from server.game_state import GameState, enemy_team
from server.heroes.base import CastContext
from shared.game_types import CastType


# Seconds the render-only cast signal stays set after an ability fires, so the
# client can play a one-shot skill animation.
CAST_SIGNAL_SECS = 0.45


# ---------------------------------------------------------------------------
# Targeting
# ---------------------------------------------------------------------------

# Per-attacker target preference: lower number = higher priority. A category
# absent from the map means "never auto-attack that type".
_PRIORITY = {
    "minion": {EntityType.MINION: 0, 
               EntityType.HERO: 1, 
               EntityType.TOWER: 2, 
               EntityType.BASE: 2},
    "structure": {EntityType.MINION: 0, 
                  EntityType.HERO: 1},
    "hero": {EntityType.HERO: 0, 
             EntityType.MINION: 1, 
             EntityType.TOWER: 2, 
             EntityType.BASE: 2},
}


def _attacker_kind(attacker) -> str:
    if isinstance(attacker, Minion):
        return "minion"
    if isinstance(attacker, Structure):
        return "structure"
    return "hero"


def find_attack_target(state: GameState, attacker):
    """Nearest valid enemy within range, respecting per-type priority and
    structure invulnerability. Returns an entity or None."""
    # Neutral jungle monsters only fight back once provoked (damaged).
    if isinstance(attacker, Minion) and attacker.is_neutral and not attacker.provoked:
        return None
    order = _PRIORITY[_attacker_kind(attacker)]
    best = None
    best_key = None
    for e in state.entities.values():
        if e is attacker or not e.alive:
            continue
        if e.team == attacker.team:
            continue
        # Teamless entities aren't targetable, except neutral jungle monsters.
        if e.team == Team.NONE and not (isinstance(e, Minion) and e.is_neutral):
            continue
        if isinstance(e, Projectile):
            continue
        prio = order.get(e.entity_type)
        if prio is None:
            continue
        if isinstance(e, Structure) and not state.is_structure_vulnerable(e):
            continue
        if isinstance(e, Hero) and e.is_invulnerable():
            continue  # can't be targeted while invulnerable (e.g. split upper half)
        if isinstance(e, Hero) and e.is_invisible() and e.reveal_timer <= 0:
            continue  # stealthed (e.g. in trees/walls) and not currently revealed
        d = attacker.distance_to(e)
        if d > attacker.effective_attack_range() + e.radius:
            continue
        key = (prio, d)
        if best_key is None or key < best_key:
            best, best_key = e, key
    return best


# ---------------------------------------------------------------------------
# Status: cooldowns, buffs, mana regen
# ---------------------------------------------------------------------------

def system_status(state: GameState, dt: float) -> None:
    for hero in state.heroes():
        for key in hero.cooldowns:
            if hero.cooldowns[key] > 0:
                hero.cooldowns[key] = max(0.0, hero.cooldowns[key] - dt)
        for key in hero.item_cooldowns:
            if hero.item_cooldowns[key] > 0:
                hero.item_cooldowns[key] = max(0.0, hero.item_cooldowns[key] - dt)
        if hero.buffs:
            for b in hero.buffs:
                b["remaining"] -= dt
            hero.buffs[:] = [b for b in hero.buffs if b["remaining"] > 0]
        if hero.reveal_timer > 0:
            hero.reveal_timer = max(0.0, hero.reveal_timer - dt)
        if hero.cast_timer > 0:
            hero.cast_timer = max(0.0, hero.cast_timer - dt)
        if hero.alive:
            _regen(hero, dt)


def _regen(hero: Hero, dt: float) -> None:
    """Accrue slow hp/mana regen (plus temporary buff bonuses), applying whole
    points as the carry fills."""
    hp_regen = hero.hp_regen + sum(b.get("hp_regen_bonus", 0) for b in hero.buffs)
    mana_regen = hero.mana_regen + sum(b.get("mana_regen_bonus", 0) for b in hero.buffs)
    if hero.hp < hero.max_hp and hp_regen > 0:
        hero.regen_hp_acc += hp_regen * dt
        whole = int(hero.regen_hp_acc)
        if whole:
            hero.hp = min(hero.max_hp, hero.hp + whole)
            hero.regen_hp_acc -= whole
    if hero.mana < hero.max_mana and mana_regen > 0:
        hero.regen_mana_acc += mana_regen * dt
        whole = int(hero.regen_mana_acc)
        if whole:
            hero.mana = min(hero.max_mana, hero.mana + whole)
            hero.regen_mana_acc -= whole


# ---------------------------------------------------------------------------
# Creeps
# ---------------------------------------------------------------------------

def system_clock(state: GameState, dt: float) -> None:
    """Advance the match clock. Negative = pre-game countdown, 0+ = elapsed."""
    state.match_clock += dt


def system_spawn_creeps(state: GameState, dt: float) -> None:
    if state.match_clock < 0:
        return  # creeps wait for the countdown to finish
    state.creep_timer -= dt
    if state.creep_timer > 0:
        return
    state.creep_timer = CREEP_WAVE_INTERVAL
    state.wave_count += 1
    _spawn_wave(state)


def _spawn_wave(state: GameState) -> None:
    cart = state.wave_count % CREEP_CART_EVERY == 0
    for team_int in (1, 2):
        team = Team(team_int)
        for lane in LANE_PATHS:
            _spawn_lane_group(state, team, lane, cart)


def _spawn_lane_group(state: GameState, team: Team, lane: str, cart: bool) -> None:
    """Spawn one team's wave for one lane: melee, then ranged, then an optional
    cart, marching out from the team's base along the lane polyline."""
    # Waypoints run base -> enemy base; Team 2 walks the lane in reverse.
    path = list(LANE_PATHS[lane])
    if team == Team.TEAM2:
        path = path[::-1]

    classes = ([MeleeMinion] * CREEP_MELEE_PER_WAVE
               + [RangedMinion] * CREEP_RANGED_PER_WAVE
               + ([CartMinion] if cart else []))

    # Minions spawn next to their lane's base tower (not the fountain/core).
    # The path is already oriented per team, so BASE_TOWER_T is "base tower" for
    # both sides.
    spawn = point_along(path, BASE_TOWER_T)
    # March direction toward the first waypoint, for spacing the column.
    nxt = path[1] if len(path) > 1 else path[0]
    dx, dy = nxt[0] - spawn[0], nxt[1] - spawn[1]
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d

    # Wave 1 marches faster until it reaches the lane's meeting point, then
    # reverts to default speed (so both sides clash at the meet point).
    meet = MEET_POINTS.get(lane) if state.wave_count == 1 else None

    for i, cls in enumerate(classes):
        waypoints = path[1:]  # remaining waypoints after the spawn point
        minion = cls(
            team=team,
            x=spawn[0] + ux * (i * 35 - 60),
            y=spawn[1] + uy * (i * 35 - 60),
            dest_x=waypoints[0][0],
            dest_y=waypoints[0][1],
            path=waypoints[1:],
        )
        if meet is not None:
            minion.meet_x, minion.meet_y = meet
            minion.meet_speed = minion.move_speed * 1.4
        state.entities[minion.entity_id] = minion


# ---------------------------------------------------------------------------
# Jungle camps (neutral monsters)
# ---------------------------------------------------------------------------

def system_neutral_camps(state: GameState, dt: float) -> None:
    """Spawn jungle camps at match start and respawn each camp after it is
    cleared. Camps are passive: their monsters idle until provoked."""
    if state.match_clock < 0:
        return  # neutrals appear when the countdown ends
    for camp_id, (cx, cy, count) in enumerate(JUNGLE_CAMPS):
        camp = state.neutral_camps.get(camp_id)
        if camp is None:
            _spawn_camp(state, camp_id, cx, cy, count)
            state.neutral_camps[camp_id] = {"timer": 0.0}
            continue
        alive = any(isinstance(e, NeutralMinion) and e.camp_id == camp_id and e.alive
                    for e in state.entities.values())
        if alive:
            camp["timer"] = 0.0
            continue
        # Camp cleared: count down, then respawn.
        if camp["timer"] <= 0.0:
            camp["timer"] = NEUTRAL_RESPAWN
        else:
            camp["timer"] -= dt
            if camp["timer"] <= 0.0:
                _spawn_camp(state, camp_id, cx, cy, count)


def _spawn_camp(state: GameState, camp_id: int, cx: float, cy: float,
                count: int) -> None:
    for i in range(count):
        angle = (2 * math.pi / count) * i
        mob = NeutralMinion(
            x=cx + math.cos(angle) * 40,
            y=cy + math.sin(angle) * 40,
            camp_id=camp_id,
        )
        state.entities[mob.entity_id] = mob


# ---------------------------------------------------------------------------
# Runes (roaming neutrals that drop timed buffs)
# ---------------------------------------------------------------------------

RUNE_BUFF_DURATION = 25.0      # haste / double_damage / cdr_50 last this long
RUNE_REGEN_DURATION = 30.0     # regen_10x window (also cancels on taking damage)
RUNE_HASTE_SPEED = 220         # near-max move speed bonus
RUNE_BUFF_TYPES = ("haste", "double_damage", "cdr_50", "regen_10x")


def apply_rune_buff(hero: Hero, kind: str) -> None:
    """Grant a hero the timed buff a slain rune drops."""
    if kind == "haste":
        hero.buffs.append(make_effect(RUNE_BUFF_DURATION, 
                                      source="rune:haste",
                                      speed_bonus=RUNE_HASTE_SPEED))
    elif kind == "double_damage":
        hero.buffs.append(make_effect(RUNE_BUFF_DURATION,
                                      source="rune:double_damage", 
                                      dmg_mult=2.0))
    elif kind == "cdr_50":
        hero.buffs.append(make_effect(RUNE_BUFF_DURATION, 
                                      source="rune:cdr_50",
                                      cd_mult=0.5))
    elif kind == "regen_10x":
        # 10x current regen, but the buff fizzles the moment the hero is hit.
        eff = make_effect(RUNE_REGEN_DURATION, 
                          source="rune:regen_10x",
                          hp_regen_bonus=hero.hp_regen * 9.0,
                          mana_regen_bonus=hero.mana_regen * 9.0)
        eff["cancel_on_hit"] = True
        hero.buffs.append(eff)


def system_runes(state: GameState, dt: float) -> None:
    """Spawn runes at match start, respawn cleared ones, and patrol live ones."""
    if state.match_clock < 0:
        return  # runes appear when the countdown ends
    for idx, cfg in enumerate(RUNES):
        rs = state.rune_state.get(idx)
        if rs is None:
            _spawn_rune(state, idx, cfg)
            continue
        ent = state.entities.get(rs.get("eid"))
        if ent is not None and ent.alive:
            _patrol_rune(state, ent, dt)
            continue
        # Cleared: count down, then respawn.
        if rs["timer"] <= 0.0:
            rs["timer"] = NEUTRAL_RESPAWN
        else:
            rs["timer"] -= dt
            if rs["timer"] <= 0.0:
                _spawn_rune(state, idx, cfg)


def _spawn_rune(state: GameState, idx: int, cfg: dict) -> None:
    # Spawn at a uniform-random point inside the rune's rectangular zone.
    zx, zy, zw, zh = cfg["zone"]
    px = random.uniform(zx, zx + zw)
    py = random.uniform(zy, zy + zh)
    # A "random" (or unset) config buff rerolls each spawn/respawn, so the two
    # mirrored runes — and successive spawns — vary across the buff catalog.
    buff = cfg.get("buff", "random")
    if buff == "random":
        buff = random.choice(RUNE_BUFF_TYPES)
    rune = RuneCreature(
        x=px, y=py, dest_x=px, dest_y=py,
        home_x=px, home_y=py,
        patrol_radius=cfg.get("patrol", 400),
        rune_buff=buff,
        rune_index=idx,
    )
    state.entities[rune.entity_id] = rune
    state.rune_state[idx] = {"eid": rune.entity_id, "timer": 0.0}


def _patrol_rune(state: GameState, rune: RuneCreature, dt: float) -> None:
    if find_attack_target(state, rune) is not None:
        return  # an enemy is in range: stand and fight (combat handles attacks)
    dx, dy = rune.dest_x - rune.x, rune.dest_y - rune.y
    if math.hypot(dx, dy) < rune.radius + 5.0:
        ang = random.uniform(0, 2 * math.pi)
        rad = random.uniform(0, rune.patrol_radius)
        rune.dest_x = rune.home_x + math.cos(ang) * rad
        rune.dest_y = rune.home_y + math.sin(ang) * rad
        return
    d = math.hypot(dx, dy)
    step = min(rune.move_speed * dt, d)
    rune.x += dx / d * step
    rune.y += dy / d * step


# ---------------------------------------------------------------------------
# Movement
# ---------------------------------------------------------------------------

def system_movement(state: GameState, dt: float) -> None:
    """Heroes move toward click targets; minions walk the lane unless fighting."""
    for entity in state.entities.values():
        if not entity.alive:
            continue
        if isinstance(entity, Hero):
            if entity.is_stunned():
                continue  # stunned heroes hold position
            _update_focus_chase(state, entity)
            _update_attack_move(state, entity)
            entity.move_toward_target(dt)
            _block_hero_against_units(state, entity)
            entity.x = max(entity.radius, min(MAP_WIDTH - entity.radius, entity.x))
            entity.y = max(entity.radius, min(MAP_HEIGHT - entity.radius, entity.y))
        elif isinstance(entity, Minion):
            if entity.is_neutral:
                continue  # jungle monsters hold their camp
            if find_attack_target(state, entity) is None:
                _advance_minion(state, entity, dt)


_MINION_AVOID_BUFFER = 45  # extra clearance when steering around a structure


def _advance_minion(state: GameState, minion: Minion, dt: float) -> None:
    """Walk toward the current waypoint, advancing along the lane path as each is
    reached, steering around any structure (tower or core) blocking the way."""
    dx = minion.dest_x - minion.x
    dy = minion.dest_y - minion.y
    dist = math.hypot(dx, dy)
    if dist < minion.radius + 5.0:
        # Reached this waypoint; pick up the next one if the lane bends onward.
        if minion.path:
            minion._next_waypoint()
            dx = minion.dest_x - minion.x
            dy = minion.dest_y - minion.y
            dist = math.hypot(dx, dy)
        if dist < 1.0:
            return
    dirx, diry = dx / dist, dy / dist

    obstacle = _blocking_obstacle(state, minion, dirx, diry)
    if obstacle is not None:
        # Slide around the obstacle: move along the tangent that best preserves
        # forward progress, blended with a little forward bias to round it off.
        ax, ay = minion.x - obstacle.x, minion.y - obstacle.y
        al = math.hypot(ax, ay) or 1.0
        ax, ay = ax / al, ay / al
        t1 = (-ay, ax)
        t2 = (ay, -ax)
        tang = t1 if (t1[0] * dirx + t1[1] * diry) >= (t2[0] * dirx + t2[1] * diry) else t2
        dirx, diry = tang[0] + dirx * 0.4, tang[1] + diry * 0.4
        sl = math.hypot(dirx, diry) or 1.0
        dirx, diry = dirx / sl, diry / sl

    speed = minion.move_speed
    if minion.meet_speed:
        if math.hypot(minion.meet_x - minion.x, minion.meet_y - minion.y) <= 200:
            minion.meet_speed = 0.0  # reached the meet point: back to default
        else:
            speed = minion.meet_speed
    step = min(speed * dt, dist)
    minion.x += dirx * step
    minion.y += diry * step


def _blocking_obstacle(state: GameState, minion: Minion, dirx: float, diry: float):
    """Nearest alive blocker ahead of the minion and close enough to require
    steering around it, or None. Blockers are structures (avoided with a wide
    berth) and other units (avoided only when nearly touching, i.e. genuinely
    stuck behind a stalled minion/hero — so a marching column doesn't zigzag)."""
    best = None
    best_d = None
    for e in state.entities.values():
        if e is minion or not e.alive:
            continue
        if isinstance(e, Structure):
            margin = _MINION_AVOID_BUFFER
        elif isinstance(e, (Hero, Minion)):
            margin = 8.0
        else:
            continue
        ox, oy = e.x - minion.x, e.y - minion.y
        od = math.hypot(ox, oy)
        if od < 1e-6 or od > e.radius + minion.radius + margin:
            continue
        if ox * dirx + oy * diry <= 0:
            continue  # behind the minion's travel direction; not in the way
        if best_d is None or od < best_d:
            best, best_d = e, od
    return best


def _update_focus_chase(state: GameState, hero: Hero) -> None:
    """If the hero has a focus target (from 'A + click enemy'), chase it until
    in range, then hold position so combat can fire. Clears when invalid."""
    if hero.forced_target_id is None:
        return
    target = state.entities.get(hero.forced_target_id)
    if (target is None or not target.alive or target.team == hero.team
            or (isinstance(target, Structure) and not state.is_structure_vulnerable(target))):
        hero.forced_target_id = None
        return
    in_range = hero.distance_to(target) <= hero.effective_attack_range() + target.radius
    if in_range:
        hero.target_x = hero.target_y = None  # stand and attack
    else:
        hero.target_x, hero.target_y = target.x, target.y  # close the gap


_ATTACK_MOVE_ARRIVE = 8.0  # distance at which an attack-move goal counts as reached


def _update_attack_move(state: GameState, hero: Hero) -> None:
    """Attack-move ('A + click ground'): walk toward the stored goal, but stop
    (clear the move target so combat can fire) whenever an enemy is in attack
    range, then resume once nothing is in range. A focus target takes priority."""
    if hero.forced_target_id is not None or not hero.attack_move:
        return
    if hero.attack_move_x is None or hero.attack_move_y is None:
        hero.attack_move = False
        return
    if math.hypot(hero.attack_move_x - hero.x,
                  hero.attack_move_y - hero.y) <= _ATTACK_MOVE_ARRIVE:
        hero.attack_move = False
        hero.attack_move_x = hero.attack_move_y = None
        hero.target_x = hero.target_y = None
        return
    if find_attack_target(state, hero) is not None:
        hero.target_x = hero.target_y = None  # stop and let combat attack it
    else:
        hero.target_x, hero.target_y = hero.attack_move_x, hero.attack_move_y


def _block_hero_against_units(state: GameState, hero: Hero) -> None:
    """One-sided block: after the hero has moved, eject IT out of any other unit
    it now overlaps (the other unit is never moved). The radial eject only undoes
    the component of motion into the blocker, so the hero stops at it but can
    still slide sideways/backwards and never gets permanently stuck — and because
    only the mover adjusts itself, it never pushes the blocker."""
    if hero.ability_state.get("bind"):
        return  # bound inside a tree/wall: not body-blocked by other units
    for other in state.entities.values():
        if other is hero or not other.alive:
            continue
        if isinstance(other, (Hero, Minion)):
            _eject_circle(hero, other.x, other.y, other.radius)


# ---------------------------------------------------------------------------
# Collision (units cannot share space)
# ---------------------------------------------------------------------------

def system_collision(state: GameState, dt: float) -> None:
    """Eject units out of immovable map geometry (structures and wall/tree
    capsules) so they can't tunnel through it. Unit-vs-unit blocking is handled
    during movement (heroes stop+slide in system_movement; minions steer around
    in _advance_minion) — units are never elastic-shoved apart here."""
    units = [e for e in state.entities.values()
             if isinstance(e, (Hero, Minion)) and e.alive]
    structs = [e for e in state.entities.values()
               if isinstance(e, Structure) and e.alive]
    obstacles = state.obstacle_capsules()
    for u in units:
        for s in structs:
            _eject_circle(u, s.x, s.y, s.radius)
        # A Manananggal's detached upper half flies over walls and trees; a hero
        # bound inside a tree/wall (Kapre R / Tiktik W) likewise ignores it.
        ignores_terrain = isinstance(u, Hero) and (
            u.ability_state.get("split") or u.ability_state.get("bind")
            or any(b.get("phase") for b in u.buffs))
        if not ignores_terrain:
            for cap in obstacles:
                _push_out_of_capsule(u, cap)
        u.x = max(u.radius, min(MAP_WIDTH - u.radius, u.x))
        u.y = max(u.radius, min(MAP_HEIGHT - u.radius, u.y))


def _eject_circle(u, cx: float, cy: float, cr: float) -> None:
    """Move unit `u` fully out of a circular blocker at (cx, cy, cr). One-sided:
    only `u` moves, so this blocks without pushing the blocker."""
    dx, dy = u.x - cx, u.y - cy
    dist = math.hypot(dx, dy)
    mind = u.radius + cr
    if dist >= mind:
        return
    if dist < 1e-6:
        nx, ny, overlap = 1.0, 0.0, mind
    else:
        nx, ny, overlap = dx / dist, dy / dist, mind - dist
    u.x += nx * overlap
    u.y += ny * overlap


def _push_out_of_capsule(u, cap) -> None:
    """Push a unit's circle out of a wall/tree capsule (centerline + thickness),
    one-sided and along the centerline normal."""
    x0, y0, x1, y1, th = cap
    cx, cy = closest_point_on_segment(u.x, u.y, x0, y0, x1, y1)
    dx, dy = u.x - cx, u.y - cy
    dist = math.hypot(dx, dy)
    reach = u.radius + th / 2.0
    if dist >= reach:
        return  # not overlapping
    if dist > 1e-9:
        nx, ny = dx / dist, dy / dist
    else:
        # Center lies on the centerline: eject perpendicular to the segment.
        sx, sy = x1 - x0, y1 - y0
        sl = math.hypot(sx, sy) or 1.0
        nx, ny = -sy / sl, sx / sl
    u.x = cx + nx * (reach + 0.5)
    u.y = cy + ny * (reach + 0.5)


# ---------------------------------------------------------------------------
# Abilities
# ---------------------------------------------------------------------------

def system_ability_cast(state: GameState, dt: float) -> None:
    for cast in state.ability_casts:
        caster = state.entities.get(cast["caster"])
        if not isinstance(caster, Hero) or not caster.alive:
            continue
        if caster.is_silenced():
            continue  # stun or silence: no abilities (covers is_stunned too)
        key = cast["key"]
        # Item actives use slot keys "I1".."I6"; hero abilities use "Q".."R".
        if isinstance(key, str) and key.startswith("I") and key[1:].isdigit():
            _cast_item_active(state, caster, cast, int(key[1:]) - 1)
            continue
        ab = caster.ability_by_key(cast["key"])
        if ab is None or caster.hero_def is None:
            continue
        adef = caster.hero_def.ability(ab["key"])
        if adef is None or adef.cast_type == CastType.PASSIVE:
            continue  # passives are not castable
        rank = caster.ability_rank(ab["key"])
        if rank < 1:
            continue  # not learned yet
        if caster.cooldowns.get(ab["key"], 0.0) > 0:
            continue
        if caster.mana < ab["mana"]:
            continue
        caster.mana -= ab["mana"]
        caster.cooldowns[ab["key"]] = ab["cd"] * caster.cooldown_mult()
        ctx = CastContext(state, caster,
                          cast.get("tx", 0.0), cast.get("ty", 0.0),
                          cast.get("tid"), rank=rank)
        adef.fn(ctx)
        # Render-only cast signal so the client plays a one-shot skill animation.
        caster.cast_key = ab["key"]
        caster.cast_timer = CAST_SIGNAL_SECS
        # "On skill use" passive hook (e.g. Manananggal Bloodlust).
        hook = getattr(caster.hero_def, "on_ability_cast", None)
        if hook is not None:
            hook(ctx, ab["key"])
    state.ability_casts.clear()


def _cast_item_active(state: GameState, caster: Hero, cast: dict, slot: int) -> None:
    """Cast the active of the item in the given inventory slot, if any."""
    from server.items import get_item_def
    if slot < 0 or slot >= len(caster.inventory):
        return
    item = get_item_def(caster.inventory[slot])
    if item is None or item.active is None:
        return
    active = item.active
    if caster.item_cooldowns.get(item.item_id, 0.0) > 0:
        return
    if caster.mana < active.mana:
        return
    caster.mana -= active.mana
    caster.item_cooldowns[item.item_id] = active.cd * caster.cooldown_mult()
    ctx = CastContext(state, caster,
                      cast.get("tx", 0.0), cast.get("ty", 0.0), cast.get("tid"))
    active.fn(ctx)


# ---------------------------------------------------------------------------
# Projectiles
# ---------------------------------------------------------------------------

def system_projectiles(state: GameState, dt: float) -> None:
    dead: list[int] = []
    for proj in state.entities.values():
        if not isinstance(proj, Projectile):
            continue
        if proj.homing:
            if _advance_homing(state, proj, dt, dead):
                continue
        else:
            step = math.hypot(proj.vx, proj.vy) * dt
            proj.x += proj.vx * dt
            proj.y += proj.vy * dt
            proj.range_left -= step
            hit = _projectile_hit(state, proj)
            if hit is not None:
                state.damage_events.append(
                    {"src": proj.owner_id, "tgt": hit.entity_id, "amt": proj.damage,
                     "dtype": proj.damage_type, "basic": proj.is_basic}
                )
                if isinstance(proj, HookProjectile):
                    _resolve_hook(state, proj, hit)
                dead.append(proj.entity_id)
            elif proj.range_left <= 0 or not (0 <= proj.x <= MAP_WIDTH and 0 <= proj.y <= MAP_HEIGHT):
                dead.append(proj.entity_id)
    for eid in dead:
        state.entities.pop(eid, None)


def _advance_homing(state: GameState, proj: Projectile, dt: float, dead: list) -> bool:
    """Steer a basic-attack projectile toward its target. Returns True when the
    projectile has been resolved (hit or fizzled) and added to `dead`."""
    target = state.entities.get(proj.target_id)
    if target is None or not target.alive:
        dead.append(proj.entity_id)  # target gone before the shot landed
        return True
    step = proj.speed * dt
    proj.range_left -= step
    dx, dy = target.x - proj.x, target.y - proj.y
    dist = math.hypot(dx, dy)
    if dist <= step + proj.radius + target.radius:
        proj.x, proj.y = target.x, target.y
        state.damage_events.append(
            {"src": proj.owner_id, "tgt": target.entity_id, "amt": proj.damage,
             "basic": proj.is_basic}
        )
        dead.append(proj.entity_id)
        return True
    proj.x += (dx / dist) * step
    proj.y += (dy / dist) * step
    if proj.range_left <= 0:
        dead.append(proj.entity_id)
        return True
    return False


def _projectile_hit(state: GameState, proj: Projectile):
    for e in state.entities.values():
        if e is proj or not e.alive:
            continue
        # Team.NONE (neutrals/runes) are valid targets for either team's shots.
        if e.team == proj.team:
            continue
        if isinstance(e, Projectile):
            continue
        if isinstance(e, Structure) and not state.is_structure_vulnerable(e):
            continue
        if math.hypot(e.x - proj.x, e.y - proj.y) <= proj.radius + e.radius:
            return e
    return None


def _resolve_hook(state: GameState, proj: HookProjectile, hit) -> None:
    """A landed tongue hook: drag the victim toward the caster and (when the
    rider is set, i.e. Tiktik's E is learned) stun it, then leave a slow."""
    owner = state.entities.get(proj.owner_id)
    if proj.pull and owner is not None and isinstance(hit, (Hero, Minion)):
        state.pulls.append({"tgt": hit.entity_id, "to": owner.entity_id,
                            "speed": proj.pull_speed, "stop": proj.stop_dist})
    if isinstance(hit, Hero):
        if proj.stun_dur > 0:
            hit.buffs.append(make_effect(proj.stun_dur, stun=True))
        if proj.slow_dur > 0 and proj.slow_pct > 0:
            # Slow spans the stun + the after-window, so it lingers once the
            # stun ends ("stunned, then slowed").
            hit.buffs.append(
                make_effect(proj.stun_dur + proj.slow_dur, slow_pct=proj.slow_pct))


# ---------------------------------------------------------------------------
# Displacements (pulls)
# ---------------------------------------------------------------------------

def system_displacements(state: GameState, dt: float) -> None:
    """Drag each pulled unit toward its puller, dropping the pull once the unit
    is within `stop` units or either party is gone. Heroes and minions alike can
    be pulled (e.g. by Tiktik's hook)."""
    keep: list[dict] = []
    for pull in state.pulls:
        tgt = state.entities.get(pull["tgt"])
        to = state.entities.get(pull["to"])
        if (tgt is None or not tgt.alive or to is None or not to.alive):
            continue
        dx, dy = to.x - tgt.x, to.y - tgt.y
        dist = math.hypot(dx, dy)
        if dist <= pull["stop"] + to.radius:
            continue  # arrived
        step = min(pull["speed"] * dt, dist - (pull["stop"] + to.radius))
        tgt.x += (dx / dist) * step
        tgt.y += (dy / dist) * step
        tgt.x = max(tgt.radius, min(MAP_WIDTH - tgt.radius, tgt.x))
        tgt.y = max(tgt.radius, min(MAP_HEIGHT - tgt.radius, tgt.y))
        keep.append(pull)
    state.pulls = keep


# ---------------------------------------------------------------------------
# Combat (auto-attacks for heroes, minions, structures)
# ---------------------------------------------------------------------------

REVEAL_TIME = 0.4  # seconds a stealthed hero is revealed after it attacks


def system_combat(state: GameState, dt: float) -> None:
    # Snapshot: ranged attacks insert projectiles into state.entities mid-loop.
    for e in list(state.entities.values()):
        if not e.alive or e.attack_damage <= 0 or isinstance(e, Projectile):
            continue
        if isinstance(e, Hero) and e.is_disarmed():
            continue  # stunned or disarmed (e.g. Tiktik in a wall): no attacks
        if e.attack_timer > 0:
            e.attack_timer = max(0.0, e.attack_timer - dt)
            continue
        # Moving and attacking are mutually exclusive: a hero on the move holds
        # its fire (the cooldown still ticks above, so it can shoot the instant
        # it stops). Minions/towers are unaffected.
        if isinstance(e, Hero) and (e.target_x is not None or e.target_y is not None):
            continue
        target = _combat_target(state, e)
        if target is None:
            continue
        dmg = e.effective_damage() if isinstance(e, Hero) else e.attack_damage
        if getattr(e, "attack_type", "melee") == "ranged":
            _spawn_basic_projectile(state, e, target, dmg)
        else:
            state.damage_events.append(
                {"src": e.entity_id, "tgt": target.entity_id, "amt": dmg,
                 "basic": True}
            )
            # On-hit movement slow (e.g. Kapre attacking from the trees).
            if isinstance(e, Hero) and isinstance(target, Hero):
                pct, slow_dur = e.attack_slow()
                if pct > 0:
                    target.buffs.append(make_effect(slow_dur, slow_pct=pct))
        # Attacking breaks stealth for a brief moment.
        if isinstance(e, Hero) and e.is_invisible():
            e.reveal_timer = REVEAL_TIME
        e.attack_timer = (e.effective_attack_interval()
                          if isinstance(e, Hero) else e.attack_interval)


def _combat_target(state: GameState, attacker):
    """Prefer a hero's focus target (from 'A + click enemy') if it is a valid,
    in-range enemy; otherwise fall back to automatic target acquisition."""
    if isinstance(attacker, Hero) and attacker.forced_target_id is not None:
        t = state.entities.get(attacker.forced_target_id)
        if (t is not None and t.alive and t.team != attacker.team
                and not isinstance(t, Projectile)
                and not (isinstance(t, Hero) and t.is_invulnerable())
                and not (isinstance(t, Hero) and t.is_invisible() and t.reveal_timer <= 0)
                and not (isinstance(t, Structure) and not state.is_structure_vulnerable(t))
                and attacker.distance_to(t) <= attacker.effective_attack_range() + t.radius):
            return t
    return find_attack_target(state, attacker)


def _spawn_basic_projectile(state: GameState, attacker, target, dmg: int) -> None:
    proj = Projectile(
        team=attacker.team,
        x=attacker.x,
        y=attacker.y,
        radius=BASIC_PROJECTILE_RADIUS,
        damage=dmg,
        owner_id=attacker.entity_id,
        homing=True,
        target_id=target.entity_id,
        speed=getattr(attacker, "attack_proj_speed", 1000.0),
        range_left=attacker.effective_attack_range() * 3.0,
        is_basic=True,
    )
    state.entities[proj.entity_id] = proj


# ---------------------------------------------------------------------------
# Damage / death / rewards
# ---------------------------------------------------------------------------

def xp_to_next(level: int) -> int:
    return XP_BASE + (level - 1) * XP_PER_LEVEL


def _grant_xp(hero: Hero, xp: int) -> None:
    hero.xp += xp
    while hero.level < MAX_LEVEL and hero.xp >= xp_to_next(hero.level):
        hero.xp -= xp_to_next(hero.level)
        hero.level += 1
        hero.max_hp += HP_PER_LEVEL
        hero.hp += HP_PER_LEVEL
        hero.attack_damage += DAMAGE_PER_LEVEL
        hero.sp_atk += hero.sp_atk_per_level
        hero.phys_def += hero.phys_def_per_level
        hero.sp_def += hero.sp_def_per_level
        hero.skill_points += 1  # one skill point per level


def _apply_defense(target, raw: float, dtype: str) -> int:
    """Reduce raw damage by the target's matching defense via an armor curve:
    reduction = DEF / (DEF + DEFENSE_K). 'true' damage ignores defense."""
    if dtype == "true":
        return int(raw)
    if dtype == "special":
        defense = target.effective_sp_def()
    else:  # physical (default)
        defense = target.effective_phys_def()
    if defense <= 0:
        return int(raw)
    return int(raw * DEFENSE_K / (defense + DEFENSE_K))


def system_damage_death(state: GameState, dt: float) -> None:
    for ev in state.damage_events:
        tgt = state.entities.get(ev.get("tgt"))
        if tgt is None or not tgt.alive:
            continue
        if "heal" in ev:
            tgt.hp = min(tgt.max_hp, tgt.hp + ev["heal"])
            continue
        if isinstance(tgt, Structure) and not state.is_structure_vulnerable(tgt):
            continue
        if isinstance(tgt, Hero) and tgt.is_invulnerable():
            continue  # invulnerable (e.g. split upper half) takes no damage
        src = state.entities.get(ev.get("src"))
        dtype = ev.get("dtype", "physical")
        is_basic = ev.get("basic", False)
        attacker = src if isinstance(src, Hero) else None

        # Evasion: dodge incoming basic physical attacks, unless the attacker has
        # true-strike. Abilities and non-physical damage can't be dodged.
        if (isinstance(tgt, Hero) and is_basic and dtype == "physical"
                and tgt.effective_evasion() > 0
                and not (attacker is not None and attacker.has_true_strike())):
            if random.random() < tgt.effective_evasion():
                state.combat_events.append(
                    {"k": "miss", "x": round(tgt.x, 1), "y": round(tgt.y, 1),
                     "eid": tgt.entity_id})
                continue

        # Critical strike: basic attacks always roll; abilities only if they opt
        # in with "crit_ok". Multiplies the pre-mitigation amount.
        raw = ev["amt"]
        crit = False
        if attacker is not None and (is_basic or ev.get("crit_ok")):
            if random.random() < attacker.effective_crit_chance():
                crit = True
                raw = int(raw * attacker.effective_crit_mult())

        amt = _apply_defense(tgt, raw, dtype)
        if isinstance(tgt, Hero):
            amt = int(amt * (1.0 - tgt.damage_reduction()))  # flat mitigation
            amt = tgt.absorb_with_shield(amt)                # soak with shields
        if isinstance(tgt, SplitBody):
            amt = int(amt * tgt.dmg_mult)  # the lower body takes amplified damage
        tgt.hp -= amt

        # Lifesteal: heal the attacker for a fraction of the damage dealt.
        if attacker is not None and amt > 0 and attacker.alive:
            ls = attacker.effective_lifesteal()
            if ls > 0:
                attacker.hp = min(attacker.max_hp, attacker.hp + int(amt * ls))

        # Render-only hit event: damage number + flash + lunge/recoil on the
        # client. Gated to hero-involved trades so creep fights don't flood the
        # wire. `eid` = victim (also the vision key); `src` = attacker (lunge).
        if amt > 0 and (isinstance(tgt, (Hero, SplitBody, RuneCreature))
                        or isinstance(src, Hero)):
            state.combat_events.append({
                "k": "hit", "x": round(tgt.x, 1), "y": round(tgt.y, 1),
                "amt": int(amt), "eid": tgt.entity_id, "crit": crit,
                "src": ev.get("src"), "dt": dtype})
        # Effects that fizzle the moment their bearer takes damage (e.g. the
        # rune regen buff) are dropped here.
        if isinstance(tgt, Hero) and amt > 0:
            tgt.buffs[:] = [b for b in tgt.buffs if not b.get("cancel_on_hit")]
        if isinstance(tgt, Minion) and tgt.is_neutral:
            _provoke_camp(state, tgt.camp_id)  # whole camp aggros when one is hit
        if tgt.hp <= 0:
            _kill(state, tgt, ev.get("src"))
    state.damage_events.clear()

    # Remove dead minions + detached bodies (heroes respawn; structures linger).
    dead = [eid for eid, e in state.entities.items()
            if isinstance(e, (Minion, SplitBody)) and not e.alive]
    for eid in dead:
        state.entities.pop(eid, None)


def _reward(state: GameState, hero: Hero, kind: str, amt: int) -> None:
    """Record a gold/xp reward popup for the client (rendered as floating text)."""
    if amt:
        state.combat_events.append({"k": kind, 
                                    "amt": int(amt), 
                                    "x": round(hero.x, 1),
                                    "y": round(hero.y, 1), 
                                    "eid": hero.entity_id})


def _fx(state: GameState, name: str, x: float, y: float, r: float = 0.0,
        eid: int = 0, dur: float = 0.5) -> None:
    """Record a render-only effect event (AoE decal / shockwave) for the client.

    `eid` ties the event to a source entity for vision; the broadcast filter also
    reveals it by position so telegraphs show even when the caster is fogged.
    """
    state.combat_events.append({"k": "fx", "name": name,
                                "x": round(x, 1), "y": round(y, 1),
                                "r": int(r), "eid": eid, "dur": dur})


def _provoke_camp(state: GameState, camp_id: int) -> None:
    """Mark every monster in a camp as provoked so the whole camp fights back."""
    if camp_id < 0:
        return
    for e in state.entities.values():
        if isinstance(e, Minion) and e.is_neutral and e.camp_id == camp_id:
            e.provoked = True


def _award_minion_bounty(state: GameState, victim: Minion, killer) -> None:
    """Last-hit economy: the killer (if a hero) gets full gold; other allied
    heroes near the dying minion get a gold share; all nearby allied heroes get
    full XP regardless of who last-hit. Bounty values come from the minion type.
    Neutral (jungle) kills only reward the killer's team."""
    gold, xp = victim.gold_value, victim.xp_value
    if victim.is_neutral:
        if not isinstance(killer, Hero):
            return  # neutral killed by a tower/minion: no hero benefits
        beneficiary = killer.team
    else:
        beneficiary = enemy_team(victim.team)

    if isinstance(killer, Hero) and killer.team == beneficiary:
        killer.gold += gold
        _reward(state, killer, "gold", gold)
    share = int(gold * MINION_ASSIST_GOLD_FRACTION)
    for hero in state.heroes():
        if not hero.alive or hero.team != beneficiary:
            continue
        d = hero.distance_to(victim)
        # Gold share to nearby allies who did NOT land the last hit.
        if (hero is not killer and share > 0
                and d <= GOLD_SHARE_RADIUS + victim.radius):
            hero.gold += share
            _reward(state, hero, "gold", share)
        # XP is awarded in full to every nearby allied hero (incl. the killer).
        if d <= XP_SHARE_RADIUS + victim.radius:
            _grant_xp(hero, xp)
            _reward(state, hero, "xp", xp)


def _kill(state: GameState, victim, src_id) -> None:
    victim.alive = False
    victim.hp = 0
    killer = state.entities.get(src_id) if src_id is not None else None

    # Destroying a Manananggal's detached lower body kills the owning hero.
    if isinstance(victim, SplitBody):
        owner = state.entities.get(victim.owner_id)
        if isinstance(owner, Hero) and owner.alive:
            owner.ability_state.pop("split", None)
            _kill(state, owner, src_id)
        return

    if isinstance(victim, Hero):
        # Dying while split: clean up the detached body too.
        st = victim.ability_state.pop("split", None)
        if st is not None:
            body = state.entities.get(st.get("body_id"))
            if body is not None:
                body.alive = False
                state.entities.pop(body.entity_id, None)
        release_bind(victim)  # dying inside a tree/wall drops the bind
        victim.reveal_timer = 0.0
        victim.respawn_timer = HERO_RESPAWN_BASE + victim.level * HERO_RESPAWN_PER_LEVEL
        victim.target_x = victim.target_y = None
        victim.attack_move = False
        victim.attack_move_x = victim.attack_move_y = None
        victim.buffs.clear()
        kteam = killer.team if killer is not None else None
        if kteam is not None and kteam != victim.team and kteam in state.team_kills:
            state.team_kills[kteam] += 1
        if isinstance(killer, Hero) and killer.team != victim.team:
            killer.gold += HERO_KILL_GOLD
            _grant_xp(killer, HERO_KILL_XP)
            _reward(state, killer, "gold", HERO_KILL_GOLD)
            _reward(state, killer, "xp", HERO_KILL_XP)
    elif isinstance(victim, Minion):
        _award_minion_bounty(state, victim, killer)
        # Credit the hero's creep score: jungle/rune kills count as neutral,
        # lane creeps as minion last-hits.
        if isinstance(killer, Hero):
            if victim.is_neutral:
                killer.neutral_kills += 1
            else:
                killer.minion_kills += 1
        # A slain rune also grants its killer a timed buff.
        if isinstance(victim, RuneCreature) and isinstance(killer, Hero):
            apply_rune_buff(killer, victim.rune_buff)
    elif isinstance(victim, Structure):
        if isinstance(killer, Hero):
            killer.gold += STRUCTURE_GOLD
            _reward(state, killer, "gold", STRUCTURE_GOLD)


# ---------------------------------------------------------------------------
# Per-hero tick hooks (stateful abilities)
# ---------------------------------------------------------------------------

def system_summons(state: GameState, dt: float) -> None:
    """Tick player-summoned creatures: age them out and steer them toward their
    assigned target (falling back to the nearest enemy) so the shared minion
    movement/combat systems carry them the rest of the way."""
    dead: list[int] = []
    for e in state.entities.values():
        if not isinstance(e, SummonedMinion) or not e.alive:
            continue
        e.lifetime -= dt
        if e.lifetime <= 0:
            dead.append(e.entity_id)
            continue
        tgt = state.entities.get(e.forced_target_id) if e.forced_target_id else None
        if tgt is None or not tgt.alive or tgt.team == e.team:
            tgt = find_attack_target(state, e)
        if tgt is not None:
            e.dest_x, e.dest_y = tgt.x, tgt.y
    for eid in dead:
        state.entities.pop(eid, None)


def system_hero_hooks(state: GameState, dt: float) -> None:
    """Run each hero definition's optional on_tick hook (e.g. the Manananggal
    split leash + auto-recombine). Runs after movement so position clamps stick."""
    for hero in state.heroes():
        hd = hero.hero_def
        if hd is not None and getattr(hd, "on_tick", None) is not None:
            hd.on_tick(state, hero, dt)


# ---------------------------------------------------------------------------
# Spawn-point regen zones
# ---------------------------------------------------------------------------

SPAWN_ZONE_HP_PER_SEC = 80.0    # fast hp regen at your own spawn
SPAWN_ZONE_MP_PER_SEC = 50.0
SPAWN_ZONE_DPS = 80.0           # enemies inside take this much true damage/sec


def system_spawn_zone(state: GameState, dt: float) -> None:
    """Heroes standing in their own spawn zone regenerate quickly; enemy units
    inside it are burned at the same rate (so you can't camp the enemy base)."""
    if SPAWN_ZONE_RADIUS <= 0:
        return
    heal = int(SPAWN_ZONE_HP_PER_SEC * dt) or 1
    mana = int(SPAWN_ZONE_MP_PER_SEC * dt) or 1
    burn = int(SPAWN_ZONE_DPS * dt) or 1
    for team_int, (cx, cy) in SPAWN_POSITIONS.items():
        team = Team(team_int)
        for e in state.entities.values():
            if not e.alive or isinstance(e, (Structure, Projectile)):
                continue
            if math.hypot(e.x - cx, e.y - cy) > SPAWN_ZONE_RADIUS:
                continue
            if isinstance(e, Hero) and e.team == team:
                e.hp = min(e.max_hp, e.hp + heal)
                e.mana = min(e.max_mana, e.mana + mana)
            elif e.team != team and e.team != Team.NONE:
                state.damage_events.append(
                    {"src": None, "tgt": e.entity_id, "amt": burn, "dtype": "true"})


# ---------------------------------------------------------------------------
# Economy
# ---------------------------------------------------------------------------

def system_economy(state: GameState, dt: float) -> None:
    state.econ_accum += dt
    while state.econ_accum >= 1.0:
        state.econ_accum -= 1.0
        for hero in state.heroes():
            if hero.alive:
                hero.gold += int(PASSIVE_GOLD_PER_SEC)


# ---------------------------------------------------------------------------
# Respawn
# ---------------------------------------------------------------------------

def system_respawn(state: GameState, dt: float) -> None:
    for hero in state.heroes():
        if hero.alive:
            continue
        hero.respawn_timer -= dt
        if hero.respawn_timer <= 0:
            spawn = SPAWN_POSITIONS[int(hero.team)]
            hero.x, hero.y = spawn[0], spawn[1]
            hero.hp = hero.max_hp
            hero.mana = hero.max_mana
            hero.alive = True
            hero.respawn_timer = 0.0
            hero.target_x = hero.target_y = None
            hero.attack_move = False
            hero.attack_move_x = hero.attack_move_y = None


# ---------------------------------------------------------------------------
# Win check
# ---------------------------------------------------------------------------

def system_win_check(state: GameState, dt: float) -> None:
    if state.winner is not None:
        return
    for team, kills in state.team_kills.items():
        if kills >= state.kill_target:
            _finish(state, team)
            return
    for team_int in (1, 2):
        team = Team(team_int)
        core = state.core_of(team)
        if core is None or not core.alive:
            _finish(state, enemy_team(team))
            return


def _finish(state: GameState, winner: Team) -> None:
    state.winner = winner
    state.phase = GamePhase.FINISHED


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def step(state: GameState, dt: float) -> None:
    """Run one full simulation tick in dependency order."""
    state.combat_events.clear()  # one-shot reward popups for this tick
    system_clock(state, dt)
    system_status(state, dt)
    system_spawn_creeps(state, dt)
    system_neutral_camps(state, dt)
    system_runes(state, dt)
    system_summons(state, dt)
    system_movement(state, dt)
    system_ability_cast(state, dt)
    system_collision(state, dt)
    system_hero_hooks(state, dt)
    system_projectiles(state, dt)
    system_displacements(state, dt)
    system_combat(state, dt)
    system_spawn_zone(state, dt)
    system_damage_death(state, dt)
    system_economy(state, dt)
    system_respawn(state, dt)
    system_win_check(state, dt)
