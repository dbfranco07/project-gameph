"""Tests for the TP scroll: dedicated charge slot, 300u validation, cooldown."""

import unittest

from server.server_main import GameServer
from server.entity import Structure
from server.systems import system_ability_cast, system_status
from shared.game_types import Team
from shared.config import TP_RANGE, TP_COOLDOWN


class TestTpScroll(unittest.TestCase):
    def setUp(self):
        self.server = GameServer()
        self.state = self.server.state
        self.hero = self.state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")
        self.hero.x, self.hero.y = 500, 500
        self.hero.gold = 10000
        # An alive allied structure to teleport near.
        self.struct = Structure(team=Team.TEAM1, x=3000, y=3000)
        self.state.entities[self.struct.entity_id] = self.struct

    def _buy(self):
        self.server._handle_buy_item(1, {"item": "tp_scroll"})

    def _cast_tp(self, tx, ty):
        self.state.ability_casts.append(
            {"caster": self.hero.entity_id, "key": "TP",
             "tx": tx, "ty": ty, "tid": None})
        system_ability_cast(self.state, 0.05)

    def test_buy_adds_charge_not_inventory_slot(self):
        self._buy()
        self.assertEqual(self.hero.tp_charges, 1)
        self.assertEqual(self.hero.inventory, [])

    def test_buy_multiple_stacks_charges(self):
        self._buy()
        self._buy()
        self._buy()
        self.assertEqual(self.hero.tp_charges, 3)

    def test_teleport_near_structure(self):
        self._buy()
        self._cast_tp(self.struct.x + 100, self.struct.y)  # within TP_RANGE
        self.assertAlmostEqual(self.hero.x, self.struct.x + 100)
        self.assertAlmostEqual(self.hero.y, self.struct.y)
        self.assertEqual(self.hero.tp_charges, 0)
        self.assertEqual(self.hero.tp_cooldown, TP_COOLDOWN)

    def test_teleport_rejected_far_from_structure(self):
        self._buy()
        x0, y0 = self.hero.x, self.hero.y
        self._cast_tp(self.struct.x + TP_RANGE + 200, self.struct.y)
        self.assertEqual((self.hero.x, self.hero.y), (x0, y0))  # didn't move
        self.assertEqual(self.hero.tp_charges, 1)               # charge kept
        self.assertEqual(self.hero.tp_cooldown, 0.0)

    def test_dead_structure_is_not_valid(self):
        self._buy()
        self.struct.alive = False
        x0, y0 = self.hero.x, self.hero.y
        self._cast_tp(self.struct.x, self.struct.y)
        self.assertEqual((self.hero.x, self.hero.y), (x0, y0))
        self.assertEqual(self.hero.tp_charges, 1)

    def test_cooldown_persists_across_rebuy(self):
        self._buy()
        self._cast_tp(self.struct.x, self.struct.y)
        self.assertEqual(self.hero.tp_cooldown, TP_COOLDOWN)
        self._buy()  # rebuy adds a charge but must NOT reset the cooldown
        self.assertEqual(self.hero.tp_charges, 1)
        self.assertGreater(self.hero.tp_cooldown, 0)
        # Using again while on cooldown is blocked (charge not consumed).
        self._cast_tp(self.struct.x, self.struct.y)
        self.assertEqual(self.hero.tp_charges, 1)

    def test_cooldown_ticks_down(self):
        self.hero.tp_cooldown = 1.0
        for _ in range(30):
            system_status(self.state, 0.05)
        self.assertEqual(self.hero.tp_cooldown, 0.0)


if __name__ == "__main__":
    unittest.main()
