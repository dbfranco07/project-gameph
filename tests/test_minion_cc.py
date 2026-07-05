"""Tests for CC/debuffs on minions and neutrals (buffs live on Entity)."""

import unittest

from server.game_state import GameState
from server.entity import MeleeMinion, NeutralMinion
from server.skills import apply_effect
from server.systems import system_combat, system_movement, system_status
from shared.game_types import Team


class TestMinionCC(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.minion = MeleeMinion(team=Team.TEAM1, x=1000, y=1000,
                                  dest_x=3000, dest_y=1000)
        self.state.entities[self.minion.entity_id] = self.minion

    def test_apply_effect_lands_on_minion(self):
        apply_effect(self.minion, 1.0, stun=True)
        self.assertTrue(self.minion.is_stunned())

    def test_minion_buff_expires_via_system_status(self):
        apply_effect(self.minion, 0.2, slow_pct=0.4)
        self.assertGreater(self.minion.slow_pct(), 0)
        for _ in range(6):
            system_status(self.state, 0.05)
        self.assertEqual(self.minion.slow_pct(), 0)

    def test_stunned_minion_holds_position(self):
        apply_effect(self.minion, 1.0, stun=True)
        x0 = self.minion.x
        system_movement(self.state, 0.05)
        self.assertEqual(self.minion.x, x0)

    def test_stunned_minion_does_not_attack(self):
        enemy = MeleeMinion(team=Team.TEAM2, x=1040, y=1000)
        self.state.entities[enemy.entity_id] = enemy
        apply_effect(self.minion, 1.0, stun=True)
        system_combat(self.state, 0.05)
        self.assertFalse(any(ev.get("src") == self.minion.entity_id
                             for ev in self.state.damage_events))

    def test_slowed_minion_moves_less(self):
        x0 = self.minion.x
        system_movement(self.state, 0.05)
        free_step = self.minion.x - x0
        self.assertGreater(free_step, 0)
        slowed = MeleeMinion(team=Team.TEAM1, x=1000, y=2000,
                             dest_x=3000, dest_y=2000)
        self.state.entities[slowed.entity_id] = slowed
        apply_effect(slowed, 5.0, slow_pct=0.5)
        system_movement(self.state, 0.05)
        self.assertAlmostEqual(slowed.x - 1000, free_step * 0.5, places=5)

    def test_shred_lowers_neutral_defense(self):
        mob = NeutralMinion(x=2000, y=2000, phys_def=20)
        self.state.entities[mob.entity_id] = mob
        apply_effect(mob, 2.0, phys_def=-10)
        self.assertEqual(mob.effective_phys_def(), 10)


if __name__ == "__main__":
    unittest.main()
