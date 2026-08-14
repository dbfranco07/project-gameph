"""Procedural sprites for the Aswang: a shapeshifting devourer.

On sprite_engine's shaded chibi rig now. The base form is a chibi humanoid
with a monstrous overlay (bared fangs on attack, a harder eye-glint); the 7
Shapeshift beast combos (dog/pig/bat and their pairs/triple, see
server/heroes/aswang.py's shapeshift()) use sprite_engine's `beast_body` —
genuinely non-humanoid quadruped bodies instead of a person wearing animal
parts, now with cel-shaded fur/tusks/wings instead of flat outlined shapes.

    uv run python scripts/gen_sprite_aswang.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX

ASWANG_PAL = {
    "skin": (150, 140, 130), "hair": (24, 20, 24),
    "cloth": (72, 40, 46), "cloth_dk": (48, 28, 32),
    "eye": (240, 200, 80), "claw": (232, 230, 224),
}

# Fur tones per beast form; Shapeshift combos blend whichever apply.
_BEAST_FUR = {
    "dog": {"cloth": (120, 92, 68), "cloth_dk": (78, 58, 42)},
    "pig": {"cloth": (150, 128, 108), "cloth_dk": (104, 86, 70)},
    "bat": {"cloth": (58, 40, 52), "cloth_dk": (36, 26, 34)},
}

_BEAST_FEATURES = {
    "dog": se.dog_beast_features,
    "pig": se.boar_beast_features,
    "bat": se.bat_beast_features,
}

# Every beast combo Shapeshift can roll: 3 singles (rank 1), 3 pairs (R2),
# and the full trio (R3) — see server/heroes/aswang.py's shapeshift().
_ASWANG_FORMS = [("dog",), ("pig",), ("bat",),
                 ("dog", "pig"), ("pig", "bat"), ("bat", "dog"),
                 ("dog", "pig", "bat")]


def _combo_pal(combo: tuple[str, ...]) -> dict:
    pal = dict(ASWANG_PAL)
    n = len(combo)
    cloth = [0.0, 0.0, 0.0]
    cloth_dk = [0.0, 0.0, 0.0]
    for beast in combo:
        fur = _BEAST_FUR[beast]
        for i in range(3):
            cloth[i] += fur["cloth"][i] / n
            cloth_dk[i] += fur["cloth_dk"][i] / n
    pal["cloth"] = tuple(int(c) for c in cloth)
    pal["cloth_dk"] = tuple(int(c) for c in cloth_dk)
    return pal


def _variant_key(combo: tuple[str, ...]) -> str:
    return "aswang_" + "+".join(sorted(combo))


def _beast_body_fn(combo: tuple[str, ...]):
    features = [_BEAST_FEATURES[b] for b in combo]

    def body_fn(s, pal, action, facing, frame):
        se.beast_body(s, pal, action, facing, frame, features=features)
    return body_fn


# ---------------------------------------------------------------------------
# Base (unshifted) Aswang: chibi humanoid + monstrous overlay
# ---------------------------------------------------------------------------
def aswang_overlay(s, action, facing, frame):
    """Baseline "more monstrous" juice on the default body: bared fangs on
    the attack swing, a harder glint in the eye."""
    if action == "attack":
        for t in (-3, 3):
            pygame.draw.polygon(s, sl.WHITE,
                                [(CX + t - 1, 18), (CX + t + 1, 18), (CX + t, 21)])
    se.dot(s, (255, 230, 120), (CX - 4.5, 15), 1.0)
    se.dot(s, (255, 230, 120), (CX + 4.5, 15), 1.0)


def _devour_bite(s, frame):
    """A large fang-bite chomping shut across the 3 Devour cast frames —
    open jaws -> fangs bared wide -> snapped shut with an impact burst.
    Runs post-downsample on the final 64x64 surface."""
    cx, cy = CX + 14, 28
    w = 22
    gap = (14, 7, 1)[frame]
    upper_y, lower_y = cy - gap, cy + gap
    pygame.draw.polygon(s, (26, 10, 12), [
        (cx - w // 2, upper_y), (cx + w // 2, upper_y),
        (cx + w // 2, lower_y), (cx - w // 2, lower_y)])
    for jaw_y, sign in ((upper_y, -1), (lower_y, 1)):
        jaw = [(cx - w // 2 - 3, jaw_y + sign * 6),
               (cx + w // 2 + 3, jaw_y + sign * 6),
               (cx + w // 2, jaw_y), (cx - w // 2, jaw_y)]
        pygame.draw.polygon(s, (60, 24, 26), jaw)
        pygame.draw.polygon(s, (20, 10, 10), jaw, 1)
    n_fangs = 5
    for i in range(n_fangs):
        fx = cx - w // 2 + i * (w // (n_fangs - 1))
        pygame.draw.polygon(s, sl.WHITE,
                            [(fx - 2, upper_y), (fx + 2, upper_y), (fx, upper_y + 6)])
        pygame.draw.polygon(s, sl.WHITE,
                            [(fx - 2, lower_y), (fx + 2, lower_y), (fx, lower_y - 6)])
    if frame == 2:
        pygame.draw.circle(s, (170, 30, 36), (cx + 4, cy + 3), 2)
        for ang in (0.3, 1.0, 1.8, 2.6):
            ex = cx + math.cos(ang) * 14
            ey = cy + math.sin(ang) * 14
            pygame.draw.line(s, (230, 230, 230), (cx, cy), (ex, ey), 1)


def aswang_fx(s, key, frame):
    if key == "q":  # Devour: a large fang-bite chomp
        _devour_bite(s, frame)
    elif key == "w":  # Shapeshift: morphing swirl
        for i, col in enumerate(((220, 200, 120), (160, 120, 90),
                                 (110, 150, 110))):
            a = math.radians(frame * 40 + i * 120)
            pygame.draw.arc(s, col, (CX - 16, 14, 32, 32), a, a + 2.0, 3)
    elif key == "e":  # Nightstalker: fang + a blood drop
        pygame.draw.polygon(s, sl.WHITE,
                            [(CX + 8, 16), (CX + 12, 16), (CX + 10, 23)])
        pygame.draw.circle(s, (170, 30, 36), (CX + 10, 27 + frame), 2)
    else:  # r True Aswang: dark winged terror
        sl.glow(s, CX, 30, 18, (120, 30, 40), alpha=130)
        for side in (-1, 1):
            pygame.draw.arc(s, (30, 20, 26),
                            (CX + side * 4 - 14, 18, 28, 22),
                            0.2, 2.9, 3)


def main() -> int:
    n = se.emit_hero("aswang", ASWANG_PAL,
                     skill_fx=aswang_fx, overlay=aswang_overlay)
    for combo in _ASWANG_FORMS:
        n += se.emit_hero(_variant_key(combo), _combo_pal(combo),
                          body_fn=_beast_body_fn(combo), skill_keys=())
    return n


if __name__ == "__main__":
    sl.main_guard(main)
