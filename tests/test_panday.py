"""Tests for Panday: the wall-forged sword, its claim/throw lifecycle, the
disarm passive, and the wall-pin on E."""

import unittest

from server.entity import Wall, GroundItem
from server.systems import system_ground_items
from server.heroes.panday import (
    Q_SWORD_LIFETIME, CARRY_RANGE_BONUS, CARRY_DMG_BONUS,
)
from tests.herotest import HeroTestCase


class TestPanday(HeroTestCase):
    hero_id = "panday"

    def _add_wall(self, x1, y1, x2, y2, th=60):
        wall = Wall(x1=x1, y1=y1, x2=x2, y2=y2, thickness=th)
        self.state.entities[wall.entity_id] = wall
        return wall

    # ----- Q Sword of Panday -------------------------------------------------
    def test_q_without_a_wall_does_nothing(self):
        hp0 = self.enemy.hp
        self.cast("Q", tx=self.hero.x, ty=self.hero.y)
        self.assertEqual(self.enemy.hp, hp0)
        self.assertNotIn("sword_id", self.hero.ability_state)

    def test_q_on_a_wall_damages_stuns_and_drops_a_sword(self):
        self._add_wall(self.hero.x + 40, self.hero.y - 200,
                       self.hero.x + 40, self.hero.y + 200)
        self.enemy.x, self.enemy.y = self.hero.x + 40, self.hero.y
        hp0 = self.enemy.hp
        self.cast("Q", tx=self.hero.x + 40, ty=self.hero.y)
        self.resolve_damage()
        self.assertLess(self.enemy.hp, hp0)
        self.assertTrue(self.enemy.is_stunned())
        sword_id = self.hero.ability_state.get("sword_id")
        self.assertIsNotNone(sword_id)
        self.assertIsInstance(self.state.entities.get(sword_id), GroundItem)

    def test_recast_replaces_unclaimed_sword(self):
        self._add_wall(self.hero.x + 40, self.hero.y - 200,
                       self.hero.x + 40, self.hero.y + 200)
        self.cast("Q", tx=self.hero.x + 40, ty=self.hero.y)
        first_id = self.hero.ability_state["sword_id"]
        self.ready("Q")
        self.cast("Q", tx=self.hero.x + 40, ty=self.hero.y + 50)
        second_id = self.hero.ability_state["sword_id"]
        self.assertNotEqual(first_id, second_id)
        self.assertNotIn(first_id, self.state.entities)

    def test_sword_expires_after_its_lifetime(self):
        self._add_wall(self.hero.x + 40, self.hero.y - 200,
                       self.hero.x + 40, self.hero.y + 200)
        self.cast("Q", tx=self.hero.x + 40, ty=self.hero.y)
        sword_id = self.hero.ability_state["sword_id"]
        system_ground_items(self.state, Q_SWORD_LIFETIME + 1.0)
        self.assertNotIn(sword_id, self.state.entities)

    # ----- claiming the sword (on_tick) --------------------------------------
    def test_walking_up_claims_the_sword_and_grants_the_passive(self):
        self._add_wall(self.hero.x + 40, self.hero.y - 200,
                       self.hero.x + 40, self.hero.y + 200)
        self.cast("Q", tx=self.hero.x + 40, ty=self.hero.y)
        rng0 = self.hero.effective_attack_range()
        dmg0 = self.hero.effective_damage()
        self.hero.x, self.hero.y = self.hero.x + 40, self.hero.y
        # Claiming the sword and the aura's condition turning true both happen
        # inside the same on_tick; the modifier sync that reads it lands the
        # following tick (a ~50ms lag, invisible in real play).
        self.tick(times=2)
        self.assertTrue(self.hero.ability_state.get("carries_sword"))
        self.assertNotIn("sword_id", self.hero.ability_state)
        self.assertEqual(self.hero.effective_attack_range() - rng0,
                         CARRY_RANGE_BONUS)
        self.assertEqual(self.hero.effective_damage() - dmg0, CARRY_DMG_BONUS)

    def test_far_from_the_sword_does_not_claim_it(self):
        self._add_wall(self.hero.x + 400, self.hero.y - 200,
                       self.hero.x + 400, self.hero.y + 200)
        self.cast("Q", tx=self.hero.x + 400, ty=self.hero.y)
        self.tick()
        self.assertFalse(self.hero.ability_state.get("carries_sword"))

    # ----- W Weakness Reader --------------------------------------------------
    def test_weakness_reader_disarms_nearby_enemy(self):
        self.enemy.x, self.enemy.y = self.hero.x + 100, self.hero.y
        self.cast("W")
        self.assertTrue(self.enemy.is_disarmed())

    def test_weakness_reader_misses_far_enemy(self):
        self.enemy.x, self.enemy.y = self.hero.x + 5000, self.hero.y
        self.cast("W")
        self.assertFalse(self.enemy.is_disarmed())

    # ----- E Panday's Throw ---------------------------------------------------
    def test_throw_without_sword_just_buffs_speed(self):
        spd0 = self.hero.effective_move_speed()
        hp0 = self.enemy.hp
        self.cast_at("E", self.enemy)
        self.assertEqual(self.enemy.hp, hp0)
        self.assertGreater(self.hero.effective_move_speed(), spd0)

    def test_throw_with_sword_damages_and_consumes_it(self):
        self.hero.ability_state["carries_sword"] = True
        hp0 = self.enemy.hp
        self.cast_at("E", self.enemy)
        self.resolve_damage()
        self.assertLess(self.enemy.hp, hp0)  # armor mitigates E_THROW_DMG some
        self.assertFalse(self.hero.ability_state.get("carries_sword"))

    def test_throw_pins_and_stuns_when_wall_is_behind_target(self):
        # Wall directly behind the enemy from the hero's point of view.
        self._add_wall(self.enemy.x + 60, self.enemy.y - 200,
                       self.enemy.x + 60, self.enemy.y + 200)
        self.hero.ability_state["carries_sword"] = True
        self.cast_at("E", self.enemy)
        self.assertTrue(self.enemy.is_stunned())
        # Pinned onto (or right at) the wall's band.
        self.assertGreater(self.enemy.x, self.hero.x)

    def test_throw_without_wall_behind_target_no_pin(self):
        self.hero.ability_state["carries_sword"] = True
        self.cast_at("E", self.enemy)
        self.assertFalse(self.enemy.is_stunned())

    # ----- R Master's Slash ----------------------------------------------------
    def test_masters_slash_hits_twice_0_2s_apart(self):
        self.enemy.x = self.hero.x + self.hero.effective_attack_range() * 1.5
        self.enemy.y = self.hero.y
        spd0 = self.enemy.effective_move_speed()
        hp0 = self.enemy.hp
        self.cast("R", tx=self.enemy.x, ty=self.enemy.y)
        self.tick(times=3)          # < 0.2s: neither slash has landed yet
        self.assertEqual(self.enemy.hp, hp0)
        self.tick(times=1)          # crosses 0.2s: first slash lands
        hp_after_first = self.enemy.hp
        self.assertLess(hp_after_first, hp0)
        self.assertLess(self.enemy.effective_move_speed(), spd0)
        self.tick(times=4)          # crosses 0.4s: second slash lands
        self.assertLess(self.enemy.hp, hp_after_first)

    # ----- death resets the passive --------------------------------------------
    def test_death_drops_the_carry_bonus(self):
        self.hero.ability_state["carries_sword"] = True
        self.hero.hero_def.on_death(self.state, self.hero, None)
        self.assertFalse(self.hero.ability_state.get("carries_sword"))


if __name__ == "__main__":
    unittest.main()
