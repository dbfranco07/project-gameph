"""Tests for server-side fog-of-war (per-team visibility)."""

import unittest

from server.game_state import GameState
from server.entity import Hero
from shared.game_types import Team, EntityType
from shared.config import HERO_VISION_RADIUS


class TestVision(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.me = self.state.add_hero(1, "Me", Team.TEAM1, hero_id="ranger")
        self.enemy = self.state.add_hero(2, "En", Team.TEAM2, hero_id="brawler")
        self.me.x, self.me.y = 1000, 1000

    def test_enemy_hidden_when_out_of_vision(self):
        self.enemy.x, self.enemy.y = 1000 + HERO_VISION_RADIUS + 500, 1000
        vis = self.state.visible_entity_ids_for(Team.TEAM1)
        self.assertIn(self.me.entity_id, vis)
        self.assertNotIn(self.enemy.entity_id, vis)
        ids = {e["id"] for e in self.state.build_snapshot_for(Team.TEAM1)}
        self.assertNotIn(self.enemy.entity_id, ids)

    def test_enemy_visible_when_in_vision(self):
        self.enemy.x, self.enemy.y = 1000 + HERO_VISION_RADIUS - 100, 1000
        vis = self.state.visible_entity_ids_for(Team.TEAM1)
        self.assertIn(self.enemy.entity_id, vis)

    def test_structures_always_visible(self):
        self.state.start_match(kill_target=10)
        # Move my hero far from everything so no unit grants vision near towers.
        self.me.x, self.me.y = 10, 10
        vis = self.state.visible_entity_ids_for(Team.TEAM1)
        struct_ids = [e.entity_id for e in self.state.entities.values()
                      if e.entity_type in (EntityType.TOWER, EntityType.BASE)]
        self.assertTrue(struct_ids)
        for sid in struct_ids:
            self.assertIn(sid, vis)  # both teams' structures revealed

    def test_per_team_snapshots_differ(self):
        self.enemy.x, self.enemy.y = 5500, 1000  # far from my hero
        s1 = {e["id"] for e in self.state.build_snapshot_for(Team.TEAM1)}
        s2 = {e["id"] for e in self.state.build_snapshot_for(Team.TEAM2)}
        self.assertNotEqual(s1, s2)


if __name__ == "__main__":
    unittest.main()
