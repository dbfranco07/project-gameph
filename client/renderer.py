"""Render the game world using Pygame.

Entities are drawn by a small per-type drawer registry keyed on the snapshot's
entity-type tag ("et"). Each drawer reads a shape descriptor today; swapping a
descriptor to a sprite later needs no gameplay changes.
"""

from __future__ import annotations

import math
import time
import pygame
from shared.geometry import closest_point_on_segment
from shared.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    MAP_WIDTH,
    MAP_HEIGHT,
    LANE_PATHS,
    JUNGLE_CAMPS,
    LANE_WIDTH,
    COLOR_BG,
    COLOR_TEAM1,
    COLOR_TEAM2,
    COLOR_HEALTH_BG,
    COLOR_HEALTH,
    COLOR_MANA,
    COLOR_GRID,
    COLOR_TEXT,
    COLOR_PROJECTILE,
    COLOR_STRUCTURE_DEAD,
    COLOR_LANE,
    PASSIVE_GOLD_PER_SEC,
    RIVER,
    HERO_VISION_RADIUS,
    MINION_VISION_RADIUS,
    TOWER_VISION_RADIUS,
)
from shared.game_types import Team, GamePhase, EntityType

# Fog-of-war overlay: ground outside your vision is darkened by this much
# (0 = off, 255 = pitch black). Vision footprints are punched back to full
# brightness, so seen areas read lighter than the fogged ones.
FOG_ALPHA = 95
# The fog/vision mask is built at 1/FOG_SCALE resolution then smoothscaled up
# once per frame -- it's a soft darkening overlay, not crisp art, so the
# downsample is invisible while cutting circle/polygon fill cost by FOG_SCALE**2.
FOG_SCALE = 2
from client.camera import Camera
from client.sprites import SpriteManager, facing_from_delta

# Combat-feedback timing (seconds).
CAST_DUR = 0.4      # how long a one-shot skill-cast pose plays
FLASH_DUR = 0.12    # white/red hit flash on a unit that just took damage
LUNGE_DUR = 0.14    # attacker lunge + victim recoil duration
LUNGE_PX = 7.0      # attacker step toward its target on a hit
RECOIL_PX = 5.0     # victim knock-back on a hit

# Per-fx fallback ring colors (used when no effect art exists on disk).
_FX_COLORS = {
    "smash": (235, 150, 60), "earthshatter": (210, 120, 50),
    "arrowstorm": (240, 220, 120), "renewwave": (120, 220, 150),
    "sanctuary": (150, 235, 170),
}


def _ease_out(t: float) -> float:
    """0->1 eased; a quick step that settles (for lunge/recoil)."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) * (1.0 - t)


def _add_step(ox, oy, me, other, dist_px, age, toward):
    """Add a lunge/recoil offset (px) along me<->other, peaking early then
    settling. `toward` True = step toward `other`, False = away from it."""
    age_frac = age / LUNGE_DUR
    mag = dist_px * (1.0 - _ease_out(age_frac))  # quick out, ease back to 0
    dx = other["x"] - me["x"]
    dy = other["y"] - me["y"]
    d = math.hypot(dx, dy)
    if d < 1e-6:
        return ox, oy
    s = (1.0 if toward else -1.0) * mag / d
    return ox + dx * s, oy + dy * s


def _team_color(team: int) -> tuple[int, int, int]:
    if team == Team.TEAM1:
        return COLOR_TEAM1
    if team == Team.TEAM2:
        return COLOR_TEAM2
    return (180, 180, 180)


def _capsule_corners(p1, p2, thpx):
    """Four corners of the rectangle body of a screen-space capsule (p1->p2 with
    pixel thickness ``thpx``), for drawing its outline. [] if p1 == p2."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length < 1e-6:
        return []
    nx, ny = -dy / length * thpx / 2.0, dx / length * thpx / 2.0
    return [(p1[0] + nx, p1[1] + ny), (p2[0] + nx, p2[1] + ny),
            (p2[0] - nx, p2[1] - ny), (p1[0] - nx, p1[1] - ny)]


class Renderer:
    def __init__(self, screen: pygame.Surface, camera: Camera) -> None:
        self.screen = screen
        self.camera = camera
        # Optional sprite art (falls back to primitive shapes when absent).
        self.sprites = SpriteManager()
        # Per-entity render memory for deriving facing + move/idle from motion:
        # id -> {"x", "y", "facing"}.
        self._unit_pose: dict[int, dict] = {}
        self.font = pygame.font.SysFont("monospace", 14)
        self.font_large = pygame.font.SysFont("monospace", 24)
        self.font_huge = pygame.font.SysFont("monospace", 48, bold=True)
        # Ability metadata for the local hero (key/name/cd/mana/cast), delivered
        # from the server in JOIN_ACK. Used to draw the ability bar.
        self.hero_abilities: list[dict] = []
        # Key of an ability currently awaiting a target click (highlighted).
        self.pending_cast: str | None = None
        # True while an 'A' attack command is waiting for a target click.
        self.attack_armed = False
        # Shop catalog + open state.
        self.item_catalog: list[dict] = []
        self.shop_open = False
        # Minimap panel (bottom-left), map aspect ratio preserved.
        mm_w = 240
        mm_h = int(mm_w * MAP_HEIGHT / MAP_WIDTH)
        self.minimap = pygame.Rect(8, SCREEN_HEIGHT - 8 - mm_h, mm_w, mm_h)
        # In-game chat box (set by the client); drawn just above the minimap.
        self.chat = None
        # Floating combat text (gold/xp/damage popups): {wx,wy,text,color,born,dur}.
        self.floaters: list[dict] = []
        # Combat feedback state, all keyed/aged off server `hit`/`fx` events:
        self._last_hit: dict[int, float] = {}       # eid -> monotonic time of last hit
        self._lunge: dict[int, dict] = {}           # attacker eid -> {t0, tgt}
        self._recoil: dict[int, dict] = {}          # victim eid -> {t0, src}
        self._ground_fx: list[dict] = []            # AoE decals, under units
        self._spark_fx: list[dict] = []             # hit sparks, over units
        # Per-projectile heading memory (id -> (x, y, heading)) for rotation.
        self._proj_pose: dict[int, tuple] = {}
        # Terrain texture caches (built lazily from assets/terrain/*.png).
        self._ground_cache: pygame.Surface | None = None
        self._strip_cache: dict[tuple, pygame.Surface] = {}
        # Fog-of-war: reusable overlay surfaces (allocated lazily, sized once)
        # plus a per-source world-space visibility-polygon cache so a vision
        # source's raycast is only redone when its own position/radius/occluder
        # set changes, not every frame just because the camera panned.
        # The mask itself is built at reduced resolution (FOG_SCALE) and
        # smoothscaled up once at the end -- fog edges are a soft darkening
        # overlay to begin with, so the lower-res mask is indistinguishable
        # on screen while cutting circle/polygon fill cost by FOG_SCALE**2.
        self._fog: pygame.Surface | None = None
        self._vis: pygame.Surface | None = None
        self._fog_upscaled: pygame.Surface | None = None
        self._vis_poly_cache: dict[int, tuple] = {}
        # smoothscale results, keyed by (source surface identity, target size).
        # Sprite frames are loaded once and reused by SpriteManager, so the same
        # frame gets asked to scale to the same size over and over every frame.
        self._scale_cache: dict[tuple[int, tuple[int, int]], pygame.Surface] = {}
        # Minimap static background (panel fill + river/lane/wall/tree lines),
        # rebuilt only when the alive wall/tree set changes (e.g. a tree died
        # or respawned) instead of redrawn from scratch every frame.
        self._minimap_bg: pygame.Surface | None = None
        self._minimap_bg_sig: tuple | None = None
        # The current frame's entity list, stashed for owner/target lookups.
        self._frame_entities: list[dict] = []

    def add_combat_events(self, events) -> None:
        """Turn server combat events into floating text + feedback state.

        gold/xp -> rising reward popups; hit -> damage number + flash + lunge/
        recoil + impact spark; heal -> green number; fx -> AoE ground decal.
        """
        now = time.monotonic()
        for ev in events or []:
            kind = ev.get("k")
            if kind == "gold":
                self._floater(ev, f"+{ev['amt']}g", (240, 215, 90), 1.1)
            elif kind == "xp":
                self._floater(ev, f"+{ev['amt']} xp", (150, 200, 255), 1.1)
            elif kind == "hit":
                eid, src = ev.get("eid"), ev.get("src")
                self._floater(ev, f"-{ev['amt']}", (235, 90, 90), 0.8)
                if eid is not None:
                    self._last_hit[eid] = now
                    if src is not None:
                        self._recoil[eid] = {"t0": now, "src": src}
                if src is not None and eid is not None:
                    self._lunge[src] = {"t0": now, "tgt": eid}
                spark = ("hit_special" if ev.get("dt") == "special"
                         else "hit_phys")
                self._spark_fx.append({"name": spark, "wx": ev["x"],
                                       "wy": ev["y"], "r": 22,
                                       "born": now, "dur": 0.3})
            elif kind == "heal":
                self._floater(ev, f"+{ev['amt']}", (120, 220, 150), 0.9)
            elif kind == "fx":
                self._ground_fx.append({
                    "name": ev.get("name", ""), "wx": ev["x"], "wy": ev["y"],
                    "r": ev.get("r", 0), "born": now,
                    "dur": ev.get("dur", 0.5)})

    def _floater(self, ev, text, color, dur) -> None:
        self.floaters.append({"wx": ev["x"], "wy": ev["y"], "text": text,
                              "color": color, "born": time.monotonic(),
                              "dur": dur})

    def set_hero_abilities(self, abilities: list[dict]) -> None:
        self.hero_abilities = abilities or []

    def set_item_catalog(self, catalog: list[dict]) -> None:
        self.item_catalog = catalog or []

    def minimap_to_world(self, sx: int, sy: int):
        """If (sx, sy) is inside the minimap, return its world point, else None."""
        mm = self.minimap
        if not mm.collidepoint(sx, sy):
            return None
        wx = (sx - mm.left) / mm.width * MAP_WIDTH
        wy = (sy - mm.top) / mm.height * MAP_HEIGHT
        return wx, wy

    # ----- top-level frame --------------------------------------------------
    def draw_frame(self, entities, my_entity_id, my_team, phase, tick,
                   score=None, ktarget=0, winner=0, clock=0.0) -> None:
        self._frame_entities = entities
        self.screen.fill(COLOR_BG)
        self._draw_grid()
        self._draw_river()
        self._draw_lane()
        self._draw_map_border()
        self._draw_ground_fx()  # AoE decals/shockwaves under the units

        # Walls/trees under units; structures/minions next; heroes/projectiles on top.
        order = {EntityType.WALL: -1, EntityType.TREE: -1,
                 EntityType.TOWER: 0, EntityType.BASE: 0, EntityType.MINION: 1,
                 EntityType.HERO: 2, EntityType.PROJECTILE: 3}
        for ent in sorted(entities, key=lambda e: order.get(e.get("et"), 2)):
            self._draw_entity(ent, ent["id"] == my_entity_id if my_entity_id else False)

        self._draw_spark_fx()   # impact sparks over the units
        self._draw_fog(entities, my_team)
        self._draw_floaters()
        self._draw_hud(entities, my_entity_id, my_team, phase, tick,
                       score or {}, ktarget, winner, clock)
        self._draw_targeting_cursor()
        if self.chat is not None:
            self.chat.draw(self.screen, self.font, self.minimap.top - 12)
        self._prune_feedback()
        pygame.display.flip()

    def _draw_floaters(self) -> None:
        """Render gold/xp popups rising and fading above their world position."""
        now = time.monotonic()
        alive = []
        for f in self.floaters:
            age = now - f["born"]
            if age >= f["dur"]:
                continue
            alive.append(f)
            sx, sy = self.camera.world_to_screen(f["wx"], f["wy"])
            sy -= int(age * 34) + 24  # rise over time, start above the unit
            if sx < -50 or sx > SCREEN_WIDTH + 50 or sy < -20 or sy > SCREEN_HEIGHT:
                continue
            label = self.font.render(f["text"], True, f["color"])
            label.set_alpha(int(255 * (1 - age / f["dur"])))
            self.screen.blit(label, (sx - label.get_width() // 2, sy))
        self.floaters = alive

    def _draw_ground_fx(self) -> None:
        """AoE decals/shockwaves under the units. Sprite if present, else an
        expanding fading ring keyed to the effect's radius."""
        now = time.monotonic()
        alive = []
        for f in self._ground_fx:
            age = now - f["born"]
            if age >= f["dur"]:
                continue
            alive.append(f)
            sx, sy = self.camera.world_to_screen(f["wx"], f["wy"])
            r = max(8, int(f["r"]))
            surf = self.sprites.effect_frame(f["name"], age)
            if surf is not None:
                size = r * 2
                if surf.get_width() != size:
                    surf = self._scaled(surf, (size, size))
                self.screen.blit(surf, (sx - size // 2, sy - size // 2))
            else:
                frac = age / f["dur"]
                col = _FX_COLORS.get(f["name"], (220, 220, 220))
                ring = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
                a = int(180 * (1 - frac))
                pygame.draw.circle(ring, (*col, a), (r + 2, r + 2),
                                   max(2, int(r * frac)), 3)
                pygame.draw.circle(ring, (*col, a // 3), (r + 2, r + 2), r, 1)
                self.screen.blit(ring, (sx - r - 2, sy - r - 2))
        self._ground_fx = alive

    def _draw_spark_fx(self) -> None:
        """Short impact sparks over the units (from hit events)."""
        now = time.monotonic()
        alive = []
        for f in self._spark_fx:
            age = now - f["born"]
            if age >= f["dur"]:
                continue
            alive.append(f)
            sx, sy = self.camera.world_to_screen(f["wx"], f["wy"])
            surf = self.sprites.effect_frame(f["name"], age)
            if surf is not None:
                self.screen.blit(surf, (sx - surf.get_width() // 2,
                                        sy - surf.get_height() // 2))
            else:
                frac = age / f["dur"]
                base = ((150, 200, 255) if f["name"] == "hit_special"
                        else (255, 220, 150))
                rr = int(6 + 14 * frac)
                a = int(220 * (1 - frac))
                spark = pygame.Surface((rr * 2 + 2, rr * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(spark, (*base, a), (rr + 1, rr + 1), rr, 2)
                self.screen.blit(spark, (sx - rr - 1, sy - rr - 1))
        self._spark_fx = alive

    def _prune_feedback(self) -> None:
        """Drop expired hit/lunge/recoil entries so the dicts stay small."""
        now = time.monotonic()
        self._last_hit = {k: t for k, t in self._last_hit.items()
                          if now - t < FLASH_DUR}
        self._lunge = {k: v for k, v in self._lunge.items()
                       if now - v["t0"] < LUNGE_DUR}
        self._recoil = {k: v for k, v in self._recoil.items()
                        if now - v["t0"] < LUNGE_DUR}

    def _attack_offset(self, eid) -> tuple[float, float]:
        """Screen-space (ox, oy) lunge+recoil offset for unit `eid` this frame."""
        if eid is None:
            return 0.0, 0.0
        now = time.monotonic()
        ox = oy = 0.0
        me = self._find(self._frame_entities, eid)
        if me is None:
            return 0.0, 0.0
        lg = self._lunge.get(eid)
        if lg is not None:
            tgt = self._find(self._frame_entities, lg["tgt"])
            if tgt is not None:
                ox, oy = _add_step(ox, oy, me, tgt, LUNGE_PX,
                                   now - lg["t0"], toward=True)
        rc = self._recoil.get(eid)
        if rc is not None:
            src = self._find(self._frame_entities, rc["src"])
            if src is not None:
                ox, oy = _add_step(ox, oy, me, src, RECOIL_PX,
                                   now - rc["t0"], toward=False)
        return ox, oy

    def _draw_targeting_cursor(self) -> None:
        """Ring the cursor while awaiting a target: yellow for an ability cast,
        red for an 'A' attack command."""
        if self.pending_cast is not None:
            color, text = (240, 220, 120), f"Cast {self.pending_cast}"
        elif self.attack_armed:
            color, text = (235, 90, 90), "Attack"
        else:
            return
        mx, my = pygame.mouse.get_pos()
        pygame.draw.circle(self.screen, color, (mx, my), 16, 2)
        pygame.draw.circle(self.screen, color, (mx, my), 3)
        label = self.font.render(text, True, color)
        self.screen.blit(label, (mx + 18, my - 8))

    # ----- world ------------------------------------------------------------
    def _draw_grid(self) -> None:
        # Textured ground: tile the ground.png across the screen, offset by the
        # camera. Falls back to the faint grid lines when no tile art exists.
        if self._draw_ground_tiles():
            return
        grid_size = 200
        for gx in range(0, MAP_WIDTH + 1, grid_size):
            sx, sy = self.camera.world_to_screen(gx, 0)
            ex, ey = self.camera.world_to_screen(gx, MAP_HEIGHT)
            if -1 <= sx <= SCREEN_WIDTH + 1:
                pygame.draw.line(self.screen, COLOR_GRID, (sx, sy), (ex, ey), 1)
        for gy in range(0, MAP_HEIGHT + 1, grid_size):
            sx, sy = self.camera.world_to_screen(0, gy)
            ex, ey = self.camera.world_to_screen(MAP_WIDTH, gy)
            if -1 <= sy <= SCREEN_HEIGHT + 1:
                pygame.draw.line(self.screen, COLOR_GRID, (sx, sy), (ex, ey), 1)

    def _draw_ground_tiles(self) -> bool:
        """Blit the cached pre-tiled ground surface, or False if no ground art."""
        tile = self.sprites.terrain_tile("ground")
        if tile is None:
            return False
        tw, th = tile.get_width(), tile.get_height()
        if self._ground_cache is None:  # build a screen+1-tile tiled surface once
            cache = pygame.Surface((SCREEN_WIDTH + tw, SCREEN_HEIGHT + th))
            for ty in range(0, SCREEN_HEIGHT + th, th):
                for tx in range(0, SCREEN_WIDTH + tw, tw):
                    cache.blit(tile, (tx, ty))
            self._ground_cache = cache
        ox = -int(self.camera.x % tw)
        oy = -int(self.camera.y % th)
        self.screen.blit(self._ground_cache, (ox, oy))
        return True

    def _world_strip(self, name, p1, p2, width, fallback_rgba) -> None:
        """Draw a textured strip between two screen points (river/lane), or a
        translucent fallback band when the named tile is missing."""
        tile = self.sprites.terrain_tile(name)
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = int(math.hypot(dx, dy))
        if length < 1:
            return
        if tile is None:
            band = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            pygame.draw.line(band, fallback_rgba, p1, p2, width)
            self.screen.blit(band, (0, 0))
            return
        self._blit_tiled_strip(tile, (name, length, width), p1, p2,
                               length, width)

    def _blit_tiled_strip(self, tile, cache_key, p1, p2, length, width) -> None:
        """Tile `tile` into a length x width strip and rotate it to the p1->p2
        heading (both cached), then blit it centered on the segment midpoint.

        The camera only translates (never zooms/rotates), so for a given strip
        the heading between its two fixed world endpoints is the same every
        frame even as the camera pans -- only the on-screen midpoint moves.
        That makes the rotated surface just as cacheable as the unrotated
        tiled strip; rotating a long lane/river strip from scratch every frame
        was previously the single biggest CPU cost in the renderer."""
        angle = -math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
        rot_key = (cache_key, round(angle, 3))
        rot = self._strip_cache.get(rot_key)
        if rot is None:
            strip = self._strip_cache.get(cache_key)
            if strip is None:
                scaled = pygame.transform.smoothscale(tile, (tile.get_width(), width))
                strip = pygame.Surface((max(1, length), width), pygame.SRCALPHA)
                for tx in range(0, length, scaled.get_width()):
                    strip.blit(scaled, (tx, 0))
                self._strip_cache[cache_key] = strip
            rot = pygame.transform.rotate(strip, angle)
            self._strip_cache[rot_key] = rot
        mx, my = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
        self.screen.blit(rot, (mx - rot.get_width() // 2,
                               my - rot.get_height() // 2))

    def _draw_river(self) -> None:
        """The walkable river: a textured (or translucent) diagonal band under
        the lanes. Crosses the mid lane to form an X."""
        if RIVER is None:
            return
        p1 = self.camera.world_to_screen(RIVER.x1, RIVER.y1)
        p2 = self.camera.world_to_screen(RIVER.x2, RIVER.y2)
        thpx = max(2, int(RIVER.thickness))
        self._world_strip("river", p1, p2, thpx, (70, 130, 210, 70))

    def _draw_fog(self, entities, my_team) -> None:
        """Darken ground the player can't currently see. Each alive friendly
        vision source reveals a circle that is occluded by walls and trees (they
        cast shadows, just like the server's line-of-sight check), so areas you
        have vision over read lighter than the fogged ones.

        Reveals are accumulated into a separate mask with BLEND_RGBA_MAX (so a
        wall's shadow from one unit can't un-reveal what another unit sees), then
        subtracted from the fog. Radii mirror the server (no camera zoom, so world
        units == pixels); a hero in the split ult carries bonus sight via `visb`.
        Every vision source (heroes, towers, minions) is occluded by walls/trees;
        sources with no occluder nearby take a cheap plain-circle fast path.

        The two overlay surfaces are allocated once and reused every frame, and
        each source's raycast visibility polygon (the expensive part) is cached
        in world space keyed by its own (position, radius, occluder set) — it's
        only recomputed when one of those actually changes, not just because the
        camera panned. The camera only translates (no zoom), so a cache hit is
        just a cheap per-point offset instead of a full re-cast."""
        if FOG_ALPHA <= 0 or my_team not in (Team.TEAM1, Team.TEAM2):
            return  # spectators see everything; no fog overlay
        small_w = SCREEN_WIDTH // FOG_SCALE
        small_h = SCREEN_HEIGHT // FOG_SCALE
        if self._fog is None:
            self._fog = pygame.Surface((small_w, small_h), pygame.SRCALPHA)
            self._vis = pygame.Surface((small_w, small_h), pygame.SRCALPHA)
            self._fog_upscaled = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        blockers, blockers_sig = self._fog_blockers(entities)
        self._fog.fill((0, 0, 0, FOG_ALPHA))
        self._vis.fill((0, 0, 0, 0))
        cam_x, cam_y = self.camera.x, self.camera.y
        seen_ids = set()
        for ent in entities:
            if ent.get("tm") != my_team or not ent.get("a", True):
                continue
            et = ent.get("et")
            if et == EntityType.HERO:
                radius = int(HERO_VISION_RADIUS + ent.get("visb", 0))
            elif et in (EntityType.TOWER, EntityType.BASE):
                radius = int(TOWER_VISION_RADIUS)
            elif et == EntityType.MINION and not ent.get("body"):
                radius = int(MINION_VISION_RADIUS)  # split body grants no vision
            else:
                continue
            seen_ids.add(ent["id"])
            # A source whose reveal circle doesn't even overlap the screen
            # (e.g. a minion pushing a lane you're nowhere near) can't affect
            # any visible pixel -- skip the raycast/draw entirely. The id stays
            # in seen_ids so its cache entry isn't pruned as "despawned", just
            # left stale until it's on-screen again.
            sx_full, sy_full = ent["x"] - cam_x, ent["y"] - cam_y
            if (sx_full + radius < 0 or sx_full - radius > SCREEN_WIDTH or
                    sy_full + radius < 0 or sy_full - radius > SCREEN_HEIGHT):
                continue
            # A unit with unobstructed sight (e.g. bound in a tree/wall) reveals a
            # plain circle ignoring wall/tree shadows, matching the server.
            src_blockers, src_sig = (((), ()) if ent.get("unobs")
                                      else (blockers, blockers_sig))
            self._reveal_source(ent["id"], ent["x"], ent["y"], radius,
                                src_blockers, src_sig, cam_x, cam_y)
        # Drop cache entries for sources that despawned/died this frame so the
        # dict doesn't grow forever across a match.
        stale = self._vis_poly_cache.keys() - seen_ids
        for sid in stale:
            del self._vis_poly_cache[sid]
        self._fog.blit(self._vis, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        pygame.transform.smoothscale(self._fog, (SCREEN_WIDTH, SCREEN_HEIGHT),
                                      self._fog_upscaled)
        self.screen.blit(self._fog_upscaled, (0, 0))

    def _fog_blockers(self, entities) -> tuple:
        """World-space (x1,y1,x2,y2,thickness) for each alive wall/tree that
        blocks line of sight, plus a signature (their entity ids) cheap to
        compare across frames to know when the occluder set actually changed
        (e.g. a tree was destroyed or respawned)."""
        out = []
        sig = []
        for ent in entities:
            if ent.get("et") not in (EntityType.WALL, EntityType.TREE):
                continue
            if not ent.get("a", True) or ent.get("x1") is None:
                continue
            out.append((ent["x1"], ent["y1"], ent["x2"], ent["y2"], ent.get("th", 60)))
            sig.append(ent["id"])
        return tuple(out), tuple(sig)

    def _reveal_source(self, src_id, wx, wy, radius, blockers, blockers_sig,
                       cam_x, cam_y) -> None:
        """Reveal a vision source onto the mask `self._vis` (white = visible).
        With a wall/tree in range the lit area is a raycast visibility polygon
        (rays stop at occluders); otherwise it is a plain circle. Reveals from
        several sources just overdraw (vision is a union), so no per-source
        compositing is needed. The polygon is computed in world space and cached
        per source id; a cache hit just needs the camera offset applied."""
        key = (wx, wy, radius, blockers_sig)
        cached = self._vis_poly_cache.get(src_id)
        if cached is not None and cached[0] == key:
            poly = cached[1]
        else:
            poly = self._visibility_polygon(wx, wy, radius, blockers)
            self._vis_poly_cache[src_id] = (key, poly)
        # Geometry above is full-res world space (it must line up with actual
        # wall/tree positions); only the drawing onto the downsampled `_vis`
        # mask is scaled down here.
        sx, sy = int((wx - cam_x) / FOG_SCALE), int((wy - cam_y) / FOG_SCALE)
        if poly is None:
            pygame.draw.circle(self._vis, (255, 255, 255, 255), (sx, sy),
                               int(radius / FOG_SCALE))
        elif len(poly) >= 3:
            pts = [(int((x - cam_x) / FOG_SCALE), int((y - cam_y) / FOG_SCALE))
                   for x, y in poly]
            pygame.draw.polygon(self._vis, (255, 255, 255, 255), pts)

    def _visibility_polygon(self, sx, sy, radius, blockers):
        """Field-of-view polygon for a source at (sx, sy) — world-space
        coordinates, but the math is translation-invariant so it works
        identically in screen space; only the caller's choice of input matters.
        Casts rays around the circle, each stopping at the nearest wall/tree
        centerline in range (ends extended by half-thickness for the round
        caps). Returns the ring of hit points, or None when nothing occludes
        (caller draws a plain circle).

        Extra rays are aimed just to either side of every occluder endpoint so
        the shadow edges stay crisp instead of being rounded off by the ray step."""
        segs = []
        for (ax, ay, bx, by, th) in blockers:
            cpx, cpy = closest_point_on_segment(sx, sy, ax, ay, bx, by)
            if math.hypot(cpx - sx, cpy - sy) > radius + th * 0.5:
                continue  # too far to occlude anything inside the reveal circle
            ux, uy = bx - ax, by - ay
            seglen = math.hypot(ux, uy) or 1.0
            h = th * 0.5
            ux, uy = ux / seglen * h, uy / seglen * h
            segs.append((ax - ux, ay - uy, bx + ux, by + uy))
        if not segs:
            return None
        angles = [-math.pi + (2.0 * math.pi) * i / 160 for i in range(160)]
        eps = 0.0006
        for (ax, ay, bx, by) in segs:
            for ex, ey in ((ax, ay), (bx, by)):
                a = math.atan2(ey - sy, ex - sx)
                angles.append(a - eps)
                angles.append(a + eps)
        angles.sort()
        pts = []
        for ang in angles:
            dx, dy = math.cos(ang), math.sin(ang)
            t = float(radius)
            for (ax, ay, bx, by) in segs:
                tt = self._ray_segment(sx, sy, dx, dy, ax, ay, bx, by)
                if tt is not None and tt < t:
                    t = tt
            pts.append((sx + dx * t, sy + dy * t))
        return pts

    @staticmethod
    def _ray_segment(sx, sy, dx, dy, ax, ay, bx, by):
        """Distance along ray (sx,sy)+t*(dx,dy), t>=0, to its hit with segment
        (ax,ay)-(bx,by), or None. (dx,dy) is a unit vector, so t is in pixels."""
        ex, ey = bx - ax, by - ay
        denom = dx * ey - dy * ex
        if abs(denom) < 1e-9:
            return None  # parallel
        rx, ry = ax - sx, ay - sy
        t = (rx * ey - ry * ex) / denom    # along the ray
        u = (rx * dy - ry * dx) / denom    # along the segment
        if t >= 0.0 and 0.0 <= u <= 1.0:
            return t
        return None

    def _draw_lane(self) -> None:
        # Three lanes, each a polyline (mid is the diagonal; top/bot bend at the
        # corners). A filled circle at each vertex rounds the joint so the lane
        # body stays continuous through the corner bends (no notch). Jungle camps
        # marked as faint circles in the dead zones.
        has_lane_tile = self.sprites.terrain_tile("lane") is not None
        for path in LANE_PATHS.values():
            pts = [self.camera.world_to_screen(wx, wy) for wx, wy in path]
            if has_lane_tile:  # textured: a strip per segment
                for a, b in zip(pts, pts[1:]):
                    self._world_strip("lane", a, b, LANE_WIDTH, COLOR_LANE)
            else:
                pygame.draw.lines(self.screen, COLOR_LANE, False, pts, LANE_WIDTH)
                for p in pts:
                    pygame.draw.circle(self.screen, COLOR_LANE, p, LANE_WIDTH // 2)
        for cx, cy, _count in JUNGLE_CAMPS:
            c = self.camera.world_to_screen(cx, cy)
            pygame.draw.circle(self.screen, COLOR_LANE, c, 55, 3)

    def _draw_map_border(self) -> None:
        corners = [
            self.camera.world_to_screen(0, 0),
            self.camera.world_to_screen(MAP_WIDTH, 0),
            self.camera.world_to_screen(MAP_WIDTH, MAP_HEIGHT),
            self.camera.world_to_screen(0, MAP_HEIGHT),
        ]
        pygame.draw.lines(self.screen, (100, 100, 100), True, corners, 2)

    # ----- entities ---------------------------------------------------------
    def _draw_entity(self, ent: dict, is_me: bool) -> None:
        et = ent.get("et")
        if et in (EntityType.WALL, EntityType.TREE):
            self._draw_obstacle(ent)
            return
        sx, sy = self.camera.world_to_screen(ent["x"], ent["y"])
        radius = int(ent.get("r", 20))
        # Hooks are drawn even with the head off-screen: the tongue is a line
        # back to the (possibly on-screen) owner, so culling by the head alone
        # would drop the whole tongue.
        if et == EntityType.PROJECTILE and ent.get("hook"):
            self._draw_projectile(ent, sx, sy, radius)
            return
        if sx < -radius or sx > SCREEN_WIDTH + radius:
            return
        if sy < -radius or sy > SCREEN_HEIGHT + radius:
            return

        if et == EntityType.PROJECTILE:
            self._draw_projectile(ent, sx, sy, radius)
            return
        if et in (EntityType.TOWER, EntityType.BASE):
            self._draw_structure(ent, sx, sy, radius)
            return
        if et == EntityType.MINION:
            eid = ent.get("id")
            if ent.get("rune"):  # a roaming rune neutral
                if not self._blit_entity("rune", "idle", "", sx, sy, radius,
                                         None, eid):
                    pygame.draw.circle(self.screen, (180, 120, 230), (sx, sy), radius)
                    pygame.draw.circle(self.screen, (250, 230, 255), (sx, sy), radius + 3, 2)
                self._draw_hp_bar(ent, sx, sy, radius)
                return
            if ent.get("body"):  # a Manananggal's detached lower body
                if not self._blit_sprite("manananggal", "split_body", "s",
                                         sx, sy, radius, None, eid):
                    color = _team_color(ent.get("tm", 0))
                    pygame.draw.circle(self.screen, color, (sx, sy), radius)
                    pygame.draw.circle(self.screen, (200, 40, 40), (sx, sy), radius + 3, 3)
                self._draw_hp_bar(ent, sx, sy, radius)
                return
            self._draw_unit(ent, sx, sy, radius, hp_bar=True, name=False, ring=False)
            return
        # Hero
        if not ent.get("a", True):
            return  # don't draw dead heroes in-world
        self._draw_unit(ent, sx, sy, radius, hp_bar=True, name=True, ring=is_me)

    def _draw_unit(self, ent, sx, sy, radius, hp_bar, name, ring) -> None:
        eid = ent.get("id")
        color = _team_color(ent.get("tm", 0))
        action, facing, anim_t = self._resolve_pose(ent)
        # Lunge/recoil shift the body (not the bars) for an attack-reaction feel.
        ox, oy = self._attack_offset(eid)
        bx, by = int(sx + ox), int(sy + oy)
        hid = ent.get("hid", "")
        if hid:
            drew_sprite = self._blit_sprite(hid, action, facing, bx, by,
                                            radius, anim_t, eid)
        else:  # minion: pick art by subtype tag
            drew_sprite = self._blit_entity(
                f"minion_{ent.get('sub', 'melee')}", action, facing,
                bx, by, radius, anim_t, eid)
        if not drew_sprite:
            pygame.draw.circle(self.screen, self._flash_color(color, eid),
                               (bx, by), radius)
        if ring:
            pygame.draw.circle(self.screen, (255, 255, 255), (bx, by), radius + 3, 2)
        if hp_bar:
            self._draw_hp_bar(ent, sx, sy, radius)
        # Heroes carry mana; show a thin mana bar directly under the HP bar.
        if ent.get("mmana"):
            self._draw_mana_bar(ent, sx, sy, radius)
        if name and ent.get("name"):
            lvl = ent.get("lvl")
            label_text = f"{ent['name']}" + (f" [{lvl}]" if lvl else "")
            label = self.font.render(label_text, True, COLOR_TEXT)
            self.screen.blit(label, (sx - label.get_width() // 2,
                                     sy - radius - 26))

    def _resolve_pose(self, ent) -> tuple[str, str, float]:
        """Derive (action, facing, anim_t) for a unit from its motion + cast signal.

        Facing follows movement (kept when standing still); action is move/idle,
        overridden by a one-shot cast pose (q/w/e/r) for ~CAST_DUR after the server
        flags a cast, and by the split-flyer pose while detached. `anim_t` is the
        clock to drive frame cycling: elapsed-since-cast for one-shots (so they
        play through), else wall-clock for looping idle/move.
        """
        eid = ent.get("id")
        x, y = ent.get("x", 0.0), ent.get("y", 0.0)
        mem = self._unit_pose.get(eid)
        if mem is None:
            mem = {"x": x, "y": y, "facing": "s"}
            self._unit_pose[eid] = mem
        facing, moving = mem["facing"], False
        dx, dy = x - mem["x"], y - mem["y"]
        if (dx * dx + dy * dy) > 0.25:  # moved noticeably this frame
            facing = facing_from_delta(dx, dy)
            moving = True
        mem["x"], mem["y"], mem["facing"] = x, y, facing

        # One-shot cast: latch on the rising edge of the server's `cast` flag.
        cast = ent.get("cast")
        if cast and cast != mem.get("cast_seen"):
            mem["cast_seen"] = cast
            mem["cast_action"] = cast.lower()
            mem["cast_t0"] = time.monotonic()
        elif not cast:
            mem["cast_seen"] = None  # let the same key re-trigger next time

        now = time.monotonic()
        if ent.get("split"):
            return "split_flyer", facing, time.time()
        ct0 = mem.get("cast_t0")
        if ct0 is not None and now - ct0 < CAST_DUR:
            return mem["cast_action"], facing, now - ct0
        return ("move" if moving else "idle"), facing, time.time()

    def _blit_sprite(self, hero_id, action, facing, sx, sy, radius,
                     anim_t=None, eid=None) -> bool:
        """Blit a centered hero sprite frame if one exists; else return False."""
        surf = self.sprites.hero_frame(
            hero_id, action, facing,
            time.time() if anim_t is None else anim_t)
        return self._blit_surf(surf, sx, sy, radius, eid)

    def _blit_entity(self, key, action, facing, sx, sy, radius,
                     anim_t=None, eid=None) -> bool:
        """Blit a centered non-hero entity sprite (minions/towers/...) or False."""
        surf = self.sprites.frame(
            "entities", key, action, facing,
            time.time() if anim_t is None else anim_t)
        return self._blit_surf(surf, sx, sy, radius, eid)

    def _scaled(self, surf: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
        """smoothscale `surf` to `size`, cached by (source identity, size) so
        repeated requests for the same sprite frame at the same on-screen size
        don't re-scale every frame."""
        key = (id(surf), size)
        scaled = self._scale_cache.get(key)
        if scaled is None:
            scaled = pygame.transform.smoothscale(surf, size)
            self._scale_cache[key] = scaled
        return scaled

    def _blit_surf(self, surf, sx, sy, radius, eid) -> bool:
        if surf is None:
            return False
        target = max(8, int(radius * 3.0))
        if surf.get_height() != target:
            surf = self._scaled(surf, (target, target))
        surf = self._apply_hit_flash(surf, eid)
        self.screen.blit(surf, (sx - target // 2, sy - target // 2))
        return True

    def _apply_hit_flash(self, surf, eid):
        """Additive red flash on a sprite copy for FLASH_DUR after a hit."""
        if eid is None:
            return surf
        t0 = self._last_hit.get(eid)
        if t0 is None:
            return surf
        age = time.monotonic() - t0
        if age >= FLASH_DUR:
            return surf
        s = surf.copy()
        a = int(150 * (1 - age / FLASH_DUR))
        s.fill((a, a // 4, a // 4), special_flags=pygame.BLEND_RGB_ADD)
        return s

    def _flash_color(self, color, eid):
        """Lerp a primitive fill toward red while a unit is freshly hit."""
        if eid is None:
            return color
        t0 = self._last_hit.get(eid)
        if t0 is None:
            return color
        age = time.monotonic() - t0
        if age >= FLASH_DUR:
            return color
        k = 1 - age / FLASH_DUR
        return tuple(int(c + (255 - c) * k * 0.6 if i == 0 else c * (1 - k * 0.4))
                     for i, c in enumerate(color))

    def _projectile_heading(self, ent, sx, sy) -> float:
        """Heading (radians) from per-projectile position memory; keeps the last
        good value when the projectile is momentarily stationary."""
        eid = ent.get("id")
        x, y = ent.get("x", 0.0), ent.get("y", 0.0)
        prev = self._proj_pose.get(eid)
        heading = prev[2] if prev else 0.0
        if prev is not None:
            dx, dy = x - prev[0], y - prev[1]
            if dx * dx + dy * dy > 0.5:
                heading = math.atan2(dy, dx)
        self._proj_pose[eid] = (x, y, heading)
        return heading

    def _draw_projectile(self, ent, sx, sy, radius) -> None:
        heading = self._projectile_heading(ent, sx, sy)
        # Tiktik's tongue: a stretched band from the owner's mouth to the head.
        if ent.get("hook"):
            self._draw_tongue(ent, sx, sy, heading)
            return
        kind = ent.get("k")
        if kind:
            facing = facing_from_delta(math.cos(heading), math.sin(heading))
            surf = self.sprites.projectile_frame(kind, facing, time.time())
            if surf is not None:
                rot = pygame.transform.rotate(surf, -math.degrees(heading))
                self.screen.blit(rot, (sx - rot.get_width() // 2,
                                       sy - rot.get_height() // 2))
                return
        if ent.get("b"):  # basic attack: tinted by the shooter's team
            base = _team_color(ent.get("tm", 0))
            pygame.draw.circle(self.screen, base, (sx, sy), radius)
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy),
                               max(2, radius - 4))
        else:  # generic ability projectile: bright
            pygame.draw.circle(self.screen, COLOR_PROJECTILE, (sx, sy), radius)

    def _draw_tongue(self, ent, sx, sy, heading) -> None:
        """Render a hook projectile as a fleshy tongue from owner mouth to head,
        not a moving dot. Owner anchor via `own`; falls back to a stub behind the
        head when the owner is fogged."""
        owner = self._find(self._frame_entities, ent.get("own"))
        if owner is not None:
            ax, ay = self.camera.world_to_screen(owner["x"], owner["y"])
        else:
            ax = sx - int(math.cos(heading) * 46)
            ay = sy - int(math.sin(heading) * 46)
        # Tapered tongue: dark outline, fleshy body, bright centerline, bulb tip.
        pygame.draw.line(self.screen, (120, 24, 48), (ax, ay), (sx, sy), 11)
        pygame.draw.line(self.screen, (206, 70, 96), (ax, ay), (sx, sy), 7)
        pygame.draw.line(self.screen, (236, 132, 150), (ax, ay), (sx, sy), 3)
        head = self.sprites.frame("projectiles", "tiktik_q", "tongue_head", "",
                                  time.time())
        if head is not None:
            self.screen.blit(head, (sx - head.get_width() // 2,
                                    sy - head.get_height() // 2))
        else:
            pygame.draw.circle(self.screen, (210, 80, 104), (sx, sy), 9)
            pygame.draw.circle(self.screen, (120, 24, 48), (sx, sy), 9, 2)

    def _draw_obstacle(self, ent) -> None:
        if not ent.get("a", True):
            return  # destroyed tree: no longer blocks, don't draw
        if ent.get("x1") is None:
            return
        p1 = self.camera.world_to_screen(ent["x1"], ent["y1"])
        p2 = self.camera.world_to_screen(ent["x2"], ent["y2"])
        thpx = max(2, int(ent.get("th", 60)))
        # Cull when the whole capsule is off-screen.
        lo_x, hi_x = min(p1[0], p2[0]) - thpx, max(p1[0], p2[0]) + thpx
        lo_y, hi_y = min(p1[1], p2[1]) - thpx, max(p1[1], p2[1]) + thpx
        if hi_x < 0 or lo_x > SCREEN_WIDTH or hi_y < 0 or lo_y > SCREEN_HEIGHT:
            return
        is_tree = ent.get("et") == EntityType.TREE
        key = "tree" if is_tree else "wall"
        # Textured capsule: tile the wall/tree segment sprite along the centerline,
        # rotated to its angle. Falls back to the primitive band when art is absent.
        seg = self.sprites.frame("entities", key, "seg", "", time.time())
        if seg is not None:
            length = int(math.hypot(p2[0] - p1[0], p2[1] - p1[1]))
            if length >= 1:
                eid = ent.get("id")
                self._blit_tiled_strip(seg, (key, eid, length, thpx),
                                       p1, p2, length, thpx)
        else:
            fill = (40, 95, 45) if is_tree else (90, 88, 96)
            edge = (60, 140, 65) if is_tree else (130, 128, 140)
            # Oriented band: a thick line + rounded caps, outlined by its rectangle.
            pygame.draw.line(self.screen, fill, p1, p2, thpx)
            pygame.draw.circle(self.screen, fill, p1, thpx // 2)
            pygame.draw.circle(self.screen, fill, p2, thpx // 2)
            corners = _capsule_corners(p1, p2, thpx)
            if corners:
                pygame.draw.polygon(self.screen, edge, corners, 2)
        if is_tree:  # show a damage bar on hurt trees, at the capsule midpoint
            if ent.get("hp", 1) < ent.get("mhp", 1):
                mx, my = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
                self._draw_hp_bar(ent, mx, my - thpx // 2, thpx // 2)

    def _draw_structure(self, ent, sx, sy, radius) -> None:
        eid = ent.get("id")
        is_core = ent.get("core")
        key = "base" if (is_core or ent.get("et") == EntityType.BASE) else "tower"
        alive = ent.get("a", True)
        action = "idle" if alive else "dead"
        if alive and is_core:
            action = "core"
        if self._blit_entity(key, action, "", sx, sy, radius, None, eid):
            if alive:
                self._draw_hp_bar(ent, sx, sy, radius)
            return
        rect = pygame.Rect(sx - radius, sy - radius, radius * 2, radius * 2)
        if not alive:
            pygame.draw.rect(self.screen, COLOR_STRUCTURE_DEAD, rect, border_radius=4)
            return
        color = self._flash_color(_team_color(ent.get("tm", 0)), eid)
        pygame.draw.rect(self.screen, color, rect, border_radius=4)
        if is_core:
            pygame.draw.rect(self.screen, (255, 255, 255), rect, 3, border_radius=4)
        self._draw_hp_bar(ent, sx, sy, radius)

    def _draw_hp_bar(self, ent, sx, sy, radius) -> None:
        hp = ent.get("hp", 0)
        max_hp = ent.get("mhp", 1)
        bar_w = radius * 2 + 10
        bar_h = 4
        bar_x = sx - bar_w // 2
        bar_y = sy - radius - 10
        pygame.draw.rect(self.screen, COLOR_HEALTH_BG, (bar_x, bar_y, bar_w, bar_h))
        hp_w = int(bar_w * max(hp, 0) / max(max_hp, 1))
        pygame.draw.rect(self.screen, COLOR_HEALTH, (bar_x, bar_y, hp_w, bar_h))

    def _draw_mana_bar(self, ent, sx, sy, radius) -> None:
        mana = ent.get("mana", 0)
        max_mana = ent.get("mmana", 1)
        bar_w = radius * 2 + 10
        bar_h = 3
        bar_x = sx - bar_w // 2
        bar_y = sy - radius - 10 + 5  # just under the hp bar
        pygame.draw.rect(self.screen, COLOR_HEALTH_BG, (bar_x, bar_y, bar_w, bar_h))
        mana_w = int(bar_w * max(mana, 0) / max(max_mana, 1))
        pygame.draw.rect(self.screen, COLOR_MANA, (bar_x, bar_y, mana_w, bar_h))

    # ----- HUD --------------------------------------------------------------
    def _draw_hud(self, entities, my_entity_id, my_team, phase, tick,
                  score, ktarget, winner, clock=0.0) -> None:
        me = self._find(entities, my_entity_id)

        # Top-center: match timer + scoreboard.
        self._draw_timer(clock)
        s1, s2 = score.get("1", 0), score.get("2", 0)
        board = self.font_large.render(f"{s1}  -  {s2}", True, COLOR_TEXT)
        self.screen.blit(board, (SCREEN_WIDTH // 2 - board.get_width() // 2, 30))
        sub = self.font.render(f"first to {ktarget} kills", True, (170, 170, 170))
        self.screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 56))

        # Top-left: KDA / minion stats / team / hero name.
        self._draw_scoreboard_panel(me, my_team)

        # Side columns: per-hero ultimate availability + respawn timers.
        self._draw_ult_columns(entities, my_team)

        # Minimap (bottom-left). Server already culled fogged enemies.
        self._draw_minimap(entities, my_entity_id, my_team)

        # My stats panel + skill/item grids.
        if me is not None:
            self._draw_stats_panel(me)
            self._draw_ability_bar(me)
            self._draw_inventory(me)
            if not me.get("a", True):
                self._draw_respawn(me)
            self._draw_hover_tooltip(me)

        if self.shop_open:
            self._draw_shop(me)

        # Hints / banners
        if phase == GamePhase.WAITING:
            hint = self.font_large.render(
                "Press SPACE to start", True, (200, 200, 100))
            self.screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2,
                                    SCREEN_HEIGHT // 2))
        elif phase == GamePhase.FINISHED and winner:
            self._draw_game_over(winner, my_team)
        else:
            hint = self.font.render(
                "RMB move | A+click attack | QWERTYU+I cast | Shift+key level | "
                "Cmd/Alt+QWE-ASD items | Enter chat | B shop",
                True, (150, 150, 150))
            self.screen.blit(hint, (SCREEN_WIDTH - hint.get_width() - 10, 76))

    def _draw_timer(self, clock: float) -> None:
        """Pre-game countdown (clock < 0) then elapsed time, top-center."""
        if clock < 0:
            secs = int(-clock) + 1
            text = f"0:{secs:02d}"
            color = (255, 210, 120)
        else:
            total = int(clock)
            text = f"{total // 60}:{total % 60:02d}"
            color = COLOR_TEXT
        label = self.font_large.render(text, True, color)
        self.screen.blit(label, (SCREEN_WIDTH // 2 - label.get_width() // 2, 6))

    def _draw_scoreboard_panel(self, me, my_team) -> None:
        """Top-left: KDA, minion/neutral last-hits, team, hero name."""
        white = (240, 240, 240)
        if me is None:
            return
        kda = f"KDA  {me.get('kills', 0)}/{me.get('deaths', 0)}/{me.get('assists', 0)}"
        minions = f"Minions  {me.get('mk', 0)} / {me.get('nk', 0)}"  # enemy / neutral
        team_txt = f"Team {my_team}" if my_team else "Team -"
        rows = [
            (kda, white),
            (minions, white),
            (team_txt, _team_color(my_team) if my_team else white),
            (me.get("name", ""), (200, 220, 255)),
        ]
        for i, (text, color) in enumerate(rows):
            self.screen.blit(self.font.render(text, True, color), (10, 8 + i * 18))

    def _draw_ult_columns(self, entities, my_team) -> None:
        """Two horizontal rows at the top flanking the match timer: allied heroes
        grow leftwards, enemy heroes grow rightwards. Each is a circle — green if
        the ultimate is ready, red otherwise — with a respawn countdown below
        when dead."""
        allies, enemies = [], []
        for e in entities:
            if e.get("et") != EntityType.HERO:
                continue
            (allies if e.get("tm") == my_team else enemies).append(e)
        cx = SCREEN_WIDTH // 2
        self._draw_ult_row(allies, anchor_x=cx - 95, top=18, direction=-1)
        self._draw_ult_row(enemies, anchor_x=cx + 95, top=18, direction=1)

    def _draw_ult_row(self, heroes, anchor_x: int, top: int, direction: int) -> None:
        step = 30
        for i, h in enumerate(heroes):
            x = anchor_x + direction * i * step
            alive = h.get("a", True)
            # Heroes ult on "R" unless the snapshot names a different ult key
            # (e.g. Pedro Penduko's White Mutya on "I").
            ult = h.get("ult", "R")
            r_rank = h.get("alvl", {}).get(ult, 0)
            r_cd = h.get("cds", {}).get(ult, 0)
            if not alive:
                color = (90, 90, 90)
            elif r_rank >= 1 and r_cd <= 0:
                color = (60, 210, 90)    # ult ready
            else:
                color = (210, 70, 70)    # not leveled / on cooldown
            pygame.draw.circle(self.screen, color, (x, top), 12)
            pygame.draw.circle(self.screen, (20, 20, 24), (x, top), 12, 2)
            # Respawn timer below the indicator (blank while alive).
            if not alive and h.get("resp", 0) > 0:
                t = self.font.render(f"{h['resp']:.0f}", True, (220, 180, 180))
                self.screen.blit(t, (x - t.get_width() // 2, top + 14))

    def _draw_ability_bar(self, me: dict) -> None:
        """Skills as a grid at the bottom, left of the items. Standard 4-ability
        heroes use a 2x2 (Q W / E R); wider kits (e.g. Pedro Penduko's 8 skills)
        spill into a 4-wide grid (Q W E R / T Y U I). Shows cooldown, rank pips,
        and a '+' badge when a point can be spent."""
        abilities = self.hero_abilities
        cds = me.get("cds", {})
        alvl = me.get("alvl", {})
        points = me.get("sp", 0)
        slot, gap = 54, 6
        n = min(len(abilities), 8)
        cols = 2 if n <= 4 else 4
        rows = max(1, (n + cols - 1) // cols)
        grid_w = cols * slot + (cols - 1) * gap
        x0 = SCREEN_WIDTH - 3 * 46 - 12 - grid_w - 24  # left of the 3-wide item grid
        y0 = SCREEN_HEIGHT - rows * slot - (rows - 1) * gap - 8
        self._skill_rects = []
        for i, ab in enumerate(abilities[:n]):
            col, row = i % cols, i // cols
            x = x0 + col * (slot + gap)
            y = y0 + row * (slot + gap)
            rect = pygame.Rect(x, y, slot, slot)
            self._skill_rects.append((rect, ab))
            key = ab["key"]
            rank = alvl.get(key, 0)
            cd = cds.get(key, 0)
            ready = rank >= 1 and cd <= 0 and me.get("mana", 0) >= ab["mana"]
            fill = (60, 90, 120) if ready else (45, 45, 55)
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            pending = (key == self.pending_cast)
            border = (240, 220, 120) if pending else (90, 90, 110)
            pygame.draw.rect(self.screen, border, rect, 3 if pending else 2,
                             border_radius=6)
            self.screen.blit(self.font.render(key, True, COLOR_TEXT), (x + 4, y + 2))
            if cd > 0:
                cl = self.font_large.render(f"{cd:.0f}", True, (240, 200, 120))
                self.screen.blit(cl, (x + slot // 2 - cl.get_width() // 2, y + 14))
            # Rank pips along the bottom.
            max_rank = ab.get("max_rank", 4)
            pip_w = (slot - 8) / max_rank
            for r in range(max_rank):
                px = x + 4 + int(r * pip_w)
                col_pip = (250, 210, 90) if r < rank else (70, 70, 80)
                pygame.draw.rect(self.screen, col_pip,
                                 (px, y + slot - 7, int(pip_w) - 1, 4))
            # "+" badge when a skill point is available and the skill isn't maxed.
            if points > 0 and rank < max_rank:
                pygame.draw.circle(self.screen, (60, 200, 90), (x + slot - 8, y + 8), 7)
                plus = self.font.render("+", True, (10, 30, 10))
                self.screen.blit(plus, (x + slot - 12, y + 1))

    def _draw_stats_panel(self, me: dict) -> None:
        """Dedicated panel (right of the minimap): full stat list. Values are
        white; temporary buff/debuff deltas show green (+) / red (-)."""
        rows_n = 13
        x0 = self.minimap.right + 10
        w, line = 220, 18
        h = 10 + rows_n * line
        y0 = SCREEN_HEIGHT - 8 - h
        panel = pygame.Surface((w, h))
        panel.set_alpha(225)
        panel.fill((22, 26, 32))
        self.screen.blit(panel, (x0, y0))
        pygame.draw.rect(self.screen, (90, 90, 110), (x0, y0, w, h), 2)

        white = (240, 240, 240)
        dlt = me.get("dlt", {})
        lvl = me.get("lvl", 1)
        xp, xpn = me.get("xp", 0), me.get("xpn", 0)
        xp_str = f"{xp}/{xpn}" if xpn else "MAX"
        # (label, value-text, delta-key) — delta None means no temp delta line.
        rows = [
            ("LVL", f"{lvl}   XP {xp_str}", None),
            ("HP", f"{me.get('hp', 0)}/{me.get('mhp', 0)}  +{me.get('hpr', 0)}", "hpr"),
            ("MP", f"{me.get('mana', 0)}/{me.get('mmana', 0)}  +{me.get('mpr', 0)}", "mpr"),
            ("GLD", f"{me.get('gold', 0)}  +{int(PASSIVE_GOLD_PER_SEC)}/s", None),
            ("ATK", f"{me.get('ad', 0)}", "ad"),
            ("SP.ATK", f"{me.get('spa', 0)}", "spa"),
            ("DEF", f"{me.get('pdef', 0)}", "pdef"),
            ("SP.DEF", f"{me.get('sdef', 0)}", "sdef"),
            ("ATK.SPD", f"{me.get('aspd', 0)}", "aspd"),
            ("MV.SPD", f"{me.get('ms', 0)}", "ms"),
            ("RNG", f"{me.get('rng', 0)}", "rng"),
        ]
        for i, (label, value, dkey) in enumerate(rows):
            y = y0 + 6 + i * line
            self.screen.blit(self.font.render(label, True, (150, 160, 175)),
                             (x0 + 8, y))
            vlabel = self.font.render(value, True, white)
            self.screen.blit(vlabel, (x0 + 86, y))
            if dkey and dlt.get(dkey):
                d = dlt[dkey]
                sign = "+" if d > 0 else ""
                color = (90, 220, 110) if d > 0 else (230, 90, 90)
                dl = self.font.render(f"{sign}{d}", True, color)
                self.screen.blit(dl, (x0 + 86 + vlabel.get_width() + 6, y))
        # Crowd-control flags row.
        cc = me.get("cc")
        if cc:
            txt = self.font.render(" ".join(c.upper() for c in cc), True,
                                   (255, 140, 140))
            self.screen.blit(txt, (x0 + 8, y0 + 6 + 11 * line))

    def _minimap_background(self, entities) -> pygame.Surface:
        """Panel fill + river/lane/wall/tree lines, none of which move at
        runtime except a tree dying or respawning — so this is cached and only
        redrawn when the alive wall/tree set actually changes."""
        sig = tuple(sorted(
            e["id"] for e in entities
            if e.get("et") in (EntityType.WALL, EntityType.TREE) and e.get("a", True)))
        if self._minimap_bg is not None and self._minimap_bg_sig == sig:
            return self._minimap_bg
        mm = self.minimap
        panel = pygame.Surface((mm.width, mm.height))
        panel.set_alpha(220)
        panel.fill((20, 30, 18))

        def to_local(wx, wy):
            return (int(wx / MAP_WIDTH * mm.width), int(wy / MAP_HEIGHT * mm.height))

        if RIVER is not None:
            pygame.draw.line(panel, (70, 110, 170),
                             to_local(RIVER.x1, RIVER.y1),
                             to_local(RIVER.x2, RIVER.y2), 1)
        for path in LANE_PATHS.values():
            pygame.draw.lines(panel, COLOR_LANE, False,
                              [to_local(wx, wy) for wx, wy in path], 1)
        for ent in entities:
            if ent.get("et") not in (EntityType.WALL, EntityType.TREE) or not ent.get("a", True):
                continue
            col = (60, 110, 60) if ent.get("et") == EntityType.TREE else (110, 110, 120)
            if ent.get("x1") is not None:
                pygame.draw.line(panel, col,
                                 to_local(ent["x1"], ent["y1"]),
                                 to_local(ent["x2"], ent["y2"]), 1)
            else:
                mx, my = to_local(ent["x"], ent["y"])
                pygame.draw.rect(panel, col, (mx, my, 2, 2))
        self._minimap_bg = panel
        self._minimap_bg_sig = sig
        return panel

    def _draw_minimap(self, entities, my_entity_id, my_team) -> None:
        mm = self.minimap
        self.screen.blit(self._minimap_background(entities), (mm.left, mm.top))
        pygame.draw.rect(self.screen, (90, 90, 110), mm, 2)

        def to_mm(wx, wy):
            return (int(mm.left + wx / MAP_WIDTH * mm.width),
                    int(mm.top + wy / MAP_HEIGHT * mm.height))

        for ent in entities:
            et = ent.get("et")
            if et == EntityType.PROJECTILE:
                continue
            if et == EntityType.HERO and not ent.get("a", True):
                continue
            if et in (EntityType.WALL, EntityType.TREE):
                continue  # baked into the cached background
            mx, my = to_mm(ent["x"], ent["y"])
            color = _team_color(ent.get("tm", 0))
            if et == EntityType.MINION and ent.get("rune"):
                pygame.draw.circle(self.screen, (190, 130, 235), (mx, my), 2)
                continue
            if et in (EntityType.TOWER, EntityType.BASE):
                if not ent.get("a", True):
                    color = COLOR_STRUCTURE_DEAD
                pygame.draw.rect(self.screen, color, (mx - 2, my - 2, 4, 4))
            elif et == EntityType.MINION:
                pygame.draw.rect(self.screen, color, (mx - 1, my - 1, 2, 2))
            elif et == EntityType.HERO:
                pygame.draw.circle(self.screen, color, (mx, my), 3)
                if ent["id"] == my_entity_id:
                    pygame.draw.circle(self.screen, (255, 255, 255), (mx, my), 4, 1)

        # Camera viewport rectangle.
        vx, vy = to_mm(self.camera.x, self.camera.y)
        vw = int(SCREEN_WIDTH / MAP_WIDTH * mm.width)
        vh = int(SCREEN_HEIGHT / MAP_HEIGHT * mm.height)
        pygame.draw.rect(self.screen, (220, 220, 220), (vx, vy, vw, vh), 1)

    # Inventory slot hotkey letters (Cmd/Alt + letter), laid out 2x3 to match
    # the keyboard: Q/W/E on top, A/S/D on the bottom.
    _ITEM_SLOT_LABELS = ("Q", "W", "E", "A", "S", "D")

    def _draw_inventory(self, me: dict) -> None:
        """Inventory as a 2x3 grid (bottom-right); Cmd/Alt+QWE/ASD activate."""
        inv = me.get("inv", [])
        icds = me.get("icds", {})
        names = {it["item_id"]: it["name"] for it in self.item_catalog}
        slot, gap = 46, 0
        cols, rows = 3, 2
        x0 = SCREEN_WIDTH - cols * slot - 12
        y0 = SCREEN_HEIGHT - rows * slot - 8
        self._item_rects = []
        for i in range(6):
            col, row = i % cols, i // cols
            x = x0 + col * slot
            y = y0 + row * slot
            rect = pygame.Rect(x, y, slot - 4, slot - 4)
            pygame.draw.rect(self.screen, (40, 45, 55), rect, border_radius=4)
            pygame.draw.rect(self.screen, (80, 80, 95), rect, 1, border_radius=4)
            self.screen.blit(
                self.font.render(self._ITEM_SLOT_LABELS[i], True, (120, 120, 140)),
                (x + 2, y + 1))
            if i < len(inv):
                item_id = inv[i]
                self._item_rects.append((rect, item_id))
                short = names.get(item_id, item_id)[:6]
                self.screen.blit(self.font.render(short, True, COLOR_TEXT),
                                 (x + 3, y + 16))
                cd = icds.get(item_id, 0)
                if cd > 0:
                    self.screen.blit(
                        self.font.render(f"{cd:.0f}", True, (240, 200, 120)),
                        (x + 3, y + 28))

    def _draw_hover_tooltip(self, me: dict) -> None:
        """Show a tooltip for the skill or item slot under the cursor."""
        mx, my = pygame.mouse.get_pos()
        for rect, ab in getattr(self, "_skill_rects", []):
            if rect.collidepoint(mx, my):
                rank = me.get("alvl", {}).get(ab["key"], 0)
                head = f"{ab['key']}  {ab['name']}  [{rank}/{ab.get('max_rank', 4)}]"
                meta = f"CD {ab.get('cd', 0)}s   Mana {ab.get('mana', 0)}"
                self._tooltip_box(mx, my, [head, meta, ab.get("desc", "")])
                return
        catalog = {it["item_id"]: it for it in self.item_catalog}
        for rect, item_id in getattr(self, "_item_rects", []):
            if rect.collidepoint(mx, my):
                it = catalog.get(item_id, {})
                head = it.get("name", item_id)
                bonus = ", ".join(f"+{v} {k}" for k, v
                                  in it.get("bonuses", {}).items())
                lines = [head]
                if bonus:
                    lines.append(bonus)
                if it.get("active"):
                    lines.append("Active (F-key to use)")
                self._tooltip_box(mx, my, lines)
                return

    def _tooltip_box(self, mx: int, my: int, lines: list) -> None:
        lines = [ln for ln in lines if ln]
        rendered = [self.font.render(ln, True, COLOR_TEXT) for ln in lines]
        w = max((r.get_width() for r in rendered), default=0) + 16
        h = len(rendered) * 16 + 10
        bx = min(mx + 14, SCREEN_WIDTH - w - 4)
        by = max(4, my - h - 6)
        panel = pygame.Surface((w, h))
        panel.set_alpha(235)
        panel.fill((18, 20, 26))
        self.screen.blit(panel, (bx, by))
        pygame.draw.rect(self.screen, (110, 110, 130), (bx, by, w, h), 1)
        for i, r in enumerate(rendered):
            self.screen.blit(r, (bx + 8, by + 6 + i * 16))

    def _draw_shop(self, me: dict) -> None:
        """Simple shop panel: catalog rows bought with number keys."""
        gold = me.get("gold", 0) if me else 0
        pad = 12
        w, line = 320, 26
        h = pad * 2 + line * (len(self.item_catalog) + 2)
        x0, y0 = 20, 80
        panel = pygame.Surface((w, h))
        panel.set_alpha(235)
        panel.fill((25, 28, 36))
        self.screen.blit(panel, (x0, y0))
        pygame.draw.rect(self.screen, (90, 90, 110), (x0, y0, w, h), 2)
        self.screen.blit(self.font_large.render("SHOP", True, COLOR_TEXT),
                         (x0 + pad, y0 + pad))
        self.screen.blit(self.font.render(f"Gold: {gold}", True, (240, 220, 120)),
                         (x0 + pad + 90, y0 + pad + 6))
        for i, it in enumerate(self.item_catalog):
            y = y0 + pad + line * (i + 1) + 6
            affordable = gold >= it["cost"]
            color = COLOR_TEXT if affordable else (130, 130, 130)
            bonus = ", ".join(f"+{v} {k}" for k, v in it.get("bonuses", {}).items())
            act = "  [active]" if it.get("active") else ""
            row = f"{i+1}. {it['name']} ({it['cost']}g)  {bonus}{act}"
            self.screen.blit(self.font.render(row, True, color), (x0 + pad, y))
        self.screen.blit(
            self.font.render("num=buy  F1-F6=sell  B=close", True, (150, 150, 150)),
            (x0 + pad, y0 + h - line))

    def _draw_respawn(self, me: dict) -> None:
        t = me.get("resp", 0)
        msg = self.font_huge.render(f"Respawning {t:.0f}", True, (220, 120, 120))
        self.screen.blit(msg, (SCREEN_WIDTH // 2 - msg.get_width() // 2,
                               SCREEN_HEIGHT // 2 - 40))

    def _draw_game_over(self, winner: int, my_team) -> None:
        won = (my_team == winner)
        text = "VICTORY" if won else "DEFEAT"
        color = (120, 220, 120) if won else (220, 120, 120)
        banner = self.font_huge.render(text, True, color)
        self.screen.blit(banner, (SCREEN_WIDTH // 2 - banner.get_width() // 2,
                                  SCREEN_HEIGHT // 2 - 60))
        sub = self.font_large.render(f"Team {winner} wins", True, COLOR_TEXT)
        self.screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2,
                               SCREEN_HEIGHT // 2))

    @staticmethod
    def _find(entities, eid):
        if eid is None:
            return None
        for e in entities:
            if e["id"] == eid:
                return e
        return None
