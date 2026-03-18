"""Interpolate entity positions between server snapshots for smooth rendering."""

from __future__ import annotations

import time
from shared.config import TICK_DURATION


class Interpolator:
    """Stores two most recent snapshots and lerps between them."""

    def __init__(self) -> None:
        self.prev_snapshot: dict[int, dict] | None = None
        self.curr_snapshot: dict[int, dict] | None = None
        self.snapshot_time: float = 0.0

    def push_snapshot(self, entities: list[dict]) -> None:
        """Called when a new server snapshot arrives."""
        self.prev_snapshot = self.curr_snapshot
        self.curr_snapshot = {e["id"]: e for e in entities}
        self.snapshot_time = time.monotonic()

    def get_entities(self) -> list[dict]:
        """Return interpolated entity list for rendering."""
        if self.curr_snapshot is None:
            return []

        if self.prev_snapshot is None:
            return list(self.curr_snapshot.values())

        # How far we are between prev and curr (0.0 to 1.0)
        elapsed = time.monotonic() - self.snapshot_time
        t = min(1.0, elapsed / TICK_DURATION)

        result = []
        for eid, curr in self.curr_snapshot.items():
            prev = self.prev_snapshot.get(eid)
            if prev is None:
                result.append(curr)
                continue
            # Lerp position
            interp = dict(curr)
            interp["x"] = prev["x"] + (curr["x"] - prev["x"]) * t
            interp["y"] = prev["y"] + (curr["y"] - prev["y"]) * t
            result.append(interp)
        return result
