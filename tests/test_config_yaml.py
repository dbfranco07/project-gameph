"""Phase 0: the YAML config loader reproduces the expected constants and the
map mirroring is symmetric."""
import unittest

import shared.config as c
from shared.geometry import (
    mirror_point,
    mirror_rect,
    segment_intersects_rect,
    circle_rect_overlap,
)


class TestConfigLoad(unittest.TestCase):
    def test_scalars_loaded(self):
        self.assertEqual(c.MAP_WIDTH, 6000)
        self.assertEqual(c.SERVER_TICK_RATE, 20)
        self.assertAlmostEqual(c.TICK_DURATION, 0.05)
        self.assertEqual(c.MINION_HP, 130)
        self.assertEqual(c.TOWER_HP, 1600)
        self.assertEqual(c.CORE_HP, 3200)
        self.assertEqual(c.DEFENSE_K, 100)
        self.assertEqual(c.HERO_VISION_RADIUS, c.VISION_RADIUS)

    def test_colors_are_tuples(self):
        self.assertEqual(c.COLOR_BG, (40, 60, 30))
        self.assertIsInstance(c.COLOR_TEAM1, tuple)

    def test_map_constants(self):
        self.assertEqual(c.T1_CORE, (800, 5200))
        self.assertEqual(c.T2_CORE, (5200, 800))
        self.assertEqual(c.SPAWN_POSITIONS, {1: (800, 5200), 2: (5200, 800)})
        self.assertEqual(c.LANES, ("top", "mid", "bot"))
        self.assertEqual(c.LANE_PATHS["top"], [(800, 5200), (520, 520), (5200, 800)])
        # Lane waypoints must be tuples (minion pathing compares them by ==).
        self.assertTrue(all(isinstance(p, tuple) for p in c.LANE_PATHS["mid"]))

    def test_tower_mirror(self):
        self.assertEqual(c.LANE_TOWERS[1],
                         [(2, 0.18, "base"), (1, 0.30, "inner"), (0, 0.42, "outer")])
        self.assertEqual(c.LANE_TOWERS[2],
                         [(0, 0.58, "outer"), (1, 0.70, "inner"), (2, 0.82, "base")])

    def test_jungle_camps_mirrored(self):
        self.assertEqual(
            set(c.JUNGLE_CAMPS),
            {(2100, 1800, 3), (1700, 3100, 3), (3900, 4200, 3), (4300, 2900, 3)})

    def test_new_features_present(self):
        self.assertTrue(c.WALLS and all(len(r) == 4 for r in c.WALLS))
        self.assertTrue(c.TREES and all(len(r) == 4 for r in c.TREES))
        self.assertTrue(c.RUNES)
        self.assertIn("mid", c.MEET_POINTS)
        self.assertGreater(c.SPAWN_ZONE_RADIUS, 0)


class TestMirrorHelpers(unittest.TestCase):
    W = H = 6000

    def test_mirror_point(self):
        self.assertEqual(mirror_point((800, 5200), self.W, self.H), (5200, 800))
        # mirroring twice is identity
        p = (2100, 1800)
        self.assertEqual(mirror_point(mirror_point(p, self.W, self.H),
                                      self.W, self.H), p)

    def test_mirror_rect_preserves_size(self):
        r = (1500, 4400, 60, 600)
        m = mirror_rect(r, self.W, self.H)
        self.assertEqual((m[2], m[3]), (60, 600))
        # mirroring twice is identity
        self.assertEqual(mirror_rect(m, self.W, self.H), r)


class TestIntersection(unittest.TestCase):
    def test_segment_crosses_rect(self):
        rect = (100, 100, 100, 100)
        self.assertTrue(segment_intersects_rect(0, 150, 300, 150, rect))
        self.assertFalse(segment_intersects_rect(0, 0, 50, 0, rect))
        # segment starting inside counts as crossing
        self.assertTrue(segment_intersects_rect(150, 150, 400, 400, rect))

    def test_circle_rect_overlap(self):
        rect = (100, 100, 100, 100)
        self.assertTrue(circle_rect_overlap(150, 150, 10, rect))   # inside
        self.assertTrue(circle_rect_overlap(95, 150, 10, rect))    # touching edge
        self.assertFalse(circle_rect_overlap(0, 0, 10, rect))      # far


if __name__ == "__main__":
    unittest.main()
