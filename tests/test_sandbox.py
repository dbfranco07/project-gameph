"""Tests for the sandbox chat cheat-commands (server --sandbox)."""

import unittest

from server.server_main import GameServer
from shared.game_types import Team


class TestSandbox(unittest.TestCase):
    def _server(self, sandbox=True):
        s = GameServer(sandbox=sandbox)
        s.state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")
        return s

    def test_disabled_by_default(self):
        s = GameServer()
        self.assertFalse(s.state.sandbox)
        hero = s.state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")
        g0 = hero.gold
        s._handle_chat(1, {"text": "/gold 9999"})
        self.assertEqual(hero.gold, g0)  # command ignored (relayed as chat)

    def test_gold_command(self):
        s = self._server()
        s._handle_chat(1, {"text": "/gold 12345"})
        self.assertEqual(s.state.get_hero(1).gold, 12345)

    def test_level_command_grants_levels_and_points(self):
        s = self._server()
        s._handle_chat(1, {"text": "/level 10"})
        hero = s.state.get_hero(1)
        self.assertEqual(hero.level, 10)
        self.assertGreater(hero.skill_points, 0)

    def test_refresh_clears_cooldowns(self):
        s = self._server()
        hero = s.state.get_hero(1)
        hero.cooldowns["Q"] = 5.0
        hero.tp_cooldown = 9.0
        s._handle_chat(1, {"text": "/refresh"})
        self.assertEqual(hero.cooldowns.get("Q", 0), 0)
        self.assertEqual(hero.tp_cooldown, 0.0)

    def test_heal_command(self):
        s = self._server()
        hero = s.state.get_hero(1)
        hero.hp = 1
        s._handle_chat(1, {"text": "/heal"})
        self.assertEqual(hero.hp, hero.max_hp)

    def test_item_command_grants_inventory_item(self):
        s = self._server()
        s._handle_chat(1, {"text": "/item long_sword"})
        self.assertIn("long_sword", s.state.get_hero(1).inventory)

    def test_item_command_grants_tp_charge(self):
        s = self._server()
        s._handle_chat(1, {"text": "/item tp_scroll"})
        self.assertEqual(s.state.get_hero(1).tp_charges, 1)


if __name__ == "__main__":
    unittest.main()
