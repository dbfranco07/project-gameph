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
    LANE_Y,
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
)
from shared.game_types import Team, GamePhase, EntityType
from client.camera import Camera


def _team_color(team: int) -> tuple[int, int, int]:
    if team == Team.TEAM1:
        return COLOR_TEAM1
    if team == Team.TEAM2:
        return COLOR_TEAM2
    return (180, 180, 180)


class Renderer:
    def __init__(self, screen: pygame.Surface, camera: Camera) -> None:
        self.screen = screen
        self.camera = camera
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
                   score=None, ktarget=0, winner=0) -> None:
        self.screen.fill(COLOR_BG)
        self._draw_grid()
        self._draw_lane()
        self._draw_map_border()

        # Draw structures/minions first, heroes/projectiles on top.
        order = {EntityType.TOWER: 0, EntityType.BASE: 0, EntityType.MINION: 1,
                 EntityType.HERO: 2, EntityType.PROJECTILE: 3}
        for ent in sorted(entities, key=lambda e: order.get(e.get("et"), 2)):
            self._draw_entity(ent, ent["id"] == my_entity_id if my_entity_id else False)

        self._draw_floaters()
        self._draw_hud(entities, my_entity_id, my_team, phase, tick,
                       score or {}, ktarget, winner)
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

    def _draw_lane(self) -> None:
        left = self.camera.world_to_screen(0, LANE_Y)
        right = self.camera.world_to_screen(MAP_WIDTH, LANE_Y)
        pygame.draw.line(self.screen, COLOR_LANE, left, right, 90)

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
            self._draw_unit(ent, sx, sy, radius, hp_bar=True, name=False, ring=False)
            return
        # Hero
        if not ent.get("a", True):
            return  # don't draw dead heroes in-world
        self._draw_unit(ent, sx, sy, radius, hp_bar=True, name=True, ring=is_me)

    def _draw_unit(self, ent, sx, sy, radius, hp_bar, name, ring) -> None:
        color = _team_color(ent.get("tm", 0))
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
                  score, ktarget, winner) -> None:
        # Scoreboard (top center)
        s1 = score.get("1", 0)
        s2 = score.get("2", 0)
        board = self.font_large.render(f"{s1}  -  {s2}", True, COLOR_TEXT)
        self.screen.blit(board, (SCREEN_WIDTH // 2 - board.get_width() // 2, 8))
        sub = self.font.render(f"first to {ktarget} kills", True, (170, 170, 170))
        self.screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 34))

        # Status line (top left)
        phase_names = {0: "WAITING", 1: "PLAYING", 2: "FINISHED"}
        label = self.font.render(
            f"{phase_names.get(phase, '?')}  |  tick {tick}", True, COLOR_TEXT)
        self.screen.blit(label, (10, 10))
        if my_team is not None:
            tl = self.font.render(f"Team {my_team}", True, _team_color(my_team))
            self.screen.blit(tl, (10, 28))

        me = self._find(entities, my_entity_id)

        # Minimap (bottom-left). Server already culled fogged enemies.
        self._draw_minimap(entities, my_entity_id, my_team)

        # My stats panel + ability bar
        if me is not None:
            self._draw_stats_panel(me)
            self._draw_ability_bar(me)
            self._draw_inventory(me)
            if not me.get("a", True):
                self._draw_respawn(me)

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
                "RMB move | A+click attack | Q/W/E/R cast then click | hold 1 center",
                True, (150, 150, 150))
            self.screen.blit(hint, (SCREEN_WIDTH - hint.get_width() - 10, 10))

    def _draw_ability_bar(self, me: dict) -> None:
        abilities = self.hero_abilities
        cds = me.get("cds", {})
        slot = 56
        total = slot * len(abilities)
        x0 = SCREEN_WIDTH // 2 - total // 2
        y0 = SCREEN_HEIGHT - 64
        for i, ab in enumerate(abilities):
            x = x0 + i * slot
            rect = pygame.Rect(x, y0, slot - 8, slot - 8)
            cd = cds.get(ab["key"], 0)
            ready = cd <= 0 and me.get("mana", 0) >= ab["mana"]
            fill = (60, 90, 120) if ready else (45, 45, 55)
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            pending = (ab["key"] == self.pending_cast)
            border = (240, 220, 120) if pending else (90, 90, 110)
            pygame.draw.rect(self.screen, border, rect, 3 if pending else 2,
                             border_radius=6)
            key_label = self.font.render(ab["key"], True, COLOR_TEXT)
            self.screen.blit(key_label, (x + 4, y0 + 2))
            if cd > 0:
                cd_label = self.font_large.render(f"{cd:.0f}", True, (240, 200, 120))
                self.screen.blit(cd_label, (x + (slot - 8) // 2 - cd_label.get_width() // 2,
                                            y0 + 12))

    def _draw_stats_panel(self, me: dict) -> None:
        """Dedicated panel (right of the minimap) listing all hero stats."""
        x0 = self.minimap.right + 10
        y0 = self.minimap.top
        w, h = 188, self.minimap.height
        panel = pygame.Surface((w, h))
        panel.set_alpha(220)
        panel.fill((22, 26, 32))
        self.screen.blit(panel, (x0, y0))
        pygame.draw.rect(self.screen, (90, 90, 110), (x0, y0, w, h), 2)

        name = me.get("name", "")
        lvl = me.get("lvl", 1)
        xp, xpn = me.get("xp", 0), me.get("xpn", 0)
        xp_str = f"{xp}/{xpn}" if xpn else "MAX"
        rows = [
            (f"{name}  (Lvl {lvl})", COLOR_TEXT),
            (f"HP   {me.get('hp', 0)}/{me.get('mhp', 0)}", COLOR_HEALTH),
            (f"MP   {me.get('mana', 0)}/{me.get('mmana', 0)}", COLOR_MANA),
            (f"XP   {xp_str}", (180, 200, 240)),
            (f"Gold {me.get('gold', 0)}", (240, 220, 120)),
            (f"ATK  {me.get('ad', 0)}", COLOR_TEXT),
            (f"SPD  {me.get('ms', 0)}", COLOR_TEXT),
        ]
        for i, (text, color) in enumerate(rows):
            label = self.font.render(text, True, color)
            self.screen.blit(label, (x0 + 8, y0 + 8 + i * 20))

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

        # Lane line for orientation.
        pygame.draw.line(self.screen, COLOR_LANE,
                         to_mm(0, LANE_Y), to_mm(MAP_WIDTH, LANE_Y), 1)

        for ent in entities:
            et = ent.get("et")
            if et == EntityType.PROJECTILE:
                continue
            if et == EntityType.HERO and not ent.get("a", True):
                continue
            mx, my = to_mm(ent["x"], ent["y"])
            color = _team_color(ent.get("tm", 0))
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
        """Inventory slots (bottom-right), labelled F1..F6 with active cooldowns."""
        inv = me.get("inv", [])
        icds = me.get("icds", {})
        names = {it["item_id"]: it["name"] for it in self.item_catalog}
        slot = 46
        x0 = SCREEN_WIDTH - slot * 6 - 10
        y0 = SCREEN_HEIGHT - 52
        for i in range(6):
            x = x0 + i * slot
            rect = pygame.Rect(x, y0, slot - 6, slot - 6)
            pygame.draw.rect(self.screen, (40, 45, 55), rect, border_radius=4)
            pygame.draw.rect(self.screen, (80, 80, 95), rect, 1, border_radius=4)
            self.screen.blit(self.font.render(f"F{i+1}", True, (120, 120, 140)),
                             (x + 2, y0 - 14))
            if i < len(inv):
                item_id = inv[i]
                short = names.get(item_id, item_id)[:5]
                self.screen.blit(self.font.render(short, True, COLOR_TEXT),
                                 (x + 3, y0 + 6))
                cd = icds.get(item_id, 0)
                if cd > 0:
                    self.screen.blit(
                        self.font.render(f"{cd:.0f}", True, (240, 200, 120)),
                        (x + 3, y0 + 22))

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
