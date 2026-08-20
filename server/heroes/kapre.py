"""Kapre — a towering tree-dwelling giant from Philippine folklore.

Kit:
  Q Smash       (self)    slam the ground: AoE damage + a short stun around him.
  W Grove's Vigor(point/passive)
                          PASSIVE: regenerates faster near trees. While he is
                          living in a tree (R), the skill turns ACTIVE: hurl a
                          stunning bolt and DOUBLE his regen for a few seconds.
  E Ironbark    (passive) stays melee, but gains attack damage near/inside trees
                          (and bonus range when not bound inside one).
  R Dwell       (point)   target a tree to live in it: invisible to enemies,
                          increased + unobstructed vision, confined to gliding
                          along that connected tree. He can still attack (briefly
                          revealed each swing) and his attacks slow by 50%.
                          Recast to leave.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.entity import Tree
from server.status import Aura, make_status
from server import skills, terrain, bind

# --- Tuning ----------------------------------------------------------------
Q_RADIUS, Q_STUN = 320, 0.8
Q_BASE_DMG, Q_DMG_PER_RANK = 94, 17

W_BASE_BOLT_DMG, W_BOLT_DMG_PER_RANK = 62, 11
W_BOLT_STUN = 1.0
W_BOLT_SPEED, W_BOLT_RANGE = 900, 750
W_BASE_REGEN, W_REGEN_PER_RANK = 7.0, 1.0   # bonus hp/sec while near trees (passive)
W_ACTIVE_REGEN_DUR = 4.0   # the active stacks a second, equal regen (doubled)

NEAR_PAD = 140             # how close counts as "near" a tree
E_DMG_PER_RANK = 12        # bonus attack damage per E rank near/inside trees
E_RANGE_BONUS = 70         # bonus attack range near trees (only when NOT bound)

R_TOGGLE_CD = 1.0          # min time between enter/leave presses
R_REAL_CD = 24.0           # cooldown applied when he leaves the tree
R_GRAB = 150               # click this close to a tree to enter it
R_VISION_BONUS = 400
R_ATK_SLOW, R_ATK_SLOW_DUR = 0.5, 1.5

def _bound_to_tree(hero) -> bool:
    status = bind.current_bind(hero)
    return status is not None and status.kind == "tree"


def _in_tree(state, hero) -> bool:
    """True while Kapre is living in / standing inside a tree."""
    if _bound_to_tree(hero):
        return True
    return terrain.inside_obstacle(state, hero.x, hero.y, Tree)


def _near_or_in_tree(state, hero) -> bool:
    return _bound_to_tree(hero) or terrain.near_trees(state, hero.x, hero.y,
                                                      NEAR_PAD)


# --- Passives -------------------------------------------------------------
# Both of Kapre's passives are conditional on tree proximity. As auras they are
# attached once and toggle with the condition, replacing the old idiom of
# rebuilding the buff list and allocating two fresh effect dicts every tick.

class _TreeAura(Aura):
    """Active while Kapre is near or inside a tree."""

    __slots__ = ()

    def condition(self, bearer, state) -> bool:
        return bool(bearer.alive and state is not None
                    and _near_or_in_tree(state, bearer))


class GroveVigor(_TreeAura):
    """W passive: faster health regeneration near trees, scaling with rank."""

    status_id = "kapre:vigor"
    __slots__ = ()
    dynamic = True

    @property
    def active_modifiers(self) -> dict:
        hero = self._bearer
        rank = hero.ability_rank("W") if hero else 0
        if rank <= 0:
            return {}
        return {"hp_regen_bonus": W_BASE_REGEN + W_REGEN_PER_RANK * (rank - 1)}


class Ironbark(_TreeAura):
    """E passive: bonus attack damage near trees, scaling with the ability's
    rank, plus extra range when not bound inside one. Its numbers move as Kapre
    levels the skill and as he enters/leaves a tree, so it is a dynamic aura."""

    status_id = "kapre:ironbark"
    __slots__ = ()
    dynamic = True

    @property
    def active_modifiers(self) -> dict:
        hero = self._bearer
        if hero is None:
            return {}
        rank = hero.ability_rank("E")
        if rank <= 0:
            return {}
        mods = {"dmg_bonus": E_DMG_PER_RANK * rank}
        if not _bound_to_tree(hero):  # while bound he attacks at regular range
            mods["range_bonus"] = E_RANGE_BONUS
        return mods


class Kapre(HeroDef):
    hero_id = "kapre"
    name = "Kapre"

    hp = 820
    mana = 260
    move_speed = 235
    atk_dmg = 60
    sp_atk = 8
    phys_def = 34
    sp_def = 26
    atk_range = 148
    atk_interval = 1.05
    atk_type = "melee"
    hp_regen = 5.5
    phys_def_per_level = 4.0
    sp_def_per_level = 2.5

    @ability("Q", "Smash", cd=9, mana=70, cast=CastType.NONE,
             desc="Slam the ground: damage and briefly stun nearby enemies.")
    def smash(ctx):
        # Self-centred AoE: aim the shared blocks at the caster's own position.
        ctx.tx, ctx.ty = ctx.caster.x, ctx.caster.y
        rank = ctx.caster.ability_rank("Q")
        dmg = Q_BASE_DMG + Q_DMG_PER_RANK * (rank - 1)
        skills.area_dmg(ctx, dmg=dmg, radius=Q_RADIUS, fx="smash")
        skills.stun_nearby(ctx, radius=Q_RADIUS, duration=Q_STUN)

    @ability("W", "Grove's Vigor", cd=10, mana=0, cast=CastType.POINT,
             desc="Passive regen near trees. Inside a tree: hurl a stunning bolt "
                  "and double your regen.")
    def groves_vigor(ctx):
        hero = ctx.caster
        if not _in_tree(ctx.state, hero):
            hero.cooldowns["W"] = 0.0  # passive-only outside trees: no penalty
            return
        rank = hero.ability_rank("W")
        bolt_dmg = W_BASE_BOLT_DMG + W_BOLT_DMG_PER_RANK * (rank - 1)
        regen = W_BASE_REGEN + W_REGEN_PER_RANK * (rank - 1)
        skills.hook(ctx, dmg=bolt_dmg, speed=W_BOLT_SPEED, range=W_BOLT_RANGE,
                    pull=False, stun_dur=W_BOLT_STUN, kind="kapre_w")
        # Stacks a second regen aura → doubled while it lasts.
        hero.statuses.add(make_status(W_ACTIVE_REGEN_DUR,
                                      source="kapre:vigor_active",
                                      hp_regen_bonus=regen), ctx.state)

    @ability("E", "Ironbark", cd=0, mana=0, cast=CastType.PASSIVE,
             desc="Passive: more attack damage near/inside trees (and bonus range "
                  "when not bound in one).")
    def ironbark(ctx):
        pass  # passive — applied in on_tick based on tree proximity

    @ability("R", "Dwell", cd=R_TOGGLE_CD, mana=0, cast=CastType.POINT,
             desc="Live in a targeted tree: invisible, see far through trees, "
                  "slide along it. Attacks slow 50%. Recast to leave.")
    def dwell(ctx):
        hero, state = ctx.caster, ctx.state
        if bind.is_bound(hero):
            bind.release_bind(hero, state)
            hero.cooldowns["R"] = R_REAL_CD
            return
        tree = terrain.obstacle_at(state, ctx.tx, ctx.ty, Tree, grab=R_GRAB)
        if tree is None:
            hero.cooldowns["R"] = 0.0  # no tree under the cursor: nothing happens
            return
        bind.enter_bind(state, hero, tree, kind="tree", ability_key="R",
                        vision_bonus=R_VISION_BONUS,
                        extra={"attack_slow_pct": R_ATK_SLOW,
                               "attack_slow_dur": R_ATK_SLOW_DUR})

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        bind.tick_bind(state, hero)  # clamp to the tree cluster while bound
        # Attach the passives once; from then on they toggle themselves against
        # tree proximity without any per-tick allocation.
        if hero.statuses.get("kapre:vigor") is None:
            hero.statuses.add(GroveVigor(), state)
            hero.statuses.add(Ironbark(), state)
