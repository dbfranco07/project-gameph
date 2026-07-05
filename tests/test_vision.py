"""Tests for server-side fog-of-war (per-team visibility)."""

import unittest

from server.game_state import GameState
from server.entity import Hero, MeleeMinion, NeutralMinion, Wall
from server.systems import find_attack_target, system_combat
from shared.game_types import Team, EntityType
from shared.config import HERO_VISION_RADIUS


class TestVision(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.me = self.state.add_hero(1, "Me", Team.TEAM1, hero_id="ranger")
        self.enemy = self.state.add_hero(2, "En", Team.TEAM2, hero_id="brawler")
        self.me.x, self.me.y = 1000, 1000

    def test_enemy_hidden_when_out_of_vision(self):
        self.enemy.x, self.enemy.y = 1000 + HERO_VISION_RADIUS + 500, 1000
        vis = self.state.visible_entity_ids_for(Team.TEAM1)
        self.assertIn(self.me.entity_id, vis)
        self.assertNotIn(self.enemy.entity_id, vis)
        ids = {e["id"] for e in self.state.build_snapshot_for(Team.TEAM1)}
        self.assertNotIn(self.enemy.entity_id, ids)

    def test_enemy_visible_when_in_vision(self):
        self.enemy.x, self.enemy.y = 1000 + HERO_VISION_RADIUS - 100, 1000
        vis = self.state.visible_entity_ids_for(Team.TEAM1)
        self.assertIn(self.enemy.entity_id, vis)

    def test_structures_always_visible(self):
        self.state.start_match(kill_target=10)
        # Move my hero far from everything so no unit grants vision near towers.
        self.me.x, self.me.y = 10, 10
        vis = self.state.visible_entity_ids_for(Team.TEAM1)
        struct_ids = [e.entity_id for e in self.state.entities.values()
                      if e.entity_type in (EntityType.TOWER, EntityType.BASE)]
        self.assertTrue(struct_ids)
        for sid in struct_ids:
            self.assertIn(sid, vis)  # both teams' structures revealed

    def test_per_team_snapshots_differ(self):
        self.enemy.x, self.enemy.y = 5500, 1000  # far from my hero
        s1 = {e["id"] for e in self.state.build_snapshot_for(Team.TEAM1)}
        s2 = {e["id"] for e in self.state.build_snapshot_for(Team.TEAM2)}
        self.assertNotEqual(s1, s2)


class TestFogGatesCombat(unittest.TestCase):
    """Heroes can't acquire attack targets their team can't see; minions,
    structures and neutrals stay ungated (Team.NONE has no vision sources)."""

    def setUp(self):
        self.state = GameState()
        self.me = self.state.add_hero(1, "Me", Team.TEAM1, hero_id="ranger")
        self.enemy = self.state.add_hero(2, "En", Team.TEAM2, hero_id="brawler")
        self.me.x, self.me.y = 1000, 1000
        self.enemy.x, self.enemy.y = 1400, 1000  # inside ranger attack range

    def _wall_between(self):
        wall = Wall(x1=1200, y1=800, x2=1200, y2=1200, thickness=60)
        self.state.entities[wall.entity_id] = wall
        return wall

    def test_target_found_with_line_of_sight(self):
        self.assertIs(find_attack_target(self.state, self.me), self.enemy)

    def test_no_auto_attack_target_through_fog(self):
        self._wall_between()  # blocks sight, but the enemy is still in range
        self.assertIsNone(find_attack_target(self.state, self.me))

    def test_forced_target_in_fog_deals_no_damage(self):
        self._wall_between()
        self.me.forced_target_id = self.enemy.entity_id
        system_combat(self.state, 0.05)
        self.assertFalse(any(ev.get("src") == self.me.entity_id
                             for ev in self.state.damage_events))

    def test_minions_still_fight_in_the_fog(self):
        # Far from every hero, so both lane minions are fogged for both teams;
        # they must still brawl (minion targeting is not vision-gated).
        a = MeleeMinion(team=Team.TEAM1, x=5000, y=5000)
        b = MeleeMinion(team=Team.TEAM2, x=5040, y=5000)
        self.state.entities[a.entity_id] = a
        self.state.entities[b.entity_id] = b
        self.assertIs(find_attack_target(self.state, a), b)

    def test_provoked_neutral_attacks_adjacent_hero(self):
        mob = NeutralMinion(x=1040, y=1000, provoked=True)
        self.state.entities[mob.entity_id] = mob
        self.assertIs(find_attack_target(self.state, mob), self.me)

    def test_visible_ids_cached_per_tick(self):
        s1 = self.state.visible_ids_cached(Team.TEAM1)
        self.assertIs(self.state.visible_ids_cached(Team.TEAM1), s1)
        self.state.tick += 1
        self.assertIsNot(self.state.visible_ids_cached(Team.TEAM1), s1)


if __name__ == "__main__":
    unittest.main()
