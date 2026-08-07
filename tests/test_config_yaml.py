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
    """The loader's job is derivation and mirroring, not tuning.

    These assert *invariants* rather than the numbers in `config/*.yaml`, so
    rebalancing the game does not break the suite. Anything pinned to a literal
    below is a structural contract other code depends on, not a tuning knob.
    """

    def test_scalars_loaded(self):
        # Every scalar the flat-injection path is meant to expose exists and is
        # sanely typed/signed (a missing YAML key would surface as AttributeError).
        for name in ("MAP_WIDTH", "MAP_HEIGHT", "SERVER_TICK_RATE", "MINION_HP",
                     "TOWER_HP", "CORE_HP", "DEFENSE_K", "VISION_RADIUS"):
            with self.subTest(const=name):
                self.assertIsInstance(getattr(c, name), (int, float))
                self.assertGreater(getattr(c, name), 0)
        # Derived, not authored: tick duration is the inverse of the tick rate.
        self.assertAlmostEqual(c.TICK_DURATION, 1.0 / c.SERVER_TICK_RATE)
        # Aliased for readability at call sites; must stay in lockstep.
        self.assertEqual(c.HERO_VISION_RADIUS, c.VISION_RADIUS)
        # Structural ordering the combat/objective code relies on.
        self.assertGreater(c.CORE_HP, c.TOWER_HP)
        self.assertGreater(c.TOWER_HP, c.MINION_HP)

    def test_colors_are_tuples(self):
        # Colors are popped out of the `game` block into COLOR_* RGB triples.
        for name in ("COLOR_BG", "COLOR_TEAM1", "COLOR_TEAM2"):
            with self.subTest(const=name):
                col = getattr(c, name)
                self.assertIsInstance(col, tuple)
                self.assertEqual(len(col), 3)
                self.assertTrue(all(0 <= ch <= 255 for ch in col))

    def test_map_constants(self):
        w, h = c.MAP_WIDTH, c.MAP_HEIGHT
        # Team 1 is authored; team 2 is derived by mirroring through the center.
        self.assertEqual(c.SPAWN_POSITIONS[1], c.T1_FOUNTAIN)
        self.assertEqual(c.SPAWN_POSITIONS[2], mirror_point(c.T1_FOUNTAIN, w, h))
        # The core is a distinct inland point (not the fountain), mirrored cleanly.
        self.assertNotEqual(c.T1_CORE, c.T1_FOUNTAIN)
        self.assertEqual(c.T2_CORE, mirror_point(c.T1_CORE, w, h))
        self.assertEqual(c.LANES, ("top", "mid", "bot"))
        # Every lane is a non-trivial polyline of tuples (minion pathing compares
        # waypoints by ==, so lists would silently never match).
        for lane in c.LANES:
            with self.subTest(lane=lane):
                path = c.LANE_PATHS[lane]
                self.assertGreaterEqual(len(path), 2)
                self.assertTrue(all(isinstance(p, tuple) for p in path))
                self.assertTrue(all(0 <= x <= w and 0 <= y <= h for x, y in path))

    def test_tower_mirror(self):
        # Towers are authored once for team 1 as (index, t, label) along the lane
        # and mirrored to team 2 as t -> 1 - t in reverse order. That derivation
        # is the loader's job; the specific t values are tuning.
        t1, t2 = c.LANE_TOWERS[1], c.LANE_TOWERS[2]
        self.assertEqual(len(t1), len(t2))
        self.assertEqual(t2, [(idx, round(1.0 - t, 10), label)
                              for (idx, t, label) in reversed(t1)])
        # Team 1 runs outward from its own base, so t is strictly increasing.
        self.assertEqual([t for _, t, _ in t1], sorted(t for _, t, _ in t1))
        self.assertTrue(all(0.0 <= t <= 1.0 for _, t, _ in t1))
        # Labels are the identifiers the tower-vulnerability rules key off.
        self.assertEqual({label for _, _, label in t1},
                         {"base", "inner", "outer"})

    def test_jungle_camps_mirrored(self):
        # Camps are authored for one side then center-mirrored: every camp has
        # its mirror present (counts preserved), and the total is twice authored.
        camps = set(c.JUNGLE_CAMPS)
        self.assertTrue(camps)
        self.assertEqual(len(c.JUNGLE_CAMPS), 2 * len(c._t1_camps))
        for (x, y, n) in c.JUNGLE_CAMPS:
            self.assertIn((6000 - x, 6000 - y, n), camps)

    def test_new_features_present(self):
        cap_keys = {"p1", "p2", "thickness"}
        self.assertTrue(c.WALLS and all(cap_keys <= set(w) for w in c.WALLS))
        self.assertTrue(c.TREES and all(cap_keys <= set(t) for t in c.TREES))
        self.assertTrue(c.RUNES and all("zone" in r for r in c.RUNES))
        self.assertIn("mid", c.MEET_POINTS)
        self.assertGreater(c.SPAWN_ZONE_RADIUS, 0)
        self.assertIsNotNone(c.RIVER)


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
