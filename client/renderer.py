"""Render the game world using Pygame.

Entities are drawn by a small per-type drawer registry keyed on the snapshot's
entity-type tag ("et"). Each drawer reads a shape descriptor today; swapping a
descriptor to a sprite later needs no gameplay changes.
"""

from __future__ import annotations

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
    COLOR_GRID,
    COLOR_TEXT,
    COLOR_PROJECTILE,
    COLOR_STRUCTURE_DEAD,
    COLOR_LANE,
)
from shared.game_types import Team, GamePhase, EntityType
from shared.hero_schema import get_hero_def
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

        self._draw_hud(entities, my_entity_id, my_team, phase, tick,
                       score or {}, ktarget, winner)
        pygame.display.flip()

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

        # My stats + ability bar (bottom)
        if me is not None:
            stats = self.font.render(
                f"HP {me.get('hp', 0)}/{me.get('mhp', 0)}   "
                f"MP {me.get('mana', 0)}/{me.get('mmana', 0)}   "
                f"Gold {me.get('gold', 0)}   Lvl {me.get('lvl', 1)}",
                True, COLOR_TEXT)
            self.screen.blit(stats, (10, SCREEN_HEIGHT - 26))
            self._draw_ability_bar(me)
            if not me.get("a", True):
                self._draw_respawn(me)

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
                "Right-click move  |  Q/W/E/R abilities (aim w/ cursor)",
                True, (150, 150, 150))
            self.screen.blit(hint, (SCREEN_WIDTH - hint.get_width() - 10, 10))

    def _draw_ability_bar(self, me: dict) -> None:
        hdef = get_hero_def(me.get("hid"))
        abilities = hdef.get("abilities", [])
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
            pygame.draw.rect(self.screen, (90, 90, 110), rect, 2, border_radius=6)
            key_label = self.font.render(ab["key"], True, COLOR_TEXT)
            self.screen.blit(key_label, (x + 4, y0 + 2))
            if cd > 0:
                cd_label = self.font_large.render(f"{cd:.0f}", True, (240, 200, 120))
                self.screen.blit(cd_label, (x + (slot - 8) // 2 - cd_label.get_width() // 2,
                                            y0 + 12))

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
