"""Adding a hero must touch nothing but the hero's own file.

The core claim of the hero-authoring work. These tests copy the template into
the package at runtime, then assert the hero is fully playable — discovered,
castable, wire-described, renderable — without a single edit anywhere else.
"""

import gc
import importlib
import shutil
import sys
import unittest
from pathlib import Path

from server.heroes.base import HERO_HOOKS, HeroDef
from server.heroes.validation import missing_art
from shared.game_types import CastType

_HEROES_DIR = Path(__file__).resolve().parents[1] / "server" / "heroes"
_TEMPLATE = _HEROES_DIR / "_template.py"
_SCRATCH_ID = "scratch_hero_probe"
_SCRATCH_FILE = _HEROES_DIR / f"{_SCRATCH_ID}.py"
_SCRATCH_ART = (Path(__file__).resolve().parents[1]
                / "client" / "assets" / "heroes" / _SCRATCH_ID)


class TestAddingAHero(unittest.TestCase):
    """Drop one file in server/heroes/ — that is the whole workflow."""

    @classmethod
    def setUpClass(cls):
        # Step 5 of the workflow: the hero's sprite folder. Created here so the
        # probe is a *complete* hero, and so the art check below sees a valid
        # one for as long as unittest keeps this class alive.
        _SCRATCH_ART.mkdir(parents=True, exist_ok=True)
        source = _TEMPLATE.read_text()
        source = source.replace('hero_id = "template"',
                                f'hero_id = "{_SCRATCH_ID}"')
        source = source.replace('name = "Template Hero"',
                                'name = "Scratch Probe"')
        # Distinct class/status names so it cannot collide with the template.
        source = source.replace("TemplateHero", "ScratchProbe")
        source = source.replace("TemplatePassive", "ScratchPassive")
        source = source.replace('"template:passive"',
                                f'"{_SCRATCH_ID}:passive"')
        _SCRATCH_FILE.write_text(source)

        # Re-import the package exactly as a fresh server start would.
        import server.heroes
        importlib.reload(server.heroes)
        cls.heroes = server.heroes

    @classmethod
    def tearDownClass(cls):
        _SCRATCH_FILE.unlink(missing_ok=True)
        pycache = _HEROES_DIR / "__pycache__"
        for stale in pycache.glob(f"{_SCRATCH_ID}.*"):
            stale.unlink(missing_ok=True)
        # Discovery walks HeroDef.__subclasses__(), so the probe stays
        # registered for as long as its class is reachable. Deleting the file is
        # not enough: importing a submodule also binds it as an attribute on the
        # parent package, so both that binding and the sys.modules entry have to
        # go before the class becomes collectable.
        import server.heroes
        cls.heroes = None
        sys.modules.pop(f"server.heroes.{_SCRATCH_ID}", None)
        if hasattr(server.heroes, _SCRATCH_ID):
            delattr(server.heroes, _SCRATCH_ID)
        if _SCRATCH_ART.is_dir():
            shutil.rmtree(_SCRATCH_ART)
        gc.collect()
        importlib.reload(server.heroes)

    def test_hero_is_discovered_without_registry_edits(self):
        self.assertIn(_SCRATCH_ID, self.heroes.HERO_REGISTRY)
        self.assertIn(_SCRATCH_ID, self.heroes.list_hero_ids())

    def test_template_itself_is_not_registered(self):
        # Underscore-prefixed modules are skipped, so the template stays a
        # thing you copy rather than a playable hero on the select screen.
        self.assertNotIn("template", self.heroes.HERO_REGISTRY)

    def test_hero_reaches_the_client_catalog(self):
        entry = self.heroes.hero_catalog()[_SCRATCH_ID]
        self.assertEqual(entry["name"], "Scratch Probe")
        self.assertEqual([a["key"] for a in entry["abilities"]],
                         ["Q", "W", "E", "R"])
        for ab in entry["abilities"]:
            # Everything the HUD needs, and no cast code on the wire.
            for field in ("key", "name", "cd", "mana", "cast", "desc",
                          "max_rank", "target"):
                self.assertIn(field, ab)
            self.assertNotIn("fn", ab)

    def test_ultimate_gating_defaults_apply(self):
        cls = self.heroes.HERO_REGISTRY[_SCRATCH_ID]
        self.assertEqual(cls.ult_key, "R")
        self.assertEqual(cls.ability("R").max_rank, 3)
        self.assertEqual(cls.ability("Q").max_rank, 4)

    def test_hero_is_castable_end_to_end(self):
        from tests.herotest import HeroTestCase

        class _Probe(HeroTestCase):
            hero_id = _SCRATCH_ID

            def runTest(self):
                pass

        probe = _Probe()
        probe.setUp()
        hp0 = probe.enemy.hp
        probe.cast_at("W", probe.enemy)     # unit-targeted nuke
        probe.resolve_damage()
        self.assertLess(probe.enemy.hp, hp0)

    def test_passive_aura_attaches_and_applies(self):
        from tests.herotest import HeroTestCase

        class _Probe(HeroTestCase):
            hero_id = _SCRATCH_ID

            def runTest(self):
                pass

        probe = _Probe()
        probe.setUp()
        pdef0 = probe.hero.effective_phys_def()
        probe.tick()                         # on_tick attaches the aura
        self.assertGreater(probe.hero.effective_phys_def(), pdef0)


class TestHeroContracts(unittest.TestCase):
    """Contracts that hold for every hero in the registry."""

    def setUp(self):
        from server.heroes import HERO_REGISTRY
        self.registry = HERO_REGISTRY

    def test_art_references_all_resolve(self):
        # Eight `fx` names referred to art that was never generated before this
        # check existed; the failure mode was an ability that quietly drew
        # nothing. Strict here so it can never drift again.
        problems = missing_art()
        self.assertEqual(problems, {}, f"broken art references: {problems}")

    def test_every_hero_has_abilities_and_an_ultimate(self):
        for hero_id, cls in self.registry.items():
            with self.subTest(hero=hero_id):
                self.assertTrue(cls.abilities, "declares no abilities")
                ult = cls.ability(cls.ult_key)
                self.assertIsNotNone(
                    ult, f"ult_key {cls.ult_key!r} names no declared ability")
                self.assertEqual(
                    len(cls.ult_level_gates), ult.max_rank,
                    "ult_level_gates length must match the ultimate's max_rank")

    def test_ability_keys_are_unique_and_castable_types(self):
        for hero_id, cls in self.registry.items():
            with self.subTest(hero=hero_id):
                keys = [ab.key for ab in cls.abilities]
                self.assertEqual(len(keys), len(set(keys)))
                for ab in cls.abilities:
                    self.assertIsInstance(ab.cast_type, CastType)

    def test_hooks_are_callable_when_defined(self):
        for hero_id, cls in self.registry.items():
            for name in HERO_HOOKS:
                hook = getattr(cls, name, None)
                if hook is not None:
                    with self.subTest(hero=hero_id, hook=name):
                        self.assertTrue(callable(hook))

    def test_hook_names_are_not_typos(self):
        # A misspelled hook is silent: it simply never fires. Anything on a
        # hero class that looks like a hook must be a real one.
        known = set(HERO_HOOKS)
        for hero_id, cls in self.registry.items():
            for attr in vars(cls):
                if attr.startswith("on_"):
                    with self.subTest(hero=hero_id, attr=attr):
                        self.assertIn(attr, known,
                                      f"{attr!r} is not a HeroDef lifecycle hook")

    def test_default_hero_exists(self):
        from server.heroes import DEFAULT_HERO
        self.assertIn(DEFAULT_HERO, self.registry)


if __name__ == "__main__":
    unittest.main()
