"""Tests for Kapre: smash, tree-proximity passives, and living in trees (R)."""

import unittest

from server.game_state import GameState
from server.entity import Tree
from server.systems import (
    system_ability_cast,
    system_damage_death,
    system_status,
    system_combat,
    system_hero_hooks,
)
from server.heroes.kapre import (
    Q_RADIUS, E_DMG_PER_RANK, E_RANGE_BONUS, R_VISION_BONUS,
)
from shared.geometry import point_segment_distance
from shared.game_types import Team


class TestKapre(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "K", Team.TEAM1, hero_id="kapre")
        self.enemy = self.state.add_hero(2, "E", Team.TEAM2, hero_id="brawler")
        self.hero.x, self.hero.y = 1000, 1000
        self.enemy.x, self.enemy.y = 1100, 1000
        for k in ("Q", "W", "E", "R"):
            self.hero.ability_levels[k] = 1

    def _cast(self, key, tx=None, ty=None, tid=None):
        self.state.ability_casts.append({
            "caster": self.hero.entity_id, "key": key,
            "tx": self.hero.x if tx is None else tx,
            "ty": self.hero.y if ty is None else ty, "tid": tid})
        system_ability_cast(self.state, 0.05)

    def _add_tree(self, x1, y1, x2, y2, th=80):
        tree = Tree(x1=x1, y1=y1, x2=x2, y2=y2, thickness=th)
        self.state.entities[tree.entity_id] = tree
        return tree

    # ----- Q Smash ----------------------------------------------------------
    def test_smash_damages_and_stuns_nearby(self):
        hp0 = self.enemy.hp
        self._cast("Q")
        system_damage_death(self.state, 0.05)
        self.assertLess(self.enemy.hp, hp0)
        self.assertTrue(self.enemy.is_stunned())

    def test_smash_misses_far_enemy(self):
        self.enemy.x = self.hero.x + Q_RADIUS + 400
        hp0 = self.enemy.hp
        self._cast("Q")
        system_damage_death(self.state, 0.05)
        self.assertEqual(self.enemy.hp, hp0)
        self.assertFalse(self.enemy.is_stunned())

    # ----- E / W tree-proximity passives ------------------------------------
    def test_ironbark_boosts_damage_and_range_near_tree(self):
        dmg0 = self.hero.effective_damage()
        rng0 = self.hero.effective_attack_range()
        self._add_tree(900, 1000, 1300, 1000)  # Kapre stands on the centerline
        system_hero_hooks(self.state, 0.05)
        self.assertEqual(self.hero.effective_damage() - dmg0, E_DMG_PER_RANK)
        self.assertEqual(self.hero.effective_attack_range() - rng0, E_RANGE_BONUS)

    def test_no_tree_passive_when_far(self):
        dmg0 = self.hero.effective_damage()
        self._add_tree(5000, 5000, 5400, 5000)  # far away
        system_hero_hooks(self.state, 0.05)
        self.assertEqual(self.hero.effective_damage(), dmg0)
        self.assertEqual(
            sum(b.get("hp_regen_bonus", 0) for b in self.hero.buffs), 0)

    def test_vigor_regen_near_tree(self):
        self._add_tree(900, 1000, 1300, 1000)
        system_hero_hooks(self.state, 0.05)
        self.assertGreater(
            sum(b.get("hp_regen_bonus", 0) for b in self.hero.buffs), 0)

    # ----- R Dwell ----------------------------------------------------------
    def test_dwell_binds_stealths_and_grants_vision(self):
        tree = self._add_tree(1000, 1400, 1400, 1400)
        self._cast("R", tx=1100, ty=1400)  # click on the tree
        self.assertIn("bind", self.hero.ability_state)
        self.assertTrue(self.hero.is_invisible())
        self.assertTrue(self.hero.has_unobstructed_vision())
        self.assertEqual(self.hero.bonus_vision(), R_VISION_BONUS)
        # Invisible to the enemy team, still seen by his own team.
        self.assertNotIn(self.hero.entity_id,
                         self.state.visible_entity_ids_for(Team.TEAM2))
        self.assertIn(self.hero.entity_id,
                      self.state.visible_entity_ids_for(Team.TEAM1))

    def test_dwell_recast_exits_and_sets_cooldown(self):
        self._add_tree(1000, 1400, 1400, 1400)
        self._cast("R", tx=1100, ty=1400)
        self.hero.cooldowns["R"] = 0.0  # toggle gate elapsed
        self._cast("R", tx=1100, ty=1400)
        self.assertNotIn("bind", self.hero.ability_state)
        self.assertFalse(self.hero.is_invisible())
        self.assertGreater(self.hero.cooldowns["R"], 1.0)

    def test_dwell_movement_clamps_to_tree(self):
        tree = self._add_tree(1000, 1400, 1400, 1400, th=80)
        self._cast("R", tx=1100, ty=1400)
        self.hero.x, self.hero.y = 1100, 3000  # try to wander far off the tree
        system_hero_hooks(self.state, 0.05)
        d = point_segment_distance(self.hero.x, self.hero.y,
                                   tree.x1, tree.y1, tree.x2, tree.y2)
        self.assertLessEqual(d, tree.thickness / 2.0 + 1.0)

    def test_dwell_attacks_apply_slow_and_reveal(self):
        tree = self._add_tree(1000, 1000, 1400, 1000, th=80)
        self._cast("R", tx=1100, ty=1000)
        # Park an enemy right next to Kapre's clamped position, in melee range.
        self.enemy.x, self.enemy.y = self.hero.x + 100, self.hero.y
        spd0 = self.enemy.effective_move_speed()
        system_combat(self.state, 0.05)
        system_damage_death(self.state, 0.05)
        self.assertLess(self.enemy.effective_move_speed(), spd0)  # 50% slow
        self.assertGreater(self.hero.reveal_timer, 0)             # seen attacking


if __name__ == "__main__":
    unittest.main()
