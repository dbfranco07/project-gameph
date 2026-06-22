"""Tests for the shared invisibility mechanic (hidden from enemies, seen by
allies, revealed while attacking, untargetable while hidden)."""

import unittest

from server.game_state import GameState
from server.entity import Hero
from server.effects import make_effect
from server.systems import find_attack_target
from shared.config import HERO_VISION_RADIUS
from shared.game_types import Team


class TestInvisibility(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        # Place the two heroes in clear line of sight, well within base vision.
        self.sneak = self.state.add_hero(1, "S", Team.TEAM1, hero_id="ranger")
        self.foe = self.state.add_hero(2, "F", Team.TEAM2, hero_id="brawler")
        self.sneak.x, self.sneak.y = 1000, 1000
        self.foe.x, self.foe.y = 1000 + HERO_VISION_RADIUS - 50, 1000

    def _hide(self):
        self.sneak.buffs.append(make_effect(10.0, invisible=True))

    def test_visible_before_hiding(self):
        self.assertIn(self.sneak.entity_id,
                      self.state.visible_entity_ids_for(Team.TEAM2))

    def test_hidden_from_enemy_but_seen_by_ally(self):
        self._hide()
        self.assertNotIn(self.sneak.entity_id,
                         self.state.visible_entity_ids_for(Team.TEAM2))
        self.assertIn(self.sneak.entity_id,
                      self.state.visible_entity_ids_for(Team.TEAM1))

    def test_reveal_timer_makes_visible_again(self):
        self._hide()
        self.sneak.reveal_timer = 0.4
        self.assertIn(self.sneak.entity_id,
                      self.state.visible_entity_ids_for(Team.TEAM2))

    def test_invisible_is_untargetable(self):
        # The foe is in attack range of the sneak.
        self.foe.x, self.foe.y = 1100, 1000
        self.assertIsNotNone(find_attack_target(self.state, self.foe))
        self._hide()
        self.assertIsNone(find_attack_target(self.state, self.foe))
        # ...but revealing it (attacking) makes it targetable again.
        self.sneak.reveal_timer = 0.4
        self.assertIs(find_attack_target(self.state, self.foe), self.sneak)


if __name__ == "__main__":
    unittest.main()
