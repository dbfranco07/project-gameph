"""The stat modifier layer: stacking rules, caps, and cache invalidation.

These pin contracts that used to be hand-coded inside six separate accessor
methods on `Hero`, where each stat's stacking behaviour was implicit in however
its one reader happened to sum things up.
"""
import unittest

from server.stats import (
    STAT_SPECS,
    StackRule,
    StatBlock,
    UnknownStatError,
)


class _Source:
    """An opaque modifier source token (a Status plays this role in game)."""


class TestStackRules(unittest.TestCase):
    def setUp(self):
        self.block = StatBlock()

    def test_add_sums_contributions(self):
        self.block.add(_Source(), {"dmg_bonus": 10})
        self.block.add(_Source(), {"dmg_bonus": 15})
        self.assertEqual(self.block.total("dmg_bonus", 55), 80)
        self.assertEqual(self.block.bonus("dmg_bonus"), 25)

    def test_mult_multiplies(self):
        self.block.add(_Source(), {"dmg_mult": 2.0})
        self.block.add(_Source(), {"dmg_mult": 1.5})
        self.assertAlmostEqual(self.block.total("dmg_mult", 1.0), 3.0)

    def test_min_wins_takes_the_best_cdr(self):
        # Cooldown reduction must not compound toward zero: the best one wins.
        self.block.add(_Source(), {"cd_mult": 0.5})
        self.block.add(_Source(), {"cd_mult": 0.8})
        self.assertAlmostEqual(self.block.total("cd_mult", 1.0), 0.5)

    def test_max_wins_takes_the_strongest_rider(self):
        self.block.add(_Source(), {"attack_slow_pct": 0.2})
        self.block.add(_Source(), {"attack_slow_pct": 0.45})
        self.assertAlmostEqual(self.block.total("attack_slow_pct"), 0.45)

    def test_capped_add_clamps(self):
        self.block.add(_Source(), {"slow_pct": 0.6})
        self.block.add(_Source(), {"slow_pct": 0.6})
        # Additive, but never enough to fully root: cap is 0.8.
        self.assertAlmostEqual(self.block.total("slow_pct"), 0.8)

    def test_cap_applies_to_base_plus_bonus(self):
        # A high base must not let a modifier push the total past the cap.
        self.block.add(_Source(), {"evasion": 0.5})
        self.assertAlmostEqual(self.block.total("evasion", 0.6), 0.95)

    def test_identity_when_nothing_contributes(self):
        self.assertEqual(self.block.bonus("dmg_bonus"), 0.0)
        self.assertEqual(self.block.bonus("dmg_mult"), 1.0)
        self.assertEqual(self.block.bonus("cd_mult"), 1.0)
        # ...and total() passes the base straight through.
        self.assertEqual(self.block.total("dmg_bonus", 55), 55)
        self.assertAlmostEqual(self.block.total("dmg_mult", 1.0), 1.0)


class TestSourceLifecycle(unittest.TestCase):
    def setUp(self):
        self.block = StatBlock()

    def test_remove_withdraws_only_that_source(self):
        a, b = _Source(), _Source()
        self.block.add(a, {"phys_def": 20})
        self.block.add(b, {"phys_def": 5})
        self.block.remove(a)
        self.assertEqual(self.block.total("phys_def", 10), 15)

    def test_removing_absent_source_is_a_noop(self):
        self.block.add(_Source(), {"phys_def": 20})
        self.block.remove(_Source())  # never added
        self.assertEqual(self.block.total("phys_def"), 20)

    def test_readding_same_source_replaces_rather_than_doubles(self):
        src = _Source()
        self.block.add(src, {"dmg_bonus": 10})
        self.block.add(src, {"dmg_bonus": 30})
        self.assertEqual(self.block.total("dmg_bonus"), 30)

    def test_clear_drops_everything(self):
        self.block.add(_Source(), {"dmg_bonus": 10})
        self.block.clear()
        self.assertEqual(self.block.total("dmg_bonus", 55), 55)

    def test_sources_for_finds_contributors(self):
        a, b = _Source(), _Source()
        self.block.add(a, {"attack_slow_pct": 0.3})
        self.block.add(b, {"dmg_bonus": 5})
        self.assertEqual(self.block.sources_for("attack_slow_pct"), [a])


class TestCacheInvalidation(unittest.TestCase):
    """Reads are cached, so every mutation path must invalidate or stats go
    silently stale — the one failure mode this layer could introduce."""

    def test_add_invalidates(self):
        block = StatBlock()
        self.assertEqual(block.total("dmg_bonus"), 0)  # populates the cache
        block.add(_Source(), {"dmg_bonus": 25})
        self.assertEqual(block.total("dmg_bonus"), 25)

    def test_remove_invalidates(self):
        block = StatBlock()
        src = _Source()
        block.add(src, {"dmg_bonus": 25})
        self.assertEqual(block.total("dmg_bonus"), 25)
        block.remove(src)
        self.assertEqual(block.total("dmg_bonus"), 0)

    def test_touch_forces_recompute_for_in_place_mutation(self):
        block = StatBlock()
        src = _Source()
        block.add(src, {"dmg_bonus": 10})
        self.assertEqual(block.total("dmg_bonus"), 10)
        # A source that drains its own value in place then asks for a rebuild.
        block._mods[src]["dmg_bonus"] = 3
        block.touch()
        self.assertEqual(block.total("dmg_bonus"), 3)


class TestValidation(unittest.TestCase):
    def test_unknown_stat_is_rejected_on_add(self):
        # The dict system accepted any keyword, so a typo was a silent no-op.
        with self.assertRaises(UnknownStatError):
            StatBlock().add(_Source(), {"dmg_bonuss": 10})

    def test_unknown_stat_is_rejected_on_read(self):
        with self.assertRaises(UnknownStatError):
            StatBlock().total("not_a_stat")

    def test_empty_mods_is_accepted(self):
        block = StatBlock()
        block.add(_Source(), {})
        self.assertEqual(len(block._mods), 0)


class TestSpecs(unittest.TestCase):
    def test_every_spec_is_self_consistent(self):
        for key, spec in STAT_SPECS.items():
            with self.subTest(stat=key):
                self.assertEqual(spec.name, key)
                self.assertIsInstance(spec.rule, StackRule)
                # Only the capped rule should carry a cap.
                if spec.cap is not None:
                    self.assertIs(spec.rule, StackRule.CAPPED_ADD)

    def test_caps_match_the_documented_gameplay_limits(self):
        self.assertEqual(STAT_SPECS["slow_pct"].cap, 0.8)
        self.assertEqual(STAT_SPECS["evasion"].cap, 0.95)
        self.assertEqual(STAT_SPECS["dmg_reduction"].cap, 0.8)
        self.assertEqual(STAT_SPECS["crit_chance"].cap, 1.0)


if __name__ == "__main__":
    unittest.main()
