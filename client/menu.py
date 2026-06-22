"""Pre-game UI: main menu (name/host/port) and lobby (pick side + start).

These screens are intentionally self-contained — they own their fonts and
return high-level *actions* (e.g. ``("connect", name, host, port)`` or
``("team", 2)``) for the client to act on, so the networking lives in
``client_main`` and the drawing lives here.
"""

from __future__ import annotations

import os

import pygame

from shared.config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_BG, COLOR_TEXT, COLOR_TEAM1, COLOR_TEAM2,
)

_ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")

_PANEL = (28, 30, 38)
_PANEL_HI = (44, 48, 60)
_ACCENT = (90, 170, 220)
_MUTED = (150, 150, 160)
_ERROR = (220, 90, 90)


def _center_rect(w: int, h: int, cy: int) -> pygame.Rect:
    return pygame.Rect((SCREEN_WIDTH - w) // 2, cy, w, h)


class TextInput:
    """A single click-to-focus text field."""

    def __init__(self, label: str, text: str, rect: pygame.Rect,
                 numeric: bool = False, maxlen: int = 24) -> None:
        self.label = label
        self.text = text
        self.rect = rect
        self.numeric = numeric
        self.maxlen = maxlen
        self.active = False

    def handle(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_TAB,
                               pygame.K_ESCAPE):
                pass  # handled by the owning screen
            elif len(self.text) < self.maxlen and event.unicode:
                ch = event.unicode
                if (not self.numeric or ch.isdigit()) and ch.isprintable():
                    self.text += ch

    def draw(self, surf, font) -> None:
        lbl = font.render(self.label, True, _MUTED)
        surf.blit(lbl, (self.rect.x, self.rect.y - 22))
        bg = _PANEL_HI if self.active else _PANEL
        pygame.draw.rect(surf, bg, self.rect, border_radius=6)
        border = _ACCENT if self.active else (70, 74, 88)
        pygame.draw.rect(surf, border, self.rect, 2, border_radius=6)
        txt = font.render(self.text or "", True, COLOR_TEXT)
        surf.blit(txt, (self.rect.x + 10,
                        self.rect.y + (self.rect.height - txt.get_height()) // 2))


class MainMenu:
    """Name / host / port entry + Connect."""

    def __init__(self, name: str, host: str, port: int) -> None:
        self.font = pygame.font.SysFont("monospace", 18)
        self.font_big = pygame.font.SysFont("monospace", 44, bold=True)
        w = 380
        cx0 = (SCREEN_WIDTH - w) // 2
        self.name = TextInput("NAME", name, pygame.Rect(cx0, 250, w, 40))
        self.host = TextInput("SERVER HOST / IP", host,
                              pygame.Rect(cx0, 322, w, 40), maxlen=40)
        self.port = TextInput("PORT", str(port),
                              pygame.Rect(cx0, 394, w, 40), numeric=True,
                              maxlen=5)
        self.fields = [self.name, self.host, self.port]
        self.connect_btn = _center_rect(200, 48, 460)
        self.error = ""

    def handle(self, events) -> tuple | None:
        for event in events:
            for f in self.fields:
                f.handle(event)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                return self._connect_action()
            if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                    and self.connect_btn.collidepoint(event.pos)):
                return self._connect_action()
        return None

    def _connect_action(self) -> tuple | None:
        name = self.name.text.strip() or "Player"
        host = self.host.text.strip() or "127.0.0.1"
        try:
            port = int(self.port.text)
        except ValueError:
            self.error = "Port must be a number"
            return None
        return ("connect", name, host, port)

    def draw(self, surf) -> None:
        surf.fill(COLOR_BG)
        title = self.font_big.render("MOBA LITE", True, COLOR_TEXT)
        surf.blit(title, ((SCREEN_WIDTH - title.get_width()) // 2, 140))
        sub = self.font.render("Enter your name and a server to join",
                               True, _MUTED)
        surf.blit(sub, ((SCREEN_WIDTH - sub.get_width()) // 2, 200))
        for f in self.fields:
            f.draw(surf, self.font)
        mouse = pygame.mouse.get_pos()
        hot = self.connect_btn.collidepoint(mouse)
        pygame.draw.rect(surf, _ACCENT if hot else _PANEL_HI,
                         self.connect_btn, border_radius=8)
        ct = self.font.render("CONNECT", True, COLOR_TEXT)
        surf.blit(ct, (self.connect_btn.centerx - ct.get_width() // 2,
                       self.connect_btn.centery - ct.get_height() // 2))
        if self.error:
            err = self.font.render(self.error, True, _ERROR)
            surf.blit(err, ((SCREEN_WIDTH - err.get_width()) // 2, 524))
        hint = self.font.render(
            "Same WiFi: enter the host PC's LAN IP. Solo: 127.0.0.1",
            True, _MUTED)
        surf.blit(hint, ((SCREEN_WIDTH - hint.get_width()) // 2, 560))


class LobbyScreen:
    """Team columns, hero picker, and the host's Start button."""

    def __init__(self) -> None:
        self.font = pygame.font.SysFont("monospace", 18)
        self.font_big = pygame.font.SysFont("monospace", 40, bold=True)
        self.font_small = pygame.font.SysFont("monospace", 15)
        self.players: list[dict] = []
        self.heroes: list[dict] = []   # [{id, name}]
        self.my_cid: int | None = None
        self.is_host = False
        self.status = "Connecting…"
        # rects rebuilt every layout pass for hit-testing
        self._hero_btns: list[tuple[pygame.Rect, str]] = []
        self._switch_btn = pygame.Rect(0, 0, 0, 0)
        self._start_btn = pygame.Rect(0, 0, 0, 0)
        # hero-select face thumbnails, loaded lazily + cached.
        self._face_px = 50
        self._faces: dict[str, pygame.Surface | None] = {}

    def _my_team(self) -> int:
        for p in self.players:
            if p["cid"] == self.my_cid:
                return p["team"]
        return 1

    # Hero picker is a centered grid of face thumbnails so every hero fits and
    # is clickable no matter how many there are.
    _GRID_TOP = 366
    _CELL_W, _CELL_H = 92, 74
    _MAX_COLS = 7

    def _layout(self) -> None:
        self._hero_btns = []
        n = len(self.heroes)
        cols = max(1, min(self._MAX_COLS, n))
        rows = max(1, (n + cols - 1) // cols)
        x0 = (SCREEN_WIDTH - cols * self._CELL_W) // 2
        for i, h in enumerate(self.heroes):
            r, c = divmod(i, cols)
            rect = pygame.Rect(x0 + c * self._CELL_W,
                               self._GRID_TOP + r * self._CELL_H,
                               self._CELL_W, self._CELL_H)
            self._hero_btns.append((rect, h["id"]))
        grid_bottom = self._GRID_TOP + rows * self._CELL_H
        self._switch_btn = _center_rect(220, 42, grid_bottom + 14)
        self._start_btn = _center_rect(240, 54, grid_bottom + 66)

    def _face(self, hid: str) -> pygame.Surface | None:
        """Load + cache a hero's select portrait, scaled to the thumbnail size."""
        if hid not in self._faces:
            path = os.path.join(_ASSET_DIR, "heroes", hid, "face.png")
            img = None
            if os.path.isfile(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                    img = pygame.transform.smoothscale(
                        img, (self._face_px, self._face_px))
                except pygame.error:
                    img = None
            self._faces[hid] = img
        return self._faces[hid]

    def _fit(self, text: str, max_w: int) -> str:
        """Truncate `text` with an ellipsis so it fits within `max_w` px."""
        if self.font_small.size(text)[0] <= max_w:
            return text
        while text and self.font_small.size(text + "…")[0] > max_w:
            text = text[:-1]
        return text + "…"

    def handle(self, events) -> list[tuple]:
        self._layout()
        actions: list[tuple] = []
        for event in events:
            if not (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
                continue
            for rect, hid in self._hero_btns:
                if rect.collidepoint(event.pos):
                    actions.append(("hero", hid))
            if self._switch_btn.collidepoint(event.pos):
                actions.append(("team", 2 if self._my_team() == 1 else 1))
            if self.is_host and self._start_btn.collidepoint(event.pos):
                actions.append(("start",))
        return actions

    def _hero_name(self, hid: str) -> str:
        for h in self.heroes:
            if h["id"] == hid:
                return h["name"]
        return hid

    def draw(self, surf) -> None:
        self._layout()
        surf.fill(COLOR_BG)
        title = self.font_big.render("LOBBY", True, COLOR_TEXT)
        surf.blit(title, ((SCREEN_WIDTH - title.get_width()) // 2, 40))

        col_w, col_h = 420, 210
        gap = 40
        x1 = SCREEN_WIDTH // 2 - col_w - gap // 2
        x2 = SCREEN_WIDTH // 2 + gap // 2
        for x, team, color, label in (
                (x1, 1, COLOR_TEAM1, "TEAM 1"),
                (x2, 2, COLOR_TEAM2, "TEAM 2")):
            rect = pygame.Rect(x, 120, col_w, col_h)
            pygame.draw.rect(surf, _PANEL, rect, border_radius=8)
            pygame.draw.rect(surf, color, rect, 2, border_radius=8)
            hdr = self.font.render(label, True, color)
            surf.blit(hdr, (rect.x + 14, rect.y + 10))
            ty = rect.y + 46
            for p in self.players:
                if p["team"] != team:
                    continue
                mark = "★ " if p["host"] else "  "
                tag = "  (you)" if p["cid"] == self.my_cid else ""
                line = f"{mark}{p['name']}{tag}"
                surf.blit(self.font.render(line, True, COLOR_TEXT),
                          (rect.x + 14, ty))
                hero_line = f"      {self._hero_name(p['hero'])}"
                surf.blit(self.font_small.render(hero_line, True, _MUTED),
                          (rect.x + 14, ty + 20))
                ty += 48

        # Hero picker
        my_hero = next((p["hero"] for p in self.players
                        if p["cid"] == self.my_cid), None)
        pick_lbl = self.font.render("PICK YOUR HERO", True, _MUTED)
        surf.blit(pick_lbl,
                  ((SCREEN_WIDTH - pick_lbl.get_width()) // 2,
                   self._GRID_TOP - 24))
        mouse = pygame.mouse.get_pos()
        fpx = self._face_px
        for rect, hid in self._hero_btns:
            sel = hid == my_hero
            hot = rect.collidepoint(mouse)
            fx = rect.centerx - fpx // 2
            fy = rect.y + 2
            frame = pygame.Rect(fx - 3, fy - 3, fpx + 6, fpx + 6)
            if sel:
                pygame.draw.rect(surf, _ACCENT, frame, border_radius=8)
            elif hot:
                pygame.draw.rect(surf, _PANEL_HI, frame, border_radius=8)
            face = self._face(hid)
            if face is not None:
                surf.blit(face, (fx, fy))
            else:  # no art yet: a labelled placeholder tile
                pygame.draw.rect(surf, _PANEL, (fx, fy, fpx, fpx),
                                 border_radius=8)
            col = COLOR_TEXT if (sel or hot) else _MUTED
            name = self.font_small.render(
                self._fit(self._hero_name(hid), self._CELL_W - 4), True, col)
            surf.blit(name, (rect.centerx - name.get_width() // 2,
                             fy + fpx + 3))

        # Switch side
        hot = self._switch_btn.collidepoint(mouse)
        pygame.draw.rect(surf, _PANEL_HI if hot else _PANEL,
                         self._switch_btn, border_radius=8)
        st = self.font.render("SWITCH SIDE", True, COLOR_TEXT)
        surf.blit(st, (self._switch_btn.centerx - st.get_width() // 2,
                       self._switch_btn.centery - st.get_height() // 2))

        # Start (host) or waiting (others)
        if self.is_host:
            hot = self._start_btn.collidepoint(mouse)
            pygame.draw.rect(surf, (70, 170, 90) if hot else (54, 130, 70),
                             self._start_btn, border_radius=10)
            gt = self.font_big.render("START", True, COLOR_TEXT)
            surf.blit(gt, (self._start_btn.centerx - gt.get_width() // 2,
                           self._start_btn.centery - gt.get_height() // 2))
        else:
            wt = self.font.render("Waiting for the host to start…",
                                  True, _MUTED)
            surf.blit(wt, ((SCREEN_WIDTH - wt.get_width()) // 2,
                           self._start_btn.centery - wt.get_height() // 2))

        if self.status:
            s = self.font_small.render(self.status, True, _MUTED)
            surf.blit(s, (16, SCREEN_HEIGHT - 28))
