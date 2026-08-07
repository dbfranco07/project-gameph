"""Interpolate entity positions between server snapshots for smooth rendering.

The server sends deltas: each snapshot carries only the entities whose state
changed since the last one this client received, plus the ids that dropped out
of view. The interpolator owns the merged world, so it is also the thing that
knows what "the previous frame" looked like.
"""

from __future__ import annotations

import time
from shared.config import TICK_DURATION


class Interpolator:
    """Merges snapshot deltas and lerps entity positions between them."""

    def __init__(self) -> None:
        self.prev_snapshot: dict[int, dict] | None = None
        self.curr_snapshot: dict[int, dict] | None = None
        self.snapshot_time: float = 0.0

    def reset(self) -> None:
        """Forget the world (match restart, reconnect)."""
        self.prev_snapshot = None
        self.curr_snapshot = None

    def push_snapshot(self, entities: list[dict], gone=(),
                      full: bool = False) -> None:
        """Apply a server snapshot.

        `entities` holds only changed/new entries unless `full` is set, in which
        case it is the whole world and replaces what we have. `gone` lists ids
        that are no longer visible.
        """
        if full or self.curr_snapshot is None:
            merged = {e["id"]: e for e in entities}
        else:
            # Copy, so the previous frame stays intact to interpolate from.
            merged = dict(self.curr_snapshot)
            for e in entities:
                merged[e["id"]] = e
            for eid in gone:
                merged.pop(eid, None)
        self.prev_snapshot = self.curr_snapshot
        self.curr_snapshot = merged
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
