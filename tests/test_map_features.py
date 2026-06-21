"""Phase 3: walls/trees (collision + vision), runes, spawn zones, meet points."""
import math
import unittest

from shared.game_types import Team
from server.entity import Hero, Wall, Tree, RuneCreature, MeleeMinion
from server.game_state import GameState
from server.systems import (
    system_collision, system_movement, system_damage_death, system_runes,
    system_spawn_zone, apply_rune_buff, _kill, _advance_minion,
)


class TestObstacles(unittest.TestCase):
    def test_walls_spawn_on_match_start(self):
        state = GameState()
        state.start_match(kill_target=10)
        walls = [e for e in state.entities.values() if isinstance(e, Wall)]
        trees = [e for e in state.entities.values() if isinstance(e, Tree)]
        self.assertTrue(walls)
        self.assertTrue(trees)

    def test_wall_blocks_walking(self):
        from shared.geometry import circle_capsule_overlap
        state = GameState()
        # Vertical capsule wall centred at (200, 250).
        wall = Wall(x1=200, y1=150, x2=200, y2=350, thickness=100)
        hero = Hero(team=Team.TEAM1, x=200, y=250, radius=20)  # on the centerline
        state.entities[wall.entity_id] = wall
        state.entities[hero.entity_id] = hero
        self.assertTrue(circle_capsule_overlap(hero.x, hero.y, hero.radius,
                                               *wall.capsule()))
        system_collision(state, 0.05)
        # Pushed out: the hero's circle no longer overlaps the wall capsule.
        self.assertFalse(circle_capsule_overlap(hero.x, hero.y, hero.radius,
                                                *wall.capsule()))

    def test_tree_destructible_then_walkable(self):
        state = GameState()
        tree = Tree(x1=500, y1=460, x2=500, y2=540, thickness=80, hp=30, max_hp=30)
        state.entities[tree.entity_id] = tree
        self.assertEqual(len(state.obstacle_capsules()), 1)
        state.damage_events.append(
            {"src": None, "tgt": tree.entity_id, "amt": 50, "dtype": "true"})
        system_damage_death(state, 0.05)
        self.assertFalse(tree.alive)
        self.assertEqual(state.obstacle_capsules(), [])  # no longer blocks

    def test_hero_blocked_by_unit_without_pushing_it(self):
        """A hero walking into another unit stops at it but never pushes it."""
        state = GameState()
        blocker = Hero(team=Team.TEAM1, x=300, y=300, radius=20)
        mover = Hero(team=Team.TEAM1, x=240, y=300, radius=20)
        mover.target_x, mover.target_y = 400, 300  # walk right, into the blocker
        state.entities[blocker.entity_id] = blocker
        state.entities[mover.entity_id] = mover
        bx, by = blocker.x, blocker.y
        for _ in range(40):
            system_movement(state, 0.05)
            system_collision(state, 0.05)
        # The blocker never moved; the mover stopped short (no overlap).
        self.assertEqual((blocker.x, blocker.y), (bx, by))
        gap = math.hypot(mover.x - blocker.x, mover.y - blocker.y)
        self.assertGreaterEqual(gap, mover.radius + blocker.radius - 1.0)


class TestRiver(unittest.TestCase):
    def test_in_river(self):
        state = GameState()
        # The configured river runs the anti-diagonal through the map centre.
        self.assertTrue(state.in_river(3000, 3000))
        self.assertFalse(state.in_river(800, 5200))  # a base corner


class TestVisionBlocking(unittest.TestCase):
    def test_wall_blocks_line_of_sight(self):
        state = GameState()
        seer = Hero(team=Team.TEAM1, x=0, y=300)
        enemy = Hero(team=Team.TEAM2, x=600, y=300)
        wall = Wall(x1=300, y1=200, x2=300, y2=400, thickness=40)  # between them
        for e in (seer, enemy, wall):
            state.entities[e.entity_id] = e
        self.assertNotIn(enemy.entity_id,
                         state.visible_entity_ids_for(Team.TEAM1))
        # Remove the wall -> now visible (close enough, clear line).
        wall.alive = False
        self.assertIn(enemy.entity_id, state.visible_entity_ids_for(Team.TEAM1))


class TestRunes(unittest.TestCase):
    def test_rune_spawns_and_respawns(self):
        state = GameState()
        state.start_match(kill_target=10)
        state.match_clock = 0.0  # skip the pre-game countdown
        system_runes(state, 0.05)
        runes = [e for e in state.entities.values() if isinstance(e, RuneCreature)]
        self.assertTrue(runes)

    def test_rune_death_grants_buff(self):
        state = GameState()
        killer = Hero(team=Team.TEAM1)
        rune = RuneCreature(x=0, y=0, rune_buff="double_damage")
        state.entities[killer.entity_id] = killer
        state.entities[rune.entity_id] = rune
        _kill(state, rune, killer.entity_id)
        self.assertAlmostEqual(killer.damage_mult(), 2.0)

    def test_regen_buff_cancels_on_hit(self):
        state = GameState()
        hero = Hero(team=Team.TEAM1, hp=100, max_hp=600, hp_regen=3.0)
        state.entities[hero.entity_id] = hero
        apply_rune_buff(hero, "regen_10x")
        self.assertTrue(any(b.get("cancel_on_hit") for b in hero.buffs))
        state.damage_events.append(
            {"src": None, "tgt": hero.entity_id, "amt": 10, "dtype": "true"})
        system_damage_death(state, 0.05)
        self.assertFalse(any(b.get("cancel_on_hit") for b in hero.buffs))


class TestSpawnZone(unittest.TestCase):
    def test_ally_heals_enemy_burns(self):
        from shared.config import SPAWN_POSITIONS
        state = GameState()
        cx, cy = SPAWN_POSITIONS[1]
        ally = Hero(team=Team.TEAM1, x=cx, y=cy, hp=100, max_hp=600)
        enemy = Hero(team=Team.TEAM2, x=cx, y=cy, hp=600, max_hp=600)
        state.entities[ally.entity_id] = ally
        state.entities[enemy.entity_id] = enemy
        system_spawn_zone(state, 0.05)        # ally healed directly
        system_damage_death(state, 0.05)      # enemy burn applied via events
        self.assertGreater(ally.hp, 100)
        self.assertLess(enemy.hp, 600)


class TestMeetPoints(unittest.TestCase):
    def test_wave1_minion_speeds_up_then_reverts(self):
        from shared.config import MEET_POINTS
        state = GameState()
        m = MeleeMinion(team=Team.TEAM1, x=0, y=0, dest_x=1000, dest_y=0)
        m.meet_x, m.meet_y = 1000, 0
        m.meet_speed = m.move_speed * 1.4
        state.entities[m.entity_id] = m
        x0 = m.x
        _advance_minion(state, m, 0.1)
        fast_step = m.x - x0
        # Faster than default while far from the meet point.
        self.assertGreater(fast_step, m.move_speed * 0.1 * 1.2)
        # Jump next to the meet point: speed reverts.
        m.x, m.y = 950, 0
        _advance_minion(state, m, 0.1)
        self.assertEqual(m.meet_speed, 0.0)


if __name__ == "__main__":
    unittest.main()
