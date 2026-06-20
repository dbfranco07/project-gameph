"""Tests for the data-driven ability system, projectiles, and leveling."""

import unittest

from server.game_state import GameState
from server.entity import Hero, Projectile
from server.systems import (
    system_ability_cast,
    system_projectiles,
    system_damage_death,
    system_status,
    _grant_xp,
    xp_to_next,
)
from shared.game_types import Team
from server.heroes import validate_all, get_hero_def, list_hero_ids


class TestHeroData(unittest.TestCase):
    def test_all_hero_defs_valid(self):
        validate_all()  # raises on malformed data

    def test_hero_ids_nonempty(self):
        self.assertTrue(len(list_hero_ids()) >= 1)

    def test_loadout_applied_to_hero(self):
        state = GameState()
        hero = state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")
        self.assertEqual(hero.hero_id, "ranger")
        self.assertEqual(len(hero.abilities), 4)
        self.assertIn("Q", hero.cooldowns)
        self.assertIsNotNone(hero.hero_def)

    def test_describe_metadata_is_wire_safe(self):
        """JOIN_ACK ability metadata must carry cast-type and exclude cast code."""
        meta = get_hero_def("ranger").describe()
        keys = [a["key"] for a in meta["abilities"]]
        self.assertEqual(keys, ["Q", "W", "E", "R"])
        for ab in meta["abilities"]:
            self.assertIn("cast", ab)            # cast-type for client targeting
            self.assertIn("mana", ab)
            self.assertNotIn("fn", ab)           # no server cast code on the wire


class TestStun(unittest.TestCase):
    def test_stun_blocks_movement_and_clears(self):
        from server.skills import stun_nearby
        from server.heroes.base import CastContext
        from server.systems import system_movement, system_status
        state = GameState()
        caster = state.add_hero(1, "A", Team.TEAM1, hero_id="brawler")
        victim = state.add_hero(2, "B", Team.TEAM2, hero_id="ranger")
        caster.x, caster.y = 1000, 1000
        victim.x, victim.y = 1050, 1000
        stun_nearby(CastContext(state, caster, 0, 0, None), radius=200, duration=1.0)
        self.assertTrue(victim.is_stunned())
        victim.target_x, victim.target_y = 2000, 1000  # try to walk away
        x0 = victim.x
        system_movement(state, 0.05)
        self.assertEqual(victim.x, x0)               # stunned -> can't move
        for _ in range(30):                          # tick the stun out (~1.5s)
            system_status(state, 0.05)
        self.assertFalse(victim.is_stunned())


class TestAbilityCast(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.caster = self.state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")
        self.target = self.state.add_hero(2, "B", Team.TEAM2, hero_id="mender")
        self.caster.x, self.caster.y = 1000, 1000
        self.target.x, self.target.y = 1300, 1000

    def _cast(self, key, tx=None, ty=None, tid=None):
        self.state.ability_casts.append({
            "caster": self.caster.entity_id, "key": key,
            "tx": tx if tx is not None else self.target.x,
            "ty": ty if ty is not None else self.target.y,
            "tid": tid,
        })
        system_ability_cast(self.state, 0.05)

    def test_projectile_spawns_and_consumes_mana(self):
        mana_before = self.caster.mana
        self._cast("Q")
        projs = [e for e in self.state.entities.values() if isinstance(e, Projectile)]
        self.assertEqual(len(projs), 1)
        self.assertLess(self.caster.mana, mana_before)
        self.assertGreater(self.caster.cooldowns["Q"], 0)

    def test_projectile_hits_target(self):
        self._cast("Q")
        before = self.target.hp
        for _ in range(30):
            system_projectiles(self.state, 0.05)
            system_damage_death(self.state, 0.05)
        self.assertLess(self.target.hp, before)

    def test_cooldown_blocks_recast(self):
        self._cast("Q")
        first_count = len([e for e in self.state.entities.values()
                            if isinstance(e, Projectile)])
        self._cast("Q")  # still on cooldown -> no new projectile
        second_count = len([e for e in self.state.entities.values()
                             if isinstance(e, Projectile)])
        self.assertEqual(first_count, second_count)

    def test_insufficient_mana_blocks_cast(self):
        self.caster.mana = 0
        self._cast("R")  # ultimate costs 100 mana
        self.assertEqual(self.caster.cooldowns["R"], 0)

    def test_dash_moves_caster(self):
        x0 = self.caster.x
        self._cast("W", tx=self.caster.x + 1000, ty=self.caster.y)
        self.assertGreater(self.caster.x, x0)

    def test_buff_boosts_damage_and_expires(self):
        brawler = self.state.add_hero(3, "C", Team.TEAM1, hero_id="brawler")
        base = brawler.effective_damage()
        self.state.ability_casts.append({
            "caster": brawler.entity_id, "key": "E",
            "tx": brawler.x, "ty": brawler.y, "tid": None})
        system_ability_cast(self.state, 0.05)
        self.assertGreater(brawler.effective_damage(), base)
        for _ in range(200):  # tick down ~10s of buff duration
            system_status(self.state, 0.05)
        self.assertEqual(brawler.effective_damage(), base)


class TestLeveling(unittest.TestCase):
    def test_xp_grants_levels_and_stats(self):
        hero = Hero(name="L", level=1, max_hp=600, hp=600, attack_damage=55)
        hp0, dmg0 = hero.max_hp, hero.attack_damage
        _grant_xp(hero, xp_to_next(1) + xp_to_next(2))
        self.assertEqual(hero.level, 3)
        self.assertGreater(hero.max_hp, hp0)
        self.assertGreater(hero.attack_damage, dmg0)


if __name__ == "__main__":
    unittest.main()
