"""Shared attack-target validity rules.

Every path that picks something to attack — automatic acquisition, an 'A + click'
focus order, an in-flight homing projectile, an AoE sweep, a unit-targeted
ability — has to answer the same question: "may `attacker` attack `e`?" Those
rules used to be written out inline at each of those call sites, and they
drifted: only `find_attack_target` excluded terrain, so everything else happily
accepted a wall or a tree.

That drift is not a cosmetic problem. `Obstacle.__post_init__` sets an
obstacle's ``x, y`` to its capsule *midpoint* and its ``radius`` to half the
capsule's *length*, so a long tree reads as a ~615-unit-wide ball. A hero that
latched onto one stopped hundreds of units short of anything, considered itself
"in range", and swung at empty ground forever.

So the rules live here once, and the callers compose them. This mirrors
``client/targeting.py``, which exists for the same reason on the client side —
but note the client's copy is only UX. The server is authoritative: it must
reject an illegal target even when the client never offered it.
"""

from __future__ import annotations

from shared.game_types import Team
from server.entity import Hero, Minion, Obstacle, Projectile, Structure


def is_terrain(e) -> bool:
    """True for map geometry (walls and trees alike).

    Terrain is an `Entity` only so it can be spawned, snapshotted and queried
    like everything else; it is never a combat participant, whatever its
    ``hp``/``alive``/``team`` happen to say.
    """
    return isinstance(e, Obstacle)


def is_attackable(state, e) -> bool:
    """Attacker-independent validity: could *anyone* attack `e` right now?

    Covers existence, terrain, projectiles, and the two "temporarily immune"
    cases (a structure still shielded by its front-liners, a hero mid
    invulnerability).
    """
    if e is None or not e.alive:
        return False
    if isinstance(e, (Projectile, Obstacle)):
        return False
    if isinstance(e, Structure) and not state.is_structure_vulnerable(e):
        return False
    if isinstance(e, Hero) and e.is_invulnerable():
        return False
    return True


def is_hostile_team(team: Team, e) -> bool:
    """True if `e` is on a side that `team` is allowed to attack.

    `Team.NONE` is deliberately asymmetric: neutral jungle monsters and runes
    are hostile to everyone, but obstacles also sit at `Team.NONE` and must not
    inherit that. Testing for a neutral `Minion` rather than for `Team.NONE`
    itself is what keeps terrain out.
    """
    if e.team == team:
        return False
    if e.team == Team.NONE:
        return isinstance(e, Minion) and e.is_neutral
    return True


def is_perceptible(state, attacker, e) -> bool:
    """True if `attacker` can currently see `e` well enough to target it.

    Stealth applies to every attacker; fog of war only gates heroes (minions,
    towers and neutrals fight whatever walks up to them, and `Team.NONE` has no
    vision sources of its own). `visible_ids_cached` is memoized per tick, so
    calling this per candidate is cheap.
    """
    if isinstance(e, Hero) and e.is_invisible() and e.reveal_timer <= 0:
        return False
    if isinstance(attacker, Hero):
        return e.entity_id in state.visible_ids_cached(attacker.team)
    return True


def is_valid_attack_target(state, attacker, e, *, check_vision: bool = True) -> bool:
    """The full rule set, minus range: may `attacker` attack `e` at all?

    Range is deliberately excluded — auto-acquisition, focus-chasing and
    ability casts each measure reach differently, so they apply their own test
    (see `in_attack_range`) on top of this.

    Pass ``check_vision=False`` for abilities, which are not fog-gated today;
    only auto-attack acquisition is.
    """
    if e is attacker:
        return False
    if not is_attackable(state, e):
        return False
    if not is_hostile_team(attacker.team, e):
        return False
    if check_vision and not is_perceptible(state, attacker, e):
        return False
    return True


def in_attack_range(attacker, e) -> bool:
    """True if `e` is within `attacker`'s basic-attack reach (edge to center)."""
    return attacker.distance_to(e) <= attacker.effective_attack_range() + e.radius
