"""Tests for melee/ranged attacks, homing projectiles, focus targeting, and stop."""

import unittest

from server.game_state import GameState
from server.server_main import GameServer
from server.entity import Projectile, Minion, Tree
from server.systems import (
    find_attack_target,
    system_combat,
    system_projectiles,
    system_damage_death,
    system_movement,
)
from shared.game_types import Team


def _projectiles(state):
    return [e for e in state.entities.values() if isinstance(e, Projectile)]


class TestMeleeVsRanged(unittest.TestCase):
    def test_melee_deals_instant_damage(self):
        state = GameState()
        a = state.add_hero(1, "M", Team.TEAM1, hero_id="brawler")  # melee
        b = state.add_hero(2, "T", Team.TEAM2, hero_id="brawler")
        a.x, a.y = 100, 100
        b.x, b.y = 200, 100
        before = b.hp
        system_combat(state, 0.05)
        self.assertEqual(len(_projectiles(state)), 0)  # no projectile for melee
        system_damage_death(state, 0.05)
        self.assertLess(b.hp, before)

    def test_ranged_spawns_basic_projectile(self):
        state = GameState()
        a = state.add_hero(1, "R", Team.TEAM1, hero_id="ranger")  # ranged
        b = state.add_hero(2, "T", Team.TEAM2, hero_id="brawler")
        a.x, a.y = 1000, 1000
        b.x, b.y = 1300, 1000  # within ranger range (520)
        before = b.hp
        system_combat(state, 0.05)
        projs = _projectiles(state)
        self.assertEqual(len(projs), 1)
        self.assertTrue(projs[0].is_basic)
        self.assertEqual(projs[0].team, Team.TEAM1)
        self.assertEqual(b.hp, before)  # damage not applied until the shot lands

    def test_homing_projectile_lands_and_damages(self):
        state = GameState()
        a = state.add_hero(1, "R", Team.TEAM1, hero_id="ranger")
        b = state.add_hero(2, "T", Team.TEAM2, hero_id="brawler")
        a.x, a.y = 1000, 1000
        b.x, b.y = 1300, 1000
        before = b.hp
        system_combat(state, 0.05)
        for _ in range(40):
            system_projectiles(state, 0.05)
            system_damage_death(state, 0.05)
        self.assertLess(b.hp, before)
        self.assertEqual(len(_projectiles(state)), 0)  # despawned after hitting

    def test_homing_projectile_fizzles_if_target_dies(self):
        state = GameState()
        a = state.add_hero(1, "R", Team.TEAM1, hero_id="ranger")
        minion = Minion(team=Team.TEAM2, x=1300, y=1000)
        a.x, a.y = 1000, 1000
        state.entities[minion.entity_id] = minion
        system_combat(state, 0.05)
        self.assertEqual(len(_projectiles(state)), 1)
        # Target dies before the projectile arrives.
        minion.alive = False
        system_projectiles(state, 0.05)
        self.assertEqual(len(_projectiles(state)), 0)


class TestFocusAndStop(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        self.enemy = self.state.add_hero(2, "E", Team.TEAM2, hero_id="brawler")
        self.hero.x, self.hero.y = 1000, 1000
        # Out of melee range, but inside hero vision (a fogged target drops the
        # focus order, so the chase test needs a visible enemy).
        self.enemy.x, self.enemy.y = 1600, 1000

    def test_focus_target_chases_enemy(self):
        self.hero.forced_target_id = self.enemy.entity_id
        x0 = self.hero.x
        for _ in range(20):
            system_movement(self.state, 0.05)
        self.assertGreater(self.hero.x, x0)  # moved toward the enemy

    def test_focus_clears_when_target_dies(self):
        self.hero.forced_target_id = self.enemy.entity_id
        self.enemy.alive = False
        system_movement(self.state, 0.05)
        self.assertIsNone(self.hero.forced_target_id)

    def test_focus_holds_when_in_range(self):
        self.enemy.x = self.hero.x + 100  # within melee range
        self.hero.forced_target_id = self.enemy.entity_id
        system_movement(self.state, 0.05)
        # In range -> stop moving so combat can fire.
        self.assertIsNone(self.hero.target_x)


class TestMoveAttackExclusive(unittest.TestCase):
    """Moving and attacking are mutually exclusive for heroes."""

    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        self.enemy = self.state.add_hero(2, "E", Team.TEAM2, hero_id="brawler")
        self.hero.x, self.hero.y = 1000, 1000
        self.enemy.x, self.enemy.y = 1100, 1000  # within brawler melee range

    def _hero_attacked(self) -> bool:
        return any(ev.get("src") == self.hero.entity_id
                   for ev in self.state.damage_events)

    def test_stationary_hero_attacks(self):
        self.hero.target_x = self.hero.target_y = None
        system_combat(self.state, 0.05)
        self.assertTrue(self._hero_attacked())

    def test_moving_hero_does_not_attack(self):
        self.hero.target_x, self.hero.target_y = 2000, 1000  # walking away
        system_combat(self.state, 0.05)
        self.assertFalse(self._hero_attacked())  # holds fire while moving

    def test_attack_move_stops_for_enemy_in_range(self):
        # Attack-moving toward a far point, but an enemy is in range: the hero
        # should halt (clear its move target) so combat can fire.
        self.hero.attack_move = True
        self.hero.attack_move_x, self.hero.attack_move_y = 5000, 1000
        self.hero.target_x, self.hero.target_y = 5000, 1000
        system_movement(self.state, 0.05)
        self.assertIsNone(self.hero.target_x)
        system_combat(self.state, 0.05)
        self.assertTrue(self._hero_attacked())

    def test_attack_move_advances_when_no_enemy(self):
        self.enemy.x = 9000  # nothing in range
        self.hero.attack_move = True
        self.hero.attack_move_x, self.hero.attack_move_y = 5000, 1000
        self.hero.target_x, self.hero.target_y = 5000, 1000
        x0 = self.hero.x
        system_movement(self.state, 0.05)
        self.assertGreater(self.hero.x, x0)  # keeps walking toward the goal


class TestTerrainNotTargetable(unittest.TestCase):
    """Terrain (walls and trees) can never become an attack target.

    An obstacle's `radius` is half its capsule length, so a latched tree read
    as "in range" from hundreds of units away: the hero stopped walking and
    swung at empty ground forever. Against a wall no damage event was produced
    at all, which is the "attacks but targets nobody" symptom.
    """

    def setUp(self):
        self.server = GameServer()
        self.state = self.server.state
        self.hero = self.state.add_hero(1, "H", Team.TEAM1, hero_id="brawler")
        self.hero.x, self.hero.y = 1000, 1000
        # A long tree: midpoint (1800, 1000), radius ~= 440.
        self.tree = Tree(x1=1200, y1=1000, x2=2400, y2=1000, thickness=80)
        self.state.entities[self.tree.entity_id] = self.tree

    def test_forced_terrain_target_is_cleared(self):
        self.hero.forced_target_id = self.tree.entity_id
        system_movement(self.state, 0.05)
        self.assertIsNone(self.hero.forced_target_id)

    def test_combat_ignores_forced_terrain_target(self):
        self.hero.forced_target_id = self.tree.entity_id
        self.hero.target_x = self.hero.target_y = None
        system_combat(self.state, 0.05)
        self.assertEqual(self.state.damage_events, [])

    def test_attack_command_on_tree_becomes_attack_move(self):
        """The server is authoritative: a tree `tid` degrades to attack-move."""
        self.server._handle_attack(
            1, {"tx": 1800.0, "ty": 1000.0, "tid": self.tree.entity_id})
        self.assertIsNone(self.hero.forced_target_id)
        self.assertTrue(self.hero.attack_move)
        self.assertEqual((self.hero.attack_move_x, self.hero.attack_move_y),
                         (1800.0, 1000.0))

    def test_no_auto_attack_on_terrain(self):
        self.state.rebuild_spatial_index()
        self.assertIsNone(find_attack_target(self.state, self.hero))

    def test_homing_projectile_fizzles_on_terrain_target(self):
        ranger = self.state.add_hero(2, "R", Team.TEAM1, hero_id="ranger")
        ranger.x, ranger.y = 1000, 1000
        proj = Projectile(team=Team.TEAM1, x=1000, y=1000, damage=50,
                          owner_id=ranger.entity_id, homing=True,
                          target_id=self.tree.entity_id, speed=1000.0,
                          range_left=2000.0, is_basic=True)
        self.state.entities[proj.entity_id] = proj
        system_projectiles(self.state, 0.05)
        self.assertEqual(_projectiles(self.state), [])
        self.assertEqual(self.state.damage_events, [])

    def test_no_lifesteal_off_terrain(self):
        """Terrain damage is dropped before the pipeline, so nothing procs."""
        self.hero.hp = 100
        self.state.damage_events.append(
            {"src": self.hero.entity_id, "tgt": self.tree.entity_id,
             "amt": 500, "basic": True})
        system_damage_death(self.state, 0.05)
        self.assertEqual(self.hero.hp, 100)
        self.assertTrue(self.tree.alive)


if __name__ == "__main__":
    unittest.main()
