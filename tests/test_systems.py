"""Tests for game systems."""

import unittest
from server.game_state import GameState
from server.systems import system_movement
from shared.game_types import Team
from shared.config import MAP_WIDTH, MAP_HEIGHT


class TestMovementSystem(unittest.TestCase):
    def setUp(self):
        self.state = GameState()

    def test_hero_moves_toward_target(self):
        hero = self.state.add_hero(1, "Runner", Team.TEAM1)
        hero.x, hero.y = 500, 500
        hero.target_x, hero.target_y = 600, 500
        old_x = hero.x
        system_movement(self.state, 0.05)
        self.assertGreater(hero.x, old_x)

    def test_hero_stays_if_no_target(self):
        hero = self.state.add_hero(1, "Idle", Team.TEAM1)
        hero.x, hero.y = 500, 500
        hero.target_x, hero.target_y = None, None
        system_movement(self.state, 0.05)
        self.assertEqual(hero.x, 500)
        self.assertEqual(hero.y, 500)

    def test_clamp_to_map_bounds(self):
        hero = self.state.add_hero(1, "Edge", Team.TEAM1)
        hero.x, hero.y = -100, -100
        hero.target_x, hero.target_y = None, None
        system_movement(self.state, 0.05)
        self.assertGreaterEqual(hero.x, hero.radius)
        self.assertGreaterEqual(hero.y, hero.radius)

    def test_clamp_to_map_upper_bounds(self):
        hero = self.state.add_hero(1, "Edge2", Team.TEAM2)
        hero.x = MAP_WIDTH + 100
        hero.y = MAP_HEIGHT + 100
        system_movement(self.state, 0.05)
        self.assertLessEqual(hero.x, MAP_WIDTH - hero.radius)
        self.assertLessEqual(hero.y, MAP_HEIGHT - hero.radius)

    def test_dead_hero_does_not_move(self):
        hero = self.state.add_hero(1, "Dead", Team.TEAM1)
        hero.x, hero.y = 500, 500
        hero.target_x, hero.target_y = 600, 500
        hero.alive = False
        system_movement(self.state, 0.05)
        self.assertEqual(hero.x, 500)


if __name__ == "__main__":
    unittest.main()
