"""Phase 2: unified buff/debuff effects + stun / slow / silence enforcement."""
import unittest

from shared.game_types import Team, CastType
from server.effects import make_effect, describe_effect
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


class TestEffectBuilder(unittest.TestCase):
    def test_make_effect_drops_zero_mods(self):
        eff = make_effect(3.0, phys_def=10, sp_def=0, source="x")
        self.assertEqual(eff["phys_def"], 10)
        self.assertNotIn("sp_def", eff)
        self.assertEqual(eff["remaining"], 3.0)
        self.assertEqual(eff["source"], "x")


class TestDescribeEffect(unittest.TestCase):
    def test_make_effect_stores_duration(self):
        eff = make_effect(2.5, stun=True)
        self.assertEqual(eff["dur"], 2.5)
        self.assertEqual(eff["remaining"], 2.5)

    def test_cc_is_debuff_with_icon_and_timer(self):
        d = describe_effect(make_effect(1.5, stun=True))
        self.assertEqual(d["cat"], "debuff")
        self.assertEqual(d["icon"], "stun")
        self.assertEqual(d["dur"], 1.5)
        self.assertEqual(d["rem"], 1.5)

    def test_slow_is_debuff(self):
        self.assertEqual(describe_effect(make_effect(2.0, slow_pct=0.3))["cat"],
                         "debuff")

    def test_positive_stat_is_buff(self):
        self.assertEqual(describe_effect(make_effect(3.0, dmg_bonus=20))["cat"],
                         "buff")

    def test_negative_stat_is_debuff(self):
        self.assertEqual(describe_effect(make_effect(3.0, phys_def=-10))["cat"],
                         "debuff")

    def test_nohud_is_hidden(self):
        self.assertIsNone(describe_effect(
            make_effect(3.0, evasion=0.1, nohud=True)))

    def test_expired_is_hidden(self):
        eff = make_effect(1.0, stun=True)
        eff["remaining"] = 0.0
        self.assertIsNone(describe_effect(eff))

    def test_source_tagged_custom_buff_named(self):
        d = describe_effect(make_effect(9.0, source="tiktik:frenzy", frenzy=True))
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
        self.hero.buffs.append(make_effect(2.0, stun=True))
        system_movement(self.state, 0.1)
        self.assertEqual(self.hero.x, 100)  # didn't move

    def test_slow_reduces_speed_and_stacks_capped(self):
        self.hero.buffs.append(make_effect(2.0, slow_pct=0.5))
        self.hero.buffs.append(make_effect(2.0, slow_pct=0.5))
        # Stacks additively but is capped at 0.8.
        self.assertAlmostEqual(self.hero.slow_pct(), 0.8)
        self.assertAlmostEqual(self.hero.effective_move_speed(),
                               self.hero.move_speed * 0.2)

    def test_silence_blocks_cast_but_not_stun_movement(self):
        self.hero.buffs.append(make_effect(2.0, silence=True))
        self.state.ability_casts.append(
            {"caster": self.hero.entity_id, "key": "Q", "tx": 0, "ty": 0,
             "tid": None})
        system_ability_cast(self.state, 0.1)
        self.assertNotIn("zapped", self.hero.ability_state)
        # Silence does not stop movement.
        self.assertFalse(self.hero.is_stunned())

    def test_stun_also_silences(self):
        self.hero.buffs.append(make_effect(2.0, stun=True))
        self.assertTrue(self.hero.is_silenced())

    def test_effects_expire(self):
        self.hero.buffs.append(make_effect(0.05, stun=True))
        system_status(self.state, 0.1)
        self.assertEqual(self.hero.buffs, [])


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
