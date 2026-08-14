"""Expressive chibi sprite engine — the successor to spritelib's smooth-shape
humanoid and pixelart's blocky pre-upscaled chibi.

Where those two draw flat single-color shapes (optionally nearest-neighbor
upscaled for a chunky pixel look), this module composes every sprite on a 4x
supersampled canvas using cheap inset cel-shading (a soft highlight + a soft
shadow lobe inset into every filled shape) and downsamples with
``pygame.transform.smoothscale``. The box filter in that downsample is what
turns hard-edged supersampled geometry into soft anti-aliased curves and
outlines in the final 64x64 image — a "vector-ish" flat-chibi look (rounded
big-headed proportions, bold clean outlines, mitten hands) instead of a
pixel-art or bare-primitive one.

Reuses spritelib's I/O contract helpers directly (paths, orientation,
portrait cropping, frame-count constants, easing) — that plumbing has nothing
to do with the "shapes stacked on shapes" complaint this engine fixes, so
duplicating it would just be risk for no benefit.

Authoring model mirrors pixelart.py's on purpose (same hook names/signatures:
``head_fn``, ``torso_fn``, ``extra_back``, ``extra_front``, ``hunch``,
``scale``, ``chibi_prop`` anchoring, ``pattern_fill``) so hero scripts port by
swapping which module they draw with, not by relearning an API.

IMPORTANT for hero authors: everything drawn onto the supersampled canvas
(``back``/``body_fn``/``overlay`` hooks) must go through this module's scaled
drawing helpers (``ellipse``/``circle``/``rect``/``poly``/``line``/
``filled_shape``) — never raw ``pygame.draw`` calls — because those helpers
translate base-space (64x64) coordinates onto the 4x canvas. ``skill_fx`` and
``face_fx`` run *after* downsampling, directly on the final 64x64 surface (so
fx read as crisp graphic overlays, not doubly-softened) — there, raw
``pygame.draw``/``spritelib.ring``/``spritelib.glow`` calls with ordinary
64-space coordinates are correct, exactly as in the existing hero scripts.

    uv run python scripts/gen_sprite_pedro.py
"""

from __future__ import annotations

import math
import random

import pygame

import spritelib as sl

# ---------------------------------------------------------------------------
# Canvas + contract passthroughs
# ---------------------------------------------------------------------------
BASE = sl.SIZE                # 64 — the final on-disk sprite size
SS = 4                         # supersample factor for soft AA curves/outlines
CANVAS = BASE * SS             # 256 — internal drawing resolution
CX = BASE / 2.0

FACINGS = sl.FACINGS
IDLE_FRAMES = sl.IDLE_FRAMES
MOVE_FRAMES = sl.MOVE_FRAMES
ATTACK_FRAMES = sl.ATTACK_FRAMES
CAST_FRAMES = sl.CAST_FRAMES
ease_out = sl.ease_out
ease_in = sl.ease_in
ease_in_out = sl.ease_in_out
save = sl.save
oriented = sl.oriented
main_guard = sl.main_guard
portrait = sl.portrait

OUTLINE = (26, 22, 28)
SHOULDER_Y = 29.0


def canvas() -> pygame.Surface:
    return pygame.Surface((CANVAS, CANVAS), pygame.SRCALPHA)


def downsample(s: pygame.Surface) -> pygame.Surface:
    return pygame.transform.smoothscale(s, (BASE, BASE))


def _phase_for(action: str, frame: int) -> float:
    return sl._phase_for(action, frame)


# ---------------------------------------------------------------------------
# Color tone helpers (auto-derive highlight/shadow tones from a base color)
# ---------------------------------------------------------------------------
def _clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))


def lighten(col, amt: float = 0.4):
    r, g, b = col[:3]
    return (_clamp(r + (255 - r) * amt), _clamp(g + (255 - g) * amt),
            _clamp(b + (255 - b) * amt))


def darken(col, amt: float = 0.32):
    r, g, b = col[:3]
    return (_clamp(r * (1 - amt)), _clamp(g * (1 - amt)), _clamp(b * (1 - amt)))


# ---------------------------------------------------------------------------
# Scaled shape drawing — the shading primitive every part is built from
# ---------------------------------------------------------------------------
def _scale_pts(pts):
    return [(x * SS, y * SS) for x, y in pts]


def _scale_rect(r):
    x, y, w, h = r
    return (x * SS, y * SS, w * SS, h * SS)


def _bbox(kind, geom):
    if kind == "poly":
        xs = [p[0] for p in geom]
        ys = [p[1] for p in geom]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    return geom  # ellipse/rect are already (x, y, w, h)


def _fill(s, kind, sgeom, col):
    if kind == "poly":
        if len(sgeom) >= 3:
            pygame.draw.polygon(s, col, sgeom)
    elif kind == "ellipse":
        pygame.draw.ellipse(s, col, sgeom)
    else:  # rect
        x, y, w, h = sgeom
        r = max(1, int(min(w, h) * 0.28))
        pygame.draw.rect(s, col, (x, y, w, h), border_radius=r)


def _stroke(s, kind, sgeom, col, width):
    if kind == "poly":
        if len(sgeom) >= 3:
            pygame.draw.polygon(s, col, sgeom, width)
    elif kind == "ellipse":
        pygame.draw.ellipse(s, col, sgeom, width)
    else:
        x, y, w, h = sgeom
        r = max(1, int(min(w, h) * 0.28))
        pygame.draw.rect(s, col, (x, y, w, h), width, border_radius=r)


def filled_shape(s: pygame.Surface, kind: str, geom, base, *, outline=OUTLINE,
                 ow: float = 2.0, highlight: bool = True, shadow: bool = True,
                 hi=None, sh=None) -> None:
    """Fill+shade+outline `geom` (base-space coords) onto the SS canvas `s`.

    `kind` is "poly" (geom = [(x, y), ...]), "ellipse", or "rect" (geom =
    (x, y, w, h)). Shading is a cheap inset-ellipse highlight (upper-left)
    and shadow (lower-right) rather than a true per-pixel clip — visually
    equivalent to the flat cel-shading in the chibi references and far
    simpler/more robust than masking.
    """
    sgeom = _scale_pts(geom) if kind == "poly" else _scale_rect(geom)
    _fill(s, kind, sgeom, base)
    x, y, w, h = _bbox(kind, geom)
    if highlight and w > 1.5 and h > 1.5:
        hc = hi or lighten(base, 0.45)
        hr = (x + w * 0.14, y + h * 0.08, w * 0.5, h * 0.36)
        pygame.draw.ellipse(s, (*hc[:3], 125), _scale_rect(hr))
    if shadow and w > 1.5 and h > 1.5:
        sc = sh or darken(base, 0.32)
        sr = (x + w * 0.26, y + h * 0.52, w * 0.62, h * 0.4)
        pygame.draw.ellipse(s, (*sc[:3], 100), _scale_rect(sr))
    if outline:
        _stroke(s, kind, sgeom, outline, max(1, int(round(ow * SS))))


def ellipse(s, col, rc, outline=OUTLINE, ow: float = 2.0, **kw) -> None:
    filled_shape(s, "ellipse", rc, col, outline=outline, ow=ow, **kw)


def circle(s, col, center, r, outline=OUTLINE, ow: float = 2.0, **kw) -> None:
    cx, cy = center
    filled_shape(s, "ellipse", (cx - r, cy - r, 2 * r, 2 * r), col,
                outline=outline, ow=ow, **kw)


def rect(s, col, rc, outline=OUTLINE, ow: float = 2.0, **kw) -> None:
    filled_shape(s, "rect", rc, col, outline=outline, ow=ow, **kw)


def poly(s, col, pts, outline=OUTLINE, ow: float = 2.0, **kw) -> None:
    filled_shape(s, "poly", pts, col, outline=outline, ow=ow, **kw)


def line(s, col, p0, p1, width: float = 1.4) -> None:
    pygame.draw.line(s, col, (p0[0] * SS, p0[1] * SS), (p1[0] * SS, p1[1] * SS),
                     max(1, int(round(width * SS))))


def dot(s, col, center, r) -> None:
    """A tiny unshaded/unoutlined accent (pupils, buttons, ...)."""
    circle(s, col, center, r, outline=None, highlight=False, shadow=False)


def capsule_pts(x0, y0, x1, y1, w0, w1=None):
    """A tapered thick "line" polygon — used for shaded limbs/props instead
    of a bare `pygame.draw.line` (which can't be cel-shaded)."""
    if w1 is None:
        w1 = w0
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    return [
        (x0 + nx * w0 / 2, y0 + ny * w0 / 2),
        (x1 + nx * w1 / 2, y1 + ny * w1 / 2),
        (x1 - nx * w1 / 2, y1 - ny * w1 / 2),
        (x0 - nx * w0 / 2, y0 - ny * w0 / 2),
    ]


# ---------------------------------------------------------------------------
# Pattern fills (checkerboard, ...) — for costumes like Lastikman's
# ---------------------------------------------------------------------------
def pattern_fill(s, rc, colors, *, cell: float = 3.0, outline=OUTLINE,
                 ow: float = 2.0) -> None:
    """Fill `rc` (base-space x, y, w, h) with a checkerboard instead of a
    flat color, still cel-shaded/outlined like any other part. Cells are
    keyed off absolute canvas coordinates so the pattern stays stable across
    `oriented()`'s horizontal mirror for the "w" facing."""
    x0, y0, w, h = _scale_rect(rc)
    c0, c1 = colors
    cell_px = max(1, int(round(cell * SS)))
    x0i, y0i = int(round(x0)), int(round(y0))
    for yy in range(y0i, y0i + int(round(h)), cell_px):
        for xx in range(x0i, x0i + int(round(w)), cell_px):
            col = c0 if ((xx // cell_px) + (yy // cell_px)) % 2 == 0 else c1
            pygame.draw.rect(s, col, (xx, yy, cell_px, cell_px))
    bx, by, bw, bh = x0, y0, w, h
    if outline:
        r = max(1, int(min(bw, bh) * 0.28))
        pygame.draw.rect(s, outline, (bx, by, bw, bh),
                         max(1, int(round(ow * SS))), border_radius=r)


def chibi_torso_patterned(s, action, facing, frame, lean, bob, *, colors,
                          cell: float = 3.0, w: float = 16.0, h: float = 15.0,
                          outline=None) -> None:
    """A `torso_fn`-compatible drop-in that fills the torso with a pattern
    (e.g. Lastikman's checkerboard) instead of `chibi_torso`'s flat color."""
    x = CX - w / 2 + lean
    y = 22 + bob
    pattern_fill(s, (x, y, w, h), colors, cell=cell,
                outline=outline if outline is not None else colors[1])


# ---------------------------------------------------------------------------
# Ground shadow
# ---------------------------------------------------------------------------
def shadow(s: pygame.Surface, *, scale: float = 1.0) -> None:
    sh = canvas()
    w, h = 22 * scale, 7
    pygame.draw.ellipse(sh, (0, 0, 0, 75),
                        _scale_rect((CX - w / 2, 53, w, h)))
    s.blit(sh, (0, 0))


# ---------------------------------------------------------------------------
# Chibi humanoid parts — same hook contract as pixelart.chibi_body_raw
# ---------------------------------------------------------------------------
_ARM_PEAK = {"attack": 9.0, "q": 10.0, "w": 6.0, "pounce": 5.0, "scratch": 10.0}


def chibi_hand_points(action: str, phase: float, *, scale: float = 1.0,
                      side_offset: float = 7.0, hang: float = 9.0):
    """Where each hand is for this action/phase — the single source of truth
    `chibi_arms` and `chibi_prop` both read from. Idle/move keep the arms
    resting near the sides (hanging below the shoulder); an attack/cast
    raises the arm up and out in a windup -> strike -> recover arc."""
    if action == "idle":
        out = side_offset + 0.7 * ease_in_out(phase)
        down = hang + 0.8 * ease_in_out(phase)
    elif action == "move":
        out = side_offset + 1.3 * math.sin(phase * math.tau)
        down = hang - 3.2 * abs(math.sin(phase * math.tau))
    else:
        peak = _ARM_PEAK.get(action, 6.0)
        windup, strike, recover = 0.3, 1.0, 0.6
        if phase <= 0.5:
            k = windup + (strike - windup) * ease_out(phase / 0.5)
        else:
            k = strike + (recover - strike) * ease_out((phase - 0.5) / 0.5)
        out = side_offset + peak * k
        down = hang - peak * k * 0.75
    out *= scale
    down *= scale
    pts = []
    for side in (-1, 1):
        ex = CX + side * out
        ey = SHOULDER_Y + down
        pts.append((ex, ey))
    return pts[0], pts[1]


def chibi_mouth_point(facing: str, *, cy: float = 15.0, r: float = 11.0):
    ox = {"e": r * 0.4, "w": -r * 0.4}.get(facing, 0.0)
    return (CX + ox, cy + r * 0.45)


_SHOULDER_OFFSET = 8.0


def chibi_arms(s, skin, action: str, claw=None, *, phase: float = 0.0,
               scale: float = 1.0) -> None:
    (lx, ly), (rx, ry) = chibi_hand_points(action, phase, scale=scale)
    for side, (ex, ey) in ((-1, (lx, ly)), (1, (rx, ry))):
        hx = CX + side * _SHOULDER_OFFSET * scale
        hy = SHOULDER_Y - 1 * scale
        w0 = 6.0 * scale
        poly(s, skin, capsule_pts(hx, hy, ex, ey, w0, w0 * 0.82), ow=1.6)
        circle(s, skin, (ex, ey), w0 * 0.5, ow=1.4)
        if claw:
            for k in (-2.2, 0, 2.2):
                line(s, claw, (ex, ey), (ex + side * 3.4 * scale, ey + k * scale), 1.0)


def chibi_legs(s, col, dark, phase: float = 0.0, *, scale: float = 1.0) -> None:
    swing = 2.6 * scale * math.sin(phase * math.tau)
    hip_y = 37.0 * scale
    foot_y = 48.0 * scale
    for side, off in ((-1, swing), (1, -swing)):
        lift = max(0.0, off) * 0.5
        ox = off * 0.5
        hip_x = CX + side * 4.0 * scale + ox
        w0 = 6.0 * scale
        poly(s, dark, capsule_pts(hip_x, hip_y, hip_x, foot_y - lift, w0),
             ow=1.6)
        ellipse(s, col, (hip_x - w0 * 0.55, foot_y - lift - 2, w0 * 1.1, 4.5),
                highlight=False)


def chibi_torso(s, col, dark, w: float = 17.0, h: float = 15.0,
                lean: float = 0.0, bob: float = 0.0) -> None:
    x = CX - w / 2 + lean
    y = 22 + bob
    rect(s, col, (x, y, w, h), sh=dark)


_HAIR_SPIKES = [
    (-11, -1), (-11, -11), (-5, -5), (-2, -14), (0, -5),
    (2, -14), (5, -5), (11, -11), (11, -1)]


def chibi_head(s, skin, hair, facing: str, eye=(40, 30, 30), *, r: float = 11.0,
              hair_fn=None, face_fn=None) -> None:
    cy = 15.0
    k = r / 11.0
    circle(s, skin, (CX, cy), r)
    if hair_fn:
        hair_fn(s, skin, hair, facing)
    else:
        spikes = [(CX + dx * k, cy + dy * k) for dx, dy in _HAIR_SPIKES]
        poly(s, hair, spikes, hi=lighten(hair, 0.35))
    if facing == "n":
        return
    dot(s, eye, (CX - 4.5 * k, cy), 1.6 * k)
    dot(s, eye, (CX + 4.5 * k, cy), 1.6 * k)
    if face_fn:
        face_fn(s, skin, facing)


def chibi_prop(s, action: str, facing: str, phase: float, side: int, draw_fn,
              *, hide_facings: tuple = (), anchor: str = "hand",
              scale: float = 1.0) -> None:
    """Draw a held/mouth-anchored prop (staff, cigar, quill, ...).

    `draw_fn(s, x, y, angle)` draws the hero-specific prop shape in
    base-space; this supplies the anchor point (tracking the hand pose) and a
    natural tilt angle, so hero scripts don't reimplement arm trig."""
    if facing in hide_facings:
        return
    if anchor == "mouth":
        x, y = chibi_mouth_point(facing)
        angle = 0.0
    else:
        (lx, ly), (rx, ry) = chibi_hand_points(action, phase, scale=scale)
        x, y = (lx, ly) if side < 0 else (rx, ry)
        shoulder_x = CX + side * _SHOULDER_OFFSET * scale
        angle = math.atan2(y - (SHOULDER_Y - 1 * scale), x - shoulder_x)
    draw_fn(s, x, y, angle)


def chibi_body_raw(s: pygame.Surface, pal: dict, action: str, facing: str,
                   frame: int, legged: bool = True, *, head_fn=None,
                   torso_fn=None, extra_back=None, extra_front=None,
                   hunch: float = 0.0, scale: float = 1.0) -> None:
    """Draw the chibi fighter body onto `s` (SS canvas, no orientation flip).

    Silhouette-override hooks (all default None/0.0/1.0, preserving the base
    chibi look exactly): `head_fn(s, pal, facing)` and
    `torso_fn(s, pal, action, facing, frame, lean, bob)` replace the default
    head/torso draws; `extra_back`/`extra_front(s, action, facing, frame)`
    draw before/after the whole body; `hunch` stoops the posture; `scale`
    grows the default head/torso/limbs proportionally (a "giant" chibi)
    without touching the 64x64 canvas contract."""
    phase = _phase_for(action, frame)
    shadow(s, scale=scale)
    if extra_back:
        extra_back(s, action, facing, frame)
    if legged:
        chibi_legs(s, pal["cloth"], pal["cloth_dk"],
                  phase if action == "move" else 0.0, scale=scale)
    lean = bob = 0.0
    if action == "move":
        lean = 1.4 * math.sin(phase * math.tau)
        bob = 1.4 * (1.0 - math.cos(phase * 2 * math.tau)) / 2.0
    elif action == "idle":
        bob = -0.9 * ease_in_out(phase)
    bob += hunch
    if torso_fn:
        torso_fn(s, pal, action, facing, frame, lean, bob)
    else:
        chibi_torso(s, pal["cloth"], pal["cloth_dk"],
                   w=17.0 * scale, h=15.0 * scale, lean=lean, bob=bob)
    chibi_arms(s, pal.get("skin", (200, 180, 160)), action, pal.get("claw"),
              phase=phase, scale=scale)
    if head_fn:
        head_fn(s, pal, facing)
    else:
        chibi_head(s, pal.get("skin", (200, 180, 160)), pal.get("hair", sl.BLACK),
                  facing, pal.get("eye", (40, 30, 30)), r=11.0 * scale)
    if extra_front:
        extra_front(s, action, facing, frame)


# ---------------------------------------------------------------------------
# Non-humanoid quadruped/creature body (Aswang shapeshift forms)
# ---------------------------------------------------------------------------
def beast_shadow(s: pygame.Surface) -> None:
    sh = canvas()
    pygame.draw.ellipse(sh, (0, 0, 0, 75), _scale_rect((CX - 16, 52, 32, 7)))
    s.blit(sh, (0, 0))


def beast_body(s: pygame.Surface, pal: dict, action: str, facing: str,
              frame: int, *, features=()) -> None:
    """A quadruped silhouette: body barrel, 4 legs, head at the front, a stub
    tail. `facing` "e"/"w" draw a side profile (w mirrored by `oriented()` at
    compose time); "s"/"n" draw a toward/away-from-camera view. `features` is
    an ordered list of `(s, action, facing, frame)` hooks stacking
    beast-specific traits (ears, tusks, wings, ...) onto this base shape."""
    phase = _phase_for(action, frame)
    beast_shadow(s)
    body_col = pal.get("cloth", (110, 90, 70))
    body_dk = pal.get("cloth_dk", (70, 56, 44))
    side = facing in ("e", "w")
    swing = 4.5 * math.sin(phase * math.tau) if action == "move" else 0.0
    for lx, ly, sign in ((-10, -6, 1), (-10, 6, -1), (10, -6, -1), (10, 6, 1)):
        off = swing * sign
        lift = max(0.0, off) * 0.4
        bx, by = CX + lx, 32 + ly
        poly(s, body_dk, capsule_pts(bx, by - lift, bx, 50 - lift, 5.5), ow=1.4)
    if side:
        ellipse(s, body_col, (CX - 15, 21, 30, 19))
        poly(s, body_dk,
             [(CX - 16, 27), (CX - 25, 18), (CX - 21, 31)], ow=1.4)
        hx = CX + 15
        circle(s, body_col, (hx, 24), 9)
        dot(s, pal.get("eye", (20, 20, 20)), (hx + 3.5, 22), 1.6)
    elif facing == "s":  # toward the camera
        ellipse(s, body_col, (CX - 13, 19, 26, 22))
        circle(s, body_col, (CX, 17), 11)
        eye_col = pal.get("eye", (20, 20, 20))
        dot(s, eye_col, (CX - 5, 15), 1.6)
        dot(s, eye_col, (CX + 5, 15), 1.6)
    else:  # "n" — away from the camera, no face
        ellipse(s, body_col, (CX - 13, 19, 26, 22))
        circle(s, body_col, (CX, 16), 11)
    for fn in features:
        fn(s, action, facing, frame)


def dog_beast_features(s, action, facing, frame) -> None:
    """Pointed ears + a bushy silhouette — Dog Shapeshift."""
    col, dark = (94, 70, 52), (60, 46, 34)
    side = facing in ("e", "w")
    if side:
        hx = CX + 15
        for ex in (hx - 2, hx + 5):
            poly(s, col, [(ex - 3, 20), (ex + 2, 6), (ex + 5, 18)], sh=dark)
        poly(s, col, [(CX - 18, 18), (CX - 27, 6), (CX - 21, 23)], sh=dark)
    else:
        for sxo in (-7, 7):
            poly(s, col,
                 [(CX + sxo - 3, 10), (CX + sxo, -2), (CX + sxo + 3, 10)], sh=dark)


def boar_beast_features(s, action, facing, frame) -> None:
    """Curved tusks — Boar Shapeshift."""
    tusk, tusk_dk = sl.WHITE, (190, 186, 178)
    if facing in ("e", "w"):
        hx = CX + 15
        for sign in (-1, 1):
            tx, ty = hx + 4, 27 + sign * 2
            poly(s, tusk, [(tx, ty), (tx + 5, ty - 3 * sign), (tx + 2, ty + 3 * sign)],
                 sh=tusk_dk, highlight=False)
    else:
        for sxo in (-6, 6):
            tip = sxo + (2 if sxo > 0 else -2)
            poly(s, tusk,
                 [(CX + sxo, 24), (CX + tip, 29), (CX + sxo, 27)],
                 sh=tusk_dk, highlight=False)


def bat_beast_features(s, action, facing, frame) -> None:
    """Small leathery wings + pointed ears — Bat Shapeshift."""
    spread = 0.5 if action == "idle" else 0.8
    wing_col, wing_edge = (46, 30, 40), (90, 60, 74)
    for side in (-1, 1):
        sx, sy = CX + side * 6, 22
        tipx = CX + side * (13 + spread * 16)
        tipy = 18 - spread * 12
        pts = [(sx, sy - 5), (tipx, tipy),
               (CX + side * (11 + spread * 11), sy + 2),
               (CX + side * (9 + spread * 7), sy + 9),
               (sx, sy + 7)]
        poly(s, wing_col, pts, sh=wing_edge, highlight=False)
    ear_col, ear_dk = (40, 30, 36), (60, 46, 54)
    for side in (-1, 1):
        bx = CX + side * 9
        poly(s, ear_col, [(bx, 14), (bx + side * 5, 3), (bx + side, 15)],
             sh=ear_dk, highlight=False)


def monster_beast_features(s, action, facing, frame) -> None:
    """Jagged spine ridges + small horns + bared fangs — generic jungle
    neutral-camp monster (distinct from the dog/boar/bat beast forms)."""
    ridge, ridge_dk = (70, 40, 46), (44, 24, 28)
    horn = (228, 218, 198)
    if facing in ("e", "w"):
        bx0 = CX - 15
        for i in range(4):
            rx = bx0 + i * 7
            poly(s, ridge, [(rx, 19), (rx + 3, 10), (rx + 6, 19)],
                 sh=ridge_dk, highlight=False)
        hx = CX + 15
        for sign in (-1, 1):
            poly(s, horn,
                 [(hx + 1, 18 + sign * 2), (hx + 7, 13 + sign * 5),
                  (hx + 3, 20 + sign * 2)], highlight=False)
        poly(s, sl.WHITE, [(hx + 5, 27), (hx + 8, 27), (hx + 6.5, 32)],
             highlight=False)
    else:
        for sxo in (-9, -3, 3, 9):
            poly(s, ridge, [(CX + sxo - 2, 10), (CX + sxo, 2), (CX + sxo + 2, 10)],
                 sh=ridge_dk, highlight=False)
        for sxo in (-6, 6):
            poly(s, sl.WHITE,
                 [(CX + sxo - 2, 24), (CX + sxo + 2, 24), (CX + sxo, 29)],
                 highlight=False)


# ---------------------------------------------------------------------------
# Small creature body (worm summons, ...) — kept parity with pixelart.py
# ---------------------------------------------------------------------------
def worm_body(s: pygame.Surface, pal: dict, action: str, frame: int,
             facing: str = "s") -> None:
    phase = _phase_for(action, frame)
    sh = canvas()
    pygame.draw.ellipse(sh, (0, 0, 0, 75), _scale_rect((CX - 11, 46, 22, 7)))
    s.blit(sh, (0, 0))
    body_col = pal.get("cloth", (110, 150, 70))
    dark = pal.get("cloth_dk", (70, 100, 44))
    eye = pal.get("eye", (20, 20, 20))
    wiggle = 3.5 * math.sin(phase * math.tau) if action == "move" else 0.0
    n = 4
    hx = hy = CX
    for i in range(n):
        t = i / (n - 1)
        dx = -14 + i * 9 + wiggle * math.sin(t * math.pi + phase * math.tau)
        dy = 3.0 * math.sin(t * math.tau + phase * math.tau) if action == "move" else 0.0
        r = 8 if i == n - 1 else 6.5
        cx, cy = CX + dx, 36 + dy
        circle(s, body_col if i % 2 == 0 else dark, (cx, cy), r, ow=1.4)
        if i == n - 1:
            hx, hy = cx, cy
    dot(s, eye, (hx - 3, hy - 2), 1.6)
    dot(s, eye, (hx + 3, hy - 2), 1.6)


def emit_creature(key: str, pal: dict, body_fn, *, category: str = "entities",
                  facings=FACINGS, move_frames: int = 2) -> int:
    """No facing-dependent cast poses, no `face` portrait — small non-hero
    creatures. Writes `idle_<facing>` + `move_<facing>_0..n`."""
    count = 0

    def compose(action, facing, frame):
        s = canvas()
        body_fn(s, pal, action, frame, facing=facing)
        return oriented(downsample(s), facing)

    for facing in facings:
        save(compose("idle", facing, 0), category, key, f"idle_{facing}")
        count += 1
        for fr in range(move_frames):
            save(compose("move", facing, fr), category, key, f"move_{facing}_{fr}")
            count += 1
    return count


# ---------------------------------------------------------------------------
# emit_hero — same output contract as spritelib.emit_hero/pixelart.emit_pixel_hero
# ---------------------------------------------------------------------------
def emit_hero(hero_id: str, pal: dict, *, body_fn=chibi_body_raw, back=None,
             overlay=None, skill_fx=None, face_fx=None,
             skill_keys=("q", "w", "e", "r")) -> int:
    """Write the standard hero set: idle/move/attack (4 facings) + a cast
    one-shot per skill key (non-directional, CAST_FRAMES frames) + a `face`
    portrait. Body composes on the SS canvas and downsamples before
    `skill_fx` is layered on, so fx read as a crisp overlay. Hooks:
      back(s, action, facing, frame)    -> before the body (wings, ...)
      body_fn(s, pal, action, facing, frame) -> the body itself
      overlay(s, action, facing, frame) -> after the body, still on the SS
                                            canvas (fur, glow, held props)
      skill_fx(s, key, frame)           -> post-downsample cast flourish
      face_fx(s)                        -> extra flourish on the portrait
    """
    count = 0

    def compose(action, facing, frame):
        s = canvas()
        if back:
            back(s, action, facing, frame)
        body_fn(s, pal, action, facing, frame)
        if overlay:
            overlay(s, action, facing, frame)
        return oriented(downsample(s), facing)

    for facing in FACINGS:
        for fr in range(IDLE_FRAMES):
            save(compose("idle", facing, fr), "heroes", hero_id, f"idle_{facing}_{fr}")
        for fr in range(MOVE_FRAMES):
            save(compose("move", facing, fr), "heroes", hero_id, f"move_{facing}_{fr}")
        for fr in range(ATTACK_FRAMES):
            save(compose("attack", facing, fr), "heroes", hero_id, f"attack_{facing}_{fr}")
        count += IDLE_FRAMES + MOVE_FRAMES + ATTACK_FRAMES
    for key in skill_keys:
        for fr in range(CAST_FRAMES):
            s = compose(key, "s", fr)
            if skill_fx:
                skill_fx(s, key, fr)
            save(s, "heroes", hero_id, f"{key}_{fr}")
            count += 1
    save(portrait(compose, pal, face_fx), "heroes", hero_id, "face")
    count += 1
    return count


# ---------------------------------------------------------------------------
# FX helper new to this engine (existing ring/glow/shockwave/spark are
# generic enough to keep using straight from spritelib post-downsample)
# ---------------------------------------------------------------------------
def tint_body(s: pygame.Surface, col, amount: float = 0.35) -> None:
    """Additively tint every already-drawn (non-transparent) pixel toward
    `col` without touching alpha — a cheap masked "rim light"/recolor for
    skill-cast flourishes (BLEND_RGB_ADD ignores alpha on both sides, so
    fully-transparent background pixels stay untouched/invisible while the
    body silhouette lights up). Call from an `overlay` hook, after the body
    is drawn on this SS canvas."""
    tint = pygame.Surface(s.get_size())
    tint.fill(tuple(_clamp(c * amount) for c in col[:3]))
    s.blit(tint, (0, 0), special_flags=pygame.BLEND_RGB_ADD)


def checkered_streak(s, x0, y0, x1, y1, colors, width: float = 6.0,
                     cell: float = 3.0) -> None:
    """A stretched checker-patterned capsule between two 64-space points —
    Lastikman's elongated checkered punches/afterimages. Draws directly on
    the final (post-downsample) 64x64 surface, so coordinates/cells are in
    plain 64-space (no SS scaling here)."""
    c0, c1 = colors
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    steps = max(1, int(length / cell))
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    for i in range(steps):
        t0, t1 = i / steps, (i + 1) / steps
        cx = x0 + dx * (t0 + t1) / 2
        cy = y0 + dy * (t0 + t1) / 2
        col = c0 if i % 2 == 0 else c1
        p0 = (cx - nx * width / 2, cy - ny * width / 2)
        p1 = (cx + nx * width / 2, cy + ny * width / 2)
        p2 = (p1[0] + ux * (length / steps), p1[1] + uy * (length / steps))
        p3 = (p0[0] + ux * (length / steps), p0[1] + uy * (length / steps))
        pygame.draw.polygon(s, col, [p0, p1, p2, p3])
    pygame.draw.line(s, OUTLINE, (x0, y0), (x1, y1), 1)
