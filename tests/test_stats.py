"""Phase 1: physical/special stats, armor-curve reduction, per-level growth."""
import unittest

from shared.config import DEFENSE_K
from shared.game_types import Team
from server.entity import Hero
from server.game_state import GameState
from server.systems import _apply_defense, _grant_xp, system_damage_death


class TestArmorCurve(unittest.TestCase):
    def test_physical_reduced_by_phys_def(self):
        tgt = Hero(phys_def=100, sp_def=0)
        # DEF == K -> exactly half damage.
        self.assertEqual(_apply_defense(tgt, 100, "physical"),
                         int(100 * DEFENSE_K / (100 + DEFENSE_K)))
        self.assertEqual(_apply_defense(tgt, 100, "physical"), 50)

    def test_special_uses_sp_def(self):
        tgt = Hero(phys_def=0, sp_def=100)
        self.assertEqual(_apply_defense(tgt, 100, "special"), 50)
        # phys_def is irrelevant to special damage
        self.assertEqual(_apply_defense(tgt, 100, "physical"), 100)

    def test_true_damage_bypasses_defense(self):
        tgt = Hero(phys_def=500, sp_def=500)
        self.assertEqual(_apply_defense(tgt, 80, "true"), 80)

    def test_zero_defense_no_reduction(self):
        tgt = Hero(phys_def=0, sp_def=0)
        self.assertEqual(_apply_defense(tgt, 77, "physical"), 77)

    def test_damage_event_applies_reduction(self):
        state = GameState()
        attacker = Hero(team=Team.TEAM1)
        victim = Hero(team=Team.TEAM2, hp=600, max_hp=600, phys_def=100, sp_def=0)
        state.entities[attacker.entity_id] = attacker
        state.entities[victim.entity_id] = victim
        state.damage_events.append(
            {"src": attacker.entity_id, "tgt": victim.entity_id, "amt": 100,
             "dtype": "physical"})
        system_damage_death(state, 0.05)
        self.assertEqual(victim.hp, 550)  # 100 raw -> 50 after armor curve


class TestPerLevelGrowth(unittest.TestCase):
    def test_new_stats_grow_on_level(self):
        hero = Hero(level=1, xp=0, sp_atk=10, phys_def=20, sp_def=20,
                    sp_atk_per_level=5, phys_def_per_level=3, sp_def_per_level=2)
        _grant_xp(hero, 100000)  # vault several levels
        self.assertGreater(hero.level, 1)
        gained = hero.level - 1
        self.assertEqual(hero.sp_atk, 10 + 5 * gained)
        self.assertEqual(hero.phys_def, 20 + 3 * gained)
        self.assertEqual(hero.sp_def, 20 + 2 * gained)


class TestEffectiveStats(unittest.TestCase):
    def test_buffs_shift_defenses(self):
        hero = Hero(phys_def=20, sp_def=20)
        hero.buffs.append({"phys_def": 15, "sp_def": -5, "remaining": 3})
        self.assertEqual(hero.effective_phys_def(), 35)
        self.assertEqual(hero.effective_sp_def(), 15)

    def test_sp_atk_buff(self):
        hero = Hero(sp_atk=40)
        hero.buffs.append({"sp_atk": 10, "remaining": 3})
        self.assertEqual(hero.effective_sp_atk(), 50)


if __name__ == "__main__":
    unittest.main()
