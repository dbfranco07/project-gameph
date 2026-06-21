"""Small geometry helpers shared by the server and config.

Lanes are polylines (lists of (x, y) waypoints). Towers are placed by arc-length
fraction along a lane, so we never hand-place individual tower coordinates.
"""
from __future__ import annotations

import math


def polyline_length(points: list[tuple[float, float]]) -> float:
    """Total length of a polyline."""
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def point_along(points: list[tuple[float, float]],
                t: float) -> tuple[float, float]:
    """Point at arc-length fraction ``t`` in [0, 1] along the polyline."""
    if t <= 0.0:
        return points[0]
    if t >= 1.0:
        return points[-1]
    target = polyline_length(points) * t
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if acc + seg >= target:
            f = (target - acc) / seg if seg > 1e-9 else 0.0
            return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)
        acc += seg
    return points[-1]


# ----- Symmetry (map authored for one side, mirrored through the center) -----

def mirror_point(p: tuple[float, float], 
                 width: float,
                 height: float) -> tuple[float, float]:
    """Point-reflect ``p`` through the map center: (x, y) -> (W - x, H - y)."""
    return (width - p[0], height - p[1])


def mirror_rect(rect: tuple[float, float, float, float], width: float,
                height: float) -> tuple[float, float, float, float]:
    """Reflect an axis-aligned (x, y, w, h) rect (top-left anchored) through the
    map center, returning another top-left-anchored rect of the same size."""
    x, y, w, h = rect
    # Reflect the far corner so the result stays top-left anchored.
    nx, ny = mirror_point((x + w, y + h), width, height)
    return (nx, ny, w, h)


# ----- Intersection tests (vision blocking + obstacle collision) -------------

def point_in_rect(px: float, 
                  py: float,
                  rect: tuple[float, float, float, float]) -> bool:
    """True if (px, py) lies inside an (x, y, w, h) top-left-anchored rect."""
    x, y, w, h = rect
    return x <= px <= x + w and y <= py <= y + h


def circle_rect_overlap(cx: float, 
                        cy: float, 
                        r: float,
                        rect: tuple[float, float, float, float]) -> bool:
    """True if a circle overlaps an axis-aligned rect (x, y, w, h)."""
    x, y, w, h = rect
    nearest_x = min(max(cx, x), x + w)
    nearest_y = min(max(cy, y), y + h)
    dx, dy = cx - nearest_x, cy - nearest_y
    return dx * dx + dy * dy <= r * r


def segment_intersects_rect(x0: float,
                            y0: float,
                            x1: float,
                            y1: float,
                            rect: tuple[float, float, float, float]) -> bool:
    """True if segment (x0,y0)->(x1,y1) crosses or starts inside an (x,y,w,h) rect.

    Used for line-of-sight: a target is hidden when the sight line crosses a wall
    or tree. Uses the Liang-Barsky segment/AABB clip.
    """
    x, y, w, h = rect
    xmin, ymin, xmax, ymax = x, y, x + w, y + h
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - xmin), (dx, xmax - x0),
                 (-dy, y0 - ymin), (dy, ymax - y0)):
        if p == 0:
            if q < 0:
                return False  # parallel and outside this slab
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return False
            if r > t0:
                t0 = r
        else:
            if r < t0:
                return False
            if r < t1:
                t1 = r
    return t0 <= t1


# ----- Capsules (oriented walls/trees/river: a segment + a thickness) --------
#
# An obstacle is a "thick segment" (capsule): the centerline runs (x0,y0)->(x1,y1)
# and the solid extends half the thickness to either side, with rounded ends.
# A point is inside when its distance to the centerline is <= thickness / 2.

def closest_point_on_segment(px: float, py: float,
                             x0: float, y0: float,
                             x1: float, y1: float) -> tuple[float, float]:
    """Closest point to (px, py) on the segment (x0,y0)->(x1,y1)."""
    dx, dy = x1 - x0, y1 - y0
    seg2 = dx * dx + dy * dy
    if seg2 <= 1e-9:
        return (x0, y0)  # degenerate segment: it's a point
    t = ((px - x0) * dx + (py - y0) * dy) / seg2
    t = max(0.0, min(1.0, t))
    return (x0 + dx * t, y0 + dy * t)


def point_segment_distance(px: float, py: float,
                           x0: float, y0: float,
                           x1: float, y1: float) -> float:
    """Distance from (px, py) to the segment (x0,y0)->(x1,y1)."""
    cx, cy = closest_point_on_segment(px, py, x0, y0, x1, y1)
    return math.hypot(px - cx, py - cy)


def circle_capsule_overlap(cx: float, cy: float, r: float,
                           x0: float, y0: float, x1: float, y1: float,
                           thickness: float) -> bool:
    """True if a circle overlaps the capsule (segment + thickness)."""
    return point_segment_distance(cx, cy, x0, y0, x1, y1) <= r + thickness / 2.0


def _segments_intersect(ax: float, ay: float, bx: float, by: float,
                        cx: float, cy: float, dx: float, dy: float) -> bool:
    """True if segments A(a->b) and B(c->d) cross (proper or touching)."""
    def orient(ox, oy, px, py, qx, qy) -> float:
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)

    d1 = orient(cx, cy, dx, dy, ax, ay)
    d2 = orient(cx, cy, dx, dy, bx, by)
    d3 = orient(ax, ay, bx, by, cx, cy)
    d4 = orient(ax, ay, bx, by, dx, dy)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return False


def segment_segment_distance(ax: float, ay: float, bx: float, by: float,
                             cx: float, cy: float, dx: float, dy: float) -> float:
    """Shortest distance between segments A(a->b) and B(c->d)."""
    if _segments_intersect(ax, ay, bx, by, cx, cy, dx, dy):
        return 0.0
    return min(
        point_segment_distance(ax, ay, cx, cy, dx, dy),
        point_segment_distance(bx, by, cx, cy, dx, dy),
        point_segment_distance(cx, cy, ax, ay, bx, by),
        point_segment_distance(dx, dy, ax, ay, bx, by),
    )


def segment_capsule_intersect(ax: float, ay: float, bx: float, by: float,
                              x0: float, y0: float, x1: float, y1: float,
                              thickness: float) -> bool:
    """True if the sight segment (ax,ay)->(bx,by) touches the capsule. Used for
    line-of-sight: a target is hidden when the sight line crosses a wall/tree."""
    return segment_segment_distance(ax, ay, bx, by,
                                    x0, y0, x1, y1) <= thickness / 2.0
