"""The OOP status system: lifecycle hooks, stacking policies, aura toggling.

The dict-based predecessor could only carry numbers; behaviour lived in the
combat systems as explicit branches. These tests pin the behaviour that now
belongs to the status objects themselves.
"""
import math
import unittest

from server.stats import StatBlock
from server.status import (
    Aura,
    Invulnerable,
    RuneRegen,
    Shield,
    Slow,
    StackPolicy,
    StatBuff,
    Status,
    StatusContainer,
    Stun,
)


class _Bearer:
    """Minimal stand-in for an entity: just the two containers statuses need."""

    def __init__(self):
        self.stats = StatBlock()
        self.statuses = StatusContainer(self.stats, self)


class _Event:
    """Stand-in for the damage pipeline's event object."""

    def __init__(self, amount):
        self.amount = amount
        self.absorbed = 0


class TestFlags(unittest.TestCase):
    def test_flag_lookup_is_reference_counted(self):
        b = _Bearer()
        self.assertFalse(b.statuses.has("stun"))
        first = Stun(2.0, source="a")
        second = Stun(2.0, source="b")
        b.statuses.add(first)
        b.statuses.add(second)
        self.assertTrue(b.statuses.has("stun"))
        # Removing one of two stun sources must not clear the flag.
        b.statuses.remove(first)
        self.assertTrue(b.statuses.has("stun"))
        b.statuses.remove(second)
        self.assertFalse(b.statuses.has("stun"))

    def test_unknown_flag_is_rejected(self):
        class Bogus(Status):
            status_id = "bogus"
            flags = frozenset({"not_a_real_flag"})

        with self.assertRaises(ValueError):
            Bogus(1.0)


class TestStackPolicies(unittest.TestCase):
    """Stacking is scoped to (status_id, source): re-applying *the same effect
    from the same source* follows the policy; two different sources are
    independent."""

    def test_refresh_keeps_one_and_extends(self):
        b = _Bearer()
        b.statuses.add(Stun(1.0, source="q"))
        b.statuses.add(Stun(3.0, source="q"))
        self.assertEqual(len(b.statuses), 1)
        self.assertAlmostEqual(b.statuses.get("stun").remaining, 3.0)

    def test_refresh_never_shortens(self):
        b = _Bearer()
        b.statuses.add(Stun(3.0, source="q"))
        b.statuses.add(Stun(0.5, source="q"))
        self.assertAlmostEqual(b.statuses.get("stun").remaining, 3.0)

    def test_different_sources_are_independent(self):
        # Two abilities that both slow must stack toward the cap rather than
        # one silently refreshing the other.
        b = _Bearer()
        b.statuses.add(Slow(2.0, 0.5, source="a"))
        b.statuses.add(Slow(2.0, 0.5, source="b"))
        self.assertEqual(len(b.statuses), 2)
        self.assertAlmostEqual(b.stats.total("slow_pct"), 0.8)  # capped

    def test_unsourced_statuses_are_independent(self):
        b = _Bearer()
        b.statuses.add(Slow(2.0, 0.3))
        b.statuses.add(Slow(2.0, 0.3))
        self.assertEqual(len(b.statuses), 2)
        self.assertAlmostEqual(b.stats.total("slow_pct"), 0.6)

    def test_ignore_discards_the_new_application(self):
        class Once(Status):
            status_id = "once"
            stack_policy = StackPolicy.IGNORE

        b = _Bearer()
        first = Once(1.0, source="s")
        b.statuses.add(first)
        self.assertIsNone(b.statuses.add(Once(9.0, source="s")))
        self.assertAlmostEqual(first.remaining, 1.0)

    def test_stack_accumulates_and_scales_modifiers(self):
        class Charge(Status):
            status_id = "charge"
            stack_policy = StackPolicy.STACK
            max_stacks = 3
            modifiers = {"dmg_bonus": 10}

        b = _Bearer()
        for _ in range(5):  # more than max_stacks
            b.statuses.add(Charge(5.0, source="s"))
        held = b.statuses.get("charge")
        self.assertEqual(held.stacks, 3)
        self.assertEqual(b.stats.total("dmg_bonus"), 30)

    def test_strongest_replaces_a_weaker_instance(self):
        b = _Bearer()
        b.statuses.add(Shield(5.0, 100, source="s"))
        b.statuses.add(Shield(5.0, 400, source="s"))
        self.assertEqual(len(b.statuses), 1)
        self.assertEqual(b.statuses.get("shield").pool, 400)

    def test_strongest_keeps_the_incumbent_when_weaker(self):
        b = _Bearer()
        b.statuses.add(Shield(5.0, 400, source="s"))
        b.statuses.add(Shield(5.0, 100, source="s"))
        self.assertEqual(b.statuses.get("shield").pool, 400)


class TestLifecycle(unittest.TestCase):
    def test_hooks_fire_in_order(self):
        calls = []

        class Watched(Status):
            status_id = "watched"

            def on_apply(self, bearer, state):
                calls.append("apply")

            def on_tick(self, bearer, state, dt):
                calls.append("tick")

            def on_expire(self, bearer, state):
                calls.append("expire")

        b = _Bearer()
        b.statuses.add(Watched(0.1))
        b.statuses.tick(0.05)   # still alive -> ticks
        b.statuses.tick(0.05)   # hits zero -> expires without ticking again
        self.assertEqual(calls, ["apply", "tick", "expire"])

    def test_expiry_withdraws_modifiers(self):
        b = _Bearer()
        b.statuses.add(StatBuff(1.0, source="test", dmg_bonus=40))
        self.assertEqual(b.stats.total("dmg_bonus", 55), 95)
        b.statuses.tick(1.5)
        self.assertEqual(b.stats.total("dmg_bonus", 55), 55)
        self.assertEqual(len(b.statuses), 0)

    def test_infinite_duration_never_expires(self):
        b = _Bearer()
        b.statuses.add(Invulnerable(math.inf))
        for _ in range(100):
            b.statuses.tick(1.0)
        self.assertTrue(b.statuses.has("invuln"))

    def test_clear_fires_expire_and_withdraws_everything(self):
        expired = []

        class Watched(Status):
            status_id = "w"
            modifiers = {"dmg_bonus": 10}

            def on_expire(self, bearer, state):
                expired.append(True)

        b = _Bearer()
        b.statuses.add(Watched(5.0))
        b.statuses.clear()
        self.assertTrue(expired)
        self.assertEqual(b.stats.total("dmg_bonus"), 0)

    def test_remove_source_targets_by_tag(self):
        b = _Bearer()
        b.statuses.add(StatBuff(5.0, source="kapre:grove", phys_def=10))
        b.statuses.add(StatBuff(5.0, source="rune:haste", speed_bonus=200))
        b.statuses.remove_source("kapre:grove")
        self.assertEqual(b.stats.total("phys_def"), 0)
        self.assertEqual(b.stats.total("speed_bonus"), 200)


class TestShield(unittest.TestCase):
    def test_absorbs_then_expires_when_spent(self):
        b = _Bearer()
        b.statuses.add(Shield(10.0, 50))
        event = _Event(30)
        b.statuses.on_damage_taken(event)
        self.assertEqual(event.amount, 0)
        self.assertEqual(event.absorbed, 30)
        self.assertEqual(b.statuses.get("shield").pool, 20)

        event2 = _Event(80)
        b.statuses.on_damage_taken(event2)
        self.assertEqual(event2.amount, 60)   # 20 soaked, rest passes through
        # A spent shield marks itself done and is swept on the next tick.
        b.statuses.tick(0.01)
        self.assertIsNone(b.statuses.get("shield"))


class TestCancelOnHit(unittest.TestCase):
    def test_rune_regen_fizzles_when_damaged(self):
        b = _Bearer()
        b.statuses.add(RuneRegen(30.0, source="rune:regen_10x",
                                 hp_regen_bonus=45))
        self.assertEqual(b.stats.total("hp_regen_bonus"), 45)
        b.statuses.on_damage_taken(_Event(10))
        b.statuses.tick(0.01)
        self.assertEqual(len(b.statuses), 0)
        self.assertEqual(b.stats.total("hp_regen_bonus"), 0)

    def test_zero_damage_does_not_fizzle_it(self):
        b = _Bearer()
        b.statuses.add(RuneRegen(30.0, source="rune:regen_10x",
                                 hp_regen_bonus=45))
        b.statuses.on_damage_taken(_Event(0))
        b.statuses.tick(0.01)
        self.assertEqual(len(b.statuses), 1)


class TestAura(unittest.TestCase):
    """Replaces the strip-and-reapply-every-tick passive idiom."""

    def test_payload_follows_the_condition(self):
        class InTrees(Aura):
            status_id = "in_trees"
            modifiers = {"phys_def": 25}

            def condition(self, bearer, state):
                return getattr(bearer, "in_trees", False)

        b = _Bearer()
        b.in_trees = False
        b.statuses.add(InTrees())
        self.assertEqual(b.stats.total("phys_def"), 0)

        b.in_trees = True
        b.statuses.tick(0.05)
        self.assertEqual(b.stats.total("phys_def"), 25)

        b.in_trees = False
        b.statuses.tick(0.05)
        self.assertEqual(b.stats.total("phys_def"), 0)
        # Throughout, it stayed a single attached status rather than being
        # rebuilt each tick.
        self.assertEqual(len(b.statuses), 1)

    def test_aura_is_hidden_from_the_hud_by_default(self):
        class Ambient(Aura):
            status_id = "ambient"

        self.assertIsNone(Ambient().describe())


class TestHudDescription(unittest.TestCase):
    def test_wire_shape_is_stable(self):
        # The renderer reads exactly these keys; changing them breaks the HUD.
        desc = Slow(4.0, 0.3).describe()
        self.assertEqual(set(desc), {"lbl", "cat", "icon", "rem", "dur"})
        self.assertEqual(desc["cat"], "debuff")

    def test_stack_count_is_reported(self):
        class Charge(Status):
            status_id = "charge"
            stack_policy = StackPolicy.STACK
            max_stacks = 3
            modifiers = {"dmg_bonus": 5}

        b = _Bearer()
        b.statuses.add(Charge(5.0, source="s"))
        b.statuses.add(Charge(5.0, source="s"))
        self.assertEqual(b.statuses.get("charge").describe()["n"], 2)

    def test_sign_decides_category_for_a_generic_stat_buff(self):
        self.assertEqual(StatBuff(3.0, source="s", phys_def=-15)
                         .describe()["cat"], "debuff")
        self.assertEqual(StatBuff(3.0, source="s", phys_def=15)
                         .describe()["cat"], "buff")


if __name__ == "__main__":
    unittest.main()
