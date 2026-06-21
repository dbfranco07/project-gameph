"""Reusable skill building blocks, composed by per-hero ability code.

Each function takes a `CastContext` (`ctx`) plus parameters and mutates the game
state, **returning** what it created/affected so a hero can customize further —
e.g. `p = projectile(ctx, dmg=95, ...); p.homing = True`, or `blink(ctx, 320);
stun_nearby(ctx, 150, 0.5)` to make an otherwise-shared blink unique.

These are deliberately small and parameterized. A hero's uniqueness lives in how
it combines and tweaks them, in its own file under `server/heroes/`.
"""

from __future__ import annotations

import math

from shared.config import MAP_WIDTH, MAP_HEIGHT
from server.entity import Hero, Projectile, Structure
from server.effects import make_effect


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def enemies_in_radius(state, team, cx, cy, radius):
    out = []
    for e in state.entities.values():
        if not e.alive or e.team == team or e.team.value == 0:
            continue
        if isinstance(e, Projectile):
            continue
        if math.hypot(e.x - cx, e.y - cy) <= radius + e.radius:
            out.append(e)
    return out


def allies_in_radius(state, team, cx, cy, radius):
    out = []
    for e in state.entities.values():
        if not e.alive or e.team != team:
            continue
        if isinstance(e, (Structure, Projectile)):
            continue
        if math.hypot(e.x - cx, e.y - cy) <= radius + e.radius:
            out.append(e)
    return out


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def projectile(ctx, dmg, speed, range, radius=18, homing=False,
               dtype="physical") -> Projectile:
    """Fire a projectile from the caster toward (tx, ty). Returns it for tweaks."""
    caster = ctx.caster
    dx, dy = ctx.tx - caster.x, ctx.ty - caster.y
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        dx, dy, dist = 1.0, 0.0, 1.0
    proj = Projectile(
        team=caster.team,
        x=caster.x,
        y=caster.y,
        radius=radius,
        vx=(dx / dist) * speed,
        vy=(dy / dist) * speed,
        damage=dmg,
        damage_type=dtype,
        owner_id=caster.entity_id,
        range_left=range,
        speed=speed,
        homing=homing,
    )
    ctx.state.entities[proj.entity_id] = proj
    return proj


def dash(ctx, dist) -> Hero:
    """Move the caster up to `dist` units toward (tx, ty). Returns the caster."""
    caster = ctx.caster
    dx, dy = ctx.tx - caster.x, ctx.ty - caster.y
    d = math.hypot(dx, dy)
    if d >= 1e-6:
        step = min(dist, d)
        caster.x += (dx / d) * step
        caster.y += (dy / d) * step
        caster.x = max(caster.radius, min(MAP_WIDTH - caster.radius, caster.x))
        caster.y = max(caster.radius, min(MAP_HEIGHT - caster.radius, caster.y))
    return caster


# A blink is just a dash; heroes give it personality by what they pair it with.
blink = dash


def area_dmg(ctx, dmg, radius, dtype="physical") -> list:
    """Damage all enemies within `radius` of (tx, ty). Returns those hit."""
    hit = enemies_in_radius(ctx.state, ctx.caster.team, ctx.tx, ctx.ty, radius)
    for e in hit:
        ctx.state.damage_events.append(
            {"src": ctx.caster.entity_id, 
             "tgt": e.entity_id, 
             "amt": dmg,
             "dtype": dtype})
    return hit


def area_heal(ctx, heal, radius) -> list:
    """Heal all allies within `radius` of the target point (or the caster)."""
    cx = ctx.tx if (ctx.tx or ctx.ty) else ctx.caster.x
    cy = ctx.ty if (ctx.tx or ctx.ty) else ctx.caster.y
    healed = allies_in_radius(ctx.state, ctx.caster.team, cx, cy, radius)
    for e in healed:
        ctx.state.damage_events.append({"tgt": e.entity_id, "heal": heal})
    return healed


def target_dmg(ctx, dmg, range, dtype="physical") -> object | None:
    """Damage a single targeted enemy if it is valid and within `range`."""
    target = ctx.state.entities.get(ctx.tid) if ctx.tid else None
    if target is None or not target.alive or target.team == ctx.caster.team:
        return None
    if ctx.caster.distance_to(target) <= range + target.radius:
        ctx.state.damage_events.append(
            {"src": ctx.caster.entity_id, "tgt": target.entity_id, "amt": dmg,
             "dtype": dtype})
        return target
    return None


def buff(ctx, duration, speed_bonus=0, dmg_bonus=0, radius=0) -> list:
    """Apply a temporary speed/damage buff to the caster (or allies in radius)."""
    base = {"speed_bonus": speed_bonus, 
            "dmg_bonus": dmg_bonus,
            "remaining": duration}
    if radius and radius > 0:
        targets = [e for e in allies_in_radius(
            ctx.state, ctx.caster.team, ctx.caster.x, ctx.caster.y, radius
        ) if isinstance(e, Hero)]
    else:
        targets = [ctx.caster]
    for e in targets:
        e.buffs.append(dict(base))
    return targets


def dash_to_target(ctx, dist) -> Hero:
    """Dash up to `dist` toward the targeted unit's current position (falls back
    to the cursor point if no unit was targeted)."""
    target = ctx.state.entities.get(ctx.tid) if ctx.tid else None
    if target is not None:
        ctx.tx, ctx.ty = target.x, target.y
    return dash(ctx, dist)


def apply_effect(target, duration, source=None, **mods) -> None:
    """Apply a generic buff/debuff (any recognized effect key) to one hero.

    Sign of each value decides buff vs debuff. Non-heroes are ignored (only
    heroes carry effects today)."""
    if isinstance(target, Hero):
        target.buffs.append(make_effect(duration, source=source, **mods))


def slow(ctx, target, pct, duration) -> None:
    """Apply a movement slow to a single enemy (heroes carry the debuff)."""
    apply_effect(target, duration, slow_pct=pct)


def silence(ctx, target, duration) -> None:
    """Silence a single enemy hero (cannot cast abilities) for `duration`."""
    apply_effect(target, duration, silence=True)


def stun_target(ctx, target, duration) -> None:
    """Stun a single enemy hero (cannot move / attack / cast) for `duration`."""
    apply_effect(target, duration, stun=True)


def stun_nearby(ctx, radius, duration) -> list:
    """Stun enemy heroes within `radius` of the caster (can't move/attack)."""
    stunned = [e for e in enemies_in_radius(
        ctx.state, ctx.caster.team, ctx.caster.x, ctx.caster.y, radius)
        if isinstance(e, Hero)]
    for e in stunned:
        apply_effect(e, duration, stun=True)
    return stunned
