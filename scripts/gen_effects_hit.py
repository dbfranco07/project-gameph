"""Per-hero impact spark art (`effects/hit_<hero_id>/play_0.png` + `play_1.png`),
plus refreshed generic `hit_special`/`hit_phys` fallbacks.

`client/renderer.py`'s `add_combat_events` picks `hit_<hero_id>` for a hit's
attacker when art exists (via `SpriteManager.frame_count`), falling back to the
damage-type-based generic name otherwise — so this is additive art plus a
small renderer lookup, not a rename of the existing two names.

    uv run python scripts/gen_effects_hit.py
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


def _burst(col, dark, n=6, r0=6.0, r1=15.0, shape="dot") -> tuple:
    """A generic radial burst (n shards/dots around a bright core) at two
    growth fractions — the shared skeleton each hero variant re-colors and
    re-shapes."""
    def frame(frac):
        s = sl.surf()
        a = int(220 * (1 - frac))
        sl.glow(s, CX, CX, 6 + 6 * frac, col, alpha=int(160 * (1 - frac)))
        pygame.draw.circle(s, (*col, a), (int(CX), int(CX)), int(3 + 3 * frac))
        for k in range(n):
            ang = k * math.tau / n + frac * 0.4
            rr = r0 + (r1 - r0) * frac
            x = CX + math.cos(ang) * rr
            y = CX + math.sin(ang) * rr
            if shape == "dot":
                pygame.draw.circle(s, (*dark, a), (int(x), int(y)), 2)
            else:
                x0 = CX + math.cos(ang) * r0 * 0.6
                y0 = CX + math.sin(ang) * r0 * 0.6
                pygame.draw.line(s, (*dark, a), (int(x0), int(y0)), (int(x), int(y)), 2)
        return s
    return frame(0.15), frame(0.65)


# ---------------------------------------------------------------------------
# Hero themes: (key, builder) -> (frame0, frame1)
# ---------------------------------------------------------------------------
def _aswang() -> tuple:
    def frame(frac):
        s = sl.surf()
        a = int(230 * (1 - frac))
        for ang in (-0.5, 0.0, 0.5):
            x0 = CX - math.cos(ang) * 4
            y0 = CX - math.sin(ang) * 4
            x1 = CX + math.cos(ang) * (10 + 8 * frac)
            y1 = CX + math.sin(ang) * (10 + 8 * frac)
            pygame.draw.line(s, (150, 20, 30, a), (x0, y0), (x1, y1), 3)
        return s
    return frame(0.1), frame(0.6)


def _bonifacio() -> tuple:
    return _burst((210, 60, 50), (255, 210, 60), n=5, shape="line")


def _brawler() -> tuple:
    def frame(frac):
        s = sl.surf()
        sl.ring(s, CX, CX, 6 + 12 * frac, (255, 170, 60), width=3, alpha=int(220 * (1 - frac)))
        for k in range(4):
            ang = k * math.tau / 4 + math.pi / 4
            x = CX + math.cos(ang) * (8 + 6 * frac)
            y = CX + math.sin(ang) * (8 + 6 * frac)
            pygame.draw.circle(s, (255, 220, 150, int(200 * (1 - frac))), (int(x), int(y)), 2)
        return s
    return frame(0.15), frame(0.6)


def _kapre() -> tuple:
    def frame(frac):
        s = sl.surf()
        for k in range(5):
            ang = k * math.tau / 5
            x = CX + math.cos(ang) * (4 + 10 * frac)
            y = CX + math.sin(ang) * (4 + 10 * frac) - 3 * frac
            pygame.draw.circle(s, (90, 70, 50, int(180 * (1 - frac))), (int(x), int(y)), int(2 + 2 * frac))
        pygame.draw.circle(s, (200, 140, 60, int(160 * (1 - frac))), (int(CX), int(CX)), 3)
        return s
    return frame(0.15), frame(0.6)


def _lastikman() -> tuple:
    def frame(frac):
        s = sl.surf()
        r = 5 + 10 * frac
        cell = 3
        for yy in range(-8, 9, cell):
            for xx in range(-8, 9, cell):
                if xx * xx + yy * yy > r * r:
                    continue
                col = (240, 240, 240) if ((xx // cell) + (yy // cell)) % 2 == 0 else (30, 30, 30)
                a = int(210 * (1 - frac))
                pygame.draw.rect(s, (*col, a), (CX + xx, CX + yy, cell, cell))
        return s
    return frame(0.1), frame(0.55)


def _mabini() -> tuple:
    def frame(frac):
        s = sl.surf()
        sl.ring(s, CX, CX, 8 + 8 * frac, (140, 190, 255), width=2, alpha=int(200 * (1 - frac)))
        for k in range(4):
            ang = k * math.tau / 4 + frac
            x0 = CX + math.cos(ang) * 5
            y0 = CX + math.sin(ang) * 5
            x1 = CX + math.cos(ang) * (12 + 5 * frac)
            y1 = CX + math.sin(ang) * (12 + 5 * frac)
            pygame.draw.line(s, (220, 235, 255, int(210 * (1 - frac))), (x0, y0), (x1, y1), 2)
        return s
    return frame(0.15), frame(0.6)


def _manananggal() -> tuple:
    return _burst((160, 20, 20), (90, 10, 10), n=5, r0=5, r1=14, shape="line")


def _mangkukulam() -> tuple:
    return _burst((150, 60, 200), (90, 30, 130), n=5, r0=5, r1=13)


def _melchora() -> tuple:
    def frame(frac):
        s = sl.surf()
        sl.glow(s, CX, CX, 8 + 8 * frac, (255, 220, 150), alpha=int(170 * (1 - frac)))
        for k in range(6):
            ang = k * math.tau / 6
            x = CX + math.cos(ang) * (5 + 9 * frac)
            y = CX + math.sin(ang) * (5 + 9 * frac)
            pygame.draw.circle(s, (255, 245, 210, int(200 * (1 - frac))), (int(x), int(y)), 2)
        return s
    return frame(0.15), frame(0.6)


def _mender() -> tuple:
    def frame(frac):
        s = sl.surf()
        sl.ring(s, CX, CX, 6 + 10 * frac, (170, 255, 200), width=2, alpha=int(210 * (1 - frac)))
        pygame.draw.circle(s, (230, 255, 235, int(200 * (1 - frac))), (int(CX), int(CX)), int(3 + 2 * frac))
        return s
    return frame(0.15), frame(0.6)


def _ranger() -> tuple:
    def frame(frac):
        s = sl.surf()
        for k in range(5):
            ang = k * math.tau / 5 + 0.2
            x0 = CX + math.cos(ang) * 4
            y0 = CX + math.sin(ang) * 4
            x1 = CX + math.cos(ang) * (10 + 6 * frac)
            y1 = CX + math.sin(ang) * (10 + 6 * frac)
            pygame.draw.line(s, (120, 90, 55, int(210 * (1 - frac))), (x0, y0), (x1, y1), 2)
        return s
    return frame(0.15), frame(0.6)


def _rizal() -> tuple:
    def frame(frac):
        s = sl.surf()
        pygame.draw.circle(s, (245, 238, 218, int(200 * (1 - frac))), (int(CX), int(CX)), int(4 + 7 * frac), 1)
        for k in range(3):
            y = CX - 4 + k * 4
            pygame.draw.line(s, (60, 50, 30, int(200 * (1 - frac))), (CX - 5, y), (CX + 5, y), 1)
        return s
    return frame(0.1), frame(0.55)


def _tiktik() -> tuple:
    def frame(frac):
        s = sl.surf()
        for k in range(5):
            ang = k * math.tau / 5 + frac
            r = 4 + 9 * frac
            x = CX + math.cos(ang) * r
            y = CX + math.sin(ang) * r
            pygame.draw.circle(s, (210, 90, 150, int(200 * (1 - frac))), (int(x), int(y)), int(2 + 2 * frac))
        return s
    return frame(0.15), frame(0.6)


def _tiyanak() -> tuple:
    def frame(frac):
        s = sl.surf()
        sl.glow(s, CX, CX, 8 + 8 * frac, (150, 220, 130), alpha=int(150 * (1 - frac)))
        sl.ring(s, CX, CX, 6 + 9 * frac, (200, 255, 190), width=2, alpha=int(200 * (1 - frac)))
        return s
    return frame(0.15), frame(0.6)


def _pedro() -> tuple:
    def frame(frac):
        s = sl.surf()
        cols = [(220, 60, 60), (240, 150, 40), (230, 220, 60), (70, 180, 90),
               (60, 130, 230), (90, 60, 200), (170, 60, 200)]
        for k, col in enumerate(cols):
            ang = k * math.tau / len(cols)
            x = CX + math.cos(ang) * (4 + 10 * frac)
            y = CX + math.sin(ang) * (4 + 10 * frac)
            pygame.draw.circle(s, (*col, int(210 * (1 - frac))), (int(x), int(y)), 2)
        return s
    return frame(0.15), frame(0.6)


def _hit_special() -> tuple:
    return _burst((150, 210, 255), (220, 240, 255), n=6, r0=6, r1=16)


def _hit_phys() -> tuple:
    return _burst((235, 120, 70), (255, 200, 150), n=6, r0=6, r1=16, shape="line")


_HEROES = {
    "aswang": _aswang, "bonifacio": _bonifacio, "brawler": _brawler,
    "kapre": _kapre, "lastikman": _lastikman, "mabini": _mabini,
    "manananggal": _manananggal, "mangkukulam": _mangkukulam,
    "melchora": _melchora, "mender": _mender, "ranger": _ranger,
    "rizal": _rizal, "tiktik": _tiktik, "tiyanak": _tiyanak, "pedro": _pedro,
}


def main() -> int:
    n = 0
    for hero_id, builder in _HEROES.items():
        f0, f1 = builder()
        n += _save2(f"hit_{hero_id}", f0, f1)
    f0, f1 = _hit_special()
    n += _save2("hit_special", f0, f1)
    f0, f1 = _hit_phys()
    n += _save2("hit_phys", f0, f1)
    return n


if __name__ == "__main__":
    sl.main_guard(main)
