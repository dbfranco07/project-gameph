"""Reusable ability "building blocks".

Each hero ability in `data/heroes.py` names a `kind` here. A block reads the ability
parameters + a cast target and mutates `GameState` (spawns a projectile, queues damage
or healing, moves the caster, applies a buff). Adding a new hero is usually just data;
adding a genuinely new mechanic means adding one block here.

All blocks share the signature:
    cast(state, caster, ability, tx, ty, tid) -> None
where (tx, ty) is the targeted world point and tid is an optional target entity id.
"""

from __future__ import annotations

import math

from shared.config import MAP_WIDTH, MAP_HEIGHT
from server.entity import Hero, Projectile, Structure


def _enemies_in_radius(state, team, cx, cy, radius):
    out = []
    for e in state.entities.values():
        if not e.alive or e.team == team or e.team.value == 0:
            continue
        if math.hypot(e.x - cx, e.y - cy) <= radius + e.radius:
            out.append(e)
    return out


def _allies_in_radius(state, team, cx, cy, radius):
    out = []
    for e in state.entities.values():
        if not e.alive or e.team != team:
            continue
        if isinstance(e, Structure):
            continue
        if math.hypot(e.x - cx, e.y - cy) <= radius + e.radius:
            out.append(e)
    return out


def cast_projectile(state, caster, ab, tx, ty, tid):
    dx, dy = tx - caster.x, ty - caster.y
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        dx, dy, dist = 1.0, 0.0, 1.0
    speed = ab["speed"]
    proj = Projectile(
        team=caster.team,
        x=caster.x,
        y=caster.y,
        radius=ab.get("radius", 18),
        vx=(dx / dist) * speed,
        vy=(dy / dist) * speed,
        damage=ab["dmg"],
        owner_id=caster.entity_id,
        range_left=ab["range"],
    )
    state.entities[proj.entity_id] = proj


def cast_dash(state, caster, ab, tx, ty, tid):
    dx, dy = tx - caster.x, ty - caster.y
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return
    step = min(ab["dist"], dist)
    caster.x += (dx / dist) * step
    caster.y += (dy / dist) * step
    caster.x = max(caster.radius, min(MAP_WIDTH - caster.radius, caster.x))
    caster.y = max(caster.radius, min(MAP_HEIGHT - caster.radius, caster.y))


def cast_area_dmg(state, caster, ab, tx, ty, tid):
    for e in _enemies_in_radius(state, caster.team, tx, ty, ab["radius"]):
        state.damage_events.append(
            {"src": caster.entity_id, "tgt": e.entity_id, "amt": ab["dmg"]}
        )


def cast_area_heal(state, caster, ab, tx, ty, tid):
    cx = tx if (tx or ty) else caster.x
    cy = ty if (tx or ty) else caster.y
    for e in _allies_in_radius(state, caster.team, cx, cy, ab["radius"]):
        state.damage_events.append({"tgt": e.entity_id, "heal": ab["heal"]})


def cast_target_dmg(state, caster, ab, tx, ty, tid):
    target = state.entities.get(tid) if tid else None
    if target is None or not target.alive or target.team == caster.team:
        return
    if caster.distance_to(target) <= ab["range"] + target.radius:
        state.damage_events.append(
            {"src": caster.entity_id, "tgt": target.entity_id, "amt": ab["dmg"]}
        )


def cast_buff(state, caster, ab, tx, ty, tid):
    buff = {
        "speed_bonus": ab.get("speed_bonus", 0),
        "dmg_bonus": ab.get("dmg_bonus", 0),
        "remaining": ab["duration"],
    }
    radius = ab.get("radius", 0)
    if radius and radius > 0:
        for e in _allies_in_radius(state, caster.team, caster.x, caster.y, radius):
            if isinstance(e, Hero):
                e.buffs.append(dict(buff))
    else:
        caster.buffs.append(dict(buff))


ABILITY_KINDS = {
    "projectile": cast_projectile,
    "dash": cast_dash,
    "area_dmg": cast_area_dmg,
    "area_heal": cast_area_heal,
    "target_dmg": cast_target_dmg,
    "buff": cast_buff,
}
