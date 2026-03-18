"""Tests for the client camera module."""

import unittest
from client.camera import Camera
from shared.config import SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT


class TestCamera(unittest.TestCase):
    def setUp(self):
        self.cam = Camera()

    def test_follow_centers_on_position(self):
        self.cam.follow(1000, 1000)
        # Camera top-left should be offset by half screen
        self.assertAlmostEqual(self.cam.x, 1000 - SCREEN_WIDTH / 2)
        self.assertAlmostEqual(self.cam.y, 1000 - SCREEN_HEIGHT / 2)

    def test_follow_clamps_to_top_left(self):
        self.cam.follow(0, 0)
        self.assertEqual(self.cam.x, 0)
        self.assertEqual(self.cam.y, 0)

    def test_follow_clamps_to_bottom_right(self):
        self.cam.follow(MAP_WIDTH, MAP_HEIGHT)
        self.assertEqual(self.cam.x, MAP_WIDTH - SCREEN_WIDTH)
        self.assertEqual(self.cam.y, MAP_HEIGHT - SCREEN_HEIGHT)

    def test_world_to_screen(self):
        self.cam.x = 100
        self.cam.y = 200
        sx, sy = self.cam.world_to_screen(150, 250)
        self.assertEqual(sx, 50)
        self.assertEqual(sy, 50)

    def test_screen_to_world(self):
        self.cam.x = 100
        self.cam.y = 200
        wx, wy = self.cam.screen_to_world(50, 50)
        self.assertAlmostEqual(wx, 150)
        self.assertAlmostEqual(wy, 250)

    def test_roundtrip_conversion(self):
        self.cam.follow(2000, 1500)
        wx, wy = 2000, 1500
        sx, sy = self.cam.world_to_screen(wx, wy)
        wx2, wy2 = self.cam.screen_to_world(sx, sy)
        self.assertAlmostEqual(wx2, wx, places=0)
        self.assertAlmostEqual(wy2, wy, places=0)


if __name__ == "__main__":
    unittest.main()
