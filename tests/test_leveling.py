"""Phase 4: skill leveling (points, caps, R gates) + the pre-game countdown."""
import unittest

from shared.game_types import Team
from shared.config import PREGAME_COUNTDOWN, MAX_LEVEL
from server.entity import Minion
from server.game_state import GameState
from server.systems import _grant_xp, system_spawn_creeps, system_runes, step


class TestSkillPoints(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")

    def test_starts_with_one_point(self):
        self.assertEqual(self.hero.skill_points, 1)
        self.assertEqual(self.hero.ability_levels["Q"], 0)

    def test_level_up_grants_points(self):
        _grant_xp(self.hero, 10_000_000)  # vault to max level
        # 1 starting point + (level-1) from level-ups.
        self.assertEqual(self.hero.skill_points, 1 + (self.hero.level - 1))

    def test_learn_basic_ability(self):
        self.assertTrue(self.state.level_ability(1, "Q"))
        self.assertEqual(self.hero.ability_levels["Q"], 1)
        self.assertEqual(self.hero.skill_points, 0)

    def test_cannot_learn_without_points(self):
        self.hero.skill_points = 0
        self.assertFalse(self.state.level_ability(1, "Q"))

    def test_basic_caps_at_four(self):
        self.hero.skill_points = 99
        for _ in range(4):
            self.assertTrue(self.state.level_ability(1, "Q"))
        self.assertFalse(self.state.level_ability(1, "Q"))  # 5th blocked
        self.assertEqual(self.hero.ability_levels["Q"], 4)

    def test_ultimate_gated_by_hero_level(self):
        self.hero.skill_points = 99
        self.hero.level = 1
        self.assertFalse(self.state.level_ability(1, "R"))  # needs level 4
        self.hero.level = 4
        self.assertTrue(self.state.level_ability(1, "R"))   # rank 1 ok
        self.assertFalse(self.state.level_ability(1, "R"))  # rank 2 needs level 8
        self.hero.level = 8
        self.assertTrue(self.state.level_ability(1, "R"))
        self.hero.level = 12
        self.assertTrue(self.state.level_ability(1, "R"))
        self.assertEqual(self.hero.ability_levels["R"], 3)  # capped at 3
        self.assertFalse(self.state.level_ability(1, "R"))


class TestRankGate(unittest.TestCase):
    def test_unlearned_ability_cannot_cast(self):
        from server.entity import Projectile
        from server.systems import system_ability_cast
        state = GameState()
        hero = state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")
        state.ability_casts.append(
            {"caster": hero.entity_id, "key": "Q", "tx": hero.x + 100,
             "ty": hero.y, "tid": None})
        system_ability_cast(state, 0.05)
        projs = [e for e in state.entities.values() if isinstance(e, Projectile)]
        self.assertEqual(projs, [])  # rank 0 -> no cast
        # Learn it, then it casts.
        state.level_ability(1, "Q")
        state.ability_casts.append(
            {"caster": hero.entity_id, "key": "Q", "tx": hero.x + 100,
             "ty": hero.y, "tid": None})
        system_ability_cast(state, 0.05)
        self.assertTrue(any(isinstance(e, Projectile)
                            for e in state.entities.values()))


class TestMaxLevel(unittest.TestCase):
    def test_max_level_is_15(self):
        self.assertEqual(MAX_LEVEL, 15)


class TestCountdown(unittest.TestCase):
    def test_clock_starts_negative_and_gates_spawns(self):
        state = GameState()
        state.start_match(kill_target=10)
        self.assertAlmostEqual(state.match_clock, -PREGAME_COUNTDOWN)
        # During countdown: no creeps, no runes.
        system_spawn_creeps(state, 0.05)
        system_runes(state, 0.05)
        self.assertFalse(any(isinstance(e, Minion) for e in state.entities.values()))

    def test_wave_spawns_after_countdown(self):
        state = GameState()
        state.start_match(kill_target=10)
        # Run the clock down to 0 then one more tick.
        for _ in range(int(PREGAME_COUNTDOWN / 0.05) + 2):
            step(state, 0.05)
        self.assertGreater(state.match_clock, 0)
        self.assertTrue(any(isinstance(e, Minion) for e in state.entities.values()))


if __name__ == "__main__":
    unittest.main()
