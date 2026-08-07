"""Terrain-bind: a hero "living" inside a tree/wall structure.

Shared by Kapre (R, trees) and Tiktik (W, walls). A bound hero is invisible to
enemies, has increased + unobstructed vision, and may only move along the
connected cluster of capsules it bound to (it is exempt from obstacle collision
while bound — see system_collision).

The whole bind is one `Bound` status: its flags grant the terrain phasing and
unobstructed sight, and the cluster it is attached to rides on the status
object. Previously the state was split between a free-form
`Hero.ability_state["bind"]` dict and a parallel buff dict tagged
`{"bind": True}` that had to be kept in sync by hand — and re-armed with a fresh
5-second timer every tick so the expiry sweep would not drop it. A status with
an infinite duration simply persists until it is removed.

This module imports only low-level helpers (terrain/status), so heroes AND the
systems pipeline can import it without an import cycle.
"""

from __future__ import annotations

import math

from server import terrain
from server.status.mechanics import Bound

BIND_VISION_BONUS = 350.0   # extra sight radius while bound (added to base)


def enter_bind(state, hero, obstacle, kind: str, ability_key: str,
               vision_bonus: float = BIND_VISION_BONUS,
               extra: dict | None = None) -> Bound:
    """Bind `hero` to the connected cluster containing `obstacle`. Re-entering
    (e.g. Tiktik hopping walls) cleanly replaces any current bind."""
    release_bind(hero, state)
    cluster = terrain.connected_cluster(state, obstacle)
    ids = [o.entity_id for o in cluster]
    # Snap onto the structure and drop any stale move order.
    caps = terrain.cluster_capsules(state, ids)
    hero.x, hero.y = terrain.clamp_to_cluster(hero.x, hero.y, caps)
    # The snap is a discontinuous move: break any tow this hero owns so a
    # hooked victim isn't dragged across the map after a wall-hop.
    state.pulls = [p for p in state.pulls if p.get("to") != hero.entity_id]
    hero.target_x = hero.target_y = None
    hero.attack_move = False
    hero.attack_move_x = hero.attack_move_y = None

    status = Bound(math.inf, obstacle_id=obstacle.entity_id,
                   ability_key=ability_key, kind=kind,
                   modifiers={"vision_bonus": vision_bonus},
                   flags=Bound.flags | frozenset({"invisible"}))
    status.cluster_ids = ids
    if extra:
        _apply_extra(hero, status, extra)
    hero.statuses.add(status, state)
    return status


def _apply_extra(hero, status: Bound, extra: dict) -> None:
    """Fold caller-supplied properties (e.g. Kapre's on-hit slow) into the bind.

    Kept as a separate status rather than merged into `Bound` so the rider keeps
    its own behaviour — an attack-slow is a hook, not a number.
    """
    from server.status import make_status
    rider = make_status(math.inf, source=f"bind:{status.ability_key}", **extra)
    status.rider = rider
    hero.statuses.add(rider, None)


def release_bind(hero, state=None) -> None:
    """Pop the bind and strip its stealth/vision status (no-op if not bound)."""
    for status in hero.statuses.all_of("bind"):
        rider = getattr(status, "rider", None)
        if rider is not None:
            hero.statuses.remove(rider, state)
        hero.statuses.remove(status, state)


def is_bound(hero) -> bool:
    return hero.statuses.has("bind")


def current_bind(hero) -> Bound | None:
    return hero.statuses.get("bind")


def tick_bind(state, hero) -> bool:
    """Keep a bound hero clamped to its (still-alive) cluster. Auto-exits if the
    structure is gone (e.g. all bound trees destroyed). Returns True while bound.
    Called every tick from the hero's on_tick hook."""
    status = current_bind(hero)
    if status is None:
        return False
    caps = terrain.cluster_capsules(state, status.cluster_ids)
    if not caps:
        release_bind(hero, state)
        return False
    hero.x, hero.y = terrain.clamp_to_cluster(hero.x, hero.y, caps)
    return True
