"""The code-driven item system: buy/sell, recipes, passives, procs, actives.

Items are modifier sources on the hero's `StatBlock` rather than direct writes
to base stats, so the invariant that matters most here is that **selling
withdraws exactly what buying granted** — with duplicates, with recipes, and
after dying.
"""

import unittest

from server.game_state import GameState
from server.systems import (
    system_ability_cast, system_damage_death, system_status, _kill,
)
from server.items import (
    ITEM_REGISTRY, apply_inventory_change, get_item_def, item_catalog,
    list_item_ids, purchase_plan, resync, upgrades_from,
)
from shared.game_types import Team
from shared.config import ITEM_SLOTS


class _Harness(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")
        self.hero.gold = 99999

    def buy(self, item_id):
        """Buy through the same path the server handler uses."""
        item = get_item_def(item_id)
        plan = purchase_plan(self.hero, item)
        self.assertIsNotNone(plan, f"no room to buy {item_id}")
        price, slots = plan
        self.hero.gold -= price

        def mutate():
            for slot in sorted(slots, reverse=True):
                self.hero.inventory.pop(slot)
            self.hero.inventory.append(item_id)

        apply_inventory_change(self.hero, self.state, mutate)
        return price

    def sell(self, slot):
        apply_inventory_change(self.hero, self.state,
                               lambda: self.hero.inventory.pop(slot))


class TestCatalog(unittest.TestCase):
    def test_catalog_is_wire_safe(self):
        self.assertTrue(len(list_item_ids()) >= 1)
        for it in item_catalog():
            self.assertIn("item_id", it)
            self.assertIn("cost", it)
            self.assertIn("bonuses", it)
            self.assertNotIn("fn", it)  # no cast code on the wire

    def test_registry_is_auto_discovered(self):
        # No hand-maintained list: the recipe items below are only ever
        # declared as classes, never registered anywhere.
        for expected in ("long_sword", "bloodblade", "thorn_mail"):
            self.assertIn(expected, ITEM_REGISTRY)

    def test_recipe_prices_are_consistent(self):
        # A recipe's full price must equal its parts plus the combine cost,
        # otherwise buying components first would be a strict win or loss.
        for cls in ITEM_REGISTRY.values():
            if not cls.components:
                continue
            with self.subTest(item=cls.item_id):
                self.assertEqual(cls.cost,
                                 cls.component_cost() + cls.recipe_cost)

    def test_every_component_exists(self):
        for cls in ITEM_REGISTRY.values():
            for cid in cls.components:
                with self.subTest(item=cls.item_id, component=cid):
                    self.assertIn(cid, ITEM_REGISTRY)

    def test_upgrades_from_finds_dependents(self):
        ids = {c.item_id for c in upgrades_from("long_sword")}
        self.assertIn("bloodblade", ids)


class TestBuySell(_Harness):
    def test_buy_grants_stats_and_sell_withdraws_them(self):
        sword = get_item_def("long_sword")
        dmg0 = self.hero.effective_damage()
        self.buy("long_sword")
        self.assertEqual(self.hero.effective_damage(),
                         dmg0 + sword.bonuses["atk_dmg"])
        self.assertIn("long_sword", self.hero.inventory)
        self.sell(0)
        self.assertEqual(self.hero.effective_damage(), dmg0)

    def test_hp_item_heals_on_buy_and_clamps_on_sell(self):
        gem = get_item_def("vitality_gem")
        mhp0, hp0 = self.hero.effective_max_hp(), self.hero.hp
        self.buy("vitality_gem")
        self.assertEqual(self.hero.effective_max_hp(), mhp0 + gem.bonuses["hp"])
        self.assertEqual(self.hero.hp, hp0 + gem.bonuses["hp"])  # heals on buy
        self.sell(0)
        self.assertEqual(self.hero.effective_max_hp(), mhp0)
        self.assertLessEqual(self.hero.hp, self.hero.effective_max_hp())

    def test_duplicate_copies_both_contribute(self):
        sword = get_item_def("long_sword")
        dmg0 = self.hero.effective_damage()
        self.buy("long_sword")
        self.buy("long_sword")
        self.assertEqual(self.hero.effective_damage(),
                         dmg0 + 2 * sword.bonuses["atk_dmg"])
        # Selling one leaves exactly one copy's worth behind — the bug class
        # that instance-indexed bookkeeping is prone to.
        self.sell(0)
        self.assertEqual(self.hero.effective_damage(),
                         dmg0 + sword.bonuses["atk_dmg"])

    def test_any_stat_can_be_granted(self):
        # The old design hard-limited items to six stats; armor was impossible.
        pdef0 = self.hero.effective_phys_def()
        self.buy("iron_plate")
        self.assertGreater(self.hero.effective_phys_def(), pdef0)

    def test_item_stats_show_in_hud_deltas(self):
        # Item bonuses were previously invisible to the HUD's delta row because
        # they were written straight onto the base stat.
        self.buy("long_sword")
        self.assertEqual(self.hero.to_snapshot()["dlt"]["ad"],
                         get_item_def("long_sword").bonuses["atk_dmg"])

    def test_inventory_cap_is_respected(self):
        for _ in range(ITEM_SLOTS):
            self.buy("iron_plate")
        self.assertEqual(len(self.hero.inventory), ITEM_SLOTS)
        # No room for a seventh: the plan refuses rather than overflowing.
        self.assertIsNone(purchase_plan(self.hero, get_item_def("long_sword")))


class TestRecipes(_Harness):
    def test_owning_components_costs_only_the_recipe(self):
        blade = get_item_def("bloodblade")
        self.buy("long_sword")
        self.buy("hunting_knife")
        paid = self.buy("bloodblade")
        self.assertEqual(paid, blade.recipe_cost)

    def test_components_are_consumed(self):
        self.buy("long_sword")
        self.buy("hunting_knife")
        self.buy("bloodblade")
        self.assertEqual(self.hero.inventory, ["bloodblade"])

    def test_buying_outright_costs_full_price(self):
        blade = get_item_def("bloodblade")
        self.assertEqual(self.buy("bloodblade"), blade.cost)

    def test_stats_are_not_double_counted_after_combining(self):
        blade = get_item_def("bloodblade")
        dmg0 = self.hero.effective_damage()
        self.buy("long_sword")
        self.buy("hunting_knife")
        self.buy("bloodblade")
        # Only the upgrade's stats remain — the components' are withdrawn.
        self.assertEqual(self.hero.effective_damage(),
                         dmg0 + blade.bonuses["atk_dmg"])

    def test_partial_components_pay_for_the_rest(self):
        blade = get_item_def("bloodblade")
        knife = get_item_def("hunting_knife")
        self.buy("long_sword")
        paid = self.buy("bloodblade")
        self.assertEqual(paid, blade.recipe_cost + knife.cost)

    def test_combining_frees_a_slot(self):
        # Fill up, then confirm a combine still fits: it consumes two and adds
        # one, so a full inventory can still upgrade.
        self.buy("long_sword")
        self.buy("hunting_knife")
        for _ in range(ITEM_SLOTS - 2):
            self.buy("iron_plate")
        self.assertEqual(len(self.hero.inventory), ITEM_SLOTS)
        self.assertIsNotNone(purchase_plan(self.hero, get_item_def("bloodblade")))


class TestPassivesAndProcs(_Harness):
    def _enemy(self):
        e = self.state.add_hero(2, "B", Team.TEAM2, hero_id="brawler")
        e.x, e.y = self.hero.x + 40, self.hero.y
        return e

    def test_passive_is_granted_and_withdrawn(self):
        self.buy("thorn_mail")
        self.assertIsNotNone(self.hero.statuses.get("item:thorns"))
        self.sell(0)
        self.assertIsNone(self.hero.statuses.get("item:thorns"))

    def test_unique_passive_does_not_stack(self):
        self.buy("thorn_mail")
        self.buy("thorn_mail")
        self.assertEqual(len(self.hero.statuses.all_of("item:thorns")), 1)

    def test_on_hit_proc_slows_the_victim(self):
        enemy = self._enemy()
        self.buy("frost_maul")
        self.state.damage_events.append(
            {"src": self.hero.entity_id, "tgt": enemy.entity_id, "amt": 40,
             "basic": True})
        system_damage_death(self.state, 0.05)
        self.assertGreater(enemy.slow_pct(), 0)

    def test_on_kill_proc_stacks_damage(self):
        enemy = self._enemy()
        self.buy("bloodblade")
        proc = self.hero.statuses.get("item:bloodthirst")
        self.assertEqual(proc.kills, 0)
        bonus0 = self.hero.stats.bonus("dmg_bonus")
        enemy.hp = 1
        self.state.damage_events.append(
            {"src": self.hero.entity_id, "tgt": enemy.entity_id, "amt": 999,
             "dtype": "true"})
        system_damage_death(self.state, 0.05)
        system_status(self.state, 0.05)   # dynamic modifiers re-pushed here
        # Assert on the proc's own contribution: a hero kill also grants XP,
        # which levels the hero and raises base attack damage, so comparing
        # effective_damage() alone would pass even with the proc unwired.
        self.assertEqual(proc.kills, 1)
        self.assertEqual(self.hero.stats.bonus("dmg_bonus"),
                         bonus0 + proc.DMG_PER_STACK)

    def test_on_kill_proc_ignores_minions(self):
        from server.entity import MeleeMinion
        from shared.game_types import Team as T
        self.buy("bloodblade")
        proc = self.hero.statuses.get("item:bloodthirst")
        minion = MeleeMinion(team=T.TEAM2, x=self.hero.x + 30, y=self.hero.y)
        self.state.entities[minion.entity_id] = minion
        minion.hp = 1
        self.state.damage_events.append(
            {"src": self.hero.entity_id, "tgt": minion.entity_id, "amt": 999,
             "dtype": "true"})
        system_damage_death(self.state, 0.05)
        self.assertEqual(proc.kills, 0)

    def test_thorns_reflects_damage_to_the_attacker(self):
        enemy = self._enemy()
        self.buy("thorn_mail")
        hp0 = enemy.hp
        self.state.damage_events.append(
            {"src": enemy.entity_id, "tgt": self.hero.entity_id, "amt": 200,
             "basic": True})
        system_damage_death(self.state, 0.05)
        system_damage_death(self.state, 0.05)  # the reflect resolves next pass
        self.assertLess(enemy.hp, hp0)

    def test_second_wind_survives_a_lethal_blow_once(self):
        self.buy("guardian_amulet")
        self.hero.hp = 300
        self.state.damage_events.append(
            {"src": None, "tgt": self.hero.entity_id, "amt": 9999,
             "dtype": "true"})
        system_damage_death(self.state, 0.05)
        self.assertTrue(self.hero.alive)
        self.assertEqual(self.hero.hp, 1)
        # Spent: the next lethal hit kills.
        self.hero.hp = 300
        self.state.damage_events.append(
            {"src": None, "tgt": self.hero.entity_id, "amt": 9999,
             "dtype": "true"})
        system_damage_death(self.state, 0.05)
        self.assertFalse(self.hero.alive)


class TestDeathAndPersistence(_Harness):
    def test_items_survive_death(self):
        # Statuses are cleared on death; equipped items must not be, or dying
        # would silently strip your build.
        sword = get_item_def("long_sword")
        self.buy("long_sword")
        dmg = self.hero.effective_damage()
        _kill(self.state, self.hero, None)
        self.assertEqual(self.hero.effective_damage(), dmg)
        self.assertIn("long_sword", self.hero.inventory)

    def test_temporary_buffs_do_not_survive_death(self):
        from server.status import make_status
        self.hero.statuses.add(make_status(30.0, source="x", dmg_bonus=100))
        _kill(self.state, self.hero, None)
        self.assertEqual(self.hero.stats.bonus("dmg_bonus"), 0)

    def test_resync_is_idempotent(self):
        self.buy("long_sword")
        self.buy("iron_plate")
        dmg, pdef = self.hero.effective_damage(), self.hero.effective_phys_def()
        for _ in range(3):
            resync(self.hero, self.state)
        self.assertEqual(self.hero.effective_damage(), dmg)
        self.assertEqual(self.hero.effective_phys_def(), pdef)


class TestActives(_Harness):
    def _cast(self, key):
        self.state.ability_casts.append(
            {"caster": self.hero.entity_id, "key": key,
             "tx": self.hero.x, "ty": self.hero.y, "tid": None})
        system_ability_cast(self.state, 0.05)

    def test_active_heals_and_goes_on_cooldown(self):
        self.buy("health_flask")
        self.hero.hp = 100
        self._cast("I1")
        system_damage_death(self.state, 0.05)  # heal events resolved here
        self.assertGreater(self.hero.hp, 100)
        self.assertGreater(self.hero.item_cooldowns.get("health_flask", 0), 0)

    def test_second_active_is_addressable_and_independently_cooled(self):
        # Two actives on one item — impossible under the old single-active
        # design, which stopped collecting after the first.
        amulet = get_item_def("guardian_amulet")
        self.assertEqual(len(amulet.actives), 2)
        self.buy("guardian_amulet")
        self._cast("I1")        # Barrier
        self.assertIsNotNone(self.hero.statuses.get("shield"))
        self.assertGreater(self.hero.item_cooldowns.get("guardian_amulet", 0), 0)
        # The second active is on its own cooldown key, so it is still ready.
        self.assertEqual(
            self.hero.item_cooldowns.get("guardian_amulet#1", 0), 0)

    def test_cleanse_active_strips_crowd_control(self):
        from server.status import Stun
        self.buy("guardian_amulet")
        self.hero.statuses.add(Stun(5.0), self.state)
        self.assertTrue(self.hero.is_stunned())
        self._cast("I1#1")      # Cleanse
        self.assertFalse(self.hero.is_stunned())


if __name__ == "__main__":
    unittest.main()
