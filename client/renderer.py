"""Render the game world using Pygame.

Entities are drawn by a small per-type drawer registry keyed on the snapshot's
entity-type tag ("et"). Each drawer reads a shape descriptor today; swapping a
descriptor to a sprite later needs no gameplay changes.
"""

from __future__ import annotations

import time
import pygame
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
)
from shared.game_types import Team, GamePhase, EntityType
from client.camera import Camera
from client.sprites import SpriteManager, facing_from_delta


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
        # Floating combat text (gold/xp popups): {wx, wy, text, color, born, dur}.
        self.floaters: list[dict] = []

    def add_combat_events(self, events) -> None:
        """Spawn floating gold/xp text from server reward events."""
        now = time.monotonic()
        for ev in events or []:
            kind = ev.get("k")
            if kind == "gold":
                text, color = f"+{ev['amt']}g", (240, 215, 90)
            elif kind == "xp":
                text, color = f"+{ev['amt']} xp", (150, 200, 255)
            else:
                continue
            self.floaters.append({
                "wx": ev["x"], "wy": ev["y"], "text": text, "color": color,
                "born": now, "dur": 1.1,
            })

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
        self.screen.fill(COLOR_BG)
        self._draw_grid()
        self._draw_river()
        self._draw_lane()
        self._draw_map_border()

        # Walls/trees under units; structures/minions next; heroes/projectiles on top.
        order = {EntityType.WALL: -1, EntityType.TREE: -1,
                 EntityType.TOWER: 0, EntityType.BASE: 0, EntityType.MINION: 1,
                 EntityType.HERO: 2, EntityType.PROJECTILE: 3}
        for ent in sorted(entities, key=lambda e: order.get(e.get("et"), 2)):
            self._draw_entity(ent, ent["id"] == my_entity_id if my_entity_id else False)

        self._draw_floaters()
        self._draw_hud(entities, my_entity_id, my_team, phase, tick,
                       score or {}, ktarget, winner, clock)
        self._draw_targeting_cursor()
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

    def _draw_river(self) -> None:
        """The walkable river: a translucent diagonal band drawn under the
        lanes. Crosses the mid lane to form an X."""
        if RIVER is None:
            return
        p1 = self.camera.world_to_screen(RIVER.x1, RIVER.y1)
        p2 = self.camera.world_to_screen(RIVER.x2, RIVER.y2)
        thpx = max(2, int(RIVER.thickness))
        band = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        pygame.draw.line(band, (70, 130, 210, 70), p1, p2, thpx)
        self.screen.blit(band, (0, 0))

    def _draw_lane(self) -> None:
        # Three lanes, each a polyline (mid is the diagonal; top/bot bend at the
        # corners). A filled circle at each vertex rounds the joint so the lane
        # body stays continuous through the corner bends (no notch). Jungle camps
        # marked as faint circles in the dead zones.
        for path in LANE_PATHS.values():
            pts = [self.camera.world_to_screen(wx, wy) for wx, wy in path]
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
        if sx < -radius or sx > SCREEN_WIDTH + radius:
            return
        if sy < -radius or sy > SCREEN_HEIGHT + radius:
            return

        if et == EntityType.PROJECTILE:
            if ent.get("b"):  # basic attack: tinted by the shooter's team
                base = _team_color(ent.get("tm", 0))
                pygame.draw.circle(self.screen, base, (sx, sy), radius)
                pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), max(2, radius - 4))
            else:  # ability projectile: bright
                pygame.draw.circle(self.screen, COLOR_PROJECTILE, (sx, sy), radius)
            return
        if et in (EntityType.TOWER, EntityType.BASE):
            self._draw_structure(ent, sx, sy, radius)
            return
        if et == EntityType.MINION:
            if ent.get("rune"):  # a roaming rune neutral
                pygame.draw.circle(self.screen, (180, 120, 230), (sx, sy), radius)
                pygame.draw.circle(self.screen, (250, 230, 255), (sx, sy), radius + 3, 2)
                self._draw_hp_bar(ent, sx, sy, radius)
                return
            if ent.get("body"):  # a Manananggal's detached lower body
                if not self._blit_sprite("manananggal", "split_body", "s",
                                         sx, sy, radius):
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
        color = _team_color(ent.get("tm", 0))
        action, facing = self._resolve_pose(ent)
        drew_sprite = self._blit_sprite(
            ent.get("hid", ""), action, facing, sx, sy, radius)
        if not drew_sprite:
            pygame.draw.circle(self.screen, color, (sx, sy), radius)
        if ring:
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), radius + 3, 2)
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

    def _resolve_pose(self, ent) -> tuple[str, str]:
        """Derive (action, facing) for a unit from its motion since last frame.

        Facing follows the movement direction (kept when standing still); action
        is move/idle by whether it moved, overridden to the split flyer pose
        while a Manananggal's upper half is detached.
        """
        eid = ent.get("id")
        x, y = ent.get("x", 0.0), ent.get("y", 0.0)
        prev = self._unit_pose.get(eid)
        facing = prev["facing"] if prev else "s"
        moving = False
        if prev is not None:
            dx, dy = x - prev["x"], y - prev["y"]
            if (dx * dx + dy * dy) > 0.25:  # moved noticeably this frame
                facing = facing_from_delta(dx, dy)
                moving = True
        self._unit_pose[eid] = {"x": x, "y": y, "facing": facing}

        if ent.get("split"):
            return "split_flyer", facing
        return ("move" if moving else "idle"), facing

    def _blit_sprite(self, hero_id, action, facing, sx, sy, radius) -> bool:
        """Blit a centered sprite frame if one exists; return False to fall back."""
        surf = self.sprites.hero_frame(hero_id, action, facing, time.time())
        if surf is None:
            return False
        target = max(8, int(radius * 3.0))
        if surf.get_height() != target:
            surf = pygame.transform.smoothscale(surf, (target, target))
        self.screen.blit(surf, (sx - target // 2, sy - target // 2))
        return True

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
        rect = pygame.Rect(sx - radius, sy - radius, radius * 2, radius * 2)
        if not ent.get("a", True):
            pygame.draw.rect(self.screen, COLOR_STRUCTURE_DEAD, rect, border_radius=4)
            return
        color = _team_color(ent.get("tm", 0))
        pygame.draw.rect(self.screen, color, rect, border_radius=4)
        if ent.get("core"):
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
                "RMB move | A+click attack | QWER cast | Alt+QWER level up | B shop",
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
            r_rank = h.get("alvl", {}).get("R", 0)
            r_cd = h.get("cds", {}).get("R", 0)
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
        """Skills as a 2x2 grid (Q W / E R) at the bottom, left of the items.
        Shows cooldown, rank pips, and a '+' badge when a point can be spent."""
        abilities = self.hero_abilities
        cds = me.get("cds", {})
        alvl = me.get("alvl", {})
        points = me.get("sp", 0)
        slot, gap = 54, 6
        grid_w = 2 * slot + gap
        x0 = SCREEN_WIDTH - 3 * 46 - 12 - grid_w - 24  # left of the 3-wide item grid
        y0 = SCREEN_HEIGHT - 2 * slot - gap - 8
        self._skill_rects = []
        for i, ab in enumerate(abilities[:4]):
            col, row = i % 2, i // 2
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

    def _draw_minimap(self, entities, my_entity_id, my_team) -> None:
        mm = self.minimap
        panel = pygame.Surface((mm.width, mm.height))
        panel.set_alpha(220)
        panel.fill((20, 30, 18))
        self.screen.blit(panel, (mm.left, mm.top))
        pygame.draw.rect(self.screen, (90, 90, 110), mm, 2)

        def to_mm(wx, wy):
            return (int(mm.left + wx / MAP_WIDTH * mm.width),
                    int(mm.top + wy / MAP_HEIGHT * mm.height))

        # River + lane lines for orientation.
        if RIVER is not None:
            pygame.draw.line(self.screen, (70, 110, 170),
                             to_mm(RIVER.x1, RIVER.y1),
                             to_mm(RIVER.x2, RIVER.y2), 1)
        for path in LANE_PATHS.values():
            pygame.draw.lines(self.screen, COLOR_LANE, False,
                              [to_mm(wx, wy) for wx, wy in path], 1)

        for ent in entities:
            et = ent.get("et")
            if et == EntityType.PROJECTILE:
                continue
            if et == EntityType.HERO and not ent.get("a", True):
                continue
            if et in (EntityType.WALL, EntityType.TREE):
                if not ent.get("a", True):
                    continue
                col = (60, 110, 60) if et == EntityType.TREE else (110, 110, 120)
                if ent.get("x1") is not None:
                    pygame.draw.line(self.screen, col,
                                     to_mm(ent["x1"], ent["y1"]),
                                     to_mm(ent["x2"], ent["y2"]), 1)
                else:
                    mx, my = to_mm(ent["x"], ent["y"])
                    pygame.draw.rect(self.screen, col, (mx, my, 2, 2))
                continue
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

    def _draw_inventory(self, me: dict) -> None:
        """Inventory as a 2x3 grid (bottom-right), F1..F6, with active cooldowns."""
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
            self.screen.blit(self.font.render(f"F{i+1}", True, (120, 120, 140)),
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
