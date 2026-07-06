"""Tests for Lastikman's Grapple (W): a self-hook that reels the caster to the
first wall / tree / structure it strikes, and fizzles over open ground."""

import unittest

from server.game_state import GameState
from server.entity import HookProjectile, Wall, Structure
from server.systems import (
    system_ability_cast, system_projectiles, system_displacements,
)
from shared.game_types import Team
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

    def test_grapple_reels_caster_to_structure(self):
        struct = Structure(team=Team.TEAM2, x=1700, y=1000)
        self.state.entities[struct.entity_id] = struct
        self._cast(1700, 1000)
        self._advance()
        self.assertGreater(self.hero.x, 1150)

    def test_grapple_fizzles_on_open_ground(self):
        x0, y0 = self.hero.x, self.hero.y
        self._cast(1000 + W_MAX_DIST, 1000)  # nothing along the path
        self._advance()
        self.assertIsNone(self._proj())          # despawned at max range
        self.assertEqual((self.hero.x, self.hero.y), (x0, y0))  # never moved


if __name__ == "__main__":
    unittest.main()
