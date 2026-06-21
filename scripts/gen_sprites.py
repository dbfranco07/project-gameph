"""Generate placeholder hero sprites procedurally with Pygame draw primitives.

This is *not* hand art — it draws stylized flat sprites (shapes + shading) and
saves them as PNGs, so the sprite pipeline can be exercised and judged before
real art exists. Re-run any time to regenerate; drop real PNGs with the same
names (see client/assets/README.md) to replace them.

    uv run python scripts/gen_sprites.py

Currently generates the full Manananggal set (idle / move / attack / pounce /
split flyer + lower body / recombine / death) for facings n/e/s/w.
"""

from __future__ import annotations

import math
import os

# Headless: we only rasterize Surfaces, no window needed.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

SIZE = 64
CX = SIZE // 2

# Palette — a Filipino aswang: pale skin, black hair, maroon dress, bat wings,
# and trailing entrails when the torso detaches.
SKIN = (216, 186, 162)
SKIN_SH = (168, 138, 118)
HAIR = (22, 18, 26)
DRESS = (116, 30, 44)
DRESS_SH = (84, 20, 32)
WING = (52, 30, 40)
WING_EDGE = (96, 54, 66)
GUT = (158, 48, 58)
GUT_DK = (112, 32, 44)
EYE = (220, 70, 60)
WHITE = (240, 240, 240)

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "client", "assets", "heroes", "manananggal",
)


def _surf() -> pygame.Surface:
    return pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)


def _wing(surf, side: int, spread: float) -> None:
    """One leathery bat wing. side=-1 left, +1 right. spread in [0,1]."""
    sx = CX + side * 7
    sy = 26
    tipx = CX + side * (10 + spread * 16)
    tipy = 26 - spread * 12
    midx = CX + side * (8 + spread * 9)
    pts = [
        (sx, sy - 4),
        (tipx, tipy),
        (midx, sy + 2),
        (midx + side * 2, sy + 9),
        (CX + side * 6, sy + 14),
        (sx, sy + 8),
    ]
    pygame.draw.polygon(surf, WING, pts)
    pygame.draw.polygon(surf, WING_EDGE, pts, 1)
    # wing ribs
    for fx, fy in ((tipx, tipy), (midx, sy + 2), (midx + side * 2, sy + 9)):
        pygame.draw.line(surf, WING_EDGE, (sx, sy - 1), (fx, fy), 1)


def _entrails(surf, length: int, frame: int) -> None:
    """Dangling viscera below the torso (the detached-body signature)."""
    y = 40
    x = CX
    for i in range(length):
        nx = CX + int(3.2 * math.sin(i * 0.7 + frame))
        pygame.draw.line(surf, GUT_DK, (x, y), (nx, y + 3), 3)
        x, y = nx, y + 3
    pygame.draw.circle(surf, GUT, (x, y), 3)


def _legs(surf) -> None:
    pygame.draw.rect(surf, DRESS_SH, (CX - 7, 40, 5, 16), border_radius=2)
    pygame.draw.rect(surf, DRESS_SH, (CX + 2, 40, 5, 16), border_radius=2)
    pygame.draw.rect(surf, (40, 30, 30), (CX - 8, 54, 7, 4), border_radius=1)
    pygame.draw.rect(surf, (40, 30, 30), (CX + 1, 54, 7, 4), border_radius=1)


def _torso(surf) -> None:
    pygame.draw.ellipse(surf, DRESS, (CX - 9, 24, 18, 20))
    pygame.draw.ellipse(surf, DRESS_SH, (CX - 9, 24, 18, 20), 1)


def _arms(surf, action: str, facing: str) -> None:
    reach = {"attack": 11, "pounce": 4, "split_flyer": 8}.get(action, 6)
    fwd = 1 if facing in ("e", "s") else -1
    for side in (-1, 1):
        hx = CX + side * 8
        cx2 = CX + side * (6 + reach) * (fwd if side == 1 else 1)
        cy = 30 + (4 if action == "attack" else 0)
        pygame.draw.line(surf, SKIN_SH, (hx, 28), (cx2, cy), 3)
        # claws
        for k in (-2, 0, 2):
            pygame.draw.line(surf, WHITE, (cx2, cy),
                             (cx2 + side * 3, cy + k), 1)


def _head(surf, facing: str) -> None:
    pygame.draw.circle(surf, SKIN, (CX, 16), 6)
    # hair frames the head and falls behind the shoulders
    pygame.draw.polygon(surf, HAIR, [
        (CX - 7, 12), (CX - 8, 26), (CX - 4, 24),
        (CX, 11), (CX + 4, 24), (CX + 8, 26), (CX + 7, 12), (CX, 8),
    ])
    if facing == "n":
        return  # back of the head: hair only, no face
    # glowing aswang eyes + mouth
    pygame.draw.circle(surf, EYE, (CX - 2, 16), 1)
    pygame.draw.circle(surf, EYE, (CX + 2, 16), 1)
    pygame.draw.line(surf, SKIN_SH, (CX - 2, 19), (CX + 2, 19), 1)


def render(action: str, facing: str, frame: int) -> pygame.Surface:
    surf = _surf()
    spread = {
        "idle": 0.25 + 0.1 * frame,
        "move": 0.55 + 0.35 * frame,
        "attack": 0.5,
        "pounce": 0.9,
        "split_flyer": 0.7 + 0.25 * frame,
    }.get(action, 0.3)
    has_legs = action not in ("split_flyer",)
    gut_len = 6 if action == "split_flyer" else (2 if not has_legs else 0)

    _wing(surf, -1, spread)
    _wing(surf, 1, spread)
    _torso(surf)
    _arms(surf, action, facing)
    _head(surf, facing)
    if gut_len:
        _entrails(surf, gut_len, frame)
    if has_legs:
        _legs(surf)

    if facing == "w":
        surf = pygame.transform.flip(surf, True, False)
    return surf


def render_split_body() -> pygame.Surface:
    """The grounded, vulnerable lower half left behind on R Split."""
    surf = _surf()
    # bloody stump at the waist
    pygame.draw.ellipse(surf, GUT, (CX - 8, 22, 16, 8))
    pygame.draw.ellipse(surf, GUT_DK, (CX - 8, 22, 16, 8), 1)
    pygame.draw.rect(surf, DRESS, (CX - 8, 26, 16, 12), border_radius=3)
    _legs(surf)
    return surf


def render_effect(kind: str) -> pygame.Surface:
    surf = _surf()
    if kind == "recombine":
        for r, a in ((16, 60), (11, 120), (6, 200)):
            pygame.draw.circle(surf, (*GUT, a), (CX, CX), r, 3)
    else:  # death
        pygame.draw.circle(surf, (60, 20, 26), (CX, CX), 14)
        pygame.draw.line(surf, (180, 40, 46), (CX - 8, CX - 8),
                         (CX + 8, CX + 8), 3)
        pygame.draw.line(surf, (180, 40, 46), (CX + 8, CX - 8),
                         (CX - 8, CX + 8), 3)
    return surf


def main() -> None:
    pygame.init()
    os.makedirs(OUT_DIR, exist_ok=True)

    facings = ("n", "e", "s", "w")
    count = 0

    def save(surf, name):
        nonlocal count
        pygame.image.save(surf, os.path.join(OUT_DIR, f"{name}.png"))
        count += 1

    for facing in facings:
        save(render("idle", facing, 0), f"idle_{facing}")
        for frame in (0, 1):
            save(render("move", facing, frame), f"move_{facing}_{frame}")
        save(render("attack", facing, 0), f"attack_{facing}")
        save(render("pounce", facing, 0), f"pounce_{facing}")
        for frame in (0, 1):
            save(render("split_flyer", facing, frame),
                 f"split_flyer_{facing}_{frame}")

    save(render_split_body(), "split_body")
    save(render_effect("recombine"), "recombine")
    save(render_effect("death"), "death")

    pygame.quit()
    print(f"[gen_sprites] wrote {count} PNGs to {OUT_DIR}")


if __name__ == "__main__":
    main()
