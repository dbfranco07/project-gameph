"""Checks for the stringly-typed art contracts hero code relies on.

Three parameters name client art by string and are never verified:
`skills.projectile(kind=...)`, the `fx=` on the AoE helpers, and a hero's sprite
folder. A typo in any of them is silent — the renderer falls back to a coloured
dot or draws nothing at all — which is how **eight** `fx` names ended up
referring to art that was never generated.

Nothing here can run at class-definition time, because it needs the whole
registry and the asset tree at once. `heroes.validate_all()` calls it at server
startup, and a test runs it too, so a broken reference fails loudly instead of
being noticed months later as "that spell has no animation".
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from server.heroes.base import HERO_HOOKS

# The asset tree the client loads from (see client/sprites.py for the layout).
_ASSETS = Path(__file__).resolve().parents[2] / "client" / "assets"


def _available(category: str) -> set[str]:
    """Art keys that exist on disk for a category (empty if none generated)."""
    root = _ASSETS / category
    if not root.is_dir():
        return set()
    return {p.name for p in root.iterdir() if p.is_dir()}


# Which calls actually name client art, and where. Scoping to these matters:
# `bind.enter_bind(kind="tree")` also uses the word "kind", but means the sort
# of terrain being entered, not a projectile sprite.
#   callee name -> (art category, keyword, positional index or None)
_ART_CALLS = {
    "projectile": ("projectiles", "kind", None),
    "hook": ("projectiles", "kind", None),
    "grapple": ("projectiles", "kind", None),
    "area_dmg": ("effects", "fx", None),
    "area_heal": ("effects", "fx", None),
    "_emit_fx": ("effects", "name", 1),
}


def _callee_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _art_references(fn) -> dict[str, set[str]]:
    """Art keys named by literal in `fn`'s body, grouped by asset category.

    Read from the source rather than by calling the ability, since an ability
    body only runs mid-match with a live CastContext.
    """
    out: dict[str, set[str]] = {"projectiles": set(), "effects": set()}
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):  # pragma: no cover - source always available
        return out
    try:
        tree = ast.parse(inspect.cleandoc(src))
    except SyntaxError:  # pragma: no cover - defensive
        return out

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        spec = _ART_CALLS.get(_callee_name(node))
        if spec is None:
            continue
        category, keyword, pos = spec
        value = None
        for kw in node.keywords:
            if kw.arg == keyword and isinstance(kw.value, ast.Constant):
                value = kw.value.value
        if value is None and pos is not None and len(node.args) > pos:
            arg = node.args[pos]
            if isinstance(arg, ast.Constant):
                value = arg.value
        if isinstance(value, str) and value:
            out[category].add(value)
    return out


def collect_art_references() -> dict[str, dict[str, set[str]]]:
    """Every `kind=` / `fx=` literal in the registry, grouped by hero id."""
    from server.heroes import HERO_REGISTRY

    out: dict[str, dict[str, set[str]]] = {}
    for hero_id, cls in HERO_REGISTRY.items():
        kinds: set[str] = set()
        effects: set[str] = set()
        sources = [ab.fn for ab in cls.abilities]
        sources += [hook for hook in
                    (getattr(cls, name, None) for name in HERO_HOOKS)
                    if hook is not None]
        for fn in sources:
            refs = _art_references(fn)
            kinds |= refs["projectiles"]
            effects |= refs["effects"]
        out[hero_id] = {"kind": kinds, "fx": effects}
    return out


def missing_art() -> dict[str, list[str]]:
    """Art references that resolve to nothing, as ``{hero_id: [problems]}``.

    Returns empty when the asset tree has not been generated at all, so a fresh
    checkout without generated sprites does not fail every check.
    """
    projectiles = _available("projectiles")
    effects = _available("effects")
    heroes_art = _available("heroes")
    if not (projectiles or effects or heroes_art):
        return {}

    problems: dict[str, list[str]] = {}
    for hero_id, refs in collect_art_references().items():
        bad: list[str] = []
        if projectiles:
            bad += [f"kind={k!r} has no client/assets/projectiles/{k}/"
                    for k in sorted(refs["kind"]) if k not in projectiles]
        if effects:
            bad += [f"fx={f!r} has no client/assets/effects/{f}/"
                    for f in sorted(refs["fx"]) if f not in effects]
        if heroes_art and hero_id not in heroes_art:
            bad.append(f"no client/assets/heroes/{hero_id}/ sprite folder")
        if bad:
            problems[hero_id] = bad
    return problems


def validate_art_references(strict: bool = False) -> dict[str, list[str]]:
    """Report art references that resolve to nothing.

    Warns by default rather than refusing to start: missing art degrades to a
    placeholder shape, which is a real workflow (block out the mechanic, draw it
    later) and should not block a match. Pass ``strict=True`` — as the test does
    — to turn it into a hard failure.
    """
    problems = missing_art()
    if not problems:
        return problems
    lines = [f"  {hero_id}: {issue}"
             for hero_id, issues in sorted(problems.items())
             for issue in issues]
    message = "hero art references with no matching assets:\n" + "\n".join(lines)
    if strict:
        raise ValueError(message)
    print(f"[HEROES] warning: {message}")
    return problems
