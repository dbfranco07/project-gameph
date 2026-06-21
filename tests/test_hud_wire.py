"""Phase 5: the snapshot/metadata fields the new HUD relies on are present."""
import unittest

from shared.game_types import Team
from server.entity import Hero
from server.effects import make_effect
from server.heroes import get_hero_def


class TestHeroSnapshotFields(unittest.TestCase):
    def test_scoreboard_and_stats_present(self):
        h = Hero(team=Team.TEAM1, name="X", kills=3, deaths=1, assists=2,
                 minion_kills=20, neutral_kills=4)
        h.ability_levels = {"Q": 2, "W": 0, "E": 0, "R": 1}
        h.skill_points = 1
        snap = h.to_snapshot()
        for key in ("kills", "deaths", "assists", "mk", "nk",
                    "spa", "pdef", "sdef", "rng", "aspd", "hpr", "mpr",
                    "alvl", "sp"):
            self.assertIn(key, snap)
        self.assertEqual(snap["alvl"], {"Q": 2, "W": 0, "E": 0, "R": 1})

    def test_temp_deltas_only_when_nonzero(self):
        h = Hero(team=Team.TEAM1, phys_def=20)
        self.assertEqual(h.to_snapshot().get("dlt", {}), {})
        h.buffs.append(make_effect(3.0, phys_def=15, dmg_bonus=-5))
        dlt = h.to_snapshot()["dlt"]
        self.assertEqual(dlt["pdef"], 15)
        self.assertEqual(dlt["ad"], -5)

    def test_cc_flags_reported(self):
        h = Hero(team=Team.TEAM1)
        h.buffs.append(make_effect(2.0, stun=True))
        self.assertIn("stun", h.to_snapshot().get("cc", []))


class TestAbilityMetadata(unittest.TestCase):
    def test_describe_has_desc_and_max_rank(self):
        meta = get_hero_def("ranger").describe()
        for ab in meta["abilities"]:
            self.assertIn("desc", ab)
            self.assertIn("max_rank", ab)
        ranks = {ab["key"]: ab["max_rank"] for ab in meta["abilities"]}
        self.assertEqual(ranks["Q"], 4)
        self.assertEqual(ranks["R"], 3)  # ultimate caps at 3


if __name__ == "__main__":
    unittest.main()
