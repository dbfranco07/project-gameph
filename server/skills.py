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

import random

from shared.config import MAP_WIDTH, MAP_HEIGHT
from shared.geometry import closest_point_on_segment
from server.entity import (
    Hero, Projectile, HookProjectile, Structure, Minion, SummonedMinion,
    GroundItem,
)
from server.status import Slow, Silence, Stun, make_status
from server.targeting import (
    is_attackable, is_hostile_team, is_valid_attack_target)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def enemies_in_radius(state, team, cx, cy, radius):
    out = []
    for e in state.entities.values():
        # Teamless units (Team.NONE: neutrals/runes) are hostile to everyone,
        # but terrain also sits at Team.NONE and must never be swept up: an
        # obstacle's radius is half its capsule length, so a tree would be
        # "in radius" from hundreds of units away.
        if not is_attackable(state, e) or not is_hostile_team(team, e):
            continue
        if math.hypot(e.x - cx, e.y - cy) <= radius + e.radius:
            out.append(e)
    return out


def nearest_enemy(state, team, cx, cy, radius, toward=None):
    """Nearest non-structure enemy within `radius` of (cx, cy), or None. Ranked
    by distance to `toward` (a point) when given, else to (cx, cy) — so a skill
    can gather candidates around the caster but prefer the one under the cursor.
    Reuses `enemies_in_radius` (skips allies, projectiles, teamless units)."""
    rx, ry = toward if toward is not None else (cx, cy)
    best, best_d = None, None
    for e in enemies_in_radius(state, team, cx, cy, radius):
        if isinstance(e, Structure):
            continue
        d = math.hypot(e.x - rx, e.y - ry)
        if best_d is None or d < best_d:
            best, best_d = e, d
    return best


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
               dtype="physical", kind="") -> Projectile:
    """Fire a projectile from the caster toward (tx, ty). Returns it for tweaks.

    `kind` is a render-only art selector (e.g. "ranger_q") the client uses to
    draw a hero/skill-specific projectile; "" keeps the generic look."""
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
        kind=kind,
        own=caster.entity_id,
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
    # Teleporting cancels any in-flight move/attack-move order so the hero stops
    # at the blink spot instead of drifting back toward a stale destination.
    caster.target_x = caster.target_y = None
    caster.attack_move = False
    caster.attack_move_x = caster.attack_move_y = None
    return caster


# A blink is just a dash; heroes give it personality by what they pair it with.
blink = dash


def hook(ctx, dmg, speed, range, radius=22, dtype="physical", pull=True,
         stop_dist=120, pull_speed=900, stun_dur=0.0, slow_dur=0.0,
         slow_pct=0.0, kind="") -> HookProjectile:
    """Fire a grabbing skillshot toward (tx, ty). On hitting the first enemy unit
    it damages, optionally drags the victim toward the caster (see
    system_displacements) and optionally stuns-then-slows. With ``pull=False`` it
    is just a damaging (and optionally stunning) bolt. Returns it for tweaks."""
    caster = ctx.caster
    dx, dy = ctx.tx - caster.x, ctx.ty - caster.y
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        dx, dy, dist = 1.0, 0.0, 1.0
    proj = HookProjectile(
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
        pull=pull,
        stop_dist=stop_dist,
        pull_speed=pull_speed,
        stun_dur=stun_dur,
        slow_dur=slow_dur,
        slow_pct=slow_pct,
        kind=kind,
        own=caster.entity_id,
    )
    ctx.state.entities[proj.entity_id] = proj
    return proj


def grapple(ctx, speed, range, radius=20, pull_speed=1200, stop_dist=70,
            kind="") -> HookProjectile:
    """Fire a self-hook toward (tx, ty). On striking the first wall / tree /
    structure along its path it anchors there and reels the *caster* to it (see
    _grapple_hit / system_displacements). Misses simply fizzle. Returns it."""
    caster = ctx.caster
    dx, dy = ctx.tx - caster.x, ctx.ty - caster.y
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        dx, dy, dist = 1.0, 0.0, 1.0
    proj = HookProjectile(
        team=caster.team,
        x=caster.x,
        y=caster.y,
        radius=radius,
        vx=(dx / dist) * speed,
        vy=(dy / dist) * speed,
        damage=0,
        owner_id=caster.entity_id,
        range_left=range,
        speed=speed,
        pull=True,
        self_pull=True,
        anchor_terrain=True,
        pull_speed=pull_speed,
        stop_dist=stop_dist,
        kind=kind,
        own=caster.entity_id,
    )
    ctx.state.entities[proj.entity_id] = proj
    return proj


def pull_to(state, target, owner, speed, stop) -> None:
    """Queue a displacement that drags `target` toward `owner` each tick until it
    is within `stop` units (resolved by system_displacements)."""
    state.pulls.append({"tgt": target.entity_id, "to": owner.entity_id,
                        "speed": speed, "stop": stop})


def _emit_fx(ctx, name, cx, cy, radius) -> None:
    """Record a render-only AoE effect event (ground decal / shockwave). Emitted
    straight onto combat_events to avoid a circular import with systems."""
    if name:
        ctx.state.combat_events.append(
            {"k": "fx", "name": name, "x": round(cx, 1), "y": round(cy, 1),
             "r": int(radius), "eid": ctx.caster.entity_id, "dur": 0.5})


def area_dmg(ctx, dmg, radius, dtype="physical", fx="") -> list:
    """Damage all enemies within `radius` of (tx, ty). Returns those hit.

    `fx` names a client AoE animation (e.g. "smash") drawn at the impact point."""
    _emit_fx(ctx, fx, ctx.tx, ctx.ty, radius)
    hit = enemies_in_radius(ctx.state, ctx.caster.team, ctx.tx, ctx.ty, radius)
    for e in hit:
        ctx.state.damage_events.append(
            {"src": ctx.caster.entity_id,
             "tgt": e.entity_id,
             "amt": dmg,
             "dtype": dtype})
    return hit


def area_heal(ctx, heal, radius, fx="") -> list:
    """Heal all allies within `radius` of the target point (or the caster)."""
    cx = ctx.tx if (ctx.tx or ctx.ty) else ctx.caster.x
    cy = ctx.ty if (ctx.tx or ctx.ty) else ctx.caster.y
    _emit_fx(ctx, fx, cx, cy, radius)
    healed = allies_in_radius(ctx.state, ctx.caster.team, cx, cy, radius)
    for e in healed:
        ctx.state.damage_events.append({"tgt": e.entity_id, "heal": heal})
    return healed


def target_dmg(ctx, dmg, range, dtype="physical") -> object | None:
    """Damage a single targeted enemy if it is valid and within `range`."""
    target = ctx.state.entities.get(ctx.tid) if ctx.tid else None
    # check_vision=False: abilities are not fog-gated today (only auto-attack
    # acquisition is), so this only adds the team/terrain/invulnerability rules.
    if target is None or not is_valid_attack_target(
            ctx.state, ctx.caster, target, check_vision=False):
        return None
    if ctx.caster.distance_to(target) <= range + target.radius:
        ctx.state.damage_events.append(
            {"src": ctx.caster.entity_id, "tgt": target.entity_id, "amt": dmg,
             "dtype": dtype})
        return target
    return None


def buff(ctx, duration, speed_bonus=0, dmg_bonus=0, radius=0, source="buff") -> list:
    """Apply a temporary speed/damage buff to the caster (or allies in radius)."""
    if radius and radius > 0:
        targets = [e for e in allies_in_radius(
            ctx.state, ctx.caster.team, ctx.caster.x, ctx.caster.y, radius
        ) if isinstance(e, Hero)]
    else:
        targets = [ctx.caster]
    for e in targets:
        # Built through the same constructor as every other effect, so it gets a
        # source tag and an original duration — this used to hand-roll a bare
        # dict, which left the HUD without a timer ring to draw.
        e.statuses.add(make_status(duration, source=source,
                                   speed_bonus=speed_bonus,
                                   dmg_bonus=dmg_bonus), ctx.state)
    return targets


def dash_to_target(ctx, dist) -> Hero:
    """Dash up to `dist` toward the targeted unit's current position (falls back
    to the cursor point if no unit was targeted)."""
    target = ctx.state.entities.get(ctx.tid) if ctx.tid else None
    if target is not None:
        ctx.tx, ctx.ty = target.x, target.y
    return dash(ctx, dist)


def apply_status(target, status, state=None):
    """Attach an already-built `Status` to one unit.

    Heroes, minions and neutrals all carry statuses; anything else (structures,
    projectiles) is ignored. Effects a unit can't act on (a silence on a minion)
    are harmless no-ops."""
    if isinstance(target, (Hero, Minion)):
        return target.statuses.add(status, state)
    return None


def apply_effect(target, duration, source=None, state=None, **mods) -> None:
    """Apply a generic buff/debuff described by keyword properties.

    Sign of each value decides buff vs debuff. Unknown property names raise
    rather than being silently ignored — see `server.status.factory`."""
    apply_status(target, make_status(duration, source=source, **mods), state)


def slow(ctx, target, pct, duration) -> None:
    """Apply a movement slow to a single enemy unit."""
    apply_status(target, Slow(duration, pct), ctx.state if ctx else None)


def silence(ctx, target, duration) -> None:
    """Silence a single enemy hero (cannot cast abilities) for `duration`."""
    apply_status(target, Silence(duration), ctx.state if ctx else None)


def stun_target(ctx, target, duration) -> None:
    """Stun a single enemy hero (cannot move / attack / cast) for `duration`."""
    apply_status(target, Stun(duration), ctx.state if ctx else None)


def stun_nearby(ctx, radius, duration) -> list:
    """Stun enemy units within `radius` of the caster (can't move/attack)."""
    stunned = [e for e in enemies_in_radius(
        ctx.state, ctx.caster.team, ctx.caster.x, ctx.caster.y, radius)
        if isinstance(e, (Hero, Minion))]
    for e in stunned:
        apply_status(e, Stun(duration), ctx.state)
    return stunned


def shred_armor(ctx, target, amount, duration) -> None:
    """Reduce a single enemy's physical defense for `duration` (a negative
    phys_def buff; effective_phys_def sums it in)."""
    apply_effect(target, duration, phys_def=-abs(amount))


def shred_sp_def(ctx, target, amount, duration) -> None:
    """Reduce a single enemy's special defense for `duration`."""
    apply_effect(target, duration, sp_def=-abs(amount))


def shield(ctx, amount, duration, target=None) -> object:
    """Grant an absorb shield to the caster (or `target`). Returns the status."""
    from server.status import Shield
    bearer = target if target is not None else ctx.caster
    return bearer.statuses.add(
        Shield(duration, amount, source=f"{bearer.hero_id or 'skill'}:shield"),
        ctx.state)


def cone(ctx, dmg, radius, half_angle_deg=45.0, dtype="physical", fx=""):
    """Damage enemies inside a cone from the caster toward (tx, ty).

    `half_angle_deg` is measured from the aim line, so 45 is a 90-degree cone.
    """
    caster = ctx.caster
    ax, ay = ctx.tx - caster.x, ctx.ty - caster.y
    alen = math.hypot(ax, ay)
    if alen < 1e-6:
        ax, ay, alen = 1.0, 0.0, 1.0
    ax, ay = ax / alen, ay / alen
    _emit_fx(ctx, fx, caster.x + ax * radius / 2, caster.y + ay * radius / 2,
             radius)
    cos_limit = math.cos(math.radians(half_angle_deg))
    hit = []
    for e in enemies_in_radius(ctx.state, caster.team, caster.x, caster.y, radius):
        dx, dy = e.x - caster.x, e.y - caster.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            hit.append(e)  # standing on top of the caster is always inside
            continue
        if (dx / d) * ax + (dy / d) * ay >= cos_limit:
            hit.append(e)
    for e in hit:
        ctx.state.damage_events.append(
            {"src": caster.entity_id, "tgt": e.entity_id, "amt": dmg,
             "dtype": dtype})
    return hit


def line_aoe(ctx, dmg, length, width, dtype="physical", fx=""):
    """Damage enemies inside a rectangle from the caster toward (tx, ty)."""
    caster = ctx.caster
    ax, ay = ctx.tx - caster.x, ctx.ty - caster.y
    alen = math.hypot(ax, ay)
    if alen < 1e-6:
        ax, ay, alen = 1.0, 0.0, 1.0
    ax, ay = ax / alen, ay / alen
    ex, ey = caster.x + ax * length, caster.y + ay * length
    _emit_fx(ctx, fx, (caster.x + ex) / 2, (caster.y + ey) / 2, width)
    half = width / 2.0
    hit = []
    for e in enemies_in_radius(ctx.state, caster.team, caster.x, caster.y,
                               length + width):
        px, py = closest_point_on_segment(e.x, e.y, caster.x, caster.y, ex, ey)
        if math.hypot(e.x - px, e.y - py) <= half + e.radius:
            hit.append(e)
    for e in hit:
        ctx.state.damage_events.append(
            {"src": caster.entity_id, "tgt": e.entity_id, "amt": dmg,
             "dtype": dtype})
    return hit


def knockback(ctx, target, distance, from_point=None) -> None:
    """Shove `target` away from the caster (or `from_point`) by `distance`."""
    ox, oy = from_point if from_point is not None else (ctx.caster.x, ctx.caster.y)
    dx, dy = target.x - ox, target.y - oy
    d = math.hypot(dx, dy)
    if d < 1e-6:
        dx, dy, d = 1.0, 0.0, 1.0
    target.x = max(target.radius,
                   min(MAP_WIDTH - target.radius, target.x + dx / d * distance))
    target.y = max(target.radius,
                   min(MAP_HEIGHT - target.radius, target.y + dy / d * distance))
    # A shove overrides whatever the victim was walking toward.
    if hasattr(target, "target_x"):
        target.target_x = target.target_y = None


def pulse(ctx, key, duration, interval, on_pulse) -> None:
    """Start a repeating effect on the caster, ticked by the hero's `on_tick`.

    Lastikman's Rubber Storm and Pedro's channels each hand-rolled this: a dict
    in `ability_state` with a countdown and an accumulator, advanced by bespoke
    arithmetic in `on_tick`. `pulse` + `tick_pulses` is that pattern once.

    `on_pulse(state, hero)` fires every `interval` seconds for `duration`.
    """
    ctx.caster.ability_state.setdefault("_pulses", {})[key] = {
        "t": duration, "acc": 0.0, "interval": interval, "fn": on_pulse}


def tick_pulses(state, hero, dt) -> None:
    """Advance every pulse on `hero`. Call from the hero's `on_tick`."""
    pulses = hero.ability_state.get("_pulses")
    if not pulses:
        return
    if not hero.alive:
        pulses.clear()
        return
    for key, p in list(pulses.items()):
        p["t"] -= dt
        p["acc"] += dt
        while p["acc"] >= p["interval"]:
            p["acc"] -= p["interval"]
            p["fn"](state, hero)
        if p["t"] <= 0:
            pulses.pop(key, None)


def is_pulsing(hero, key) -> bool:
    return key in hero.ability_state.get("_pulses", {})


def toggle(ctx, key, on, off, active_cd=0.0, cancel_cd=0.0) -> bool:
    """Run `off()` if the ability is currently on, else `on()`.

    Returns True when it switched on. Handles the cooldown bookkeeping that
    toggles otherwise write by hand — including the "nothing happened, so don't
    charge a cooldown" refund that Kapre, Tiktik and Manananggal each spell out
    with a bare `hero.cooldowns[K] = 0.0`.
    """
    hero = ctx.caster
    toggles = hero.ability_state.setdefault("_toggles", set())
    if key in toggles:
        toggles.discard(key)
        off()
        hero.cooldowns[key] = cancel_cd
        return False
    if on() is False:          # the body reports it could not start
        hero.cooldowns[key] = 0.0   # refund: nothing happened
        return False
    toggles.add(key)
    hero.cooldowns[key] = active_cd
    return True


def is_toggled(hero, key) -> bool:
    return key in hero.ability_state.get("_toggles", set())


def summon(ctx, count, lifetime, target_id=None, spread=50.0,
           **overrides) -> list:
    """Spawn `count` short-lived creatures on the caster's team near the caster,
    each chasing `target_id` (or the nearest enemy). Extra kwargs override the
    SummonedMinion stat defaults (hp, attack_damage, move_speed, ...)."""
    caster, state = ctx.caster, ctx.state
    out = []
    for _ in range(count):
        ang = random.uniform(0, 2 * math.pi)
        rad = random.uniform(0, spread)
        px = caster.x + math.cos(ang) * rad
        py = caster.y + math.sin(ang) * rad
        worm = SummonedMinion(
            team=caster.team, x=px, y=py, dest_x=px, dest_y=py,
            owner_id=caster.entity_id, lifetime=lifetime,
            forced_target_id=target_id, **overrides)
        state.entities[worm.entity_id] = worm
        out.append(worm)
    return out


def drop_item(ctx, x, y, kind="", radius=24.0, lifetime=0.0,
             owner_only=True) -> GroundItem:
    """Place a ground pickup at (x, y) (e.g. Panday's forged sword). Not a
    combat target (excluded from targeting/the spatial grid like a projectile).

    `owner_only` restricts it to the caster; `lifetime` <= 0 means no
    timeout — pair that with `system_ground_items` (age it from a hero's own
    on_tick) or the item lingers until something else clears it. Returns the
    entity so the hero can remember its id (e.g. to replace it on recast)."""
    caster = ctx.caster
    item = GroundItem(team=caster.team, x=x, y=y, radius=radius,
                      owner_id=caster.entity_id if owner_only else 0,
                      kind=kind, lifetime=lifetime)
    ctx.state.entities[item.entity_id] = item
    return item


def nearby_ground_item(state, hero, radius, kind="") -> GroundItem | None:
    """The closest live `GroundItem` within `radius` of `hero` that it may
    claim (owned by `hero` or unowned), optionally filtered by `kind`."""
    best, best_d = None, None
    for e in state.entities.values():
        if not isinstance(e, GroundItem) or not e.alive:
            continue
        if e.owner_id and e.owner_id != hero.entity_id:
            continue
        if kind and e.kind != kind:
            continue
        d = hero.distance_to(e)
        if d > radius + e.radius:
            continue
        if best_d is None or d < best_d:
            best, best_d = e, d
    return best


def devour(ctx, range, buff_dur=0.0, hero_bite=0, dtype="physical",
           source="devour", **buff_mods) -> object | None:
    """Consume the targeted enemy. A minion/neutral is instantly slain and the
    caster gains a timed buff (`buff_mods`); a hero instead takes `hero_bite`
    damage. Returns the target acted on, or None."""
    caster = ctx.caster
    target = ctx.state.entities.get(ctx.tid) if ctx.tid else None
    if target is None or not is_valid_attack_target(
            ctx.state, caster, target, check_vision=False):
        target = nearest_enemy(ctx.state, caster.team, caster.x, caster.y,
                               range, toward=(ctx.tx, ctx.ty))
    if target is None or caster.distance_to(target) > range + target.radius:
        return None
    if isinstance(target, Minion):
        # Lethal true damage routes through the normal death/reward flow.
        ctx.state.damage_events.append(
            {"src": caster.entity_id, "tgt": target.entity_id,
             "amt": int(target.hp) + 1, "dtype": "true"})
        if buff_dur > 0 and buff_mods:
            # `source` is a parameter rather than a literal: this is the shared
            # skill library, so it must not name the one hero that uses it.
            apply_effect(caster, buff_dur, source=source, state=ctx.state,
                         **buff_mods)
    else:  # an enemy hero: a heavy bite instead of an instant kill
        ctx.state.damage_events.append(
            {"src": caster.entity_id, "tgt": target.entity_id,
             "amt": hero_bite, "dtype": dtype})
    return target
