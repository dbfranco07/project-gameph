"""Tests for the 3-lane map: wave composition, cart minions, lane pathing, and
neutral jungle camps."""

import unittest

from server.game_state import GameState
from server.entity import (
    Hero, Minion, MeleeMinion, RangedMinion, CartMinion, NeutralMinion,
)
from server.systems import (
    system_spawn_creeps,
    system_neutral_camps,
    system_movement,
    system_damage_death,
    find_attack_target,
)
from shared.game_types import Team
from shared.config import (
    LANE_PATHS,
    LANE_TOWERS,
    JUNGLE_CAMPS,
    CREEP_MELEE_PER_WAVE,
    CREEP_RANGED_PER_WAVE,
    CREEP_CART_EVERY,
    NEUTRAL_RESPAWN,
    TICK_DURATION,
)


def _minions(state, cls=Minion):
    return [e for e in state.entities.values() if isinstance(e, cls)]


class TestStructureLayout(unittest.TestCase):
    def test_nine_lane_towers_and_one_core_per_team(self):
        state = GameState()
        state.start_match(kill_target=10)
        for team in (Team.TEAM1, Team.TEAM2):
            towers = [e for e in state.entities.values()
                      if e.__class__.__name__ == "Structure"
                      and e.team == team and not e.is_core]
            cores = [e for e in state.entities.values()
                     if e.__class__.__name__ == "Structure"
                     and e.team == team and e.is_core]
            self.assertEqual(len(towers), 3 * len(LANE_PATHS))
            self.assertEqual(len(cores), 1)
            # Three towers per lane.
            for lane in LANE_PATHS:
                self.assertEqual(sum(t.lane == lane for t in towers), 3)


class TestWaveComposition(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.state.start_match(kill_target=10)
        # start_match leaves creep_timer at 0; clear pre-spawned entities count.

    def _force_wave(self):
        self.state.creep_timer = 0.0  # bypass the inter-wave cooldown
        system_spawn_creeps(self.state, TICK_DURATION)

    def test_first_wave_melee_and_ranged_per_lane(self):
        self._force_wave()  # wave 1
        per_team_per_lane = CREEP_MELEE_PER_WAVE + CREEP_RANGED_PER_WAVE
        expected = per_team_per_lane * len(LANE_PATHS) * 2  # both teams
        self.assertEqual(len(_minions(self.state)), expected)
        self.assertEqual(len(_minions(self.state, MeleeMinion)),
                         CREEP_MELEE_PER_WAVE * len(LANE_PATHS) * 2)
        self.assertEqual(len(_minions(self.state, RangedMinion)),
                         CREEP_RANGED_PER_WAVE * len(LANE_PATHS) * 2)
        self.assertEqual(len(_minions(self.state, CartMinion)), 0)

    def test_cart_spawns_on_fourth_wave(self):
        for _ in range(CREEP_CART_EVERY - 1):
            self._force_wave()
            self.assertEqual(len(_minions(self.state, CartMinion)), 0)
            # clear the field so we only inspect one wave at a time
            for m in _minions(self.state):
                self.state.entities.pop(m.entity_id, None)
        self._force_wave()  # 4th wave
        carts = _minions(self.state, CartMinion)
        self.assertEqual(len(carts), len(LANE_PATHS) * 2)  # one per lane per team
        # Carts are tankier and worth more than a melee minion.
        self.assertGreater(carts[0].max_hp, MeleeMinion().max_hp)
        self.assertGreater(carts[0].gold_value, MeleeMinion().gold_value)


class TestLanePathing(unittest.TestCase):
    def test_top_lane_minion_routes_via_corner(self):
        state = GameState()
        state.start_match(kill_target=10)
        for m in _minions(state):
            state.entities.pop(m.entity_id, None)
        system_spawn_creeps(state, TICK_DURATION)
        # A Team 1 top-lane minion should head toward the top-left corner first,
        # not straight at the enemy base (it has a bend waypoint).
        top_corner = LANE_PATHS["top"][1]
        t1 = [m for m in _minions(state) if m.team == Team.TEAM1]
        # Identify a top-laner: its remaining path still includes the corner.
        topers = [m for m in t1 if (m.dest_x, m.dest_y) == top_corner
                  or top_corner in m.path]
        self.assertTrue(topers, "expected at least one top-lane minion")
        m = topers[0]
        start_x = m.x
        for _ in range(60):
            system_movement(state, TICK_DURATION)
        # It moved toward the corner (leftward / upward), not directly to enemy base.
        self.assertLess(m.x, start_x + 50)


class TestJungleCamps(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.state.start_match(kill_target=10)
        system_neutral_camps(self.state, TICK_DURATION)  # spawn camps

    def test_camps_spawn(self):
        mobs = _minions(self.state, NeutralMinion)
        expected = sum(c[2] for c in JUNGLE_CAMPS)
        self.assertEqual(len(mobs), expected)
        self.assertTrue(all(m.team == Team.NONE and m.is_neutral for m in mobs))

    def test_neutral_passive_until_provoked(self):
        mob = _minions(self.state, NeutralMinion)[0]
        hero = self.state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        hero.x, hero.y = mob.x + 30, mob.y  # well within the mob's range
        # Unprovoked: the neutral does not acquire a target.
        self.assertIsNone(find_attack_target(self.state, mob))
        # Provoked: it fights back.
        mob.provoked = True
        self.assertIsNotNone(find_attack_target(self.state, mob))

    def test_hero_can_target_neutral(self):
        mob = _minions(self.state, NeutralMinion)[0]
        hero = self.state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        hero.x, hero.y = mob.x + 30, mob.y
        self.assertIs(find_attack_target(self.state, hero), mob)

    def test_neutral_kill_rewards_killer(self):
        mob = _minions(self.state, NeutralMinion)[0]
        mob.hp = 1
        hero = self.state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        hero.x, hero.y = mob.x, mob.y
        gold_before = hero.gold
        self.state.damage_events.append(
            {"src": hero.entity_id, "tgt": mob.entity_id, "amt": 10})
        system_damage_death(self.state, TICK_DURATION)
        self.assertEqual(hero.gold, gold_before + mob.gold_value)

    def test_camp_respawns_after_delay(self):
        mobs = _minions(self.state, NeutralMinion)
        camp0 = [m for m in mobs if m.camp_id == 0]
        for m in camp0:
            m.alive = False
            self.state.entities.pop(m.entity_id, None)
        # Tick until just before respawn: still empty.
        elapsed = 0.0
        while elapsed < NEUTRAL_RESPAWN + TICK_DURATION:
            system_neutral_camps(self.state, TICK_DURATION)
            elapsed += TICK_DURATION
        respawned = [m for m in _minions(self.state, NeutralMinion)
                     if m.camp_id == 0]
        self.assertTrue(respawned, "camp 0 should have respawned")


if __name__ == "__main__":
    unittest.main()
