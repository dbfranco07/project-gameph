"""Pedro Penduko — wielder of the Mutya, the seven-colored gem of power.

A unique 8-skill hero. The seven regular skills are the colors of the Mutya, on
keys Q W E R T Y U; the White ultimate is on key I.

  Q Red    (self)  Lakas — extraordinary strength (bonus attack damage).
  W Orange (self)  Tibay — hardened body (bonus physical + special defense).
  E Yellow (self)  Awit — an enthralling song that silences nearby enemies.
  R Green  (self)  Bilis — a surge of speed and a burst of self-healing.
  T Blue   (point) Lukso — a great leap that vaults over walls and trees.
  Y Indigo (self)  Mata — far, unobstructed sight.
  U Violet (self)  Ilag — preternatural reflexes (evasion).
  I White  (unit)  Puti — a devastating nuke for a large % of the target's HP.

The catch (kit identity): he can only keep **4 of the 7** color powers committed
at once. Casting a 4th puts him at his limit, so all seven read as "in cooldown"
(the unused three lock until a committed power frees). The White ultimate is only
usable while all four slots are committed, and casting it spends the whole Mutya
— every color skill is slammed onto full cooldown.

The slot logic is self-contained here (commit guard in each body + on_tick lock
mirroring); the engine's cooldown/rank dicts are key-agnostic so no core change
is needed beyond the hero-aware leveling in game_state.level_ability.
"""

from __future__ import annotations

from shared.game_types import CastType
from server.heroes.base import HeroDef, ability
from server.effects import make_effect
from server import skills

# --- Tuning ----------------------------------------------------------------
# Regular-skill cooldowns. A committed power's buff lasts exactly this long, so
# "on cooldown" == "power active", and four of them at once is the hard cap.
RED_CD, ORANGE_CD, YELLOW_CD, GREEN_CD = 12.0, 12.0, 13.0, 12.0
BLUE_CD, INDIGO_CD, VIOLET_CD = 10.0, 14.0, 12.0

RED_DMG = 45                 # Lakas: bonus attack damage
ORANGE_PDEF, ORANGE_SDEF = 34, 34
YELLOW_RADIUS, YELLOW_SILENCE = 360, 1.6
GREEN_SPEED, GREEN_HEAL = 130, 200
BLUE_DIST, BLUE_PHASE = 460, 0.45
INDIGO_VISION = 520
VIOLET_EVASION = 0.30

WHITE_CD = 60.0
WHITE_RANGE = 320
WHITE_PCT = 0.30             # % of the target's MAX HP dealt as true damage

REGULAR = ("Q", "W", "E", "R", "T", "Y", "U")
MAX_SLOTS = 4
# Full cooldown per regular key, used when White spends the whole Mutya.
REGULAR_CDS = {
    "Q": RED_CD, "W": ORANGE_CD, "E": YELLOW_CD, "R": GREEN_CD,
    "T": BLUE_CD, "Y": INDIGO_CD, "U": VIOLET_CD,
}


def _commit(hero, key: str) -> bool:
    """Try to occupy one of the four Mutya slots with `key`. Returns False when
    he is already at his limit and this key isn't one of the committed four."""
    slots = hero.ability_state.setdefault("pedro_committed", set())
    if key not in slots and len(slots) >= MAX_SLOTS:
        return False
    slots.add(key)
    return True


def _gated(ctx, key: str) -> bool:
    """Shared opener for every color skill: enforce the 4-slot limit. On rejection
    refund the press (the cast handler already started the cooldown) and report
    that the body should abort."""
    if _commit(ctx.caster, key):
        return True
    ctx.caster.cooldowns[key] = 0.0
    return False


class Pedro(HeroDef):
    hero_id = "pedro"
    name = "Pedro Penduko"

    # The Mutya makes him a versatile bruiser; Red supplies his burst strength.
    hp = 680
    mana = 340
    move_speed = 270
    atk_dmg = 60
    sp_atk = 10
    phys_def = 22
    sp_def = 20
    atk_range = 170
    atk_interval = 1.0
    atk_type = "melee"
    hp_regen = 3.5
    phys_def_per_level = 3.0
    sp_def_per_level = 2.5

    # The ultimate lives on "I" and may only be raised (once) at level 8.
    ult_key = "I"
    ult_level_gates = (8,)

    # --- The seven colors of the Mutya (max rank 2, any time) --------------
    @ability("Q", "Red Mutya: Lakas", cd=RED_CD, mana=55, cast=CastType.NONE,
             max_rank=2,
             desc="Channel the red gem for extraordinary strength: bonus attack "
                  "damage while the power is held.")
    def red(ctx):
        if not _gated(ctx, "Q"):
            return
        ctx.caster.buffs.append(make_effect(RED_CD, source="pedro:red",
                                            dmg_bonus=RED_DMG))

    @ability("W", "Orange Mutya: Tibay", cd=ORANGE_CD, mana=55,
             cast=CastType.NONE, max_rank=2,
             desc="Channel the orange gem to harden your body: bonus physical "
                  "and special defense while held.")
    def orange(ctx):
        if not _gated(ctx, "W"):
            return
        ctx.caster.buffs.append(make_effect(ORANGE_CD, source="pedro:orange",
                                            phys_def=ORANGE_PDEF,
                                            sp_def=ORANGE_SDEF))

    @ability("E", "Yellow Mutya: Awit", cd=YELLOW_CD, mana=60,
             cast=CastType.NONE, max_rank=2,
             desc="Sing an enthralling song: silence nearby enemies for a few "
                  "seconds.")
    def yellow(ctx):
        if not _gated(ctx, "E"):
            return
        # Self-centred AoE (aim the shared block at the caster, like Kapre Smash).
        ctx.tx, ctx.ty = ctx.caster.x, ctx.caster.y
        hit = skills.area_dmg(ctx, dmg=0, radius=YELLOW_RADIUS, dtype="special",
                              fx="awit")
        for e in hit:
            skills.silence(ctx, e, YELLOW_SILENCE)

    @ability("R", "Green Mutya: Bilis", cd=GREEN_CD, mana=55,
             cast=CastType.NONE, max_rank=2,
             desc="Channel the green gem for extraordinary speed and an "
                  "immediate burst of self-healing.")
    def green(ctx):
        if not _gated(ctx, "R"):
            return
        ctx.caster.buffs.append(make_effect(GREEN_CD, source="pedro:green",
                                            speed_bonus=GREEN_SPEED))
        ctx.state.damage_events.append(
            {"tgt": ctx.caster.entity_id, "heal": GREEN_HEAL})

    @ability("T", "Blue Mutya: Lukso", cd=BLUE_CD, mana=50,
             cast=CastType.POINT, max_rank=2,
             desc="Leap with the blue gem, vaulting over walls and trees to the "
                  "target spot.")
    def blue(ctx):
        if not _gated(ctx, "T"):
            return
        # Phase briefly so the leap crosses terrain, then land.
        ctx.caster.buffs.append(make_effect(BLUE_PHASE, source="pedro:blue",
                                            phase=True))
        skills.dash(ctx, dist=BLUE_DIST)

    @ability("Y", "Indigo Mutya: Mata", cd=INDIGO_CD, mana=45,
             cast=CastType.NONE, max_rank=2,
             desc="The indigo gem grants far, unobstructed sight for a time.")
    def indigo(ctx):
        if not _gated(ctx, "Y"):
            return
        ctx.caster.buffs.append(make_effect(INDIGO_CD, source="pedro:indigo",
                                            vision_bonus=INDIGO_VISION,
                                            unobstructed_vision=True))

    @ability("U", "Violet Mutya: Ilag", cd=VIOLET_CD, mana=55,
             cast=CastType.NONE, max_rank=2,
             desc="The violet gem sharpens your reflexes: a chance to evade "
                  "physical attacks while held.")
    def violet(ctx):
        if not _gated(ctx, "U"):
            return
        ctx.caster.buffs.append(make_effect(VIOLET_CD, source="pedro:violet",
                                            evasion=VIOLET_EVASION))

    # --- White Mutya: the ultimate (max rank 1, level 8) -------------------
    @ability("I", "White Mutya: Puti", cd=WHITE_CD, mana=150,
             cast=CastType.UNIT, max_rank=1,
             desc="Only when all four Mutya slots are committed: unleash the "
                  "white gem to tear away a large share of a target's health — "
                  "then the whole Mutya goes dark (all colors hit full cooldown).")
    def white(ctx):
        caster = ctx.caster
        committed = caster.ability_state.setdefault("pedro_committed", set())
        if len(committed) < MAX_SLOTS:
            caster.cooldowns["I"] = 0.0   # not all-committed yet: do nothing
            return
        target = ctx.state.entities.get(ctx.tid) if ctx.tid else None
        if (target is None or not target.alive or target.team == caster.team
                or caster.distance_to(target) > WHITE_RANGE + target.radius):
            caster.cooldowns["I"] = 0.0   # no valid target: refund, keep charge
            return
        dmg = int(getattr(target, "max_hp", target.hp) * WHITE_PCT)
        ctx.state.damage_events.append(
            {"src": caster.entity_id, "tgt": target.entity_id, "amt": dmg,
             "dtype": "true", "fx": "puti"})
        # Spend the whole Mutya: every color skill to full cooldown.
        for k, cd in REGULAR_CDS.items():
            caster.cooldowns[k] = cd
        committed.clear()
        caster.ability_state.pop("pedro_locked", None)

    # ----- lifecycle hooks --------------------------------------------------
    @staticmethod
    def on_tick(state, hero, dt):
        committed = hero.ability_state.setdefault("pedro_committed", set())
        locked = hero.ability_state.setdefault("pedro_locked", set())
        if not hero.alive:
            committed.clear()
            locked.clear()
            return
        # Release any committed color whose real cooldown has finished.
        for k in list(committed):
            if hero.cooldowns.get(k, 0.0) <= 0:
                committed.discard(k)
        if len(committed) >= MAX_SLOTS:
            # At the limit: mirror the unused colors as "on cooldown" until the
            # soonest committed power frees, so the HUD greys + counts them down.
            unlock_in = min(hero.cooldowns.get(k, 0.0) for k in committed)
            for k in REGULAR:
                if k not in committed:
                    hero.cooldowns[k] = unlock_in
                    locked.add(k)
        else:
            # Below the limit: clear ONLY the artificial locks we placed (never a
            # real cooldown from a genuine cast or from White's Mutya reset).
            for k in list(locked):
                hero.cooldowns[k] = 0.0
                locked.discard(k)
