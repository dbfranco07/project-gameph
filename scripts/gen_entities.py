"""Procedural sprites for non-hero entities: lane minions (melee / ranged /
cart, human Team 1 vs ghoulish Team 2), monster-styled neutral creeps,
towers, the core, buff runes (one look per buff type), and tileable wall/tree
obstacle segments.

    uv run python scripts/gen_entities.py
"""

from __future__ import annotations

import math
import random

import spritelib as sl
import sprite_engine as se
import pygame

SEG = 48  # wall/tree tileable segment size


def _seg_canvas():
    return pygame.Surface((SEG * se.SS, SEG * se.SS), pygame.SRCALPHA)


def _seg_downsample(s):
    return pygame.transform.smoothscale(s, (SEG, SEG))


def wall_seg() -> pygame.Surface:
    """A horizontally-tileable mossy stone-block segment (tiled along a wall
    capsule), cel-shaded via sprite_engine instead of flat brick+mortar
    lines."""
    s = _seg_canvas()
    base = pygame.Surface((SEG, SEG))
    base.fill((88, 86, 96))
    s.blit(pygame.transform.scale(base, (SEG * se.SS, SEG * se.SS)), (0, 0))
    rng = random.Random(11)
    rows = [(0, 15), (15, 28), (28, 40), (40, 48)]
    for y0, y1 in rows:
        h = y1 - y0
        x = -rng.randint(0, 10)
        while x < SEG + 10:
            w = rng.randint(9, 17)
            tone = rng.uniform(-14, 16)
            col = tuple(max(40, min(150, int(c + tone))) for c in (98, 96, 104))
            for ox in (0, -SEG, SEG):
                se.rect(s, col, (x + ox, y0, w - 1.5, h - 1.5),
                       outline=(40, 38, 46), ow=1.4)
            x += w
    rng2 = random.Random(23)
    for _ in range(26):
        x, y = rng2.randint(0, SEG - 1), rng2.randint(0, SEG - 1)
        r = rng2.uniform(1.0, 2.6)
        col = (rng2.randint(60, 96), rng2.randint(96, 138), rng2.randint(56, 88))
        for ox in (0, -SEG, SEG):
            se.circle(s, col, (x + ox, y), r, outline=None, highlight=False,
                      shadow=False)
    return _seg_downsample(s)


def tree_seg() -> pygame.Surface:
    """A horizontally-tileable lush-canopy segment (tiled along a tree
    capsule): shaded round foliage clusters over a noise base, plus warm
    light-speckle accents, wraparound-tiled at the edges."""
    base = sl.tileable_noise(SEG, SEG, (34, 76, 40), 120, seed=7)
    s = _seg_canvas()
    s.blit(pygame.transform.scale(base, (SEG * se.SS, SEG * se.SS)), (0, 0))
    rng = random.Random(7)
    for _ in range(15):
        x, y, rr = rng.uniform(0, SEG), rng.uniform(6, 42), rng.uniform(5.5, 9.5)
        col = (rng.randint(44, 70), rng.randint(98, 136), rng.randint(50, 76))
        for ox in (0, -SEG, SEG):
            se.circle(s, col, (x + ox, y), rr, outline=(24, 52, 28), ow=1.0)
    rng2 = random.Random(19)
    for _ in range(10):
        x, y = rng2.uniform(0, SEG), rng2.uniform(4, 40)
        for ox in (0, -SEG, SEG):
            se.dot(s, (232, 214, 120), (x + ox, y), rng2.uniform(0.8, 1.6))
    return _seg_downsample(s)


# ---------------------------------------------------------------------------
# Lane minions — Team 1 reads human (soldier/scout), Team 2 reads ghoulish
# (sunken eyes, tattered cloth, bared claws via chibi_arms' claw hook).
# ---------------------------------------------------------------------------
T1_MELEE_PAL = {"skin": (224, 188, 154), "hair": (58, 42, 30),
                "cloth": (86, 106, 148), "cloth_dk": (54, 70, 100),
                "eye": (40, 30, 30)}
T1_RANGED_PAL = {"skin": (222, 186, 150), "hair": (96, 72, 40),
                 "cloth": (108, 140, 100), "cloth_dk": (68, 94, 62),
                 "eye": (40, 30, 30)}
T2_MELEE_PAL = {"skin": (118, 136, 118), "hair": (28, 28, 32),
                "cloth": (54, 46, 58), "cloth_dk": (34, 28, 38),
                "eye": (200, 40, 40), "claw": (222, 220, 210)}
T2_RANGED_PAL = {"skin": (108, 128, 116), "hair": (24, 24, 28),
                 "cloth": (60, 40, 66), "cloth_dk": (38, 26, 44),
                 "eye": (178, 60, 200), "claw": (210, 208, 198)}


def _sword_prop(s, x, y, angle):
    tipx = x + math.cos(angle) * 11
    tipy = y + math.sin(angle) * 11
    se.poly(s, (196, 198, 208), se.capsule_pts(x, y, tipx, tipy, 3.0),
           ow=1.2, outline=se.OUTLINE)
    se.dot(s, (120, 90, 50), (x, y), 1.4)


def _bow_prop(s, x, y, angle):
    ex = x + math.cos(angle) * 9
    ey = y + math.sin(angle) * 9
    se.line(s, (120, 92, 56), (x - 4, y - 6), (ex - 4, ey + 6), 1.6)


def _human_melee_overlay(s, action, facing, frame):
    if facing == "n":
        return
    phase = se._phase_for(action, frame)
    se.chibi_prop(s, action, facing, phase, 1, _sword_prop)


def _human_ranged_overlay(s, action, facing, frame):
    if facing == "n":
        return
    phase = se._phase_for(action, frame)
    se.chibi_prop(s, action, facing, phase, -1, _bow_prop)


def _ghoul_overlay(s, action, facing, frame):
    """Bared fangs at the mouth + a couple of visible rib lines."""
    if facing != "n":
        mx, my = se.chibi_mouth_point(facing)
        se.poly(s, sl.WHITE, [(mx - 2, my - 1), (mx + 2, my - 1), (mx, my + 3)],
               outline=None, highlight=False, shadow=False)
    for dy in (0, 3, 6):
        se.line(s, (24, 22, 26), (CX_ - 5, 25 + dy), (CX_ + 5, 25 + dy), 0.8)


CX_ = se.CX


def _chibi_minion(key: str, pal: dict, *, overlay=None) -> int:
    n = 0

    def compose(action, facing, frame):
        s = se.canvas()
        se.chibi_body_raw(s, pal, action, facing, frame)
        if overlay:
            overlay(s, action, facing, frame)
        return se.oriented(se.downsample(s), facing)

    for facing in se.FACINGS:
        sl.save(compose("idle", facing, 0), "entities", key, f"idle_{facing}")
        n += 1
        for fr in (0, 1):
            sl.save(compose("move", facing, fr), "entities", key, f"move_{facing}_{fr}")
            n += 1
    return n


def _cart() -> int:
    """A boxy siege cart instead of a blob (team-neutral: same on both sides)."""
    n = 0
    for facing in sl.FACINGS:
        s = sl.surf()
        sl.shadow(s)
        pygame.draw.rect(s, (120, 96, 60), (sl.CX - 12, 26, 24, 18),
                         border_radius=3)
        pygame.draw.rect(s, (80, 62, 36), (sl.CX - 12, 26, 24, 18), 2,
                         border_radius=3)
        pygame.draw.circle(s, (40, 36, 30), (sl.CX - 7, 46), 4)
        pygame.draw.circle(s, (40, 36, 30), (sl.CX + 7, 46), 4)
        sl.save(sl.oriented(s, facing), "entities", "minion_cart", f"idle_{facing}")
        n += 1
    return n


# ---------------------------------------------------------------------------
# Neutral jungle monster — a genuine quadruped monster, not a team minion.
# ---------------------------------------------------------------------------
MONSTER_PAL = {"cloth": (96, 78, 88), "cloth_dk": (60, 48, 56),
              "eye": (230, 200, 60)}


def _monster_body(s, pal, action, frame, facing="s"):
    se.beast_body(s, pal, action, facing, frame,
                 features=(se.monster_beast_features,))


# ---------------------------------------------------------------------------
# Buff runes — one distinct look per buff type instead of a generic diamond.
# ---------------------------------------------------------------------------
def _shape_haste(s, col, fr):
    cx = sl.CX
    pts = [(cx - 2, cx - 9), (cx + 4, cx - 9), (cx - 1, cx),
          (cx + 3, cx), (cx - 4, cx + 9), (cx - 1, cx + 1), (cx - 5, cx + 1)]
    pygame.draw.polygon(s, col, pts)
    pygame.draw.polygon(s, sl.WHITE, pts, 2)


def _shape_double_damage(s, col, fr):
    cx = sl.CX
    for sign in (-1, 1):
        pygame.draw.line(s, col, (cx - 8 * sign, cx - 8), (cx + 8 * sign, cx + 8), 3)
        pygame.draw.line(s, sl.WHITE, (cx - 8 * sign, cx - 8), (cx + 8 * sign, cx + 8), 1)
    pygame.draw.circle(s, sl.WHITE, (cx, cx), 3)


def _shape_cdr(s, col, fr):
    cx = sl.CX
    pygame.draw.circle(s, col, (cx, cx), 8, 2)
    ang = fr * 1.2
    pygame.draw.line(s, col, (cx, cx), (cx + math.cos(ang) * 6, cx + math.sin(ang) * 6), 2)
    pygame.draw.line(s, col, (cx, cx),
                     (cx + math.cos(ang + 2.4) * 4, cx + math.sin(ang + 2.4) * 4), 2)


def _shape_regen(s, col, fr):
    cx = sl.CX
    pts = [(cx, cx - 8), (cx + 7, cx - 1), (cx, cx + 8), (cx - 7, cx - 1)]
    pygame.draw.polygon(s, col, pts)
    pygame.draw.polygon(s, sl.WHITE, pts, 2)


_RUNE_VARIANTS = [
    ("rune_haste", (250, 220, 90), (230, 200, 60), _shape_haste),
    ("rune_double_damage", (240, 90, 90), (220, 60, 60), _shape_double_damage),
    ("rune_cdr_50", (110, 170, 240), (80, 140, 220), _shape_cdr),
    ("rune_regen_10x", (140, 220, 130), (100, 190, 100), _shape_regen),
]


def _rune_variant(key, base_col, glow_col, shape_fn) -> int:
    n = 0
    for fr in (0, 1):
        s = sl.surf()
        sl.glow(s, sl.CX, sl.CX, 12 + fr, glow_col, alpha=130)
        shape_fn(s, base_col, fr)
        sl.save(s, "entities", key, f"idle_{fr}")
        n += 1
    return n


def main() -> int:
    n = 0
    n += _chibi_minion("minion_melee_t1", T1_MELEE_PAL, overlay=_human_melee_overlay)
    n += _chibi_minion("minion_melee_t2", T2_MELEE_PAL, overlay=_ghoul_overlay)
    n += _chibi_minion("minion_ranged_t1", T1_RANGED_PAL, overlay=_human_ranged_overlay)
    n += _chibi_minion("minion_ranged_t2", T2_RANGED_PAL, overlay=_ghoul_overlay)
    n += _cart()
    n += se.emit_creature("minion_neutral", MONSTER_PAL, _monster_body,
                          category="entities")
    for key, base_col, glow_col, shape_fn in _RUNE_VARIANTS:
        n += _rune_variant(key, base_col, glow_col, shape_fn)
    # Towers + core (team-neutral grey; the client tints HP, the sprite reads as
    # a structure). Provide idle / core / dead.
    sl.save(sl.building((150, 150, 165), (90, 90, 105),
                        accent=(220, 220, 235)), "entities", "tower", "idle")
    sl.save(sl.building((150, 150, 165), (90, 90, 105), dead=True),
            "entities", "tower", "dead")
    sl.save(sl.building((170, 160, 120), (110, 100, 70),
                        accent=(255, 240, 180), core=True),
            "entities", "base", "core")
    sl.save(sl.building((170, 160, 120), (110, 100, 70),
                        accent=(255, 240, 180), core=True),
            "entities", "base", "idle")
    sl.save(sl.building((170, 160, 120), (110, 100, 70), dead=True),
            "entities", "base", "dead")
    n += 5
    # Wall + tree capsule segments (tiled along the obstacle by the renderer).
    sl.save(wall_seg(), "entities", "wall", "seg")
    sl.save(tree_seg(), "entities", "tree", "seg")
    n += 2
    return n


if __name__ == "__main__":
    sl.main_guard(main)
