"""Tests for the code-driven item system: buy/sell, stat application, actives."""

import unittest

from server.game_state import GameState
from server.systems import system_ability_cast, system_damage_death
from server.items import get_item_def, item_catalog, list_item_ids
from shared.game_types import Team
from shared.config import ITEM_SLOTS


class TestItemCatalog(unittest.TestCase):
    def test_catalog_nonempty_and_wire_safe(self):
        self.assertTrue(len(list_item_ids()) >= 1)
        for it in item_catalog():
            self.assertIn("item_id", it)
            self.assertIn("cost", it)
            self.assertIn("bonuses", it)
            self.assertNotIn("fn", it)  # no cast code on the wire


class TestBuySell(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")

    def _buy(self, item_id):
        item = get_item_def(item_id)
        self.hero.gold -= item.cost
        self.hero.inventory.append(item_id)
        item.apply(self.hero)

    def test_buy_applies_stats_and_sell_reverts(self):
        sword = get_item_def("long_sword")
        dmg0 = self.hero.attack_damage
        self._buy("long_sword")
        self.assertEqual(self.hero.attack_damage, dmg0 + sword.bonuses["atk_dmg"])
        self.assertIn("long_sword", self.hero.inventory)
        # Sell reverts the bonus exactly.
        sword.remove(self.hero)
        self.hero.inventory.remove("long_sword")
        self.assertEqual(self.hero.attack_damage, dmg0)

    def test_hp_item_grants_and_heals_then_reverts(self):
        gem = get_item_def("vitality_gem")
        mhp0, hp0 = self.hero.max_hp, self.hero.hp
        self._buy("vitality_gem")
        self.assertEqual(self.hero.max_hp, mhp0 + gem.bonuses["hp"])
        self.assertEqual(self.hero.hp, hp0 + gem.bonuses["hp"])  # heals on buy
        gem.remove(self.hero)
        self.assertEqual(self.hero.max_hp, mhp0)
        self.assertLessEqual(self.hero.hp, self.hero.max_hp)     # clamped

    def test_inventory_cap(self):
        self.assertGreaterEqual(ITEM_SLOTS, 1)


class TestItemActive(unittest.TestCase):
    def test_active_heals_and_goes_on_cooldown(self):
        state = GameState()
        hero = state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")
        flask = get_item_def("health_flask")
        hero.inventory.append("health_flask")
        flask.apply(hero)
        hero.hp = 100
        # Trigger the active in slot 1 ("I1") via the ability cast path.
        state.ability_casts.append(
            {"caster": hero.entity_id, "key": "I1", "tx": 0.0, "ty": 0.0, "tid": None})
        system_ability_cast(state, 0.05)
        system_damage_death(state, 0.05)  # heal events resolved here
        self.assertGreater(hero.hp, 100)
        self.assertGreater(hero.item_cooldowns.get("health_flask", 0), 0)


if __name__ == "__main__":
    unittest.main()
