"""Terrain queries over the map's wall/tree capsules.

Walls and trees are oriented capsules (a centerline + a thickness); see
`server/entity.py` `Obstacle` and the geometry helpers in `shared/geometry.py`.
These helpers answer the questions the tree/wall heroes (Kapre, Tiktik) ask:
"is there a tree near me?", "which obstacle did I click?", "what other capsules
connect to it?", and "keep me inside this structure". They are deliberately thin
so a hero's uniqueness stays in its own file.
"""

from __future__ import annotations

from shared.geometry import (
    closest_point_on_segment,
    point_segment_distance,
    segment_segment_distance,
)
from server.entity import Obstacle, Tree, Wall

# Two capsules count as connected when their centerlines come this close
# (the map authors connected chains by sharing endpoints, so the gap is ~0).
_CONNECT_PAD = 12.0


def alive_obstacles(state, cls: type = Obstacle) -> list:
    """Live obstacles of `cls` (default: any). Use `Tree` or `Wall` to filter."""
    return [e for e in state.entities.values()
            if isinstance(e, cls) and e.alive]


def obstacle_at(state, x: float, y: float, cls: type = Obstacle,
                grab: float = 90.0):
    """The obstacle of `cls` whose band contains (x, y), else the nearest one
    within `grab` units of its surface, else None. Lets a click on or just
    beside a tree/wall resolve to it."""
    best = None
    best_d = None
    for e in alive_obstacles(state, cls):
        x0, y0, x1, y1, th = e.capsule()
        d = point_segment_distance(x, y, x0, y0, x1, y1) - th / 2.0
        if d <= 0.0:
            return e  # inside the band
        if d <= grab and (best_d is None or d < best_d):
            best, best_d = e, d
    return best


def near_trees(state, x: float, y: float, pad: float) -> bool:
    """True if (x, y) is within `pad` of any alive tree's surface (or inside it)."""
    for e in alive_obstacles(state, Tree):
        x0, y0, x1, y1, th = e.capsule()
        if point_segment_distance(x, y, x0, y0, x1, y1) <= th / 2.0 + pad:
            return True
    return False


def inside_obstacle(state, x: float, y: float, cls: type = Obstacle) -> bool:
    """True if (x, y) lies inside the band of any alive obstacle of `cls`."""
    for e in alive_obstacles(state, cls):
        x0, y0, x1, y1, th = e.capsule()
        if point_segment_distance(x, y, x0, y0, x1, y1) <= th / 2.0:
            return True
    return False


def connected_cluster(state, seed) -> list:
    """All alive obstacles of the seed's type reachable from `seed` through
    touching capsules (so a multi-segment tree/wall acts as one structure)."""
    cls = Tree if isinstance(seed, Tree) else Wall
    pool = alive_obstacles(state, cls)
    cluster = [seed]
    seen = {seed.entity_id}
    frontier = [seed]
    while frontier:
        cur = frontier.pop()
        ax0, ay0, ax1, ay1, ath = cur.capsule()
        for other in pool:
            if other.entity_id in seen:
                continue
            bx0, by0, bx1, by1, bth = other.capsule()
            gap = segment_segment_distance(ax0, ay0, ax1, ay1,
                                           bx0, by0, bx1, by1)
            if gap <= (ath + bth) / 2.0 + _CONNECT_PAD:
                seen.add(other.entity_id)
                cluster.append(other)
                frontier.append(other)
    return cluster


def cluster_capsules(state, ids: list[int]) -> list[tuple]:
    """Live capsules for the obstacle ids of a bound cluster (dead trees drop
    out, so a destroyed segment stops counting)."""
    out = []
    for eid in ids:
        e = state.entities.get(eid)
        if isinstance(e, Obstacle) and e.alive:
            out.append(e.capsule())
    return out


def clamp_to_cluster(x: float, y: float, capsules: list[tuple]
                     ) -> tuple[float, float]:
    """Pull (x, y) onto the nearest capsule's band so a bound unit can slide
    along the structure but never leave it. Returns the clamped point; if there
    are no capsules, returns (x, y) unchanged."""
    best = None
    best_d = None
    for (x0, y0, x1, y1, th) in capsules:
        cx, cy = closest_point_on_segment(x, y, x0, y0, x1, y1)
        d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        if best_d is None or d < best_d:
            best, best_d = (cx, cy, th), d
    if best is None:
        return x, y
    cx, cy, th = best
    max_off = th / 2.0
    if best_d <= max_off:
        return x, y  # already inside the band
    if best_d < 1e-9:
        return cx, cy  # on the centerline (degenerate)
    # Outside the band: pull back to its edge along the normal from the centerline.
    nx, ny = (x - cx) / best_d, (y - cy) / best_d
    return cx + nx * max_off, cy + ny * max_off
