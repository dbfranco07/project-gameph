"""Game configuration.

All tuning lives in the YAML files under ``config/`` at the repo root; this module
loads them at import and re-exports the same module-level constant names the rest
of the codebase already imports (``MINION_HP``, ``LANE_PATHS``, ``COLOR_BG``, …)
plus the newer ones. Editing a YAML value changes the game on next launch — no
code edits needed.

Map features are authored for one side (Team 1) in ``map.yaml`` and mirrored
through the map center to build Team 2's set.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from shared.geometry import mirror_point
from shared.terrain import River
from shared._config_gen import ensure_fresh
ensure_fresh() # ensures constants from _config_constants are updated
# _config_constants are all configs from all yaml files
from shared._config_constants import *  # noqa: F401,F403

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load(name: str) -> dict[str: object]:
    """Load a config YAML file from ``config/``."""
    with open(_CONFIG_DIR / f"{name}.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}

def _mirror(p: tuple[float, float]) -> tuple[float, float]:
    """Reflect a point through the map center. The map is authored for Team 1"""
    return mirror_point((p[0], p[1]), MAP_WIDTH, MAP_HEIGHT)

def _mirror_zone(z: list[int]) -> list[int]:
    """Reflect a rectangular zone through the map center. Used for mirrored rune 
    spawn zones."""
    x, y, w, h = z
    mx, my = _mirror((x + w, y + h))  # mirror the far corner to stay top-left
    return [mx, my, w, h]

def _capsule(c: dict[str, object]) -> dict[str, object]:
    """Convert a dictionary to a capsule format."""
    return {"p1": tuple(c["p1"]), 
            "p2": tuple(c["p2"]),
            "thickness": float(c.get("thickness", 60))}

def _mirror_capsule(c: dict[str, object]) -> dict[str, object]:
    """Reflect a capsule through the map center. Used for walls and trees."""
    return {"p1": _mirror(c["p1"]), 
            "p2": _mirror(c["p2"]),
            "thickness": float(c.get("thickness", 60))}


_map = _load("map")

# Derived scalars
TICK_DURATION = 1.0 / SERVER_TICK_RATE  # seconds per tick
MAP_CENTER = (MAP_WIDTH / 2, MAP_HEIGHT / 2)
HERO_VISION_RADIUS = VISION_RADIUS

# Spawn / structure positions. The FOUNTAIN (well) is where heroes spawn and
# fast-heal; the CORE is a distinct inland win structure (see _spawn_structures).
T1_FOUNTAIN = tuple(_map["fountain"])
T2_FOUNTAIN = _mirror(T1_FOUNTAIN)
SPAWN_POSITIONS = {1: T1_FOUNTAIN, 2: T2_FOUNTAIN}

T1_CORE = tuple(_map["core"])
T2_CORE = _mirror(T1_CORE)
CORE_POSITIONS = {1: T1_CORE, 2: T2_CORE}

# Lane polylines are symmetric, authored in full; store waypoints as tuples.
LANE_WIDTH = _map["lane_width"]
LANES = tuple(_map["lanes"].keys())
LANE_PATHS = {lane: [tuple(pt) for pt in pts]
              for lane, pts in _map["lanes"].items()}

# Towers authored for Team 1 (lane_order, t, kind); Team 2 mirrors t -> 1 - t.
_t1_towers = [(t["lane_order"], t["t"], t["kind"])
              for t in _map["towers"]]
_t2_towers = [(lo, round(1.0 - t, 6), kind)
              for (lo, t, kind) in reversed(_t1_towers)]
LANE_TOWERS = {1: _t1_towers, 2: _t2_towers}

# Arc-length fraction of each team's base tower (lane_order 2). Minions spawn
# here (next to their base tower), not at the fountain/core. Because the path is
# oriented per team, the same fraction means "base tower" for both sides.
BASE_TOWER_T = next(t for (lo, t, _) in _t1_towers if lo == 2)

# Jungle camps authored for one dead zone; the mirror fills the other.
_t1_camps = [tuple(c) for c in _map["jungle_camps"]]
_t2_camps = [(*_mirror((cx, cy)), n) for (cx, cy, n) in _t1_camps]
JUNGLE_CAMPS = _t1_camps + _t2_camps

# Wave-1 meeting points per lane (single, shared between sides).
MEET_POINTS = {lane: tuple(pt) 
               for lane, pt in _map.get("meet_points", {}).items()}

# Additional map features authored for one side and mirrored to the other.
SPAWN_ZONE_RADIUS = _map.get("spawn_zone_radius", 0)

# Runes (power-ups) authored for one side and mirrored to the other.
_rune_defs = _map.get("runes", [])
RUNES = (
    [{"zone": list(r["zone"]),
      "buff": r["buff"], 
      "patrol": r.get("patrol", 400)}
      for r in _rune_defs] + 
    [{"zone": _mirror_zone(r["zone"]), 
      "buff": r["buff"],
      "patrol": r.get("patrol", 400)}
      for r in _rune_defs]
)
# Walls and trees are authored for one side and mirrored to the other. Each is a
# capsule: two endpoints and a thickness. The mirror is a geometric reflection
# through the map center.
WALLS = ([_capsule(w) for w in _map.get("walls", [])]
         + [_mirror_capsule(w) for w in _map.get("walls", [])])

# Trees are authored for one side and mirrored to the other. Each is a capsule: two
# endpoints and a thickness. The mirror is a geometric reflection through the map
# center. The thickness is optional; if missing, a default is used.
TREES = ([_capsule(t) for t in _map.get("trees", [])]
         + [_mirror_capsule(t) for t in _map.get("trees", [])])

# The river: a single walkable, center-symmetric band (see shared/terrain.py).
RIVER = River.from_config(_map["river"]) if _map.get("river") else None
