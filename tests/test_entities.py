"""Tests for server entity classes."""

import unittest
from server.entity import Entity, Hero, _gen_id
from shared.game_types import EntityType, Team


class TestEntity(unittest.TestCase):
    def test_entity_creation(self):
        e = Entity(team=Team.TEAM1, x=100, y=200)
        self.assertEqual(e.team, Team.TEAM1)
        self.assertEqual(e.x, 100)
        self.assertEqual(e.y, 200)
        self.assertTrue(e.alive)

    def test_entity_snapshot(self):
        e = Entity(team=Team.TEAM2, x=50, y=75, hp=400, max_hp=600)
        snap = e.to_snapshot()
        self.assertEqual(snap["tm"], int(Team.TEAM2))
        self.assertEqual(snap["x"], 50)
        self.assertEqual(snap["y"], 75)
        self.assertEqual(snap["hp"], 400)
        self.assertEqual(snap["mhp"], 600)
        self.assertTrue(snap["a"])

    def test_distance_to(self):
        a = Entity(x=0, y=0)
        b = Entity(x=3, y=4)
        self.assertAlmostEqual(a.distance_to(b), 5.0)


class TestHero(unittest.TestCase):
    def test_hero_creation(self):
        h = Hero(name="Warrior", team=Team.TEAM1, x=300, y=300)
        self.assertEqual(h.entity_type, EntityType.HERO)
        self.assertEqual(h.name, "Warrior")
        self.assertEqual(h.level, 1)
        self.assertEqual(h.gold, 0)

    def test_move_toward_target(self):
        h = Hero(x=0, y=0, move_speed=100)
        h.target_x = 100.0
        h.target_y = 0.0
        h.move_toward_target(0.05)  # 100 * 0.05 = 5 units
        self.assertAlmostEqual(h.x, 5.0, places=1)
        self.assertAlmostEqual(h.y, 0.0, places=1)

    def test_move_stops_at_target(self):
        h = Hero(x=0, y=0, move_speed=1000)
        h.target_x = 1.0
        h.target_y = 0.0
        h.move_toward_target(1.0)  # Would overshoot, should clamp to target
        self.assertAlmostEqual(h.x, 1.0, places=1)
        # Second call: hero is at target, within threshold, target clears
        h.move_toward_target(1.0)
        self.assertIsNone(h.target_x)

    def test_no_movement_without_target(self):
        h = Hero(x=50, y=50)
        h.move_toward_target(0.05)
        self.assertEqual(h.x, 50)
        self.assertEqual(h.y, 50)

    def test_hero_snapshot_includes_stats(self):
        h = Hero(name="Mage", team=Team.TEAM2, level=5, gold=350, mana=150, max_mana=400)
        snap = h.to_snapshot()
        self.assertEqual(snap["name"], "Mage")
        self.assertEqual(snap["lvl"], 5)
        self.assertEqual(snap["gold"], 350)
        self.assertEqual(snap["mana"], 150)
        self.assertEqual(snap["mmana"], 400)

    def test_unique_entity_ids(self):
        h1 = Hero(name="A")
        h2 = Hero(name="B")
        self.assertNotEqual(h1.entity_id, h2.entity_id)


if __name__ == "__main__":
    unittest.main()
