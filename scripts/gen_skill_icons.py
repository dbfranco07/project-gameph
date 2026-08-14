"""Procedural skill-bar icons: one round badge per ability across all 15
heroes (64 icons total), so the ability bar reads at a glance instead of
showing a plain colored rect + key letter.

Every icon shares the same badge treatment (a shaded circular background ring
in the hero/skill's accent color, a darker inner disc, a bold pale glyph on
top) so the bar stays visually coherent, while the glyph itself is drawn from
a small library of distinct pictograms (blade arc, claw marks, bolt, shield,
book, paw print, ...) picked per ability to hint at what it does.

    uv run python scripts/gen_skill_icons.py
"""

from __future__ import annotations

import math

import pygame

import spritelib as sl

CX = sl.CX
_INK = (22, 18, 24)


# ---------------------------------------------------------------------------
# Badge background
# ---------------------------------------------------------------------------
def _badge(bg) -> pygame.Surface:
    s = sl.surf()
    edge = tuple(max(0, c - 60) for c in bg)
    hi = tuple(min(255, c + 45) for c in bg)
    sl.glow(s, CX, CX, 25, bg, alpha=70)
    pygame.draw.circle(s, bg, (CX, CX), 24)
    pygame.draw.circle(s, edge, (CX, CX), 24, 3)
    pygame.draw.circle(s, hi, (CX, CX), 20, 1)
    return s


# ---------------------------------------------------------------------------
# Glyph library — each draws in white/cream on the already-badged surface,
# roughly within a radius-16 circle around (CX, CX).
# ---------------------------------------------------------------------------
def _g_fang(s, col=sl.WHITE):
    for side in (-1, 1):
        x = CX + side * 5
        pygame.draw.polygon(s, col, [(x, CX - 9), (x + side * 6, CX - 9),
                                     (x + side * 2, CX + 9)])


def _g_claws(s, col=sl.WHITE):
    for dx in (-8, 0, 8):
        pygame.draw.line(s, col, (CX + dx - 10, CX - 12),
                         (CX + dx + 6, CX + 12), 3)


def _g_swirl(s, col=sl.WHITE):
    pts = []
    for i in range(40):
        t = i / 39
        a = t * math.tau * 2.2
        r = 2 + t * 13
        pts.append((CX + math.cos(a) * r, CX + math.sin(a) * r))
    pygame.draw.lines(s, col, False, pts, 2)


def _g_eye(s, col=sl.WHITE):
    pygame.draw.polygon(s, col, [(CX - 14, CX), (CX, CX - 8), (CX + 14, CX),
                                 (CX, CX + 8)], 2)
    pygame.draw.circle(s, col, (CX, CX), 4)


def _g_wings(s, col=sl.WHITE):
    for side in (-1, 1):
        pts = [(CX, CX - 4), (CX + side * 15, CX - 10),
               (CX + side * 12, CX), (CX + side * 15, CX + 6),
               (CX, CX + 4)]
        pygame.draw.polygon(s, col, pts, 2)


def _g_blade_arc(s, col=sl.WHITE):
    pygame.draw.arc(s, col, (CX - 14, CX - 16, 28, 28), -0.9, 1.3, 3)
    pygame.draw.line(s, col, (CX + 12, CX - 9), (CX + 15, CX - 13), 2)


def _g_scroll(s, col=sl.WHITE):
    pygame.draw.rect(s, col, (CX - 10, CX - 12, 20, 24), 2, border_radius=3)
    for dy in (-5, 1, 7):
        pygame.draw.line(s, col, (CX - 6, CX + dy), (CX + 6, CX + dy), 1)


def _g_bandana(s, col=sl.WHITE):
    pygame.draw.rect(s, col, (CX - 13, CX - 3, 26, 6), border_radius=2)
    pygame.draw.polygon(s, col, [(CX + 10, CX + 3), (CX + 16, CX + 12),
                                 (CX + 6, CX + 9)])


def _g_sunburst(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 5)
    for ang in range(0, 360, 45):
        a = math.radians(ang)
        pygame.draw.line(s, col, (CX + math.cos(a) * 7, CX + math.sin(a) * 7),
                         (CX + math.cos(a) * 15, CX + math.sin(a) * 15), 2)


def _g_earthcrack(s, col=sl.WHITE):
    pygame.draw.lines(s, col, False,
                      [(CX - 14, CX + 10), (CX - 4, CX - 6), (CX + 2, CX + 4),
                       (CX + 14, CX - 10)], 3)


def _g_charge(s, col=sl.WHITE):
    pygame.draw.polygon(s, col, [(CX - 12, CX), (CX + 4, CX - 10),
                                 (CX - 2, CX), (CX + 12, CX),
                                 (CX - 4, CX + 10), (CX + 2, CX)])


def _g_fist(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX + 2), 10, 2)
    for dx in (-5, 0, 5):
        pygame.draw.line(s, col, (CX + dx, CX - 8), (CX + dx, CX - 3), 2)


def _g_bark_smash(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 11, 2)
    for a in (0.5, 2.1, 3.7, 5.3):
        pygame.draw.line(s, col, (CX, CX),
                         (CX + math.cos(a) * 14, CX + math.sin(a) * 14), 2)


def _g_root(s, col=sl.WHITE):
    pygame.draw.line(s, col, (CX, CX - 12), (CX, CX + 6), 2)
    for side in (-1, 1):
        pygame.draw.line(s, col, (CX, CX + 2), (CX + side * 10, CX + 12), 2)


def _g_bark_shield(s, col=sl.WHITE):
    pts = [(CX - 10, CX - 12), (CX + 10, CX - 12), (CX + 10, CX + 2),
           (CX, CX + 14), (CX - 10, CX + 2)]
    pygame.draw.polygon(s, col, pts, 2)
    pygame.draw.line(s, col, (CX, CX - 10), (CX, CX + 10), 1)


def _g_treehouse(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX - 4), 9, 2)
    pygame.draw.rect(s, col, (CX - 4, CX + 3, 8, 9), 2)


def _g_stretch(s, col=sl.WHITE):
    pygame.draw.line(s, col, (CX - 14, CX), (CX + 8, CX), 3)
    pygame.draw.circle(s, col, (CX + 12, CX), 4)


def _g_grapple(s, col=sl.WHITE):
    for i in range(4):
        t = i / 3
        pygame.draw.circle(s, col, (int(CX - 12 + t * 24),
                                    int(CX + 6 * math.sin(t * math.pi))), 2)
    pygame.draw.circle(s, col, (CX + 13, CX), 3, 2)


def _g_bounce(s, col=sl.WHITE):
    pygame.draw.arc(s, col, (CX - 14, CX - 2, 12, 14), 0, math.pi, 2)
    pygame.draw.arc(s, col, (CX + 2, CX - 2, 12, 14), 0, math.pi, 2)
    pygame.draw.line(s, col, (CX - 8, CX + 10), (CX + 8, CX + 10), 2)


def _g_check_burst(s, col=sl.WHITE):
    for i in range(8):
        a = i * math.tau / 8
        pygame.draw.line(s, col, (CX + math.cos(a) * 4, CX + math.sin(a) * 4),
                         (CX + math.cos(a) * 15, CX + math.sin(a) * 15), 2)


def _g_bolt(s, col=sl.WHITE):
    pygame.draw.polygon(s, col, [(CX + 2, CX - 14), (CX - 6, CX + 1),
                                 (CX, CX + 1), (CX - 3, CX + 14),
                                 (CX + 8, CX - 3), (CX + 2, CX - 3)])


def _g_tablet(s, col=sl.WHITE):
    pygame.draw.rect(s, col, (CX - 9, CX - 12, 18, 24), 2, border_radius=2)
    for dy in (-6, -1, 4, 9):
        pygame.draw.line(s, col, (CX - 5, CX + dy), (CX + 5, CX + dy), 1)


def _g_brain(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 10, 2)
    pygame.draw.arc(s, col, (CX - 8, CX - 8, 10, 12), 0.3, 2.8, 1)
    pygame.draw.arc(s, col, (CX - 2, CX - 8, 10, 12), 0.3, 2.8, 1)


def _g_stunbolts(s, col=sl.WHITE):
    for dx in (-9, 0, 9):
        pygame.draw.lines(s, col, False,
                          [(CX + dx, CX - 12), (CX + dx - 3, CX - 3),
                           (CX + dx + 3, CX + 3), (CX + dx - 2, CX + 12)], 2)


def _g_pounce(s, col=sl.WHITE):
    pygame.draw.arc(s, col, (CX - 14, CX - 12, 26, 22), 2.6, 5.6, 2)
    for dx in (-3, 3, 9):
        pygame.draw.line(s, col, (CX + dx, CX + 8), (CX + dx + 2, CX + 14), 2)


def _g_bloodlust(s, col=sl.WHITE):
    pygame.draw.polygon(s, col, [(CX, CX - 12), (CX + 8, CX + 2),
                                 (CX, CX + 13), (CX - 8, CX + 2)])
    pygame.draw.circle(s, col, (CX, CX + 1), 4, 1)


def _g_split(s, col=sl.WHITE):
    pygame.draw.line(s, col, (CX, CX - 13), (CX, CX + 13), 2)
    pygame.draw.circle(s, col, (CX - 8, CX), 5, 2)
    pygame.draw.circle(s, col, (CX + 8, CX), 5, 2)


def _g_hexring(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 12, 2)
    pygame.draw.circle(s, col, (CX, CX), 4)


def _g_wormcurse(s, col=sl.WHITE):
    pts = []
    for i in range(20):
        t = i / 19
        pts.append((CX - 14 + t * 28, CX + 6 * math.sin(t * math.tau)))
    pygame.draw.lines(s, col, False, pts, 3)


def _g_evileye(s, col=sl.WHITE):
    pygame.draw.ellipse(s, col, (CX - 13, CX - 7, 26, 14), 2)
    pygame.draw.circle(s, col, (CX, CX), 5)


def _g_hexburst(s, col=sl.WHITE):
    for i in range(6):
        a = i * math.tau / 6
        pygame.draw.line(s, col, (CX, CX),
                         (CX + math.cos(a) * 14, CX + math.sin(a) * 14), 2)
        pygame.draw.circle(s, col, (CX + int(math.cos(a) * 14),
                                    CX + int(math.sin(a) * 14)), 2)


def _g_shelter(s, col=sl.WHITE):
    pts = [(CX - 8, CX - 10), (CX + 8, CX - 10), (CX + 8, CX),
           (CX, CX + 11), (CX - 8, CX)]
    pygame.draw.polygon(s, col, pts, 2)


def _g_rally(s, col=sl.WHITE):
    for dx in (-9, 0, 10):
        pygame.draw.polygon(s, col, [(CX + dx, CX + 8), (CX + dx - 3, CX + 2),
                                     (CX + dx + 3, CX + 2)])


def _g_matriarch(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 12, 2)
    pygame.draw.circle(s, col, (CX, CX - 3), 4, 1)


def _g_refuge(s, col=sl.WHITE):
    pygame.draw.arc(s, col, (CX - 13, CX - 6, 26, 26), 0.1, math.pi - 0.1, 3)
    pygame.draw.line(s, col, (CX - 13, CX + 7), (CX + 13, CX + 7), 2)


def _g_spiritbolt(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 4)
    for a in range(0, 360, 60):
        r = math.radians(a)
        pygame.draw.line(s, col, (CX + math.cos(r) * 6, CX + math.sin(r) * 6),
                         (CX + math.cos(r) * 13, CX + math.sin(r) * 13), 1)


def _g_wave(s, col=sl.WHITE):
    pts = [(CX - 14 + i, CX + 6 * math.sin(i * 0.5)) for i in range(29)]
    pygame.draw.lines(s, col, False, pts, 2)


def _g_dashafter(s, col=sl.WHITE):
    for i, r in enumerate((5, 9, 13)):
        pygame.draw.circle(s, col, (CX - i * 3, CX), r, 1)


def _g_sanctuary(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 13, 2)
    pygame.draw.line(s, col, (CX, CX - 7), (CX, CX + 7), 2)
    pygame.draw.line(s, col, (CX - 7, CX), (CX + 7, CX), 2)


def _g_arrow(s, col=sl.WHITE):
    pygame.draw.line(s, col, (CX - 13, CX), (CX + 10, CX), 2)
    pygame.draw.polygon(s, col, [(CX + 14, CX), (CX + 6, CX - 5),
                                 (CX + 6, CX + 5)])


def _g_roll(s, col=sl.WHITE):
    pygame.draw.arc(s, col, (CX - 12, CX - 12, 24, 24), 0.6, 5.2, 2)
    pygame.draw.polygon(s, col, [(CX + 10, CX - 8), (CX + 14, CX - 3),
                                 (CX + 7, CX - 2)])


def _g_crosshair(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 11, 2)
    pygame.draw.line(s, col, (CX, CX - 15), (CX, CX - 8), 2)
    pygame.draw.line(s, col, (CX, CX + 8), (CX, CX + 15), 2)
    pygame.draw.line(s, col, (CX - 15, CX), (CX - 8, CX), 2)
    pygame.draw.line(s, col, (CX + 8, CX), (CX + 15, CX), 2)


def _g_arrowstorm(s, col=sl.WHITE):
    for dx in (-9, 0, 9):
        pygame.draw.line(s, col, (CX + dx, CX - 13), (CX + dx, CX + 5), 2)
        pygame.draw.polygon(s, col, [(CX + dx, CX + 9), (CX + dx - 3, CX + 3),
                                     (CX + dx + 3, CX + 3)])


def _g_feather(s, col=sl.WHITE):
    pygame.draw.line(s, col, (CX - 10, CX + 10), (CX + 10, CX - 10), 2)
    for t in (0.3, 0.55, 0.8):
        bx, by = CX - 10 + 20 * t, CX + 10 - 20 * t
        pygame.draw.line(s, col, (bx, by), (bx - 4, by + 1), 1)
        pygame.draw.line(s, col, (bx, by), (bx + 1, by - 4), 1)


def _g_book(s, col=sl.WHITE):
    pygame.draw.polygon(s, col, [(CX - 12, CX - 4), (CX, CX - 7),
                                 (CX + 12, CX - 4), (CX + 12, CX + 8),
                                 (CX, CX + 5), (CX - 12, CX + 8)], 2)
    pygame.draw.line(s, col, (CX, CX - 7), (CX, CX + 5), 1)


def _g_polymath(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 12, 2)
    pygame.draw.line(s, col, (CX - 8, CX), (CX + 8, CX), 1)
    pygame.draw.line(s, col, (CX, CX - 12), (CX, CX + 12), 1)


def _g_halo(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 12, 2)
    pygame.draw.circle(s, col, (CX, CX), 6, 1)


def _g_tonguehook(s, col=sl.WHITE):
    pts = [(CX - 12, CX - 10)]
    for i in range(1, 12):
        t = i / 11
        pts.append((CX - 12 + t * 22, CX - 10 + t * 20 + 3 * math.sin(t * 6)))
    pygame.draw.lines(s, col, False, pts, 2)
    pygame.draw.circle(s, col, pts[-1], 3, 2)


def _g_wallrun(s, col=sl.WHITE):
    pygame.draw.line(s, col, (CX - 12, CX + 12), (CX - 12, CX - 12), 3)
    for i in range(3):
        pygame.draw.line(s, col, (CX - 12 + i * 8, CX - 10 + i * 2),
                         (CX - 4 + i * 8, CX - 14 + i * 2), 2)


def _g_barb(s, col=sl.WHITE):
    pygame.draw.line(s, col, (CX - 13, CX), (CX + 13, CX), 2)
    for dx in (-8, -2, 4, 10):
        pygame.draw.line(s, col, (CX + dx, CX), (CX + dx + 2, CX - 5), 1)


def _g_frenzy(s, col=sl.WHITE):
    for a in range(0, 360, 30):
        r = math.radians(a)
        pygame.draw.line(s, col, (CX + math.cos(r) * 5, CX + math.sin(r) * 5),
                         (CX + math.cos(r) * 14, CX + math.sin(r) * 14), 2)


def _g_cradlebite(s, col=sl.WHITE):
    pygame.draw.arc(s, col, (CX - 13, CX - 10, 26, 20), math.pi, math.tau, 2)
    for dx in (-8, -3, 3, 8):
        pygame.draw.line(s, col, (CX + dx, CX - 9), (CX + dx, CX - 3), 2)


def _g_tantrum(s, col=sl.WHITE):
    pygame.draw.circle(s, col, (CX, CX), 10, 2)
    for a in range(0, 360, 45):
        r = math.radians(a)
        pygame.draw.line(s, col, (CX + math.cos(r) * 11, CX + math.sin(r) * 11),
                         (CX + math.cos(r) * 15, CX + math.sin(r) * 15), 2)


def _g_hunger(s, col=sl.WHITE):
    for side in (-1, 1):
        x = CX + side * 6
        pygame.draw.polygon(s, col, [(x, CX - 10), (x + side * 5, CX - 10),
                                     (x + side, CX + 10)])


def _g_umbilical(s, col=sl.WHITE):
    pts = []
    for i in range(24):
        t = i / 23
        a = t * math.tau * 2
        r = 1 + t * 12
        pts.append((CX + math.cos(a) * r, CX + math.sin(a) * r))
    pygame.draw.lines(s, col, False, pts, 2)


def _g_mutya(s, col=sl.WHITE):
    pygame.draw.polygon(s, col, [(CX, CX - 13), (CX + 7, CX - 3),
                                 (CX + 4, CX + 11), (CX - 4, CX + 11),
                                 (CX - 7, CX - 3)], 2)
    pygame.draw.circle(s, col, (CX, CX), 3)


# ---------------------------------------------------------------------------
# 64-ability table: (hero_id, key, name, accent_rgb, glyph_fn)
# ---------------------------------------------------------------------------
SKILLS = [
    ("aswang", "q", "Devour", (150, 40, 60), _g_fang),
    ("aswang", "w", "Shapeshift", (110, 60, 130), _g_swirl),
    ("aswang", "e", "Nightstalker", (40, 30, 60), _g_eye),
    ("aswang", "r", "True Aswang", (90, 20, 40), _g_wings),

    ("bonifacio", "q", "Bolo Cleave", (60, 90, 150), _g_blade_arc),
    ("bonifacio", "w", "Rip the Cedula", (150, 130, 70), _g_scroll),
    ("bonifacio", "e", "Katipunero", (180, 40, 34), _g_bandana),
    ("bonifacio", "r", "KKK Warcry", (200, 150, 50), _g_sunburst),

    ("brawler", "q", "Crushing Blow", (140, 90, 50), _g_fist),
    ("brawler", "w", "Charge", (170, 110, 40), _g_arrow),
    ("brawler", "e", "Battle Fury", (190, 70, 40), _g_frenzy),
    ("brawler", "r", "Earthshatter", (110, 80, 50), _g_earthcrack),

    ("kapre", "q", "Smash", (90, 70, 40), _g_bark_smash),
    ("kapre", "w", "Grove's Vigor", (60, 110, 60), _g_root),
    ("kapre", "e", "Ironbark", (70, 60, 40), _g_bark_shield),
    ("kapre", "r", "Dwell", (50, 90, 50), _g_treehouse),

    ("lastikman", "q", "Stretch Punch", (200, 170, 40), _g_stretch),
    ("lastikman", "w", "Grapple", (180, 150, 30), _g_grapple),
    ("lastikman", "e", "Elastic Body", (150, 120, 30), _g_bounce),
    ("lastikman", "r", "Rubber Storm", (210, 60, 60), _g_check_burst),

    ("mabini", "q", "Constitution Bolt", (70, 110, 200), _g_bolt),
    ("mabini", "w", "Decalogue", (150, 120, 70), _g_tablet),
    ("mabini", "e", "Brains over Brawn", (200, 130, 190), _g_brain),
    ("mabini", "r", "Paralysis", (100, 150, 220), _g_stunbolts),

    ("manananggal", "q", "Scratch", (150, 30, 40), _g_claws),
    ("manananggal", "w", "Pounce", (120, 30, 50), _g_pounce),
    ("manananggal", "e", "Bloodlust", (170, 20, 30), _g_bloodlust),
    ("manananggal", "r", "Split", (90, 40, 70), _g_split),

    ("mangkukulam", "q", "Hex Aura", (110, 60, 150), _g_hexring),
    ("mangkukulam", "w", "Worm Curse", (90, 130, 60), _g_wormcurse),
    ("mangkukulam", "e", "Evil Eye", (70, 40, 100), _g_evileye),
    ("mangkukulam", "r", "Pangkukulam", (140, 40, 160), _g_hexburst),

    ("melchora", "q", "Sheltering Hand", (200, 170, 100), _g_shelter),
    ("melchora", "w", "Rallying Words", (210, 180, 110), _g_rally),
    ("melchora", "e", "Matriarch", (190, 150, 90), _g_matriarch),
    ("melchora", "r", "Refuge", (220, 190, 130), _g_refuge),

    ("mender", "q", "Spirit Bolt", (90, 190, 190), _g_spiritbolt),
    ("mender", "w", "Renewing Wave", (100, 200, 170), _g_wave),
    ("mender", "e", "Blink", (150, 210, 220), _g_dashafter),
    ("mender", "r", "Sanctuary", (110, 190, 200), _g_sanctuary),

    ("ranger", "q", "Piercing Shot", (90, 150, 90), _g_arrow),
    ("ranger", "w", "Tumble", (110, 140, 80), _g_roll),
    ("ranger", "e", "Hunter's Focus", (80, 120, 70), _g_crosshair),
    ("ranger", "r", "Arrow Storm", (100, 160, 100), _g_arrowstorm),

    ("rizal", "q", "Pluma Throw", (200, 170, 90), _g_feather),
    ("rizal", "w", "Words of Reform", (140, 150, 200), _g_book),
    ("rizal", "e", "Polymath", (150, 140, 190), _g_polymath),
    ("rizal", "r", "Mi Ultimo Adios", (230, 200, 110), _g_halo),

    ("tiktik", "q", "Tongue Hook", (90, 150, 60), _g_tonguehook),
    ("tiktik", "w", "Wallrun", (70, 120, 70), _g_wallrun),
    ("tiktik", "e", "Barbed Tongue", (100, 140, 50), _g_barb),
    ("tiktik", "r", "Frenzy", (130, 160, 40), _g_frenzy),

    ("tiyanak", "q", "Cradle Bite", (120, 160, 90), _g_cradlebite),
    ("tiyanak", "w", "Tantrum", (150, 90, 70), _g_tantrum),
    ("tiyanak", "e", "Feral Hunger", (100, 140, 70), _g_hunger),
    ("tiyanak", "r", "Umbilical Cord", (140, 170, 100), _g_umbilical),

    ("pedro", "q", "Red Mutya: Lakas", (200, 60, 55), _g_mutya),
    ("pedro", "w", "Orange Mutya: Tibay", (215, 130, 45), _g_mutya),
    ("pedro", "e", "Yellow Mutya: Awit", (215, 195, 55), _g_mutya),
    ("pedro", "r", "Green Mutya: Bilis", (70, 175, 80), _g_mutya),
    ("pedro", "t", "Blue Mutya: Lukso", (60, 120, 210), _g_mutya),
    ("pedro", "y", "Indigo Mutya: Mata", (85, 70, 175), _g_mutya),
    ("pedro", "u", "Violet Mutya: Ilag", (150, 70, 190), _g_mutya),
    ("pedro", "i", "White Mutya: Puti", (225, 225, 230), _g_mutya),
]


def main() -> int:
    n = 0
    for hero_id, key, name, accent, glyph_fn in SKILLS:
        s = _badge(accent)
        glyph_fn(s, sl.WHITE)
        sl.save(s, "skills", f"{hero_id}_{key}", "icon")
        n += 1
    return n


if __name__ == "__main__":
    sl.main_guard(main)
