"""Tests for combat, death/respawn, scoring, and win conditions."""

import unittest

from server.game_state import GameState
from server.entity import Hero, Minion, Structure
from server.systems import (
    system_combat,
    system_damage_death,
    system_respawn,
    system_win_check,
    find_attack_target,
    step,
)
from shared.game_types import Team, GamePhase
from shared.config import HERO_RESPAWN_BASE


class TestCombat(unittest.TestCase):
    def setUp(self):
        self.state = GameState()

    def test_auto_attack_damages_enemy_in_range(self):
        a = self.state.add_hero(1, "A", Team.TEAM1, hero_id="brawler")
        b = self.state.add_hero(2, "B", Team.TEAM2, hero_id="brawler")
        a.x, a.y = 100, 100
        b.x, b.y = 200, 100  # within brawler range (150)
        before = b.hp
        system_combat(self.state, 0.05)        # queues a damage event
        system_damage_death(self.state, 0.05)  # applies it
        self.assertLess(b.hp, before)

    def test_no_attack_out_of_range(self):
        a = self.state.add_hero(1, "A", Team.TEAM1, hero_id="brawler")
        b = self.state.add_hero(2, "B", Team.TEAM2, hero_id="brawler")
        a.x, a.y = 0, 0
        b.x, b.y = 5000, 0
        self.assertIsNone(find_attack_target(self.state, a))

    def test_no_friendly_fire(self):
        a = self.state.add_hero(1, "A", Team.TEAM1, hero_id="brawler")
        b = self.state.add_hero(2, "B", Team.TEAM1, hero_id="brawler")
        a.x, a.y = 100, 100
        b.x, b.y = 150, 100
        self.assertIsNone(find_attack_target(self.state, a))


class TestDeathAndRespawn(unittest.TestCase):
    def setUp(self):
        self.state = GameState()

    def test_kill_scores_and_starts_respawn(self):
        killer = self.state.add_hero(1, "K", Team.TEAM1, hero_id="brawler")
        victim = self.state.add_hero(2, "V", Team.TEAM2, hero_id="brawler")
        victim.hp = 1
        self.state.damage_events.append(
            {"src": killer.entity_id, "tgt": victim.entity_id, "amt": 50})
        system_damage_death(self.state, 0.05)
        self.assertFalse(victim.alive)
        self.assertEqual(self.state.team_kills[Team.TEAM1], 1)
        self.assertGreater(victim.respawn_timer, 0)
        self.assertGreater(killer.gold, 0)

    def test_respawn_revives_at_base(self):
        hero = self.state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        hero.alive = False
        hero.hp = 0
        hero.respawn_timer = 0.01
        hero.x, hero.y = 3000, 3000
        system_respawn(self.state, 0.05)
        self.assertTrue(hero.alive)
        self.assertEqual(hero.hp, hero.max_hp)
        self.assertNotEqual((hero.x, hero.y), (3000, 3000))


class TestWinConditions(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.state.start_match(kill_target=3)

    def test_win_by_kills(self):
        self.state.team_kills[Team.TEAM1] = 3
        system_win_check(self.state, 0.05)
        self.assertEqual(self.state.winner, Team.TEAM1)
        self.assertEqual(self.state.phase, GamePhase.FINISHED)

    def test_win_by_core_destroyed(self):
        core = self.state.core_of(Team.TEAM2)
        self.assertIsNotNone(core)
        core.alive = False
        system_win_check(self.state, 0.05)
        self.assertEqual(self.state.winner, Team.TEAM1)


class TestStructures(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.state.start_match(kill_target=10)

    def test_inner_invulnerable_until_outer_dead(self):
        structs = [e for e in self.state.entities.values()
                   if isinstance(e, Structure) and e.team == Team.TEAM1]
        outer = next(s for s in structs if s.lane_order == 0)
        inner = next(s for s in structs if s.lane_order == 1)
        self.assertFalse(self.state.is_structure_vulnerable(inner))
        outer.alive = False
        self.assertTrue(self.state.is_structure_vulnerable(inner))

    def test_invulnerable_structure_takes_no_damage(self):
        inner = next(e for e in self.state.entities.values()
                     if isinstance(e, Structure) and e.team == Team.TEAM1
                     and e.lane_order == 1)
        before = inner.hp
        self.state.damage_events.append(
            {"src": None, "tgt": inner.entity_id, "amt": 500})
        system_damage_death(self.state, 0.05)
        self.assertEqual(inner.hp, before)


class TestCreepsAndEconomy(unittest.TestCase):
    def test_wave_spawns_minions(self):
        state = GameState()
        state.start_match(kill_target=10)
        before = sum(isinstance(e, Minion) for e in state.entities.values())
        step(state, 0.05)  # first tick triggers a wave (creep_timer starts at 0)
        after = sum(isinstance(e, Minion) for e in state.entities.values())
        self.assertGreater(after, before)

    def test_minion_killed_by_hero_grants_gold(self):
        state = GameState()
        hero = state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        minion = Minion(team=Team.TEAM2, x=100, y=100)
        minion.hp = 1
        state.entities[minion.entity_id] = minion
        state.damage_events.append(
            {"src": hero.entity_id, "tgt": minion.entity_id, "amt": 10})
        system_damage_death(state, 0.05)
        self.assertGreater(hero.gold, 0)
        self.assertNotIn(minion.entity_id, state.entities)  # cleaned up


if __name__ == "__main__":
    unittest.main()
