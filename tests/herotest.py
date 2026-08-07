"""Shared base class for hero tests.

Every per-hero test module used to copy the same ~15 lines: build a GameState,
spawn a hero and a dummy enemy, rank up the abilities, and define a local
`_cast` helper that appends to `state.ability_casts` and runs the cast system.
That boilerplate lives here once.

Usage:

    class TestKapre(HeroTestCase):
        hero_id = "kapre"

        def test_smash_stuns(self):
            self.cast("Q")
            self.assertTrue(self.enemy.is_stunned())
"""

from __future__ import annotations

import unittest

from shared.game_types import Team
from server.game_state import GameState
from server.systems import (
    system_ability_cast,
    system_combat,
    system_damage_death,
    system_hero_hooks,
    system_movement,
    system_status,
)


class HeroTestCase(unittest.TestCase):
    """A live hero in a real GameState, with the cast path wired up."""

    #: The hero under test. Override in the subclass.
    hero_id: str = "ranger"
    #: The opposing dummy. Override if a specific matchup matters.
    enemy_hero_id: str = "brawler"

    #: Ranks every ability starts at (0 leaves them unlearned).
    start_rank: int = 1
    #: Where the two heroes stand, far from map geometry unless a test moves them.
    hero_pos: tuple[float, float] = (1000.0, 1000.0)
    enemy_pos: tuple[float, float] = (1200.0, 1000.0)

    def setUp(self) -> None:
        self.state = GameState()
        self.state.match_clock = 0      # past the pre-game countdown
        self.hero = self.state.add_hero(1, "H", Team.TEAM1,
                                        hero_id=self.hero_id)
        self.enemy = self.state.add_hero(2, "E", Team.TEAM2,
                                         hero_id=self.enemy_hero_id)
        self.hero.x, self.hero.y = self.hero_pos
        self.enemy.x, self.enemy.y = self.enemy_pos
        if self.start_rank:
            for ab in self.hero.abilities:
                self.hero.ability_levels[ab["key"]] = self.start_rank

    # ----- driving the simulation ------------------------------------------
    def cast(self, key: str, tx: float | None = None, ty: float | None = None,
             tid: int | None = None, dt: float = 0.05):
        """Queue an ability cast and run the cast system.

        Defaults aim at the enemy, which is what most ability tests want.
        """
        self.state.ability_casts.append({
            "caster": self.hero.entity_id,
            "key": key,
            "tx": self.enemy.x if tx is None else tx,
            "ty": self.enemy.y if ty is None else ty,
            "tid": tid,
        })
        system_ability_cast(self.state, dt)

    def cast_at(self, key: str, target, dt: float = 0.05):
        """Cast a unit-targeted ability at `target`."""
        return self.cast(key, target.x, target.y, target.entity_id, dt)

    def tick(self, dt: float = 0.05, times: int = 1) -> None:
        """Advance the subsystems hero tests care about, in pipeline order."""
        for _ in range(times):
            system_status(self.state, dt)
            system_movement(self.state, dt)
            system_hero_hooks(self.state, dt)
            system_combat(self.state, dt)
            system_damage_death(self.state, dt)

    def resolve_damage(self, dt: float = 0.05) -> None:
        """Apply queued damage/heal events without advancing anything else."""
        system_damage_death(self.state, dt)

    # ----- convenience ------------------------------------------------------
    def add_enemy(self, hero_id: str = "brawler", x: float = 0.0,
                  y: float = 0.0):
        """Spawn an extra enemy hero at a position."""
        eid = 100 + len(self.state.player_heroes)
        extra = self.state.add_hero(eid, f"E{eid}", Team.TEAM2,
                                    hero_id=hero_id)
        extra.x, extra.y = x, y
        return extra

    def set_rank(self, key: str, rank: int) -> None:
        self.hero.ability_levels[key] = rank

    def ready(self, key: str) -> None:
        """Clear a cooldown so the ability can be cast again immediately."""
        self.hero.cooldowns[key] = 0.0

    def assertStatus(self, entity, status_id: str, msg: str = "") -> None:
        self.assertIsNotNone(entity.statuses.get(status_id),
                             msg or f"expected status {status_id!r}")

    def assertNoStatus(self, entity, status_id: str, msg: str = "") -> None:
        self.assertIsNone(entity.statuses.get(status_id),
                          msg or f"unexpected status {status_id!r}")
