"""Tests for GameState management."""

import unittest
from server.game_state import GameState
from shared.game_types import Team, GamePhase
from shared.config import SPAWN_POSITIONS


class TestGameState(unittest.TestCase):
    def setUp(self):
        self.state = GameState()

    def test_initial_state(self):
        self.assertEqual(self.state.phase, GamePhase.WAITING)
        self.assertEqual(self.state.tick, 0)
        self.assertEqual(len(self.state.entities), 0)

    def test_add_hero(self):
        hero = self.state.add_hero(1, "Alice", Team.TEAM1)
        self.assertEqual(hero.name, "Alice")
        self.assertEqual(hero.team, Team.TEAM1)
        spawn = SPAWN_POSITIONS[1]
        self.assertEqual(hero.x, spawn[0])
        self.assertEqual(hero.y, spawn[1])
        self.assertIn(hero.entity_id, self.state.entities)
        self.assertEqual(self.state.player_heroes[1], hero.entity_id)

    def test_remove_hero(self):
        hero = self.state.add_hero(1, "Alice", Team.TEAM1)
        eid = hero.entity_id
        self.state.remove_hero(1)
        self.assertNotIn(eid, self.state.entities)
        self.assertNotIn(1, self.state.player_heroes)

    def test_remove_nonexistent_hero(self):
        # Should not raise
        self.state.remove_hero(999)

    def test_get_hero(self):
        hero = self.state.add_hero(1, "Bob", Team.TEAM2)
        fetched = self.state.get_hero(1)
        self.assertEqual(fetched, hero)
        self.assertIsNone(self.state.get_hero(999))

    def test_assign_team_balances(self):
        # First player gets Team 1
        team1 = self.state.assign_team()
        self.assertEqual(team1, Team.TEAM1)
        self.state.add_hero(1, "P1", team1)

        # Second player gets Team 2
        team2 = self.state.assign_team()
        self.assertEqual(team2, Team.TEAM2)
        self.state.add_hero(2, "P2", team2)

        # Third player gets Team 1 (balanced)
        team3 = self.state.assign_team()
        self.assertEqual(team3, Team.TEAM1)

    def test_build_snapshot(self):
        self.state.add_hero(1, "Alice", Team.TEAM1)
        self.state.add_hero(2, "Bob", Team.TEAM2)
        snap = self.state.build_snapshot()
        self.assertEqual(len(snap), 2)
        names = {s["name"] for s in snap}
        self.assertEqual(names, {"Alice", "Bob"})


if __name__ == "__main__":
    unittest.main()
