"""Shared pending-cast target validity logic.

Both the renderer (to color the aiming ring / draw an AoE radius) and the
input handler (to decide whether a click should actually fire the ability)
need to answer the same question — "is the cursor's world position a valid
target for this pending cast?" — so the logic lives here once instead of
being duplicated (and potentially drifting out of sync) between the two.
"""

from __future__ import annotations

import math

from shared.config import ATTACK_CLICK_PIXELS, TP_RANGE
from shared.game_types import EntityType, CastType
from shared.geometry import closest_point_on_segment, segment_capsule_intersect


def pending_target_meta(pending_cast, hero_abilities) -> tuple[str, float, float]:
    """(target-kind, range, radius) for a pending cast. Unit-target casts with
    no explicit kind default to requiring an enemy; the dedicated TP slot
    requires a point near an alive allied structure."""
    if pending_cast == "TP":
        return ("ally_structure_area", TP_RANGE, 0.0)
    for ab in hero_abilities:
        if ab.get("key") == pending_cast:
            tgt = ab.get("target", "ground")
            rng = ab.get("range", 0) or 0
            radius = ab.get("radius", 0) or 0
            if tgt == "ground" and ab.get("cast") == int(CastType.UNIT):
                tgt = "enemy"
            return (tgt, rng, radius)
    return ("ground", 0.0, 0.0)


def my_hero(entities, my_entity_id):
    for e in entities:
        if e.get("id") == my_entity_id:
            return e
    return None


def unit_under_cursor(entities, my_entity_id, my_team, wx, wy, kind, rng):
    """Closest enemy/ally unit under the cursor (within its radius).

    Distance to *my hero* (`rng`) is deliberately NOT used to exclude a
    target here: a unit-targeted ability ordered beyond its range has the
    caster walk into range and fire automatically (see
    server systems._update_ability_chase), so an out-of-range enemy is still
    a perfectly valid thing to click — the cast just won't be instant.
    """
    me = my_hero(entities, my_entity_id)
    best, best_d = None, None
    for e in entities:
        # Terrain is never a unit target. (The 'obstacle' cast kind aims at it
        # through `terrain_along_aim` instead, so grapples still work.)
        if not e.get("a", True) or e.get("et") in (EntityType.PROJECTILE,
                                                   EntityType.WALL,
                                                   EntityType.TREE,
                                                   EntityType.PICKUP):
            continue
        team = e.get("tm", 0)
        # Team 0 (Team.NONE: neutrals/jungle camps) is hostile to everyone by
        # design (matches the server's `enemies_in_radius`), so it counts as
        # a valid "enemy" target here too.
        is_enemy = team != my_team
        if kind == "enemy" and not is_enemy:
            continue
        if kind == "ally" and (team != my_team or e.get("id") == my_entity_id):
            continue
        d = math.hypot(e["x"] - wx, e["y"] - wy)
        if d > e.get("r", 20) + ATTACK_CLICK_PIXELS:
            continue
        if best_d is None or d < best_d:
            best, best_d = e, d
    return best


def near_ally_structure(entities, my_team, wx, wy, rng) -> bool:
    for e in entities:
        if e.get("et") not in (EntityType.TOWER, EntityType.BASE):
            continue
        if e.get("tm", 0) != my_team or not e.get("a", True):
            continue
        if math.hypot(e["x"] - wx, e["y"] - wy) <= rng:
            return True
    return False


def terrain_along_aim(entities, my_entity_id, wx, wy, rng) -> bool:
    """True if a wall / tree / structure lies along the aim line from my hero
    (up to `rng`) — a grapple-style cast would strike it."""
    me = my_hero(entities, my_entity_id)
    if me is None:
        return False
    dx, dy = wx - me["x"], wy - me["y"]
    d = math.hypot(dx, dy) or 1.0
    reach = rng or d
    ax, ay = me["x"], me["y"]
    bx, by = ax + dx / d * reach, ay + dy / d * reach
    for e in entities:
        if not e.get("a", True):
            continue
        et = e.get("et")
        if et in (EntityType.WALL, EntityType.TREE) and e.get("x1") is not None:
            if segment_capsule_intersect(ax, ay, bx, by, e["x1"], e["y1"],
                                         e["x2"], e["y2"], e.get("th", 20) + 44):
                return True
        elif et in (EntityType.TOWER, EntityType.BASE):
            cx, cy = closest_point_on_segment(e["x"], e["y"], ax, ay, bx, by)
            if math.hypot(e["x"] - cx, e["y"] - cy) <= e.get("r", 30) + 22:
                return True
    return False


def pending_target_valid(entities, my_entity_id, my_team, hero_abilities,
                         pending_cast, wx, wy):
    """True/False validity of a world point for the pending cast, or None when
    there is nothing to validate (always-valid 'ground' point casts)."""
    kind, rng, _radius = pending_target_meta(pending_cast, hero_abilities)
    if kind == "ground":
        return None
    if kind in ("enemy", "ally"):
        return unit_under_cursor(entities, my_entity_id, my_team, wx, wy,
                                 kind, rng) is not None
    if kind == "obstacle":
        return terrain_along_aim(entities, my_entity_id, wx, wy, rng)
    if kind == "ally_structure_area":
        return near_ally_structure(entities, my_team, wx, wy, TP_RANGE)
    return None
