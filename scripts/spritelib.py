"""Shared toolkit for the procedural sprite generators.

These generators draw *placeholder* art with pygame primitives and save PNGs into
the on-disk asset contract the client loads from (see client/assets/README.md).
The renderer never cares HOW a PNG was made, so swapping any of these for real
pixel-art later is a drop-in: just write PNGs with the same paths/sizes/names.

Contract enforced here in one place:
  * 64x64 RGBA, center-anchored (entities/heroes/projectiles/effects).
  * terrain tiles are their own (tileable) sizes under assets/terrain/.
  * animation frames suffixed _0, _1, ...; the loader cycles them.

All public draw helpers take/return a pygame.Surface so generators compose them.
"""

from __future__ import annotations

import math
import os
import random

# Headless: we only rasterize Surfaces, no window/audio needed.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame  # noqa: E402

SIZE = 64
CX = SIZE // 2
FACINGS = ("n", "e", "s", "w")
FPS = 6.0

ASSETS = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "client", "assets")

WHITE = (240, 240, 240)
BLACK = (18, 16, 22)


# ---------------------------------------------------------------------------
# Surfaces + saving
# ---------------------------------------------------------------------------
def surf(size: int = SIZE) -> pygame.Surface:
    return pygame.Surface((size, size), pygame.SRCALPHA)


def _ensure_init() -> None:
    if not pygame.get_init():
        pygame.init()


def save(s: pygame.Surface, *parts: str) -> str:
    """Save `s` to assets/<parts...>.png (last part is the filename stem)."""
    *dirs, stem = parts
    folder = os.path.join(ASSETS, *dirs)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{stem}.png")
    pygame.image.save(s, path)
    return path


def oriented(s: pygame.Surface, facing: str) -> pygame.Surface:
    """West art is the east art mirrored (the loader/contract expects this)."""
    if facing == "w":
        return pygame.transform.flip(s, True, False)
    return s


# ---------------------------------------------------------------------------
# Humanoid body parts (shared silhouette; heroes recolor + accessorize)
# ---------------------------------------------------------------------------
def shadow(s: pygame.Surface) -> None:
    sh = surf()
    pygame.draw.ellipse(sh, (0, 0, 0, 70), (CX - 11, 52, 22, 8))
    s.blit(sh, (0, 0))


def legs(s: pygame.Surface, col, dark) -> None:
    pygame.draw.rect(s, dark, (CX - 7, 40, 5, 15), border_radius=2)
    pygame.draw.rect(s, dark, (CX + 2, 40, 5, 15), border_radius=2)
    pygame.draw.rect(s, col, (CX - 8, 53, 7, 4), border_radius=1)
    pygame.draw.rect(s, col, (CX + 1, 53, 7, 4), border_radius=1)


def torso(s: pygame.Surface, col, dark, w: int = 18, h: int = 20) -> None:
    pygame.draw.ellipse(s, col, (CX - w // 2, 24, w, h))
    pygame.draw.ellipse(s, dark, (CX - w // 2, 24, w, h), 1)


def arms(s: pygame.Surface, skin, action: str, claw=None) -> None:
    """Two arms whose forward reach depends on the action; `claw` adds talons."""
    reach = {"attack": 12, "q": 13, "w": 6, "pounce": 4, "scratch": 14,
             "split_flyer": 9}.get(action, 6)
    drop = 4 if action in ("attack", "q", "scratch") else 0
    for side in (-1, 1):
        hx = CX + side * 8
        ex = CX + side * (6 + reach)
        ey = 30 + drop
        pygame.draw.line(s, skin, (hx, 28), (ex, ey), 3)
        if claw:
            for k in (-2, 0, 2):
                pygame.draw.line(s, claw, (ex, ey), (ex + side * 3, ey + k), 1)


def head(s: pygame.Surface, skin, hair, facing: str, eye=(40, 30, 30)) -> None:
    pygame.draw.circle(s, skin, (CX, 16), 6)
    pygame.draw.polygon(s, hair, [
        (CX - 7, 12), (CX - 8, 25), (CX - 4, 23),
        (CX, 11), (CX + 4, 23), (CX + 8, 25), (CX + 7, 12), (CX, 8)])
    if facing == "n":
        return  # back of head: no face
    pygame.draw.circle(s, eye, (CX - 2, 16), 1)
    pygame.draw.circle(s, eye, (CX + 2, 16), 1)


def body_raw(s: pygame.Surface, pal: dict, action: str, facing: str,
             frame: int, legged: bool = True) -> None:
    """Draw the fighter body onto `s` (no orientation flip). `pal` keys: skin,
    hair, cloth, cloth_dk, claw(optional), eye(optional)."""
    shadow(s)
    if legged:
        legs(s, pal["cloth"], pal["cloth_dk"])
    torso(s, pal["cloth"], pal["cloth_dk"])
    arms(s, pal.get("skin", (200, 180, 160)), action, pal.get("claw"))
    head(s, pal.get("skin", (200, 180, 160)), pal.get("hair", BLACK),
         facing, pal.get("eye", (40, 30, 30)))


def humanoid(pal: dict, action: str, facing: str, frame: int) -> pygame.Surface:
    """A generic recolorable fighter, oriented for `facing`."""
    s = surf()
    body_raw(s, pal, action, facing, frame)
    if action == "move" and frame == 1:
        s.scroll(0, -1)
    return oriented(s, facing)


def portrait(compose, pal: dict, face_fx=None) -> pygame.Surface:
    """A 64x64 hero-select face: the idle head cropped + zoomed into a round
    frame tinted by the hero's cloth colors. ``compose`` is the body builder
    from ``emit_hero`` (so the portrait inherits the hero's overlay/back art —
    fur, wings, etc.); ``face_fx(s)`` optionally adds a signature flourish."""
    body = compose("idle", "s", 0)
    crop = pygame.Rect(CX - 14, 4, 28, 28)
    head_img = pygame.transform.scale(body.subsurface(crop).copy(), (54, 54))
    s = surf()
    bg = pal.get("cloth_dk", (48, 48, 60))
    frame_col = pal.get("cloth", (90, 90, 110))
    pygame.draw.circle(s, (*bg, 255), (CX, CX), 30)
    s.blit(head_img, (CX - 27, CX - 22))
    # Clip the zoomed head to the round frame so it doesn't spill past the rim.
    mask = surf()
    pygame.draw.circle(mask, (255, 255, 255, 255), (CX, CX), 29)
    s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if face_fx:
        face_fx(s)
    pygame.draw.circle(s, frame_col, (CX, CX), 30, 3)
    return s


def emit_hero(hero_id: str, pal: dict, *, back=None, overlay=None,
              skill_fx=None, face_fx=None,
              skill_keys=("q", "w", "e", "r")) -> int:
    """Write the standard hero set: idle/move/attack (4 facings) + a cast
    one-shot per skill key (non-directional, 2 frames) + a `face` portrait for
    hero-select. `skill_keys` defaults to the usual q/w/e/r but a wider kit can
    pass more (e.g. Pedro Penduko's q/w/e/r/t/y/u/i). Hooks layer the hero's
    signature:
      back(s, action, facing, frame)   -> behind the body (e.g. wings)
      overlay(s, action, facing, frame)-> over the body (e.g. fur, glow)
      skill_fx(s, key, frame)          -> the per-skill cast flourish
      face_fx(s)                       -> extra flourish on the select portrait
    Returns the number of PNGs written.
    """
    count = 0

    def compose(action, facing, frame):
        s = surf()
        if back:
            back(s, action, facing, frame)
        body_raw(s, pal, action, facing, frame)
        if overlay:
            overlay(s, action, facing, frame)
        if action == "move" and frame == 1:
            s.scroll(0, -1)
        return oriented(s, facing)

    for facing in FACINGS:
        save(compose("idle", facing, 0), "heroes", hero_id, f"idle_{facing}")
        for fr in (0, 1):
            save(compose("move", facing, fr),
                 "heroes", hero_id, f"move_{facing}_{fr}")
        save(compose("attack", facing, 0), "heroes", hero_id,
             f"attack_{facing}")
        count += 4
    for key in skill_keys:
        for fr in (0, 1):
            s = compose(key, "s", fr)
            if skill_fx:
                skill_fx(s, key, fr)
            save(s, "heroes", hero_id, f"{key}_{fr}")
            count += 1
    save(portrait(compose, pal, face_fx), "heroes", hero_id, "face")
    count += 1
    return count


# ---------------------------------------------------------------------------
# Signature features
# ---------------------------------------------------------------------------
def bat_wing(s: pygame.Surface, side: int, spread: float, col, edge) -> None:
    """A leathery bat wing. side=-1 left/+1 right, spread in [0,1]. Emphasized
    (big, ribbed) for the Manananggal."""
    sx, sy = CX + side * 6, 24
    tipx = CX + side * (14 + spread * 18)
    tipy = 20 - spread * 14
    pts = [
        (sx, sy - 6), (tipx, tipy),
        (CX + side * (12 + spread * 12), sy + 2),
        (CX + side * (10 + spread * 8), sy + 11),
        (CX + side * (7 + spread * 5), sy + 18),
        (sx, sy + 9)]
    pygame.draw.polygon(s, col, pts)
    pygame.draw.polygon(s, edge, pts, 2)
    for fx, fy in (pts[1], pts[2], pts[3], pts[4]):
        pygame.draw.line(s, edge, (sx, sy - 2), (fx, fy), 1)


def fur(s: pygame.Surface, col, n: int = 120, seed: int = 0) -> None:
    """Scatter many short jittered strands over the torso/limbs (Kapre hair)."""
    rng = random.Random(seed)
    for _ in range(n):
        x = rng.randint(CX - 11, CX + 11)
        y = rng.randint(22, 52)
        ang = rng.uniform(0, math.tau)
        ln = rng.randint(2, 5)
        pygame.draw.line(s, col, (x, y),
                         (x + math.cos(ang) * ln, y + math.sin(ang) * ln), 1)


def tongue_strip(s: pygame.Surface, x0, y0, x1, y1) -> None:
    """A fleshy tapered tongue between two points."""
    pygame.draw.line(s, (120, 24, 48), (x0, y0), (x1, y1), 9)
    pygame.draw.line(s, (206, 70, 96), (x0, y0), (x1, y1), 6)
    pygame.draw.line(s, (236, 132, 150), (x0, y0), (x1, y1), 2)
    pygame.draw.circle(s, (210, 80, 104), (int(x1), int(y1)), 5)


# ---------------------------------------------------------------------------
# FX primitives (effects/projectiles)
# ---------------------------------------------------------------------------
def ring(s: pygame.Surface, cx, cy, r, col, width=3, alpha=220) -> None:
    pygame.draw.circle(s, (*col, alpha), (cx, cy), max(1, int(r)), width)


def shockwave(size: int, frac: float, col) -> pygame.Surface:
    """An expanding+fading ring sized to `size`; frac in [0,1] = animation phase."""
    s = surf(size)
    c = size // 2
    r = int((size / 2 - 2) * frac)
    a = int(230 * (1 - frac))
    ring(s, c, c, r, col, width=max(2, int(4 * (1 - frac))), alpha=a)
    ring(s, c, c, int(r * 0.6), col, width=2, alpha=a // 2)
    return s


def glow(s: pygame.Surface, cx, cy, r, col, alpha=120) -> None:
    g = surf(SIZE)
    for i, aa in enumerate((alpha // 3, alpha // 2, alpha)):
        pygame.draw.circle(g, (*col, aa), (cx, cy), int(r * (1 - i * 0.28)))
    s.blit(g, (0, 0))


def spark(size: int, frac: float, col) -> pygame.Surface:
    """A small burst of lines + ring for impact feedback."""
    s = surf(size)
    c = size // 2
    r = int((size / 2 - 2) * (0.3 + 0.7 * frac))
    a = int(230 * (1 - frac))
    for k in range(8):
        ang = k * math.tau / 8
        pygame.draw.line(s, (*col, a), (c, c),
                         (c + math.cos(ang) * r, c + math.sin(ang) * r), 2)
    ring(s, c, c, r, col, width=2, alpha=a)
    return s


# ---------------------------------------------------------------------------
# Generic entity bodies
# ---------------------------------------------------------------------------
def blob(pal_col, dark, r=14, outline=None, eye=True) -> pygame.Surface:
    """A simple rounded creature body (minions/neutrals)."""
    s = surf()
    shadow(s)
    pygame.draw.circle(s, pal_col, (CX, CX), r)
    pygame.draw.circle(s, dark, (CX, CX), r, 2)
    if outline:
        pygame.draw.circle(s, outline, (CX, CX), r + 2, 2)
    if eye:
        pygame.draw.circle(s, WHITE, (CX - 4, CX - 2), 2)
        pygame.draw.circle(s, WHITE, (CX + 4, CX - 2), 2)
        pygame.draw.circle(s, BLACK, (CX - 4, CX - 2), 1)
        pygame.draw.circle(s, BLACK, (CX + 4, CX - 2), 1)
    return s


def building(body, dark, accent=None, core=False, dead=False) -> pygame.Surface:
    """A tower/core sprite: stacked battlement block. 64x64."""
    s = surf()
    shadow(s)
    if dead:
        body, dark, accent = (70, 70, 70), (45, 45, 45), None
    pygame.draw.rect(s, body, (CX - 13, 18, 26, 36), border_radius=4)
    pygame.draw.rect(s, dark, (CX - 13, 18, 26, 36), 2, border_radius=4)
    # battlements
    for bx in (CX - 12, CX - 4, CX + 4):
        pygame.draw.rect(s, body, (bx, 12, 6, 8))
        pygame.draw.rect(s, dark, (bx, 12, 6, 8), 1)
    if dead:
        pygame.draw.line(s, (40, 40, 40), (CX - 10, 24), (CX + 10, 48), 3)
        return s
    if core:
        glow(s, CX, 34, 12, accent or (255, 240, 180), alpha=150)
        pygame.draw.circle(s, accent or WHITE, (CX, 34), 6)
    elif accent:
        pygame.draw.circle(s, accent, (CX, 30), 4)
    return s


def tileable_noise(w, h, base, spots, seed=0) -> pygame.Surface:
    """A flat-color tile speckled with darker/lighter spots (ground/river/lane).
    Spots near the edges are mirrored so the tile stays seamless."""
    rng = random.Random(seed)
    s = pygame.Surface((w, h))
    s.fill(base)
    for _ in range(spots):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        d = rng.randint(-22, 22)
        col = tuple(max(0, min(255, c + d)) for c in base)
        r = rng.randint(1, 3)
        for ox in (0, w, -w):
            pygame.draw.circle(s, col, (x + ox, y), r)
        for oy in (0, h, -h):
            pygame.draw.circle(s, col, (x, y + oy), r)
    return s


def main_guard(fn) -> None:
    """Run a generator's main() with pygame init/quit + a printed summary."""
    _ensure_init()
    try:
        n = fn()
    finally:
        pygame.quit()
    if n is not None:
        print(f"[{fn.__module__}] wrote {n} PNGs")
