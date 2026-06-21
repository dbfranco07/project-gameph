"""Walkable terrain features.

Unlike walls and trees (which block movement and vision), terrain such as the
river is purely a tagged region: units walk through it freely, but the server
can ask whether a point lies inside so future hero abilities can apply river-only
effects. Authored once in ``map.yaml`` and shared by the server (queries) and the
client (rendering).
"""
from __future__ import annotations

from dataclasses import dataclass

from shared.geometry import point_segment_distance


@dataclass(frozen=True)
class River:
    """A walkable band shaped as a capsule: a centerline (p1 -> p2) plus a
    thickness. ``contains`` is the membership test future effects build on."""

    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float

    @classmethod
    def from_config(cls, cfg: dict) -> "River":
        p1, p2 = cfg["p1"], cfg["p2"]
        return cls(float(p1[0]), float(p1[1]),
                   float(p2[0]), float(p2[1]),
                   float(cfg.get("thickness", 400)))

    def contains(self, x: float, y: float) -> bool:
        """True if (x, y) lies within the river band."""
        return (point_segment_distance(x, y, self.x1, self.y1, self.x2, self.y2)
                <= self.thickness / 2.0)
