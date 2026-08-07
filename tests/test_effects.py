"""Phase 2: unified buff/debuff effects + stun / slow / silence enforcement."""
import unittest

from shared.game_types import Team, CastType
from server.status import Frenzy, Stun, make_status
from server.entity import Hero
from server.game_state import GameState
from server.heroes.base import HeroDef, ability, CastContext
from server import skills
from server.systems import (
    system_movement, system_combat, system_ability_cast, system_status,
)


class _Dummy(HeroDef):
    hero_id = "dummy"
    name = "Dummy"

    @ability("Q", "Zap", cd=1, mana=0, cast=CastType.NONE)
    def zap(ctx):
        ctx.caster.ability_state["zapped"] = ctx.caster.ability_state.get(
            "zapped", 0) + 1


class TestStatusBuilder(unittest.TestCase):
    def test_keeps_zero_valued_mods(self):
        # The dict constructor silently dropped falsy values, which made
        # "a slow of zero" indistinguishable from "no slow at all".
        status = make_status(3.0, phys_def=10, sp_def=0, source="x")
        self.assertEqual(status.active_modifiers["phys_def"], 10)
        self.assertEqual(status.active_modifiers["sp_def"], 0)
        self.assertEqual(status.remaining, 3.0)
        self.assertEqual(status.source, "x")

    def test_unknown_property_is_rejected(self):
        # Previously a silent no-op; now it fails where it is written.
        with self.assertRaises(Exception):
            make_status(3.0, phys_deff=10)

    def test_flags_are_separated_from_stats(self):
        status = make_status(2.0, stun=True, phys_def=5)
        self.assertIn("stun", status.active_flags)
        self.assertNotIn("stun", status.active_modifiers)
        self.assertEqual(status.active_modifiers["phys_def"], 5)


class TestDescribe(unittest.TestCase):
    def test_stores_duration(self):
        status = Stun(2.5)
        self.assertEqual(status.duration, 2.5)
        self.assertEqual(status.remaining, 2.5)

    def test_cc_is_debuff_with_icon_and_timer(self):
        d = Stun(1.5).describe()
        self.assertEqual(d["cat"], "debuff")
        self.assertEqual(d["icon"], "stun")
        self.assertEqual(d["dur"], 1.5)
        self.assertEqual(d["rem"], 1.5)

    def test_slow_is_debuff(self):
        self.assertEqual(make_status(2.0, source="s", slow_pct=0.3)
                         .describe()["cat"], "debuff")

    def test_positive_stat_is_buff(self):
        self.assertEqual(make_status(3.0, source="s", dmg_bonus=20)
                         .describe()["cat"], "buff")

    def test_negative_stat_is_debuff(self):
        self.assertEqual(make_status(3.0, source="s", phys_def=-10)
                         .describe()["cat"], "debuff")

    def test_nohud_is_hidden(self):
        self.assertIsNone(
            make_status(3.0, source="s", evasion=0.1, nohud=True).describe())

    def test_expired_is_hidden(self):
        status = Stun(1.0)
        status.remaining = 0.0
        self.assertIsNone(status.describe())

    def test_named_mechanic_status_describes_itself(self):
        d = Frenzy(9.0, source="tiktik:frenzy").describe()
        self.assertEqual(d["cat"], "buff")
        self.assertEqual(d["lbl"], "Frenzy")


class TestCrowdControl(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.hero = Hero(team=Team.TEAM1, x=100, y=100)
        self.hero.hero_def = _Dummy
        self.state.entities[self.hero.entity_id] = self.hero

    def test_stun_blocks_movement(self):
        self.hero.target_x, self.hero.target_y = 1000, 100
        self.hero.statuses.add(make_status(2.0, stun=True))
        system_movement(self.state, 0.1)
        self.assertEqual(self.hero.x, 100)  # didn't move

    def test_slow_reduces_speed_and_stacks_capped(self):
        self.hero.statuses.add(make_status(2.0, slow_pct=0.5))
        self.hero.statuses.add(make_status(2.0, slow_pct=0.5))
        # Stacks additively but is capped at 0.8.
        self.assertAlmostEqual(self.hero.slow_pct(), 0.8)
        self.assertAlmostEqual(self.hero.effective_move_speed(),
                               self.hero.move_speed * 0.2)

    def test_silence_blocks_cast_but_not_stun_movement(self):
        self.hero.statuses.add(make_status(2.0, silence=True))
        self.state.ability_casts.append(
            {"caster": self.hero.entity_id, "key": "Q", "tx": 0, "ty": 0,
             "tid": None})
        system_ability_cast(self.state, 0.1)
        self.assertNotIn("zapped", self.hero.ability_state)
        # Silence does not stop movement.
        self.assertFalse(self.hero.is_stunned())

    def test_stun_also_silences(self):
        self.hero.statuses.add(make_status(2.0, stun=True))
        self.assertTrue(self.hero.is_silenced())

    def test_effects_expire(self):
        self.hero.statuses.add(make_status(0.05, stun=True))
        system_status(self.state, 0.1)
        self.assertEqual(len(self.hero.statuses), 0)


class TestSkillHelpers(unittest.TestCase):
    def test_silence_helper(self):
        state = GameState()
        caster = Hero(team=Team.TEAM1)
        target = Hero(team=Team.TEAM2)
        ctx = CastContext(state, caster, 0, 0, target.entity_id)
        skills.silence(ctx, target, 2.0)
        self.assertTrue(target.is_silenced())

    def test_apply_effect_signed(self):
        h = Hero(phys_def=20)
        skills.apply_effect(h, 3.0, phys_def=-10)
        self.assertEqual(h.effective_phys_def(), 10)


if __name__ == "__main__":
    unittest.main()
