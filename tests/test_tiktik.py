"""Tests for Tiktik: tongue hook (pull + CC), wallrun, and frenzy."""

import unittest

from server.game_state import GameState
from server.entity import HookProjectile, NeutralMinion, Wall
from server.systems import (
    system_ability_cast,
    system_projectiles,
    system_displacements,
    system_damage_death,
    system_status,
    system_combat,
)
from server.heroes.tiktik import (
    FRENZY_HOOK_CD, FRENZY_HOOK_DMG, W_REAL_CD, W_VISION_BONUS,
)
from shared.game_types import Team


class TestTiktik(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "T", Team.TEAM1, hero_id="tiktik")
        self.enemy = self.state.add_hero(2, "E", Team.TEAM2, hero_id="brawler")
        self.hero.x, self.hero.y = 1000, 1000
        self.enemy.x, self.enemy.y = 1400, 1000
        for k in ("Q", "W", "E", "R"):
            self.hero.ability_levels[k] = 1

    def _cast(self, key, tx=None, ty=None, tid=None):
        self.state.ability_casts.append({
            "caster": self.hero.entity_id, "key": key,
            "tx": self.hero.x if tx is None else tx,
            "ty": self.hero.y if ty is None else ty, "tid": tid})
        system_ability_cast(self.state, 0.05)

    def _hook(self):
        return next((e for e in self.state.entities.values()
                     if isinstance(e, HookProjectile)), None)

    def _advance(self, ticks=30):
        for _ in range(ticks):
            system_projectiles(self.state, 0.05)
            system_displacements(self.state, 0.05)
            system_damage_death(self.state, 0.05)

    def _add_wall(self, x1, y1, x2, y2, th=60):
        wall = Wall(x1=x1, y1=y1, x2=x2, y2=y2, thickness=th)
        self.state.entities[wall.entity_id] = wall
        return wall

    # ----- Q Tongue Hook ----------------------------------------------------
    def test_hook_spawns_projectile(self):
        self._cast("Q", tx=self.enemy.x, ty=self.enemy.y)
        proj = self._hook()
        self.assertIsNotNone(proj)
        self.assertEqual(proj.team, Team.TEAM1)

    def test_hook_damages_and_pulls_to_melee(self):
        d0 = self.hero.distance_to(self.enemy)
        hp0 = self.enemy.hp
        self._cast("Q", tx=self.enemy.x, ty=self.enemy.y)
        self._advance()
        self.assertLess(self.enemy.hp, hp0)
        self.assertLess(self.hero.distance_to(self.enemy), d0)  # reeled in
        self.assertIsNone(self._hook())                         # hook consumed

    def test_hook_stuns_then_slows_with_E(self):
        self._cast("Q", tx=self.enemy.x, ty=self.enemy.y)
        self._advance()
        self.assertTrue(self.enemy.is_stunned())
        # Tick past the stun; the slow should linger after it.
        for _ in range(20):
            system_status(self.state, 0.05)
        self.assertFalse(self.enemy.is_stunned())
        self.assertGreater(self.enemy.slow_pct(), 0)

    def test_hook_ccs_neutral_minion(self):
        """The hook's pull/stun/slow land on neutrals, not just heroes."""
        self.enemy.x = 9000  # out of the hook's path
        mob = NeutralMinion(x=1400, y=1000)
        self.state.entities[mob.entity_id] = mob
        hp0, d0 = mob.hp, self.hero.distance_to(mob)
        self._cast("Q", tx=mob.x, ty=mob.y)
        self._advance()
        self.assertLess(mob.hp, hp0)
        self.assertLess(self.hero.distance_to(mob), d0)  # reeled in
        self.assertTrue(mob.is_stunned())
        for _ in range(20):
            system_status(self.state, 0.05)
        self.assertFalse(mob.is_stunned())
        self.assertGreater(mob.slow_pct(), 0)  # slow lingers after the stun

    def test_point_blank_hook_stays_visible(self):
        """A hook that lands on its first movement tick latches instead of
        despawning, so it appears in at least one snapshot."""
        self.enemy.x, self.enemy.y = 1080, 1000
        self._cast("Q", tx=self.enemy.x, ty=self.enemy.y)
        system_projectiles(self.state, 0.05)  # resolves the hit this tick
        proj = self._hook()
        self.assertIsNotNone(proj)
        self.assertEqual(proj.latched_id, self.enemy.entity_id)
        self._advance()
        self.assertIsNone(self._hook())  # gone once the pull + linger are done

    def test_hook_head_rides_victim_during_pull(self):
        self._cast("Q", tx=self.enemy.x, ty=self.enemy.y)
        for _ in range(30):  # fly until it lands
            system_projectiles(self.state, 0.05)
            proj = self._hook()
            if proj is not None and proj.latched_id:
                break
        self.assertEqual(proj.latched_id, self.enemy.entity_id)
        system_displacements(self.state, 0.05)  # drag the victim a step
        system_projectiles(self.state, 0.05)    # head follows
        self.assertEqual((proj.x, proj.y), (self.enemy.x, self.enemy.y))

    def test_hook_without_E_has_no_cc(self):
        self.hero.ability_levels["E"] = 0
        self._cast("Q", tx=self.enemy.x, ty=self.enemy.y)
        self._advance()
        self.assertFalse(self.enemy.is_stunned())
        self.assertEqual(self.enemy.slow_pct(), 0)

    # ----- R Frenzy ---------------------------------------------------------
    def test_frenzy_makes_hook_spammable_and_stronger(self):
        self._cast("R")
        self._cast("Q", tx=self.enemy.x, ty=self.enemy.y)
        self.assertEqual(self.hero.cooldowns["Q"], FRENZY_HOOK_CD)
        self.assertEqual(self._hook().damage, FRENZY_HOOK_DMG)

    # ----- W Wallrun --------------------------------------------------------
    def test_wallrun_binds_stealths_and_disarms(self):
        self._add_wall(1000, 1400, 1400, 1400)
        self._cast("W", tx=1100, ty=1400)
        self.assertEqual(self.hero.ability_state.get("bind", {}).get("kind"),
                         "wall")
        self.assertTrue(self.hero.is_invisible())
        self.assertTrue(self.hero.is_disarmed())
        self.assertTrue(self.hero.has_unobstructed_vision())
        self.assertEqual(self.hero.bonus_vision(), W_VISION_BONUS)
        self.assertNotIn(self.hero.entity_id,
                         self.state.visible_entity_ids_for(Team.TEAM2))

    def test_wallrun_cannot_attack(self):
        self._add_wall(1000, 1400, 1400, 1400)
        self._cast("W", tx=1100, ty=1400)
        self.enemy.x, self.enemy.y = self.hero.x + 100, self.hero.y
        hp0 = self.enemy.hp
        system_combat(self.state, 0.05)
        system_damage_death(self.state, 0.05)
        self.assertEqual(self.enemy.hp, hp0)  # disarmed: no auto-attack

    def test_wallrun_recast_on_ground_exits(self):
        self._add_wall(1000, 1400, 1400, 1400)
        self._cast("W", tx=1100, ty=1400)
        self.hero.cooldowns["W"] = 0.0
        self._cast("W", tx=5000, ty=5000)  # open ground: climb out
        self.assertNotIn("bind", self.hero.ability_state)
        self.assertFalse(self.hero.is_invisible())
        self.assertFalse(self.hero.is_disarmed())
        self.assertEqual(self.hero.cooldowns["W"], W_REAL_CD)

    def test_wall_hop_cancels_active_pull(self):
        """Binding to a wall is a teleport: any pull Tiktik owns is dropped so
        the victim isn't dragged across the map (fountain-hook bug)."""
        self._add_wall(1000, 1400, 1400, 1400)
        self.enemy.x, self.enemy.y = 1700, 1000
        self._cast("Q", tx=self.enemy.x, ty=self.enemy.y)
        for _ in range(30):  # fly until the hook lands and queues the pull
            system_projectiles(self.state, 0.05)
            if self.state.pulls:
                break
        self.assertTrue(self.state.pulls)
        self.hero.cooldowns["W"] = 0.0
        self._cast("W", tx=1100, ty=1400)  # teleport onto the wall
        self.assertEqual(self.state.pulls, [])
        ex, ey = self.enemy.x, self.enemy.y
        system_displacements(self.state, 0.05)
        self.assertEqual((self.enemy.x, self.enemy.y), (ex, ey))  # no drag

    def test_wallrun_recast_on_wall_jumps(self):
        self._add_wall(1000, 1400, 1400, 1400)
        far = self._add_wall(4000, 4000, 4400, 4000)
        self._cast("W", tx=1100, ty=1400)
        self.hero.cooldowns["W"] = 0.0
        self._cast("W", tx=4100, ty=4000)  # hop to the far wall
        self.assertIn("bind", self.hero.ability_state)
        self.assertIn(far.entity_id, self.hero.ability_state["bind"]["ids"])
        self.assertLess(abs(self.hero.y - 4000), far.thickness)  # snapped onto it


if __name__ == "__main__":
    unittest.main()
