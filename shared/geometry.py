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


def point_along(points: list[tuple[float, float]], t: float) -> tuple[float, float]:
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
