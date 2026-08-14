"""Ground/cast fx art for named ability effects (`fx=` kwargs on
`skills.area_dmg`/`area_heal` across server/heroes/*.py).

The client's `SpriteManager.effect_frame(name, anim_t)` looks up
`effects/<name>/play_0.png`, `play_1.png`, ... — no code changes are needed to
activate these; `client/renderer.py`'s `_draw_ground_fx` already keys off the
server-sent fx name and falls back to a plain circle only when art is
missing.

    uv run python scripts/gen_effects_ground.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl
import sprite_engine as se

CX = se.CX


def _save2(key: str, frame0: pygame.Surface, frame1: pygame.Surface) -> int:
    sl.save(frame0, "effects", key, "play_0")
    sl.save(frame1, "effects", key, "play_1")
    return 2


# ---------------------------------------------------------------------------
# smash (Kapre) — cracked-earth impact burst
# ---------------------------------------------------------------------------
def _smash(frac: float) -> pygame.Surface:
    s = se.canvas()
    r = 10 + 14 * frac
    a = int(200 * (1 - frac))
    se.filled_shape(s, "ellipse", (CX - r, CX - r * 0.4, r * 2, r * 0.9),
                    (110, 84, 56), outline=None, shadow=False,
                    hi=(150, 118, 80))
    dark = (60, 44, 28)
    for ang in (0.3, 1.1, 2.0, 2.8, 3.6, 4.5, 5.3):
        x1 = CX + math.cos(ang) * r * 1.15
        y1 = CX + math.sin(ang) * r * 0.55
        se.line(s, (*dark, a), (CX, CX), (x1, y1), 2.2)
    for ang in (0.6, 1.8, 3.0, 4.2, 5.4):
        x1 = CX + math.cos(ang) * r * 0.6
        y1 = CX + math.sin(ang) * r * 0.35
        se.circle(s, (90, 68, 44, a), (x1, y1), 2.2 + frac * 1.5, outline=None,
                  highlight=False, shadow=False)
    return se.downsample(s)


# ---------------------------------------------------------------------------
# bolocleave (Bonifacio) — a slashing steel arc
# ---------------------------------------------------------------------------
def _bolocleave(frac: float) -> pygame.Surface:
    s = se.canvas()
    r = 20
    a = int(235 * (1 - frac))
    start = -0.9 - 0.3 * frac
    end = 0.9 + 0.3 * frac
    steps = 18
    pts_out, pts_in = [], []
    for i in range(steps + 1):
        t = start + (end - start) * i / steps
        pts_out.append((CX + math.cos(t) * r, CX + math.sin(t) * r))
        pts_in.append((CX + math.cos(t) * (r - 5), CX + math.sin(t) * (r - 5)))
    poly = pts_out + list(reversed(pts_in))
    if len(poly) >= 3:
        pygame.draw.polygon(s, (235, 235, 245, a), [(x * se.SS, y * se.SS) for x, y in poly])
        pygame.draw.polygon(s, (150, 150, 165, a), [(x * se.SS, y * se.SS) for x, y in poly], int(1.5 * se.SS))
    return se.downsample(s)


# ---------------------------------------------------------------------------
# earthshatter (Brawler) — a big rock/shockwave burst
# ---------------------------------------------------------------------------
def _earthshatter(frac: float) -> pygame.Surface:
    s = sl.surf()
    sl.ring(s, CX, CX, 8 + 20 * frac, (120, 96, 64), width=3, alpha=int(220 * (1 - frac)))
    sl.ring(s, CX, CX, 4 + 12 * frac, (90, 70, 46), width=4, alpha=int(200 * (1 - frac)))
    rng_pts = ((-13, -4), (13, -6), (-8, 10), (10, 9), (0, -14))
    for dx, dy in rng_pts:
        rr = int(2 + 3 * frac)
        cx = CX + int(dx * (0.6 + 0.6 * frac))
        cy = CX + int(dy * (0.6 + 0.6 * frac))
        pygame.draw.circle(s, (76, 58, 38, int(230 * (1 - frac))), (cx, cy), rr)
    return s


# ---------------------------------------------------------------------------
# arrowstorm (Ranger) — falling arrow cluster / impact marks
# ---------------------------------------------------------------------------
def _arrowstorm(frame: int) -> pygame.Surface:
    s = sl.surf()
    rng = ((-14, -16, -8, -2), (2, -18, 8, -1), (-4, -14, -10, 6),
           (10, -16, 4, 4), (-16, -6, -12, 10), (14, -8, 9, 9))
    for i, (x0, y0, x1, y1) in enumerate(rng):
        if frame == 0:
            ex1, ey1 = x0 + (x1 - x0) * 0.4, y0 + (y1 - y0) * 0.4
            pygame.draw.line(s, (70, 54, 34), (CX + x0, CX + y0), (CX + ex1, CX + ey1), 2)
            pygame.draw.circle(s, (200, 190, 170), (CX + int(ex1), CX + int(ey1)), 2)
        else:
            pygame.draw.line(s, (70, 54, 34), (CX + x0 // 2, CX + y0 // 2),
                             (CX + x1, CX + y1), 2)
            pygame.draw.polygon(s, (60, 44, 28), [
                (CX + x1 - 3, CX + y1), (CX + x1 + 3, CX + y1), (CX + x1, CX + y1 - 4)])
            pygame.draw.circle(s, (150, 130, 100, 130), (CX + x1, CX + y1), 3, 1)
    return s


# ---------------------------------------------------------------------------
# sanctuary (Mender) — warm protective glow rings
# ---------------------------------------------------------------------------
def _sanctuary(frac: float) -> pygame.Surface:
    s = sl.surf()
    sl.glow(s, CX, CX, 16 + 6 * frac, (255, 230, 150), alpha=int(150 * (1 - 0.5 * frac)))
    sl.ring(s, CX, CX, 12 + 8 * frac, (255, 245, 210), width=2, alpha=int(210 * (1 - frac)))
    for k in range(6):
        ang = k * math.tau / 6 + frac * 0.6
        x = CX + math.cos(ang) * (14 + 4 * frac)
        y = CX + math.sin(ang) * (14 + 4 * frac)
        pygame.draw.circle(s, (255, 250, 220), (int(x), int(y)), 2)
    return s


# ---------------------------------------------------------------------------
# renewwave (Mender) — an outward healing ripple
# ---------------------------------------------------------------------------
def _renewwave(frac: float) -> pygame.Surface:
    s = sl.surf()
    sl.ring(s, CX, CX, 6 + 18 * frac, (140, 220, 160), width=3, alpha=int(210 * (1 - frac)))
    sl.ring(s, CX, CX, 2 + 10 * frac, (210, 255, 220), width=2, alpha=int(180 * (1 - frac)))
    for k in range(4):
        ang = k * math.tau / 4 + math.pi / 4
        x = CX + math.cos(ang) * (10 + 12 * frac)
        y = CX + math.sin(ang) * (10 + 12 * frac)
        pygame.draw.line(s, (170, 240, 180, int(200 * (1 - frac))),
                         (int(x), int(y - 3)), (int(x), int(y + 3)), 2)
        pygame.draw.line(s, (170, 240, 180, int(200 * (1 - frac))),
                         (int(x - 3), int(y)), (int(x + 3), int(y)), 2)
    return s


# ---------------------------------------------------------------------------
# reform (Rizal) — ink/paper motif
# ---------------------------------------------------------------------------
def _reform(frame: int) -> pygame.Surface:
    s = se.canvas()
    se.rect(s, (245, 238, 218), (CX - 12, CX - 15, 24, 22), outline=(90, 76, 54), ow=1.6)
    lines = 4 if frame == 0 else 5
    for i in range(lines):
        y = CX - 10 + i * 4
        w = 16 if i % 2 == 0 else 12
        se.line(s, (110, 96, 70), (CX - 8, y), (CX - 8 + w, y), 1.2)
    se.circle(s, (40, 30, 20), (CX + 9, CX + 10), 2.2, outline=None, highlight=False, shadow=False)
    return se.downsample(s)


# ---------------------------------------------------------------------------
# decalogue (Mabini) — a stone tablet / law motif
# ---------------------------------------------------------------------------
def _decalogue(frame: int) -> pygame.Surface:
    s = se.canvas()
    se.filled_shape(s, "poly", [
        (CX - 11, CX - 6), (CX - 11, CX + 14), (CX + 11, CX + 14),
        (CX + 11, CX - 6), (CX, CX - 16), (CX - 11, CX - 6)],
        (200, 196, 190), outline=(90, 86, 80), ow=1.6, hi=(226, 224, 220))
    n = 3 if frame == 0 else 4
    for i in range(n):
        y = CX - 2 + i * 4
        se.line(s, (110, 106, 100), (CX - 6, y), (CX + 6, y), 1.4)
    return se.downsample(s)


# ---------------------------------------------------------------------------
# paralysis (Mabini) — crackling restraint energy
# ---------------------------------------------------------------------------
def _paralysis(frame: int) -> pygame.Surface:
    s = sl.surf()
    sl.ring(s, CX, CX, 14, (255, 235, 90), width=2, alpha=190)
    rng = ((0.2, 0.9), (1.4, 2.1), (2.6, 3.3), (3.9, 4.5), (5.0, 5.7))
    for a0, a1 in rng:
        a = a0 if frame == 0 else a1
        x0 = CX + math.cos(a) * 6
        y0 = CX + math.sin(a) * 6
        x1 = CX + math.cos(a) * 16
        y1 = CX + math.sin(a) * 16
        xm = CX + math.cos(a + 0.3) * 11
        ym = CX + math.sin(a + 0.3) * 11
        pygame.draw.lines(s, (255, 245, 160), False,
                          [(int(x0), int(y0)), (int(xm), int(ym)), (int(x1), int(y1))], 2)
    return s


# ---------------------------------------------------------------------------
# hexaura (Mangkukulam) — pulsing purple curse aura
# ---------------------------------------------------------------------------
def _hexaura(frac: float) -> pygame.Surface:
    s = sl.surf()
    sl.glow(s, CX, CX, 15 + 4 * frac, (140, 60, 190), alpha=int(140 * (1 - 0.4 * frac)))
    sl.ring(s, CX, CX, 13, (190, 120, 230), width=2, alpha=200)
    for k in range(5):
        ang = k * math.tau / 5 + frac * math.tau
        x = CX + math.cos(ang) * 13
        y = CX + math.sin(ang) * 13
        pygame.draw.circle(s, (210, 160, 240), (int(x), int(y)), 2)
    return s


# ---------------------------------------------------------------------------
# hexheal (Mangkukulam) — green-purple restorative hex sigil
# ---------------------------------------------------------------------------
def _hexheal(frame: int) -> pygame.Surface:
    s = se.canvas()
    pts = []
    for k in range(5):
        ang = -math.pi / 2 + k * math.tau / 5
        r = 13 if k % 2 == 0 or frame == 1 else 11
        pts.append((CX + math.cos(ang) * r, CX + math.sin(ang) * r))
    se.poly(s, (150, 210, 130), pts, outline=(90, 70, 130), ow=1.4, hi=(190, 240, 170))
    se.dot(s, (200, 160, 230), (CX, CX), 2.4)
    return se.downsample(s)


# ---------------------------------------------------------------------------
# pangkukulam (Mangkukulam) — a dark curse burst, distinct from hexaura/heal
# ---------------------------------------------------------------------------
def _pangkukulam(frac: float) -> pygame.Surface:
    s = sl.surf()
    sl.glow(s, CX, CX, 10 + 16 * frac, (60, 20, 80), alpha=int(170 * (1 - frac)))
    sl.ring(s, CX, CX, 16 * frac, (30, 10, 45), width=4, alpha=int(210 * (1 - frac)))
    for k in range(7):
        ang = k * math.tau / 7
        x = CX + math.cos(ang) * (5 + 15 * frac)
        y = CX + math.sin(ang) * (5 + 15 * frac)
        pygame.draw.circle(s, (120, 40, 150, int(200 * (1 - frac))), (int(x), int(y)), 2)
    return s


# ---------------------------------------------------------------------------
# awit (Pedro) — a musical/mystical motif
# ---------------------------------------------------------------------------
def _awit(frame: int) -> pygame.Surface:
    s2 = sl.surf()
    sl.glow(s2, CX, CX, 14, (150, 200, 255), alpha=120)
    notes = ((CX - 8, CX - 8), (CX + 6, CX - 12), (CX + 1, CX + 6))
    for i, (nx, ny) in enumerate(notes):
        oy = ny + (2 if (frame + i) % 2 == 0 else -2)
        pygame.draw.circle(s2, (240, 248, 255), (nx, oy), 3)
        pygame.draw.line(s2, (240, 248, 255), (nx + 3, oy), (nx + 3, oy - 9), 2)
    return s2


def main() -> int:
    n = 0
    n += _save2("smash", _smash(0.15), _smash(0.6))
    n += _save2("bolocleave", _bolocleave(0.1), _bolocleave(0.55))
    n += _save2("earthshatter", _earthshatter(0.2), _earthshatter(0.7))
    n += _save2("arrowstorm", _arrowstorm(0), _arrowstorm(1))
    n += _save2("sanctuary", _sanctuary(0.1), _sanctuary(0.6))
    n += _save2("renewwave", _renewwave(0.15), _renewwave(0.6))
    n += _save2("reform", _reform(0), _reform(1))
    n += _save2("decalogue", _decalogue(0), _decalogue(1))
    n += _save2("paralysis", _paralysis(0), _paralysis(1))
    n += _save2("hexaura", _hexaura(0.1), _hexaura(0.6))
    n += _save2("hexheal", _hexheal(0), _hexheal(1))
    n += _save2("pangkukulam", _pangkukulam(0.15), _pangkukulam(0.65))
    n += _save2("awit", _awit(0), _awit(1))
    return n


if __name__ == "__main__":
    sl.main_guard(main)
