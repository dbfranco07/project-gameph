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
from server.effects import make_effect
from server import skills, terrain, bind

# --- Tuning ----------------------------------------------------------------
Q_RADIUS, Q_DMG, Q_STUN = 320, 120, 0.8

W_BOLT_DMG, W_BOLT_STUN = 80, 1.0
W_BOLT_SPEED, W_BOLT_RANGE = 900, 750
W_REGEN = 9.0              # bonus hp/sec while near trees (passive)
W_ACTIVE_REGEN_DUR = 4.0   # the active stacks a second, equal regen (doubled)

NEAR_PAD = 140             # how close counts as "near" a tree
E_DMG_PER_RANK = 12        # bonus attack damage per E rank near/inside trees
E_RANGE_BONUS = 70         # bonus attack range near trees (only when NOT bound)

R_TOGGLE_CD = 1.0          # min time between enter/leave presses
R_REAL_CD = 24.0           # cooldown applied when he leaves the tree
R_GRAB = 150               # click this close to a tree to enter it
R_VISION_BONUS = 400
R_ATK_SLOW, R_ATK_SLOW_DUR = 0.5, 1.5

_AURA_SOURCES = ("kapre:vigor", "kapre:ironbark")


def _in_tree(state, hero) -> bool:
    """True while Kapre is living in / standing inside a tree."""
    if hero.ability_state.get("bind", {}).get("kind") == "tree":
        return True
    return terrain.inside_obstacle(state, hero.x, hero.y, Tree)


class Kapre(HeroDef):
    hero_id = "kapre"
    name = "Kapre"

    hp = 780
    mana = 300
    move_speed = 250
    atk_dmg = 66
    sp_atk = 10
    phys_def = 30
    sp_def = 24
    atk_range = 150
    atk_interval = 1.05
    atk_type = "melee"
    hp_regen = 5.0
    phys_def_per_level = 4.0
    sp_def_per_level = 2.5

    @ability("Q", "Smash", cd=9, mana=70, cast=CastType.NONE,
             desc="Slam the ground: damage and briefly stun nearby enemies.")
    def smash(ctx):
        # Self-centred AoE: aim the shared blocks at the caster's own position.
        ctx.tx, ctx.ty = ctx.caster.x, ctx.caster.y
        skills.area_dmg(ctx, dmg=Q_DMG, radius=Q_RADIUS, fx="smash")
        skills.stun_nearby(ctx, radius=Q_RADIUS, duration=Q_STUN)

    @ability("W", "Grove's Vigor", cd=10, mana=0, cast=CastType.POINT,
             desc="Passive regen near trees. Inside a tree: hurl a stunning bolt "
                  "and double your regen.")
    def groves_vigor(ctx):
        hero = ctx.caster
        if not _in_tree(ctx.state, hero):
            hero.cooldowns["W"] = 0.0  # passive-only outside trees: no penalty
            return
        skills.hook(ctx, dmg=W_BOLT_DMG, speed=W_BOLT_SPEED, range=W_BOLT_RANGE,
                    pull=False, stun_dur=W_BOLT_STUN, kind="kapre_w")
        # Stacks a second regen aura → doubled while it lasts.
        hero.buffs.append(make_effect(W_ACTIVE_REGEN_DUR,
                                      source="kapre:vigor_active",
                                      hp_regen_bonus=W_REGEN))

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
            bind.release_bind(hero)
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
        # Refresh the tree-proximity auras (W passive regen, E damage/range).
        hero.buffs[:] = [b for b in hero.buffs
                         if b.get("source") not in _AURA_SOURCES]
        if not hero.alive:
            return
        bound_tree = hero.ability_state.get("bind", {}).get("kind") == "tree"
        if not (bound_tree or terrain.near_trees(state, hero.x, hero.y, NEAR_PAD)):
            return
        hero.buffs.append(make_effect(0.5, source="kapre:vigor",
                                      hp_regen_bonus=W_REGEN))
        erank = hero.ability_rank("E")
        if erank > 0:
            mods = {"dmg_bonus": E_DMG_PER_RANK * erank}
            if not bound_tree:  # while bound he attacks at his regular range
                mods["range_bonus"] = E_RANGE_BONUS
            hero.buffs.append(make_effect(0.5, source="kapre:ironbark", **mods))
