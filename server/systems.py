"""Game systems — plain functions called each server tick.

The whole simulation is an ordered pipeline of pure-ish functions over GameState.
`step()` runs them in order; adding a mechanic means adding a function and slotting
it into `step()`. This is the extension point the whole design leans on.
"""

from __future__ import annotations

import math

from shared.config import (
    MAP_WIDTH,
    MAP_HEIGHT,
    SPAWN_POSITIONS,
    LANE_Y,
    HERO_RESPAWN_BASE,
    HERO_RESPAWN_PER_LEVEL,
    HERO_KILL_GOLD,
    HERO_KILL_XP,
    MINION_GOLD,
    MINION_XP,
    STRUCTURE_GOLD,
    PASSIVE_GOLD_PER_SEC,
    MANA_REGEN_PER_SEC,
    MAX_LEVEL,
    XP_BASE,
    XP_PER_LEVEL,
    HP_PER_LEVEL,
    DAMAGE_PER_LEVEL,
    CREEP_WAVE_INTERVAL,
    CREEP_WAVE_SIZE,
    BASIC_PROJECTILE_RADIUS,
)
from shared.game_types import EntityType, Team, GamePhase
from server.entity import Hero, Minion, Structure, Projectile
from server.game_state import GameState, enemy_team
from server.abilities import ABILITY_KINDS


# ---------------------------------------------------------------------------
# Targeting
# ---------------------------------------------------------------------------

# Per-attacker target preference: lower number = higher priority. A category
# absent from the map means "never auto-attack that type".
_PRIORITY = {
    "minion": {EntityType.MINION: 0, EntityType.HERO: 1, EntityType.TOWER: 2, EntityType.BASE: 2},
    "structure": {EntityType.MINION: 0, EntityType.HERO: 1},
    "hero": {EntityType.HERO: 0, EntityType.MINION: 1, EntityType.TOWER: 2, EntityType.BASE: 2},
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
    order = _PRIORITY[_attacker_kind(attacker)]
    best = None
    best_key = None
    for e in state.entities.values():
        if e is attacker or not e.alive:
            continue
        if e.team == attacker.team or e.team == Team.NONE:
            continue
        if isinstance(e, Projectile):
            continue
        prio = order.get(e.entity_type)
        if prio is None:
            continue
        if isinstance(e, Structure) and not state.is_structure_vulnerable(e):
            continue
        d = attacker.distance_to(e)
        if d > attacker.attack_range + e.radius:
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
        if hero.buffs:
            for b in hero.buffs:
                b["remaining"] -= dt
            hero.buffs[:] = [b for b in hero.buffs if b["remaining"] > 0]
        if hero.alive and hero.mana < hero.max_mana:
            hero.mana = min(hero.max_mana, int(hero.mana + MANA_REGEN_PER_SEC * dt + 0.999))


# ---------------------------------------------------------------------------
# Creeps
# ---------------------------------------------------------------------------

def system_spawn_creeps(state: GameState, dt: float) -> None:
    state.creep_timer -= dt
    if state.creep_timer > 0:
        return
    state.creep_timer = CREEP_WAVE_INTERVAL
    _spawn_wave(state)


def _spawn_wave(state: GameState) -> None:
    for team_int in (1, 2):
        team = Team(team_int)
        spawn = SPAWN_POSITIONS[team_int]
        dest = SPAWN_POSITIONS[int(enemy_team(team))]
        direction = 1 if dest[0] > spawn[0] else -1
        for i in range(CREEP_WAVE_SIZE):
            minion = Minion(
                team=team,
                x=spawn[0] + direction * (i * 35) - direction * 60,
                y=LANE_Y,
                dest_x=dest[0],
                dest_y=LANE_Y,
            )
            state.entities[minion.entity_id] = minion


# ---------------------------------------------------------------------------
# Movement
# ---------------------------------------------------------------------------

def system_movement(state: GameState, dt: float) -> None:
    """Heroes move toward click targets; minions walk the lane unless fighting."""
    for entity in state.entities.values():
        if not entity.alive:
            continue
        if isinstance(entity, Hero):
            _update_focus_chase(state, entity)
            entity.move_toward_target(dt)
            entity.x = max(entity.radius, min(MAP_WIDTH - entity.radius, entity.x))
            entity.y = max(entity.radius, min(MAP_HEIGHT - entity.radius, entity.y))
        elif isinstance(entity, Minion):
            if find_attack_target(state, entity) is None:
                entity.advance(dt)


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
    in_range = hero.distance_to(target) <= hero.attack_range + target.radius
    if in_range:
        hero.target_x = hero.target_y = None  # stand and attack
    else:
        hero.target_x, hero.target_y = target.x, target.y  # close the gap


# ---------------------------------------------------------------------------
# Abilities
# ---------------------------------------------------------------------------

def system_ability_cast(state: GameState, dt: float) -> None:
    for cast in state.ability_casts:
        caster = state.entities.get(cast["caster"])
        if not isinstance(caster, Hero) or not caster.alive:
            continue
        ab = caster.ability_by_key(cast["key"])
        if ab is None:
            continue
        if caster.cooldowns.get(ab["key"], 0.0) > 0:
            continue
        if caster.mana < ab["mana"]:
            continue
        fn = ABILITY_KINDS.get(ab["kind"])
        if fn is None:
            continue
        caster.mana -= ab["mana"]
        caster.cooldowns[ab["key"]] = ab["cd"]
        fn(state, caster, ab, cast.get("tx", 0.0), cast.get("ty", 0.0), cast.get("tid"))
    state.ability_casts.clear()


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
                    {"src": proj.owner_id, "tgt": hit.entity_id, "amt": proj.damage}
                )
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
            {"src": proj.owner_id, "tgt": target.entity_id, "amt": proj.damage}
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
        if e.team == proj.team or e.team == Team.NONE:
            continue
        if isinstance(e, Projectile):
            continue
        if isinstance(e, Structure) and not state.is_structure_vulnerable(e):
            continue
        if math.hypot(e.x - proj.x, e.y - proj.y) <= proj.radius + e.radius:
            return e
    return None


# ---------------------------------------------------------------------------
# Combat (auto-attacks for heroes, minions, structures)
# ---------------------------------------------------------------------------

def system_combat(state: GameState, dt: float) -> None:
    # Snapshot: ranged attacks insert projectiles into state.entities mid-loop.
    for e in list(state.entities.values()):
        if not e.alive or e.attack_damage <= 0 or isinstance(e, Projectile):
            continue
        if e.attack_timer > 0:
            e.attack_timer = max(0.0, e.attack_timer - dt)
            continue
        target = _combat_target(state, e)
        if target is None:
            continue
        dmg = e.effective_damage() if isinstance(e, Hero) else e.attack_damage
        if getattr(e, "attack_type", "melee") == "ranged":
            _spawn_basic_projectile(state, e, target, dmg)
        else:
            state.damage_events.append(
                {"src": e.entity_id, "tgt": target.entity_id, "amt": dmg}
            )
        e.attack_timer = e.attack_interval


def _combat_target(state: GameState, attacker):
    """Prefer a hero's focus target (from 'A + click enemy') if it is a valid,
    in-range enemy; otherwise fall back to automatic target acquisition."""
    if isinstance(attacker, Hero) and attacker.forced_target_id is not None:
        t = state.entities.get(attacker.forced_target_id)
        if (t is not None and t.alive and t.team != attacker.team
                and not isinstance(t, Projectile)
                and not (isinstance(t, Structure) and not state.is_structure_vulnerable(t))
                and attacker.distance_to(t) <= attacker.attack_range + t.radius):
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
        range_left=attacker.attack_range * 3.0,
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
        tgt.hp -= ev["amt"]
        if tgt.hp <= 0:
            _kill(state, tgt, ev.get("src"))
    state.damage_events.clear()

    # Remove dead minions (heroes respawn; structures linger as rubble).
    dead = [eid for eid, e in state.entities.items()
            if isinstance(e, Minion) and not e.alive]
    for eid in dead:
        state.entities.pop(eid, None)


def _kill(state: GameState, victim, src_id) -> None:
    victim.alive = False
    victim.hp = 0
    killer = state.entities.get(src_id) if src_id is not None else None

    if isinstance(victim, Hero):
        victim.respawn_timer = HERO_RESPAWN_BASE + victim.level * HERO_RESPAWN_PER_LEVEL
        victim.target_x = victim.target_y = None
        victim.buffs.clear()
        kteam = killer.team if killer is not None else None
        if kteam is not None and kteam != victim.team and kteam in state.team_kills:
            state.team_kills[kteam] += 1
        if isinstance(killer, Hero) and killer.team != victim.team:
            killer.gold += HERO_KILL_GOLD
            _grant_xp(killer, HERO_KILL_XP)
    elif isinstance(victim, Minion):
        if isinstance(killer, Hero):
            killer.gold += MINION_GOLD
            _grant_xp(killer, MINION_XP)
    elif isinstance(victim, Structure):
        if isinstance(killer, Hero):
            killer.gold += STRUCTURE_GOLD


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
    system_status(state, dt)
    system_spawn_creeps(state, dt)
    system_movement(state, dt)
    system_ability_cast(state, dt)
    system_projectiles(state, dt)
    system_combat(state, dt)
    system_damage_death(state, dt)
    system_economy(state, dt)
    system_respawn(state, dt)
    system_win_check(state, dt)
