"""Standalone map explorer / layout tuning tool.

A host-free, no-networking viewer that draws the whole map straight from the
config (``config/*.yaml`` via ``shared.config``): lane paths, the river, walls,
trees, towers + cores (with their attack range), jungle camps + runes (with the
neutral attack range), fountains, spawn zones and wave-1 meeting points.

Its purpose is *map authoring*: pan/zoom around, read off world coordinates under
the cursor, drop coordinate markers, and measure distances so you can decide
where a wall or tree should sit relative to a tower's reach. It reads the same
mirrored data the real game spawns, so what you see here is what you get in-game.

    uv run python scripts/map_explorer.py

Controls (also shown in-window; press H to toggle the help panel):
    Left click        drop a coordinate marker (prints + labels world x, y)
    Left click minimap recenter the main view there (also prints coordinates)
    Right/Middle drag  pan
    Mouse wheel        zoom (toward the cursor)
    Arrow keys         pan
    F                  fit the whole map to the window
    C                  clear all markers
    G L V W T S N R Z I   toggle grid / lanes / river / walls / trees /
                          structures / neutrals / ranges / zones / labels
    H                  toggle help, ESC / Q quit
"""
from __future__ import annotations

import sys
from pathlib import Path

# Run from anywhere: put the repo root on the path so ``shared`` imports resolve
# whether launched as ``python scripts/map_explorer.py`` or via ``uv run``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame  # noqa: E402

from shared.config import (  # noqa: E402
    MAP_WIDTH,
    MAP_HEIGHT,
    LANE_PATHS,
    LANE_WIDTH,
    LANE_TOWERS,
    CORE_POSITIONS,
    SPAWN_POSITIONS,
    JUNGLE_CAMPS,
    RUNES,
    WALLS,
    TREES,
    RIVER,
    MEET_POINTS,
    SPAWN_ZONE_RADIUS,
    TOWER_RANGE,
    TOWER_RADIUS,
    CORE_RADIUS,
    NEUTRAL_RANGE,
    NEUTRAL_RADIUS,
    COLOR_TEAM1,
    COLOR_TEAM2,
    COLOR_BG,
    COLOR_LANE,
    COLOR_GRID,
)
from shared.geometry import point_along  # noqa: E402

# ----- palette ---------------------------------------------------------------
C_WALL = (150, 148, 162)
C_TREE = (60, 150, 70)
C_RIVER = (70, 130, 210)
C_NEUTRAL = (220, 165, 70)        # jungle camps + their attack range
C_RUNE = (185, 125, 235)
C_FOUNTAIN = (235, 225, 150)
C_SPAWN_ZONE = (90, 200, 120)
C_MEET = (230, 210, 110)
C_MARKER = (255, 255, 255)
C_MEASURE = (255, 235, 140)
C_TEXT = (235, 235, 235)
C_DIM = (150, 160, 175)
C_BORDER = (110, 110, 120)


def team_color(team: int) -> tuple[int, int, int]:
    return COLOR_TEAM1 if int(team) == 1 else COLOR_TEAM2


def brighten(c, f: float = 1.4) -> tuple[int, int, int]:
    return tuple(min(255, int(v * f)) for v in c)


# ----- map data (computed once from config, exactly like the server spawns) --
def build_map_data() -> dict:
    """Resolve every drawable feature into world coordinates, once."""
    towers = []
    for team, tlist in LANE_TOWERS.items():
        for lane, path in LANE_PATHS.items():
            for lane_order, t, kind in tlist:
                x, y = point_along(path, t)
                towers.append({"team": team, "x": x, "y": y, "kind": kind,
                               "lane": lane, "lane_order": lane_order})

    cores = [{"team": team, "x": x, "y": y}
             for team, (x, y) in CORE_POSITIONS.items()]
    fountains = [{"team": team, "x": x, "y": y}
                 for team, (x, y) in SPAWN_POSITIONS.items()]
    camps = [{"x": x, "y": y, "count": n} for (x, y, n) in JUNGLE_CAMPS]
    runes = [{"x": r["zone"][0] + r["zone"][2] / 2,
              "y": r["zone"][1] + r["zone"][3] / 2,
              "zone": r["zone"], "patrol": r["patrol"], "buff": r["buff"]}
             for r in RUNES]
    return {"towers": towers, "cores": cores, "fountains": fountains,
            "camps": camps, "runes": runes}


# ----- camera (pan + zoom over the world) ------------------------------------
class Camera:
    """Maps world<->screen with a zoom factor; (x, y) is the world point at the
    viewport's top-left corner. Clamped so the view never leaves the map."""

    MIN_ZOOM = 0.04
    MAX_ZOOM = 3.0

    def __init__(self, view_w: int, view_h: int) -> None:
        self.vw, self.vh = view_w, view_h
        self.fit()

    def resize(self, view_w: int, view_h: int) -> None:
        self.vw, self.vh = view_w, view_h
        self._clamp()

    def fit(self) -> None:
        """Frame the whole map, centered, with a little margin."""
        self.zoom = min(self.vw / MAP_WIDTH, self.vh / MAP_HEIGHT) * 0.96
        self.x = MAP_WIDTH / 2 - self.vw / (2 * self.zoom)
        self.y = MAP_HEIGHT / 2 - self.vh / (2 * self.zoom)
        self._clamp()

    def world_to_screen(self, wx: float, wy: float) -> tuple[int, int]:
        return (int((wx - self.x) * self.zoom), int((wy - self.y) * self.zoom))

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx / self.zoom + self.x, sy / self.zoom + self.y)

    def scale(self, world_len: float) -> int:
        return max(1, int(world_len * self.zoom))

    def zoom_at(self, sx: float, sy: float, factor: float) -> None:
        """Zoom by ``factor`` keeping the world point under (sx, sy) fixed."""
        wx, wy = self.screen_to_world(sx, sy)
        self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom * factor))
        self.x, self.y = wx - sx / self.zoom, wy - sy / self.zoom
        self._clamp()

    def pan_pixels(self, dx: float, dy: float) -> None:
        self.x -= dx / self.zoom
        self.y -= dy / self.zoom
        self._clamp()

    def _clamp(self) -> None:
        vw_world, vh_world = self.vw / self.zoom, self.vh / self.zoom
        if vw_world >= MAP_WIDTH:
            self.x = (MAP_WIDTH - vw_world) / 2
        else:
            self.x = max(0.0, min(MAP_WIDTH - vw_world, self.x))
        if vh_world >= MAP_HEIGHT:
            self.y = (MAP_HEIGHT - vh_world) / 2
        else:
            self.y = max(0.0, min(MAP_HEIGHT - vh_world, self.y))


class MapExplorer:
    PAN_SPEED = 16  # pixels/frame for keyboard panning

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("project-gameph — Map Explorer")
        self.w, self.h = 1280, 820
        self.screen = pygame.display.set_mode((self.w, self.h), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font_s = pygame.font.SysFont("monospace", 12)
        self.font = pygame.font.SysFont("monospace", 14)
        self.font_b = pygame.font.SysFont("monospace", 20, bold=True)

        self.data = build_map_data()
        self.cam = Camera(self.w, self.h)
        self._make_overlay()
        self._place_minimap()

        # Persistent clicked markers (world coords) + drag/pan state.
        self.markers: list[tuple[float, float]] = []
        self.dragging = False
        # Layer toggles.
        self.show = {
            "grid": True, "lanes": True, "river": True, "walls": True,
            "trees": True, "structures": True, "neutrals": True,
            "ranges": True, "zones": True, "labels": True, "help": False,
        }
        self.running = True

    # ----- layout that depends on the window size ---------------------------
    def _make_overlay(self) -> None:
        self.overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)

    def _place_minimap(self) -> None:
        mm_w = 240
        mm_h = int(mm_w * MAP_HEIGHT / MAP_WIDTH)
        self.minimap = pygame.Rect(self.w - 12 - mm_w, self.h - 12 - mm_h,
                                   mm_w, mm_h)

    def _on_resize(self, w: int, h: int) -> None:
        self.w, self.h = max(640, w), max(480, h)
        self.screen = pygame.display.set_mode((self.w, self.h), pygame.RESIZABLE)
        self.cam.resize(self.w, self.h)
        self._make_overlay()
        self._place_minimap()

    # ----- main loop --------------------------------------------------------
    def run(self) -> None:
        while self.running:
            self._handle_events()
            self._handle_held_keys()
            self._draw()
            self.clock.tick(60)
        pygame.quit()

    def _handle_events(self) -> None:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.VIDEORESIZE:
                self._on_resize(ev.w, ev.h)
            elif ev.type == pygame.KEYDOWN:
                self._on_key(ev.key)
            elif ev.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                self.cam.zoom_at(mx, my, 1.12 ** ev.y)
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                self._on_mouse_down(ev)
            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button in (2, 3):
                    self.dragging = False
            elif ev.type == pygame.MOUSEMOTION and self.dragging:
                self.cam.pan_pixels(ev.rel[0], ev.rel[1])

    def _on_key(self, key: int) -> None:
        if key in (pygame.K_ESCAPE, pygame.K_q):
            self.running = False
        elif key == pygame.K_f:
            self.cam.fit()
        elif key == pygame.K_c:
            self.markers.clear()
        else:
            toggle = {
                pygame.K_g: "grid", pygame.K_l: "lanes", pygame.K_v: "river",
                pygame.K_w: "walls", pygame.K_t: "trees",
                pygame.K_s: "structures", pygame.K_n: "neutrals",
                pygame.K_r: "ranges", pygame.K_z: "zones",
                pygame.K_i: "labels", pygame.K_h: "help",
            }.get(key)
            if toggle:
                self.show[toggle] = not self.show[toggle]

    def _on_mouse_down(self, ev) -> None:
        if ev.button in (2, 3):           # middle / right -> start panning
            self.dragging = True
            return
        if ev.button != 1:                # only the left button acts below
            return
        # Click on the minimap -> recenter the main view + report coordinates.
        if self.minimap.collidepoint(ev.pos):
            wx, wy = self._minimap_to_world(*ev.pos)
            self.cam.x = wx - self.cam.vw / (2 * self.cam.zoom)
            self.cam.y = wy - self.cam.vh / (2 * self.cam.zoom)
            self.cam._clamp()
            print(f"minimap click -> world ({wx:.0f}, {wy:.0f})")
            return
        # Click on the main map -> drop a coordinate marker.
        wx, wy = self.cam.screen_to_world(*ev.pos)
        self.markers.append((wx, wy))
        print(f"marker -> world ({wx:.0f}, {wy:.0f})")

    def _handle_held_keys(self) -> None:
        # Arrow keys pan (held). Letters are reserved for layer toggles, so we
        # deliberately don't bind WASD here.
        keys = pygame.key.get_pressed()
        dx = keys[pygame.K_LEFT] - keys[pygame.K_RIGHT]
        dy = keys[pygame.K_UP] - keys[pygame.K_DOWN]
        if dx or dy:
            self.cam.pan_pixels(dx * self.PAN_SPEED, dy * self.PAN_SPEED)

    def _minimap_to_world(self, sx: int, sy: int) -> tuple[float, float]:
        mm = self.minimap
        return ((sx - mm.left) / mm.width * MAP_WIDTH,
                (sy - mm.top) / mm.height * MAP_HEIGHT)

    # ----- drawing ----------------------------------------------------------
    def _draw(self) -> None:
        self.screen.fill(COLOR_BG)
        self.overlay.fill((0, 0, 0, 0))

        if self.show["grid"]:
            self._draw_grid()
        if self.show["river"]:
            self._draw_river()
        if self.show["lanes"]:
            self._draw_lanes()
        if self.show["zones"]:
            self._draw_zones()
        if self.show["ranges"]:
            self._draw_range_fills()        # faint fills onto the overlay

        self.screen.blit(self.overlay, (0, 0))

        if self.show["walls"]:
            self._draw_capsules(WALLS, C_WALL)
        if self.show["trees"]:
            self._draw_capsules(TREES, C_TREE)
        if self.show["structures"]:
            self._draw_structures()
        if self.show["neutrals"]:
            self._draw_neutrals()
        if self.show["ranges"]:
            self._draw_range_outlines()     # crisp rings on top of terrain

        self._draw_markers()
        self._draw_map_border()
        self._draw_minimap()
        self._draw_hud()
        pygame.display.flip()

    def _draw_grid(self) -> None:
        step = 500  # world units between grid lines
        for gx in range(0, MAP_WIDTH + 1, step):
            a = self.cam.world_to_screen(gx, 0)
            b = self.cam.world_to_screen(gx, MAP_HEIGHT)
            pygame.draw.line(self.screen, COLOR_GRID, a, b, 1)
        for gy in range(0, MAP_HEIGHT + 1, step):
            a = self.cam.world_to_screen(0, gy)
            b = self.cam.world_to_screen(MAP_WIDTH, gy)
            pygame.draw.line(self.screen, COLOR_GRID, a, b, 1)

    def _draw_river(self) -> None:
        if RIVER is None:
            return
        p1 = self.cam.world_to_screen(RIVER.x1, RIVER.y1)
        p2 = self.cam.world_to_screen(RIVER.x2, RIVER.y2)
        thpx = self.cam.scale(RIVER.thickness)
        pygame.draw.line(self.overlay, (*C_RIVER, 70), p1, p2, thpx)

    def _draw_lanes(self) -> None:
        thpx = self.cam.scale(LANE_WIDTH)
        for path in LANE_PATHS.values():
            pts = [self.cam.world_to_screen(x, y) for x, y in path]
            pygame.draw.lines(self.screen, COLOR_LANE, False, pts, thpx)
            for p in pts:
                pygame.draw.circle(self.screen, COLOR_LANE, p, thpx // 2)

    def _draw_zones(self) -> None:
        # Spawn-point regen zones around each core.
        if SPAWN_ZONE_RADIUS:
            for core in self.data["cores"]:
                c = self.cam.world_to_screen(core["x"], core["y"])
                pygame.draw.circle(self.screen, C_SPAWN_ZONE, c,
                                   self.cam.scale(SPAWN_ZONE_RADIUS), 1)
        # Rune spawn zones (rect) + patrol radius.
        for rune in self.data["runes"]:
            x, y, w, h = rune["zone"]
            a = self.cam.world_to_screen(x, y)
            pygame.draw.rect(self.screen, C_RUNE,
                             (a[0], a[1], self.cam.scale(w), self.cam.scale(h)), 1)
            c = self.cam.world_to_screen(rune["x"], rune["y"])
            pygame.draw.circle(self.screen, C_RUNE, c,
                               self.cam.scale(rune["patrol"]), 1)
        # Wave-1 meeting points.
        for name, (x, y) in MEET_POINTS.items():
            c = self.cam.world_to_screen(x, y)
            pygame.draw.line(self.screen, C_MEET, (c[0] - 6, c[1]),
                             (c[0] + 6, c[1]), 1)
            pygame.draw.line(self.screen, C_MEET, (c[0], c[1] - 6),
                             (c[0], c[1] + 6), 1)
            if self.show["labels"]:
                self._label(f"meet:{name}", c[0] + 8, c[1] - 6, C_MEET)

    def _draw_capsules(self, capsules, color) -> None:
        for cap in capsules:
            p1 = self.cam.world_to_screen(*cap["p1"])
            p2 = self.cam.world_to_screen(*cap["p2"])
            thpx = self.cam.scale(cap["thickness"])
            pygame.draw.line(self.screen, color, p1, p2, thpx)
            pygame.draw.circle(self.screen, color, p1, thpx // 2)
            pygame.draw.circle(self.screen, color, p2, thpx // 2)

    def _draw_structures(self) -> None:
        for f in self.data["fountains"]:
            c = self.cam.world_to_screen(f["x"], f["y"])
            pygame.draw.circle(self.screen, C_FOUNTAIN, c, self.cam.scale(70))
            pygame.draw.circle(self.screen, team_color(f["team"]), c,
                               self.cam.scale(70), 2)
            if self.show["labels"]:
                self._label("fountain", c[0] + 10, c[1] - 6, C_FOUNTAIN)
        for t in self.data["towers"]:
            c = self.cam.world_to_screen(t["x"], t["y"])
            r = self.cam.scale(TOWER_RADIUS)
            rect = pygame.Rect(c[0] - r, c[1] - r, r * 2, r * 2)
            pygame.draw.rect(self.screen, team_color(t["team"]), rect,
                             border_radius=3)
            if self.show["labels"]:
                self._label(f"{t['lane']}/{t['kind']}", c[0] + r + 3,
                            c[1] - 6, team_color(t["team"]))
        for core in self.data["cores"]:
            c = self.cam.world_to_screen(core["x"], core["y"])
            r = self.cam.scale(CORE_RADIUS)
            rect = pygame.Rect(c[0] - r, c[1] - r, r * 2, r * 2)
            pygame.draw.rect(self.screen, team_color(core["team"]), rect,
                             border_radius=4)
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 2,
                             border_radius=4)
            if self.show["labels"]:
                self._label("core", c[0] + r + 3, c[1] - 6,
                            brighten(team_color(core["team"])))

    def _draw_neutrals(self) -> None:
        for camp in self.data["camps"]:
            c = self.cam.world_to_screen(camp["x"], camp["y"])
            pygame.draw.circle(self.screen, C_NEUTRAL, c,
                               self.cam.scale(NEUTRAL_RADIUS))
            pygame.draw.circle(self.screen, brighten(C_NEUTRAL), c,
                               self.cam.scale(55), 1)
            if self.show["labels"]:
                self._label(f"x{camp['count']}", c[0] + 8, c[1] - 6, C_NEUTRAL)
        for rune in self.data["runes"]:
            c = self.cam.world_to_screen(rune["x"], rune["y"])
            pygame.draw.circle(self.screen, C_RUNE, c, self.cam.scale(NEUTRAL_RADIUS))
            if self.show["labels"]:
                self._label(f"rune:{rune['buff']}", c[0] + 8, c[1] - 6, C_RUNE)

    def _draw_range_fills(self) -> None:
        """Faint translucent attack-range disks onto the alpha overlay."""
        for t in self.data["towers"]:
            c = self.cam.world_to_screen(t["x"], t["y"])
            pygame.draw.circle(self.overlay, (*team_color(t["team"]), 16), c,
                               self.cam.scale(TOWER_RANGE))
        for core in self.data["cores"]:
            c = self.cam.world_to_screen(core["x"], core["y"])
            pygame.draw.circle(self.overlay, (*team_color(core["team"]), 16), c,
                               self.cam.scale(TOWER_RANGE))
        for camp in self.data["camps"]:
            c = self.cam.world_to_screen(camp["x"], camp["y"])
            pygame.draw.circle(self.overlay, (*C_NEUTRAL, 18), c,
                               self.cam.scale(NEUTRAL_RANGE))

    def _draw_range_outlines(self) -> None:
        """Crisp attack-range rings, drawn on top so they read over terrain."""
        for t in self.data["towers"]:
            c = self.cam.world_to_screen(t["x"], t["y"])
            pygame.draw.circle(self.screen, team_color(t["team"]), c,
                               self.cam.scale(TOWER_RANGE), 1)
        for core in self.data["cores"]:
            c = self.cam.world_to_screen(core["x"], core["y"])
            pygame.draw.circle(self.screen, brighten(team_color(core["team"])),
                               c, self.cam.scale(TOWER_RANGE), 2)
        for camp in self.data["camps"]:
            c = self.cam.world_to_screen(camp["x"], camp["y"])
            pygame.draw.circle(self.screen, C_NEUTRAL, c,
                               self.cam.scale(NEUTRAL_RANGE), 1)

    def _draw_markers(self) -> None:
        # A measuring line from the last marker to the cursor (world distance).
        mx, my = pygame.mouse.get_pos()
        if self.markers and not self.minimap.collidepoint(mx, my):
            last = self.markers[-1]
            a = self.cam.world_to_screen(*last)
            wx, wy = self.cam.screen_to_world(mx, my)
            dist = ((wx - last[0]) ** 2 + (wy - last[1]) ** 2) ** 0.5
            pygame.draw.line(self.screen, C_MEASURE, a, (mx, my), 1)
            self._label(f"{dist:.0f}", (a[0] + mx) // 2 + 6,
                        (a[1] + my) // 2, C_MEASURE)
        for wx, wy in self.markers:
            c = self.cam.world_to_screen(wx, wy)
            pygame.draw.line(self.screen, C_MARKER, (c[0] - 7, c[1]),
                             (c[0] + 7, c[1]), 1)
            pygame.draw.line(self.screen, C_MARKER, (c[0], c[1] - 7),
                             (c[0], c[1] + 7), 1)
            pygame.draw.circle(self.screen, C_MARKER, c, 3, 1)
            self._label(f"({wx:.0f}, {wy:.0f})", c[0] + 9, c[1] + 4, C_MARKER)

    def _draw_map_border(self) -> None:
        corners = [self.cam.world_to_screen(0, 0),
                   self.cam.world_to_screen(MAP_WIDTH, 0),
                   self.cam.world_to_screen(MAP_WIDTH, MAP_HEIGHT),
                   self.cam.world_to_screen(0, MAP_HEIGHT)]
        pygame.draw.lines(self.screen, C_BORDER, True, corners, 1)

    def _draw_minimap(self) -> None:
        mm = self.minimap
        panel = pygame.Surface((mm.width, mm.height))
        panel.set_alpha(225)
        panel.fill((18, 26, 16))
        self.screen.blit(panel, (mm.left, mm.top))
        pygame.draw.rect(self.screen, C_BORDER, mm, 1)

        def to_mm(wx, wy):
            return (int(mm.left + wx / MAP_WIDTH * mm.width),
                    int(mm.top + wy / MAP_HEIGHT * mm.height))

        def mm_scale(world_len):
            return max(1, int(world_len / MAP_WIDTH * mm.width))

        if RIVER is not None:
            pygame.draw.line(self.screen, (60, 100, 150),
                             to_mm(RIVER.x1, RIVER.y1),
                             to_mm(RIVER.x2, RIVER.y2), 1)
        for path in LANE_PATHS.values():
            pygame.draw.lines(self.screen, COLOR_LANE, False,
                              [to_mm(x, y) for x, y in path], 1)
        for cap in WALLS:
            pygame.draw.line(self.screen, C_WALL, to_mm(*cap["p1"]),
                             to_mm(*cap["p2"]), 1)
        for cap in TREES:
            pygame.draw.line(self.screen, C_TREE, to_mm(*cap["p1"]),
                             to_mm(*cap["p2"]), 1)
        # Tower attack range on the minimap (the explicit ask).
        for t in self.data["towers"]:
            c = to_mm(t["x"], t["y"])
            pygame.draw.circle(self.screen, team_color(t["team"]), c,
                               mm_scale(TOWER_RANGE), 1)
            pygame.draw.rect(self.screen, team_color(t["team"]),
                             (c[0] - 1, c[1] - 1, 3, 3))
        for core in self.data["cores"]:
            c = to_mm(core["x"], core["y"])
            pygame.draw.circle(self.screen, brighten(team_color(core["team"])),
                               c, mm_scale(TOWER_RANGE), 1)
            pygame.draw.rect(self.screen, (255, 255, 255),
                             (c[0] - 2, c[1] - 2, 4, 4))
        for camp in self.data["camps"]:
            pygame.draw.circle(self.screen, C_NEUTRAL, to_mm(camp["x"], camp["y"]), 1)
        for rune in self.data["runes"]:
            pygame.draw.circle(self.screen, C_RUNE, to_mm(rune["x"], rune["y"]), 2)
        for f in self.data["fountains"]:
            pygame.draw.circle(self.screen, C_FOUNTAIN, to_mm(f["x"], f["y"]), 2)
        for wx, wy in self.markers:
            pygame.draw.circle(self.screen, C_MARKER, to_mm(wx, wy), 1)

        # Current main-view viewport rectangle.
        vx, vy = to_mm(self.cam.x, self.cam.y)
        vw = mm_scale(self.cam.vw / self.cam.zoom)
        vh = mm_scale(self.cam.vh / self.cam.zoom)
        pygame.draw.rect(self.screen, (230, 230, 230), (vx, vy, vw, vh), 1)

    def _draw_hud(self) -> None:
        mx, my = pygame.mouse.get_pos()
        if self.minimap.collidepoint(mx, my):
            wx, wy = self._minimap_to_world(mx, my)
            where = "minimap"
        else:
            wx, wy = self.cam.screen_to_world(mx, my)
            where = "map"
        lines = [
            ("MAP EXPLORER", C_TEXT),
            (f"cursor [{where}]: ({wx:.0f}, {wy:.0f})", C_TEXT),
            (f"zoom: {self.cam.zoom:.3f}x   map: {MAP_WIDTH}x{MAP_HEIGHT}", C_DIM),
        ]
        if self.markers:
            lx, ly = self.markers[-1]
            lines.append((f"last marker: ({lx:.0f}, {ly:.0f})  "
                          f"({len(self.markers)} total)", C_MARKER))
        lines.append(("H: help   F: fit   C: clear markers", C_DIM))

        if self.show["help"]:
            lines += [("", C_DIM)]
            lines += [(t, C_DIM) for t in (
                "left click: drop marker / report coords",
                "click minimap: recenter view",
                "right or middle drag: pan   wheel: zoom",
                "arrow keys: pan",
                "toggles: G grid  L lanes  V river  W walls  T trees",
                "         S structures  N neutrals  R ranges",
                "         Z zones  I labels",
            )]
            on = "  ".join(f"{k}:{'on' if v else 'off'}" for k, v in self.show.items()
                           if k != "help")
            lines.append((on, C_DIM))

        rendered = [(self.font_b if i == 0 else self.font).render(t, True, c)
                    for i, (t, c) in enumerate(lines)]
        pad, lh = 8, 18
        w = max(r.get_width() for r in rendered) + pad * 2
        h = len(rendered) * lh + pad
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((10, 14, 20, 200))
        self.screen.blit(panel, (8, 8))
        pygame.draw.rect(self.screen, C_BORDER, (8, 8, w, h), 1)
        for i, r in enumerate(rendered):
            self.screen.blit(r, (8 + pad, 8 + pad // 2 + i * lh))

    def _label(self, text: str, x: int, y: int, color) -> None:
        self.screen.blit(self.font_s.render(text, True, color), (x, y))


def main() -> None:
    MapExplorer().run()


if __name__ == "__main__":
    main()
