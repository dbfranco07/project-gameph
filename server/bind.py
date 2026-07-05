"""Terrain-bind: a hero "living" inside a tree/wall structure.

Shared by Kapre (R, trees) and Tiktik (W, walls). A bound hero is invisible to
enemies, has increased + unobstructed vision, and may only move along the
connected cluster of capsules it bound to (it is exempt from obstacle collision
while bound — see system_collision). State lives in the free-form
`Hero.ability_state["bind"]`; the stealth/vision flags ride a buff tagged
`{"bind": True}` so they are easy to strip on exit.

This module imports only low-level helpers (terrain/entity), so heroes AND the
systems pipeline can import it without an import cycle.
"""

from __future__ import annotations

from server import terrain

BIND_VISION_BONUS = 350.0   # extra sight radius while bound (added to base)


def enter_bind(state, hero, obstacle, kind: str, ability_key: str,
               vision_bonus: float = BIND_VISION_BONUS,
               extra: dict | None = None) -> None:
    """Bind `hero` to the connected cluster containing `obstacle`. Re-entering
    (e.g. Tiktik hopping walls) cleanly replaces any current bind."""
    release_bind(hero)
    cluster = terrain.connected_cluster(state, obstacle)
    ids = [o.entity_id for o in cluster]
    hero.ability_state["bind"] = {"kind": kind, "ids": ids, "ability": ability_key}
    # Snap onto the structure and drop any stale move order.
    caps = terrain.cluster_capsules(state, ids)
    hero.x, hero.y = terrain.clamp_to_cluster(hero.x, hero.y, caps)
    # The snap is a discontinuous move: break any tow this hero owns so a
    # hooked victim isn't dragged across the map after a wall-hop.
    state.pulls = [p for p in state.pulls if p.get("to") != hero.entity_id]
    hero.target_x = hero.target_y = None
    hero.attack_move = False
    hero.attack_move_x = hero.attack_move_y = None
    buff = {"bind": True, "invisible": True, "vision_bonus": vision_bonus,
            "unobstructed_vision": True, "remaining": 5.0}
    if extra:
        buff.update(extra)
    hero.buffs.append(buff)


def release_bind(hero) -> None:
    """Pop the bind and strip its stealth/vision buff (no-op if not bound)."""
    hero.ability_state.pop("bind", None)
    hero.buffs[:] = [b for b in hero.buffs if not b.get("bind")]


def is_bound(hero) -> bool:
    return bool(hero.ability_state.get("bind"))


def tick_bind(state, hero) -> bool:
    """Keep a bound hero clamped to its (still-alive) cluster. Auto-exits if the
    structure is gone (e.g. all bound trees destroyed). Returns True while bound.
    Called every tick from the hero's on_tick hook."""
    st = hero.ability_state.get("bind")
    if not st:
        return False
    caps = terrain.cluster_capsules(state, st["ids"])
    if not caps:
        release_bind(hero)
        return False
    hero.x, hero.y = terrain.clamp_to_cluster(hero.x, hero.y, caps)
    # Refresh the long-lived bind buff so system_status never expires it.
    for b in hero.buffs:
        if b.get("bind"):
            b["remaining"] = 5.0
    return True
