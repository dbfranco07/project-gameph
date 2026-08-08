"""Tests for game systems."""

import unittest
from server.game_state import GameState
from server.entity import NeutralMinion, Projectile, Tree, Wall
from server.systems import system_movement
from server.targeting import (
    is_attackable, is_hostile_team, is_terrain, is_valid_attack_target)
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


class TestAttackTargetPredicate(unittest.TestCase):
    """The shared rules in server/targeting.py, which every attack path uses."""

    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        self.hero.x, self.hero.y = 1000, 1000

    def test_terrain_is_never_attackable(self):
        for obstacle in (Wall(x1=0, y1=0, x2=100, y2=0),
                         Tree(x1=0, y1=0, x2=100, y2=0)):
            self.assertTrue(is_terrain(obstacle))
            self.assertFalse(is_attackable(self.state, obstacle))

    def test_projectiles_and_missing_entities_are_not_attackable(self):
        self.assertFalse(is_attackable(self.state, None))
        self.assertFalse(is_attackable(
            self.state, Projectile(team=Team.TEAM2, x=0, y=0)))

    def test_dead_and_invulnerable_are_not_attackable(self):
        enemy = self.state.add_hero(2, "E", Team.TEAM2, hero_id="brawler")
        self.assertTrue(is_attackable(self.state, enemy))
        enemy.alive = False
        self.assertFalse(is_attackable(self.state, enemy))

    def test_team_none_is_hostile_only_for_neutrals(self):
        """The asymmetry that keeps terrain out while neutrals stay targetable."""
        neutral = NeutralMinion(team=Team.NONE, x=0, y=0)
        tree = Tree(x1=0, y1=0, x2=100, y2=0)
        self.assertTrue(is_hostile_team(Team.TEAM1, neutral))
        self.assertFalse(is_hostile_team(Team.TEAM1, tree))

    def test_allies_are_not_hostile(self):
        ally = self.state.add_hero(2, "A", Team.TEAM1, hero_id="brawler")
        self.assertFalse(is_hostile_team(Team.TEAM1, ally))

    def test_valid_attack_target_rejects_self_and_terrain(self):
        tree = Tree(x1=1100, y1=1000, x2=1300, y2=1000)
        self.state.entities[tree.entity_id] = tree
        self.assertFalse(is_valid_attack_target(self.state, self.hero, self.hero))
        self.assertFalse(is_valid_attack_target(self.state, self.hero, tree))


if __name__ == "__main__":
    unittest.main()
