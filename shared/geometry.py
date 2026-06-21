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
