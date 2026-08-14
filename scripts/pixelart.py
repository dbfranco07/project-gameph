"""Low-res "Pokemon overworld" pixel-art toolkit — a sibling to spritelib.py.

Where spritelib draws smooth pygame primitives straight onto the final 64x64
canvas, this module draws chibi/creature bodies on a small internal canvas
(``PIXEL_SIZE``) with hard black outlines and flat 2-tone shading, then
upscales with ``pygame.transform.scale`` (nearest-neighbor — no smoothing)
to the 64x64 asset contract. That upscale step is what gives the chunky,
visibly-pixelated GBA/DS look; nothing here does true dithering or an
indexed palette.

Reuses spritelib's surface/save/orientation/animation-phase machinery so the
output still satisfies the same path contract (see client/assets/README.md).
This is the engine's default going forward — beyond the base chibi humanoid
and non-humanoid beast_body, it also offers: held/mouth-anchored props
(chibi_prop), pattern fills (pattern_fill, e.g. checkerboard costumes),
silhouette-override hooks on chibi_body_raw (head_fn/torso_fn/extra_back/
extra_front/hunch/scale) for hats, robes, posture and giant proportions, and
a small-creature body (worm_body) + lightweight emitter (emit_pixel_creature)
for non-hero minions. Heroes not yet ported still use spritelib directly.
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl

SIZE = sl.SIZE
FACINGS = sl.FACINGS
IDLE_FRAMES = sl.IDLE_FRAMES
MOVE_FRAMES = sl.MOVE_FRAMES
ATTACK_FRAMES = sl.ATTACK_FRAMES
CAST_FRAMES = sl.CAST_FRAMES
ease_out = sl.ease_out
ease_in = sl.ease_in
ease_in_out = sl.ease_in_out

PIXEL_SIZE = 32
PIXEL_CX = PIXEL_SIZE // 2

OUTLINE = (12, 10, 14)


# ---------------------------------------------------------------------------
# Low-res canvas + outlined draw helpers
# ---------------------------------------------------------------------------
def pixel_surf() -> pygame.Surface:
    return pygame.Surface((PIXEL_SIZE, PIXEL_SIZE), pygame.SRCALPHA)


def upscale(s: pygame.Surface) -> pygame.Surface:
    """Nearest-neighbor upscale to the 64x64 contract (the chunky-pixel look
    comes from this alone — pygame.transform.scale never smooths)."""
    return pygame.transform.scale(s, (SIZE, SIZE))


def _phase_for(action: str, frame: int) -> float:
    return sl._phase_for(action, frame)


def ellipse(s, col, rect, outline=OUTLINE, ow=1):
    pygame.draw.ellipse(s, col, rect)
    if outline:
        pygame.draw.ellipse(s, outline, rect, ow)


def circle(s, col, center, r, outline=OUTLINE, ow=1):
    pygame.draw.circle(s, col, center, r)
    if outline:
        pygame.draw.circle(s, outline, center, r, ow)


def rect(s, col, rc, outline=OUTLINE, ow=1, border_radius=0):
    pygame.draw.rect(s, col, rc, border_radius=border_radius)
    if outline:
        pygame.draw.rect(s, outline, rc, ow, border_radius=border_radius)


def poly(s, col, pts, outline=OUTLINE, ow=1):
    pygame.draw.polygon(s, col, pts)
    if outline:
        pygame.draw.polygon(s, outline, pts, ow)


# ---------------------------------------------------------------------------
# Chibi humanoid parts (big head, blocky limbs, hard outlines)
# ---------------------------------------------------------------------------
def shadow(s: pygame.Surface) -> None:
    sh = pixel_surf()
    ellipse(sh, (0, 0, 0, 80), (PIXEL_CX - 6, 27, 12, 4), outline=None)
    s.blit(sh, (0, 0))


def chibi_legs(s, col, dark, phase: float = 0.0, *, scale: float = 1.0) -> None:
    swing = 2.0 * scale * math.sin(phase * math.tau)
    for side, off in ((-1, swing), (1, -swing)):
        lift = max(0.0, off) * 0.5
        ox = off * 0.5
        bx = PIXEL_CX + side * 3 * scale + ox
        rect(s, dark, (int(bx - 2 * scale), int(21 - lift),
                       int(4 * scale), int(7 * scale - lift)),
             border_radius=1)
        rect(s, col, (int(bx - 2 * scale), int(26 - lift),
                      int(5 * scale), int(2 * scale)))


def chibi_torso(s, col, dark, w: int = 11, h: int = 9,
                lean: float = 0.0, bob: float = 0.0) -> None:
    x = int(round(PIXEL_CX - w // 2 + lean))
    y = int(round(12 + bob))
    rect(s, col, (x, y, w, h), outline=dark, border_radius=2)


# ---------------------------------------------------------------------------
# Pattern fills (checkerboard, ...) — for costumes like Lastikman's
# ---------------------------------------------------------------------------
def pattern_fill(s, rc, colors, *, cell: int = 3, kind: str = "checker",
                 outline=OUTLINE, ow: int = 1) -> None:
    """Fill `rc` (x, y, w, h) with a tileable pattern instead of a flat color.
    Cells are keyed off the surface's absolute coordinates (not the rect's
    local origin), so the pattern stays stable across `oriented()`'s
    horizontal mirror for the "w" facing."""
    x0, y0, w, h = rc
    c0, c1 = colors
    for yy in range(y0, y0 + h):
        for xx in range(x0, x0 + w):
            if kind == "checker":
                col = c0 if ((xx // cell) + (yy // cell)) % 2 == 0 else c1
            else:
                col = c0
            s.set_at((xx, yy), col)
    if outline:
        pygame.draw.rect(s, outline, rc, ow)


def chibi_torso_patterned(s, action, facing, frame, lean, bob, *, colors,
                          cell: int = 3, w: int = 11, h: int = 9,
                          outline=None) -> None:
    """A `chibi_body_raw(torso_fn=...)` drop-in that fills the torso with a
    pattern (e.g. a checkerboard costume) instead of `chibi_torso`'s flat
    color. `colors` is the (light, dark) pair fed to `pattern_fill`."""
    x = int(round(PIXEL_CX - w // 2 + lean))
    y = int(round(12 + bob))
    pattern_fill(s, (x, y, w, h), colors, cell=cell,
                outline=outline if outline is not None else colors[1])


_ARM_PEAK = {"attack": 7, "q": 8, "w": 4, "pounce": 3, "scratch": 8}


def chibi_hand_points(action: str, phase: float, *, scale: float = 1.0):
    """Where each hand is for this action/phase — the single source of truth
    `chibi_arms` (drawing the limb) and `chibi_prop` (anchoring a held item)
    both read from. Returns ((lx, ly), (rx, ry))."""
    base = 3.0 * scale
    drop = 0.0
    if action == "idle":
        reach = base + 1.0 * scale * ease_in_out(phase)
    elif action == "move":
        reach = base + 1.5 * scale * math.sin(phase * math.tau)
        drop = 1.0 * scale * math.sin(phase * math.tau + math.pi)
    else:
        peak = _ARM_PEAK.get(action, 3.0) * scale
        windup = base * 0.4
        strike = peak * 1.2
        recover = peak * 0.75
        if phase <= 0.5:
            reach = windup + (strike - windup) * ease_out(phase / 0.5)
        else:
            reach = strike + (recover - strike) * ease_out((phase - 0.5) / 0.5)
        if action in ("attack", "q", "scratch"):
            drop = 2.0 * scale * min(1.0, phase / 0.5 + 0.3)
    pts = []
    for side in (-1, 1):
        ex = PIXEL_CX + side * (3 * scale + reach)
        ey = 15 + drop
        pts.append((ex, ey))
    return pts[0], pts[1]


def chibi_mouth_point(facing: str, *, cy: int = 8, r: int = 7):
    """A mouth-anchored point (for mouth-held props like a cigar), scaled to
    the head's own cy/r so a bigger `chibi_head(r=...)` moves it to match."""
    ox = {"e": r * 0.4, "w": -r * 0.4}.get(facing, 0.0)
    return (PIXEL_CX + ox, cy + r * 0.5)


def chibi_arms(s, skin, action: str, claw=None, *, phase: float = 0.0,
               scale: float = 1.0) -> None:
    (lx, ly), (rx, ry) = chibi_hand_points(action, phase, scale=scale)
    for side, (ex, ey) in ((-1, (lx, ly)), (1, (rx, ry))):
        hx = int(round(PIXEL_CX + side * 4 * scale))
        ex, ey = int(round(ex)), int(round(ey))
        pygame.draw.line(s, OUTLINE, (hx, 14), (ex, ey), 3)
        pygame.draw.line(s, skin, (hx, 14), (ex, ey), 2)
        if claw:
            for k in (-1, 0, 1):
                pygame.draw.line(s, claw, (ex, ey), (ex + side, ey + k), 1)


def chibi_prop(s, action: str, facing: str, phase: float, side: int, draw_fn,
              *, hide_facings: tuple = (), anchor: str = "hand",
              scale: float = 1.0) -> None:
    """Draw a held/mouth-anchored prop (staff, cigar, quill, ...).

    `draw_fn(s, x, y, angle)` draws the hero-specific prop shape; this just
    supplies the anchor point (tracking the hand pose across idle/move/attack/
    cast) and a natural tilt angle, so hero scripts don't reimplement arm
    trig. `anchor="mouth"` uses `chibi_mouth_point` instead (angle is 0)."""
    if facing in hide_facings:
        return
    if anchor == "mouth":
        x, y = chibi_mouth_point(facing)
        angle = 0.0
    else:
        (lx, ly), (rx, ry) = chibi_hand_points(action, phase, scale=scale)
        x, y = (lx, ly) if side < 0 else (rx, ry)
        shoulder_x = PIXEL_CX + side * 4 * scale
        angle = math.atan2(y - 14, x - shoulder_x)
    draw_fn(s, x, y, angle)


def chibi_head(s, skin, hair, facing: str, eye=(40, 30, 30), *, r: int = 7,
              hair_fn=None, face_fn=None) -> None:
    cy = 8
    circle(s, skin, (PIXEL_CX, cy), r)
    k = r / 7.0
    if hair_fn:
        hair_fn(s, skin, hair, facing)
    else:
        base_spikes = [(-8, -2), (-8, -8), (-4, -4), (-2, -10), (0, -4),
                       (2, -10), (4, -4), (8, -8), (8, -2)]
        spikes = [(PIXEL_CX + dx * k, cy + dy * k) for dx, dy in base_spikes]
        poly(s, hair, spikes)
    if facing == "n":
        return
    circle(s, eye, (int(round(PIXEL_CX - 3 * k)), cy), 1, outline=None)
    circle(s, eye, (int(round(PIXEL_CX + 3 * k)), cy), 1, outline=None)
    if face_fn:
        face_fn(s, skin, facing)


def chibi_body_raw(s: pygame.Surface, pal: dict, action: str, facing: str,
                   frame: int, legged: bool = True, *, head_fn=None,
                   torso_fn=None, extra_back=None, extra_front=None,
                   hunch: float = 0.0, scale: float = 1.0) -> None:
    """Draw the chibi fighter body onto `s` (32x32, no orientation flip).
    Mirrors spritelib.body_raw's signature/pal keys.

    Silhouette-override hooks (all default None/0.0/1.0, preserving the base
    chibi look exactly): `head_fn(s, pal, facing)` and
    `torso_fn(s, pal, action, facing, frame, lean, bob)` replace the default
    head/torso draws (hats, robes, recognizable hair/face...); `extra_back`/
    `extra_front(s, action, facing, frame)` draw before/after the whole body;
    `hunch` stoops the posture; `scale` grows the default head/torso/limbs
    proportionally (for a "giant" chibi) without touching the 64x64 canvas
    contract."""
    phase = _phase_for(action, frame)
    shadow(s)
    if extra_back:
        extra_back(s, action, facing, frame)
    if legged:
        chibi_legs(s, pal["cloth"], pal["cloth_dk"],
                  phase if action == "move" else 0.0, scale=scale)
    lean = bob = 0.0
    if action == "move":
        lean = 1.0 * math.sin(phase * math.tau)
        bob = 1.0 * (1.0 - math.cos(phase * 2 * math.tau)) / 2.0
    elif action == "idle":
        bob = -0.6 * ease_in_out(phase)
    bob += hunch
    if torso_fn:
        torso_fn(s, pal, action, facing, frame, lean, bob)
    else:
        chibi_torso(s, pal["cloth"], pal["cloth_dk"],
                    w=int(round(11 * scale)), h=int(round(9 * scale)),
                    lean=lean, bob=bob)
    chibi_arms(s, pal.get("skin", (200, 180, 160)), action, pal.get("claw"),
              phase=phase, scale=scale)
    if head_fn:
        head_fn(s, pal, facing)
    else:
        chibi_head(s, pal.get("skin", (200, 180, 160)), pal.get("hair", sl.BLACK),
                  facing, pal.get("eye", (40, 30, 30)), r=int(round(7 * scale)))
    if extra_front:
        extra_front(s, action, facing, frame)


# ---------------------------------------------------------------------------
# Non-humanoid quadruped/creature body (Shapeshift beast forms)
# ---------------------------------------------------------------------------
def beast_shadow(s: pygame.Surface) -> None:
    sh = pixel_surf()
    ellipse(sh, (0, 0, 0, 80), (PIXEL_CX - 8, 26, 16, 4), outline=None)
    s.blit(sh, (0, 0))


def beast_body(s: pygame.Surface, pal: dict, action: str, facing: str,
               frame: int, *, features=()) -> None:
    """A quadruped silhouette: body barrel, 4 legs, head at the front, a
    stub tail. `facing` "e"/"w" draw a side profile (w gets mirrored by
    `oriented()` at compose time, same as the humanoid parts); "s"/"n" draw
    a toward-camera / away-from-camera view. `features` is an ordered list
    of `(s, action, facing, frame)` hooks stacking beast-specific traits
    (ears, tusks, wings, ...) onto this base shape."""
    phase = _phase_for(action, frame)
    beast_shadow(s)
    body_col = pal.get("cloth", (110, 90, 70))
    body_dk = pal.get("cloth_dk", (70, 56, 44))
    side = facing in ("e", "w")
    swing = 2.5 * math.sin(phase * math.tau) if action == "move" else 0.0
    for lx, ly, sign in ((-5, -3, 1), (-5, 3, -1), (5, -3, -1), (5, 3, 1)):
        off = swing * sign
        lift = max(0.0, off) * 0.4
        bx, by = PIXEL_CX + lx, 18 + ly
        rect(s, body_dk, (int(bx - 1), int(by - lift), 3, int(7 - lift)),
             border_radius=1)
    if side:
        ellipse(s, body_col, (PIXEL_CX - 8, 12, 16, 10))
        poly(s, body_dk,
             [(PIXEL_CX - 9, 15), (PIXEL_CX - 13, 10), (PIXEL_CX - 11, 17)])
        hx = PIXEL_CX + 8
        circle(s, body_col, (hx, 13), 5)
        circle(s, pal.get("eye", (20, 20, 20)), (hx + 2, 12), 1, outline=None)
    elif facing == "s":  # toward the camera
        ellipse(s, body_col, (PIXEL_CX - 7, 11, 14, 12))
        circle(s, body_col, (PIXEL_CX, 10), 6)
        eye_col = pal.get("eye", (20, 20, 20))
        circle(s, eye_col, (PIXEL_CX - 3, 9), 1, outline=None)
        circle(s, eye_col, (PIXEL_CX + 3, 9), 1, outline=None)
    else:  # "n" — away from the camera, no face
        ellipse(s, body_col, (PIXEL_CX - 7, 11, 14, 12))
        circle(s, body_col, (PIXEL_CX, 9), 6)
    for fn in features:
        fn(s, action, facing, frame)


def dog_beast_features(s, action, facing, frame) -> None:
    """Pointed ears + a bushy tail — Dog Shapeshift."""
    col, dark = (90, 68, 50), (60, 46, 34)
    side = facing in ("e", "w")
    if side:
        hx = PIXEL_CX + 8
        for ex in (hx - 1, hx + 3):
            poly(s, col, [(ex - 2, 11), (ex + 1, 4), (ex + 3, 10)], outline=dark)
        poly(s, col,
             [(PIXEL_CX - 10, 10), (PIXEL_CX - 15, 4), (PIXEL_CX - 12, 13)],
             outline=dark)
    else:
        for sxo in (-4, 4):
            poly(s, col,
                 [(PIXEL_CX + sxo - 2, 6), (PIXEL_CX + sxo, 0),
                  (PIXEL_CX + sxo + 2, 6)], outline=dark)


def boar_beast_features(s, action, facing, frame) -> None:
    """Curved tusks + a stocky snout — Boar Shapeshift."""
    tusk, tusk_dk = sl.WHITE, (190, 186, 178)
    if facing in ("e", "w"):
        hx = PIXEL_CX + 8
        for sign in (-1, 1):
            tx, ty = hx + 2, 15 + sign
            poly(s, tusk, [(tx, ty), (tx + 3, ty - 2 * sign), (tx + 1, ty + 2 * sign)],
                 outline=tusk_dk)
    else:
        for sxo in (-3, 3):
            tip = sxo + (1 if sxo > 0 else -1)
            poly(s, tusk,
                 [(PIXEL_CX + sxo, 13), (PIXEL_CX + tip, 16), (PIXEL_CX + sxo, 15)],
                 outline=tusk_dk)


def bat_beast_features(s, action, facing, frame) -> None:
    """Small leathery wings + pointed ears — Bat Shapeshift."""
    spread = 0.5 if action == "idle" else 0.8
    wing_col, wing_edge = (46, 30, 40), (90, 60, 74)
    for side in (-1, 1):
        sx, sy = PIXEL_CX + side * 3, 12
        tipx = PIXEL_CX + side * (7 + spread * 9)
        tipy = 10 - spread * 7
        pts = [(sx, sy - 3), (tipx, tipy),
               (PIXEL_CX + side * (6 + spread * 6), sy + 1),
               (PIXEL_CX + side * (5 + spread * 4), sy + 5),
               (sx, sy + 4)]
        poly(s, wing_col, pts, outline=wing_edge)
    ear_col, ear_dk = (40, 30, 36), (60, 46, 54)
    for side in (-1, 1):
        bx = PIXEL_CX + side * 5
        poly(s, ear_col,
             [(bx, 8), (bx + side * 3, 2), (bx + side, 9)], outline=ear_dk)


# ---------------------------------------------------------------------------
# emit_hero equivalent — composes on the low-res canvas, then upscales
# ---------------------------------------------------------------------------
def emit_pixel_hero(hero_id: str, pal: dict, *, body_fn=chibi_body_raw,
                    back=None, overlay=None, skill_fx=None, face_fx=None,
                    skill_keys=("q", "w", "e", "r")) -> int:
    """Same responsibilities/output contract as spritelib.emit_hero, but the
    body is composed on the low-res canvas and upscaled before any skill_fx
    is layered on — fx are drawn directly at 64x64 so they read as a crisp
    graphic overlay rather than a doubly-pixelated one."""
    count = 0

    def compose(action, facing, frame):
        s = pixel_surf()
        if back:
            back(s, action, facing, frame)
        body_fn(s, pal, action, facing, frame)
        if overlay:
            overlay(s, action, facing, frame)
        return sl.oriented(upscale(s), facing)

    for facing in FACINGS:
        for fr in range(IDLE_FRAMES):
            sl.save(compose("idle", facing, fr),
                   "heroes", hero_id, f"idle_{facing}_{fr}")
        for fr in range(MOVE_FRAMES):
            sl.save(compose("move", facing, fr),
                   "heroes", hero_id, f"move_{facing}_{fr}")
        for fr in range(ATTACK_FRAMES):
            sl.save(compose("attack", facing, fr),
                   "heroes", hero_id, f"attack_{facing}_{fr}")
        count += IDLE_FRAMES + MOVE_FRAMES + ATTACK_FRAMES
    for key in skill_keys:
        for fr in range(CAST_FRAMES):
            s = compose(key, "s", fr)
            if skill_fx:
                skill_fx(s, key, fr)
            sl.save(s, "heroes", hero_id, f"{key}_{fr}")
            count += 1
    sl.save(sl.portrait(compose, pal, face_fx), "heroes", hero_id, "face")
    count += 1
    return count


# ---------------------------------------------------------------------------
# Small creature body (worm summons, ...) — not a fork of chibi_body_raw or
# beast_body, since these have no legs/arms/head-with-hat, just a segmented
# body that undulates on `move`.
# ---------------------------------------------------------------------------
def worm_body(s: pygame.Surface, pal: dict, action: str, frame: int,
             facing: str = "s") -> None:
    phase = _phase_for(action, frame)
    sh = pixel_surf()
    ellipse(sh, (0, 0, 0, 80), (PIXEL_CX - 6, 22, 12, 4), outline=None)
    s.blit(sh, (0, 0))
    body_col = pal.get("cloth", (110, 150, 70))
    dark = pal.get("cloth_dk", (70, 100, 44))
    eye = pal.get("eye", (20, 20, 20))
    wiggle = 2.0 * math.sin(phase * math.tau) if action == "move" else 0.0
    n = 4
    hx = hy = PIXEL_CX
    for i in range(n):
        t = i / (n - 1)
        dx = -8 + i * 5 + wiggle * math.sin(t * math.pi + phase * math.tau)
        dy = 2.0 * math.sin(t * math.tau + phase * math.tau) if action == "move" else 0.0
        r = 5 if i == n - 1 else 4
        cx, cy = PIXEL_CX + dx, 18 + dy
        circle(s, body_col if i % 2 == 0 else dark, (int(cx), int(cy)), r)
        if i == n - 1:
            hx, hy = cx, cy
    circle(s, eye, (int(hx - 2), int(hy - 1)), 1, outline=None)
    circle(s, eye, (int(hx + 2), int(hy - 1)), 1, outline=None)


def emit_pixel_creature(key: str, pal: dict, body_fn, *, category: str = "entities",
                        facings=FACINGS, move_frames: int = 2) -> int:
    """A lighter sibling of emit_pixel_hero for small non-hero creatures: no
    facing-dependent cast poses, no `face` portrait. Writes `idle_<facing>` +
    `move_<facing>_0..n`, matching gen_entities.py's `_minion()` naming
    convention exactly so the client's loader needs no changes."""
    count = 0

    def compose(action, facing, frame):
        s = pixel_surf()
        body_fn(s, pal, action, frame, facing=facing)
        return sl.oriented(upscale(s), facing)

    for facing in facings:
        sl.save(compose("idle", facing, 0), category, key, f"idle_{facing}")
        count += 1
        for fr in range(move_frames):
            sl.save(compose("move", facing, fr), category, key, f"move_{facing}_{fr}")
            count += 1
    return count
