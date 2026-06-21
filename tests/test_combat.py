"""Tests for combat, death/respawn, scoring, and win conditions."""

import unittest

from server.game_state import GameState
from server.entity import Hero, Minion, Structure
from server.systems import (
    system_combat,
    system_movement,
    system_damage_death,
    system_respawn,
    system_win_check,
    system_collision,
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

    def _tower(self, team, lane, lane_order):
        return next(e for e in self.state.entities.values()
                    if isinstance(e, Structure) and e.team == team
                    and e.lane == lane and e.lane_order == lane_order)

    def test_inner_invulnerable_until_outer_dead(self):
        outer = self._tower(Team.TEAM1, "mid", 0)
        inner = self._tower(Team.TEAM1, "mid", 1)
        self.assertFalse(self.state.is_structure_vulnerable(inner))
        outer.alive = False
        self.assertTrue(self.state.is_structure_vulnerable(inner))

    def test_vulnerability_is_per_lane(self):
        # A different lane's outer dying must not expose this lane's inner.
        self._tower(Team.TEAM1, "top", 0).alive = False
        mid_inner = self._tower(Team.TEAM1, "mid", 1)
        self.assertFalse(self.state.is_structure_vulnerable(mid_inner))

    def test_core_exposed_after_one_lane_cleared(self):
        core = self.state.core_of(Team.TEAM1)
        self.assertFalse(self.state.is_structure_vulnerable(core))
        for lo in (0, 1, 2):
            self._tower(Team.TEAM1, "bot", lo).alive = False
        self.assertTrue(self.state.lane_cleared(Team.TEAM1, "bot"))
        self.assertTrue(self.state.is_structure_vulnerable(core))

    def test_invulnerable_structure_takes_no_damage(self):
        inner = self._tower(Team.TEAM1, "mid", 1)
        before = inner.hp
        self.state.damage_events.append(
            {"src": None, "tgt": inner.entity_id, "amt": 500})
        system_damage_death(self.state, 0.05)
        self.assertEqual(inner.hp, before)


class TestCreepsAndEconomy(unittest.TestCase):
    def test_wave_spawns_minions(self):
        state = GameState()
        state.start_match(kill_target=10)
        state.match_clock = 0.0  # skip the pre-game countdown
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

    def test_kill_emits_gold_and_xp_reward_events(self):
        state = GameState()
        hero = state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        hero.x, hero.y = 100, 100
        minion = Minion(team=Team.TEAM2, x=100, y=100)
        minion.hp = 1
        state.entities[minion.entity_id] = minion
        state.damage_events.append(
            {"src": hero.entity_id, "tgt": minion.entity_id, "amt": 10})
        system_damage_death(state, 0.05)
        kinds = {ev["k"] for ev in state.combat_events}
        self.assertIn("gold", kinds)
        self.assertIn("xp", kinds)


class TestMinionPathing(unittest.TestCase):
    def test_minion_routes_around_blocking_tower(self):
        from shared.config import TICK_DURATION, TOWER_RADIUS
        state = GameState()
        y = 3000
        m = Minion(team=Team.TEAM1, x=2000, y=y, dest_x=5500, dest_y=y)
        state.entities[m.entity_id] = m
        tower = Structure(team=Team.TEAM1, x=2300, y=y, radius=TOWER_RADIUS)
        state.entities[tower.entity_id] = tower
        for _ in range(200):  # 10s
            system_movement(state, TICK_DURATION)
            system_collision(state, TICK_DURATION)
        # It got past the tower and kept advancing down the lane.
        self.assertGreater(m.x, tower.x + TOWER_RADIUS + m.radius)
        self.assertGreater(m.x, 3000)


class TestCollision(unittest.TestCase):
    def test_overlapping_idle_units_not_pushed_apart(self):
        # Units block each other during movement, but system_collision never
        # elastic-shoves overlapping units apart (we don't push other entities).
        state = GameState()
        a = state.add_hero(1, "A", Team.TEAM1, hero_id="brawler")
        b = state.add_hero(2, "B", Team.TEAM1, hero_id="brawler")
        a.x, a.y = 1000, 1000
        b.x, b.y = 1000, 1000  # exactly overlapping, both idle
        system_collision(state, 0.05)
        # Neither idle unit was moved.
        self.assertEqual((a.x, a.y), (1000, 1000))
        self.assertEqual((b.x, b.y), (1000, 1000))

    def test_non_overlapping_units_unchanged(self):
        state = GameState()
        a = state.add_hero(1, "A", Team.TEAM1, hero_id="brawler")
        b = state.add_hero(2, "B", Team.TEAM2, hero_id="brawler")
        a.x, a.y = 1000, 1000
        b.x, b.y = 1500, 1000  # far apart
        system_collision(state, 0.05)
        self.assertEqual((a.x, a.y), (1000, 1000))
        self.assertEqual((b.x, b.y), (1500, 1000))

    def test_last_hit_gold_split_and_full_xp(self):
        from shared.config import (MINION_GOLD, MINION_ASSIST_GOLD_FRACTION,
                                   GOLD_SHARE_RADIUS)
        state = GameState()
        killer = state.add_hero(1, "K", Team.TEAM1, hero_id="brawler")
        ally = state.add_hero(2, "A", Team.TEAM1, hero_id="ranger")
        far = state.add_hero(3, "F", Team.TEAM1, hero_id="mender")
        minion = Minion(team=Team.TEAM2, x=100, y=100)
        minion.hp = 1
        state.entities[minion.entity_id] = minion
        killer.x, killer.y = 100, 100              # last hit, in range
        ally.x, ally.y = 100, 100 + GOLD_SHARE_RADIUS - 50   # near -> share + xp
        far.x, far.y = 100, 100 + GOLD_SHARE_RADIUS + 5000   # far -> nothing
        g0_k, g0_a, g0_f = killer.gold, ally.gold, far.gold
        state.damage_events.append(
            {"src": killer.entity_id, "tgt": minion.entity_id, "amt": 10})
        system_damage_death(state, 0.05)
        self.assertEqual(killer.gold - g0_k, MINION_GOLD)               # full gold
        self.assertEqual(ally.gold - g0_a,
                         int(MINION_GOLD * MINION_ASSIST_GOLD_FRACTION))  # share
        self.assertEqual(far.gold - g0_f, 0)                            # nothing
        self.assertGreater(killer.xp + killer.level, 1)                # killer got xp
        self.assertGreater(ally.xp, 0)                                 # nearby ally full xp
        self.assertEqual(far.xp, 0)                                    # far ally none


class TestRegen(unittest.TestCase):
    def test_hp_and_mana_regen_clamp_and_pause_when_dead(self):
        from server.systems import system_status
        state = GameState()
        hero = state.add_hero(1, "R", Team.TEAM1, hero_id="ranger")
        hero.hp = hero.max_hp - 50
        hero.mana = hero.max_mana - 50
        for _ in range(200):  # ~10s of regen
            system_status(state, 0.05)
        self.assertGreater(hero.hp, hero.max_hp - 50)
        self.assertLessEqual(hero.hp, hero.max_hp)        # never exceeds max
        self.assertLessEqual(hero.mana, hero.max_mana)
        # Dead heroes do not regen.
        hero.alive = False
        hero.hp = 10
        for _ in range(40):
            system_status(state, 0.05)
        self.assertEqual(hero.hp, 10)


if __name__ == "__main__":
    unittest.main()
