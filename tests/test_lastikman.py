"""Tests for Lastikman's Grapple (W): a self-hook that reels the caster to the
first wall / tree / structure it strikes, and fizzles over open ground."""

import math
import unittest

from server.game_state import GameState
from server.entity import HookProjectile, Wall, Structure
from server.systems import (
    system_ability_cast, system_projectiles, system_displacements,
    system_collision,
)
from shared.game_types import Team
from shared.geometry import closest_point_on_segment
from server.heroes.lastikman import W_MAX_DIST


class TestLastikmanGrapple(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "L", Team.TEAM1, hero_id="lastikman")
        self.hero.x, self.hero.y = 1000, 1000
        for k in ("Q", "W", "E", "R"):
            self.hero.ability_levels[k] = 1

    def _cast(self, tx, ty):
        self.state.ability_casts.append(
            {"caster": self.hero.entity_id, "key": "W",
             "tx": tx, "ty": ty, "tid": None})
        system_ability_cast(self.state, 0.05)

    def _proj(self):
        return next((e for e in self.state.entities.values()
                     if isinstance(e, HookProjectile)), None)

    def _advance(self, ticks=60):
        for _ in range(ticks):
            system_projectiles(self.state, 0.05)
            system_displacements(self.state, 0.05)
            system_collision(self.state, 0.05)

    def test_grapple_spawns_self_hook_projectile(self):
        self._cast(2000, 1000)
        p = self._proj()
        self.assertIsNotNone(p)
        self.assertTrue(p.anchor_terrain)
        self.assertTrue(p.self_pull)
        self.assertEqual(p.team, Team.TEAM1)

    def test_grapple_reels_caster_to_wall(self):
        wall = Wall(x1=1600, y1=800, x2=1600, y2=1200, thickness=60)
        self.state.entities[wall.entity_id] = wall
        self._cast(1600, 1000)  # aim straight at the wall
        self._advance()
        self.assertGreater(self.hero.x, 1150)   # pulled toward the wall
        self.assertLess(self.hero.x, 1600)      # but stops short of it

    def test_grapple_reels_caster_to_wall_off_center(self):
        """Regression test: grappling near one end of a long wall, at a
        shallow angle, must not leave the caster stuck inside the wall's
        capsule (the anchor used to be computed against the wall's
        bounding-box midpoint instead of its true surface)."""
        wall = Wall(x1=1600, y1=700, x2=1600, y2=1900, thickness=60)
        self.state.entities[wall.entity_id] = wall
        self.hero.x, self.hero.y = 1000, 1850  # near the wall's far end
        self._cast(1600, 1850)
        self._advance()
        cx, cy = closest_point_on_segment(self.hero.x, self.hero.y,
                                          wall.x1, wall.y1, wall.x2, wall.y2)
        dist = math.hypot(self.hero.x - cx, self.hero.y - cy)
        self.assertGreater(dist, wall.thickness / 2 + self.hero.radius)

    def test_reeling_hero_ignores_wall_ejection_mid_pull(self):
        """While mid-reel toward a fixed point (grapple in flight),
        system_collision must not fight that tick's pull even if the hero's
        circle currently overlaps a wall's capsule — otherwise the eject and
        the pull fight each other every tick, reading as "stuck on the
        wall"."""
        wall = Wall(x1=1600, y1=800, x2=1600, y2=1200, thickness=60)
        self.state.entities[wall.entity_id] = wall
        self.hero.x, self.hero.y = 1600, 1000  # inside the wall's capsule
        self.state.pulls.append({"tgt": self.hero.entity_id, "pt": (1700, 1000),
                                 "speed": 1500, "stop": 70})
        system_collision(self.state, 0.05)
        self.assertEqual((self.hero.x, self.hero.y), (1600, 1000))

    def test_grapple_reels_caster_to_structure(self):
        struct = Structure(team=Team.TEAM2, x=1700, y=1000)
        self.state.entities[struct.entity_id] = struct
        self._cast(1700, 1000)
        self._advance()
        self.assertGreater(self.hero.x, 1150)

    def test_grapple_terminates_on_thick_wall(self):
        """Regression test: a flat 70-unit stop margin left zero/negative
        clearance against thick map walls (thickness up to 100), so the pull
        could rest exactly on — or never clear — the collision boundary and
        never terminate. The stop distance must scale with the wall's own
        half-thickness."""
        wall = Wall(x1=1860, y1=4555, x2=2210, y2=4220, thickness=100)
        self.state.entities[wall.entity_id] = wall
        self.hero.x, self.hero.y = 1700, 4650
        self._cast(2035, 4387)
        self._advance(200)
        self.assertEqual(self.state.pulls, [])  # pull must have terminated
        cx, cy = closest_point_on_segment(self.hero.x, self.hero.y,
                                          wall.x1, wall.y1, wall.x2, wall.y2)
        dist = math.hypot(self.hero.x - cx, self.hero.y - cy)
        self.assertGreater(dist, wall.thickness / 2 + self.hero.radius)
        # And the hero must be able to move again immediately afterward.
        from server.systems import system_movement
        self.hero.target_x, self.hero.target_y = 1000, 4650
        for _ in range(20):
            system_movement(self.state, 0.05)
            system_collision(self.state, 0.05)
        self.assertLess(self.hero.x, 1700)

    def test_grapple_terminates_on_structure_wider_than_stop_dist(self):
        """Regression test: the Core's radius (80) plus the hero's own radius
        exceeds the flat 70-unit stop margin, so a pull toward it could never
        satisfy its own arrival condition and would linger forever, fighting
        system_collision's (structure) ejection every tick."""
        core = Structure(team=Team.TEAM2, x=2000, y=2000, radius=80)
        self.state.entities[core.entity_id] = core
        self.hero.x, self.hero.y = 1700, 2000
        self._cast(2000, 2000)
        self._advance(200)
        self.assertEqual(self.state.pulls, [])
        dist = math.hypot(self.hero.x - core.x, self.hero.y - core.y)
        self.assertGreater(dist, core.radius + self.hero.radius)

    def test_grapple_fizzles_on_open_ground(self):
        x0, y0 = self.hero.x, self.hero.y
        self._cast(1000 + W_MAX_DIST, 1000)  # nothing along the path
        self._advance()
        self.assertIsNone(self._proj())          # despawned at max range
        self.assertEqual((self.hero.x, self.hero.y), (x0, y0))  # never moved


if __name__ == "__main__":
    unittest.main()
