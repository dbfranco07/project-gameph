"""Tests for the Manananggal hero: scratch/slow, pounce, bloodlust, and split."""

import unittest

from server.game_state import GameState
from server.entity import SplitBody, Wall
from server.systems import (
    system_ability_cast,
    system_damage_death,
    system_status,
    system_hero_hooks,
    system_collision,
)
from server.heroes.manananggal import (
    SPLIT_DURATION, SPLIT_LEASH, SPLIT_VISION_BONUS, Q_RANGE,
)
from shared.config import HERO_VISION_RADIUS
from shared.game_types import Team


class TestManananggal(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "M", Team.TEAM1, hero_id="manananggal")
        self.enemy = self.state.add_hero(2, "E", Team.TEAM2, hero_id="brawler")
        self.hero.x, self.hero.y = 1000, 1000
        self.enemy.x, self.enemy.y = 1200, 1000
        # Skill leveling now gates casting: learn every ability for the test.
        for k in ("Q", "W", "E", "R"):
            self.hero.ability_levels[k] = 1

    def _cast(self, key, tid=None):
        self.state.ability_casts.append({
            "caster": self.hero.entity_id, "key": key,
            "tx": self.hero.x, "ty": self.hero.y, "tid": tid})
        system_ability_cast(self.state, 0.05)

    def _body(self):
        return next((e for e in self.state.entities.values()
                     if isinstance(e, SplitBody)), None)

    # ----- Q / W / E --------------------------------------------------------
    def test_scratch_damages_and_slows(self):
        hp0 = self.enemy.hp
        spd0 = self.enemy.effective_move_speed()
        self._cast("Q", tid=self.enemy.entity_id)
        system_damage_death(self.state, 0.05)
        self.assertLess(self.enemy.hp, hp0)
        self.assertLess(self.enemy.effective_move_speed(), spd0)

    def test_scratch_falls_back_to_nearest_when_no_target(self):
        # A near-miss click sends no tid; Scratch should still claw an in-range
        # enemy (enemy is 200 units away, well within Q_RANGE).
        hp0 = self.enemy.hp
        spd0 = self.enemy.effective_move_speed()
        self._cast("Q", tid=None)  # tx/ty default to the caster's position
        system_damage_death(self.state, 0.05)
        self.assertLess(self.enemy.hp, hp0)
        self.assertLess(self.enemy.effective_move_speed(), spd0)

    def test_scratch_no_fallback_when_nothing_in_range(self):
        self.enemy.x = self.hero.x + Q_RANGE + 500  # far out of Q range
        hp0 = self.enemy.hp
        self._cast("Q", tid=None)
        system_damage_death(self.state, 0.05)
        self.assertEqual(self.enemy.hp, hp0)

    def test_pounce_dashes_toward_target(self):
        self.enemy.x = 1500
        x0 = self.hero.x
        self._cast("W", tid=self.enemy.entity_id)
        self.assertGreater(self.hero.x, x0)

    def test_pounce_cancels_pending_move(self):
        # A stale move order must not pull the hero back after it blinks.
        self.enemy.x = 1500
        self.hero.target_x, self.hero.target_y = 0, 0  # old destination behind it
        self.hero.attack_move = True
        self._cast("W", tid=self.enemy.entity_id)
        self.assertIsNone(self.hero.target_x)
        self.assertIsNone(self.hero.target_y)
        self.assertFalse(self.hero.attack_move)

    def test_bloodlust_haste_on_skill_use(self):
        interval0 = self.hero.effective_attack_interval()
        speed0 = self.hero.effective_move_speed()
        self._cast("W", tid=self.enemy.entity_id)
        self.assertLess(self.hero.effective_attack_interval(), interval0)
        self.assertGreater(self.hero.effective_move_speed(), speed0)

    def test_passive_key_is_not_castable(self):
        before = len(self.hero.buffs)
        self._cast("E")  # passive: server skips it entirely
        self.assertEqual(len(self.hero.buffs), before)

    # ----- R Split ----------------------------------------------------------
    def test_split_spawns_body_with_invuln_and_bonuses(self):
        rng0 = self.hero.effective_attack_range()
        dmg0 = self.hero.effective_damage()
        self._cast("R")
        self.assertIsNotNone(self._body())
        self.assertTrue(self.hero.is_invulnerable())
        self.assertGreater(self.hero.effective_attack_range(), rng0)
        self.assertGreater(self.hero.effective_damage(), dmg0)

    def test_split_hero_takes_no_damage_but_body_takes_double(self):
        self._cast("R")
        body = self._body()
        # Hero is invulnerable.
        self.state.damage_events.append(
            {"src": self.enemy.entity_id, "tgt": self.hero.entity_id, "amt": 9999})
        system_damage_death(self.state, 0.05)
        self.assertTrue(self.hero.alive)
        # Body takes 2x.
        hp0 = body.hp
        self.state.damage_events.append(
            {"src": self.enemy.entity_id, "tgt": body.entity_id, "amt": 10})
        system_damage_death(self.state, 0.05)
        self.assertEqual(hp0 - body.hp, 20)

    def test_body_destruction_kills_hero(self):
        self._cast("R")
        body = self._body()
        body.hp = 10
        self.state.damage_events.append(
            {"src": self.enemy.entity_id, "tgt": body.entity_id, "amt": 10})
        system_damage_death(self.state, 0.05)
        self.assertFalse(self.hero.alive)                       # body gone -> die
        self.assertNotIn(body.entity_id, self.state.entities)   # body cleaned up
        self.assertNotIn("split", self.hero.ability_state)

    def test_recombine_near_body_reforms_and_sets_cooldown(self):
        self._cast("R")
        body = self._body()
        self.hero.cooldowns["R"] = 0.0  # toggle gate elapsed; hero is at the body
        self._cast("R")
        self.assertNotIn("split", self.hero.ability_state)
        self.assertFalse(self.hero.is_invulnerable())
        self.assertNotIn(body.entity_id, self.state.entities)
        self.assertGreater(self.hero.cooldowns["R"], 1.0)       # real cooldown set

    def test_cannot_recombine_when_far(self):
        self._cast("R")
        body = self._body()
        self.hero.cooldowns["R"] = 0.0
        self.hero.x = body.x + 5000  # too far
        self._cast("R")
        self.assertIn("split", self.hero.ability_state)         # still split

    def test_leash_clamps_upper_half_to_body(self):
        self._cast("R")
        body = self._body()
        self.hero.x = body.x + 5000
        system_hero_hooks(self.state, 0.05)
        self.assertLessEqual(self.hero.distance_to(body), SPLIT_LEASH + 1)

    def test_split_auto_recombines_when_timer_expires(self):
        self._cast("R")
        for _ in range(int(SPLIT_DURATION / 0.05) + 3):
            system_status(self.state, 0.05)
            system_hero_hooks(self.state, 0.05)
        self.assertNotIn("split", self.hero.ability_state)
        self.assertFalse(self.hero.is_invulnerable())
        self.assertIsNone(self._body())

    def test_split_grants_bonus_vision(self):
        self.assertEqual(self.hero.bonus_vision(), 0)
        # An enemy parked just beyond base sight is invisible until the ult.
        far = self.state.add_hero(3, "F", Team.TEAM2, hero_id="brawler")
        far.x = self.hero.x + HERO_VISION_RADIUS + 100
        far.y = self.hero.y
        self.assertNotIn(far.entity_id,
                         self.state.visible_entity_ids_for(Team.TEAM1))
        self._cast("R")
        self.assertEqual(self.hero.bonus_vision(), SPLIT_VISION_BONUS)
        self.assertIn(far.entity_id,
                      self.state.visible_entity_ids_for(Team.TEAM1))

    def test_split_upper_half_passes_through_walls(self):
        wall = Wall(x1=self.hero.x, y1=self.hero.y - 100,
                    x2=self.hero.x, y2=self.hero.y + 100, thickness=120)
        self.state.entities[wall.entity_id] = wall
        x0 = self.hero.x
        # Grounded: collision ejects the hero out of the wall.
        system_collision(self.state, 0.05)
        self.assertNotAlmostEqual(self.hero.x, x0, places=1)
        # While split, the flying upper half ignores the wall.
        self.hero.x = x0
        self._cast("R")
        system_collision(self.state, 0.05)
        self.assertAlmostEqual(self.hero.x, x0, places=1)


if __name__ == "__main__":
    unittest.main()
