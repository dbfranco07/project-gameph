"""Render the game world using Pygame."""

from __future__ import annotations

import pygame
from shared.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    MAP_WIDTH,
    MAP_HEIGHT,
    COLOR_BG,
    COLOR_TEAM1,
    COLOR_TEAM2,
    COLOR_HEALTH_BG,
    COLOR_HEALTH,
    COLOR_GRID,
    COLOR_TEXT,
)
from shared.game_types import Team, GamePhase
from client.camera import Camera


class Renderer:
    def __init__(self, screen: pygame.Surface, camera: Camera) -> None:
        self.screen = screen
        self.camera = camera
        self.font = pygame.font.SysFont("monospace", 14)
        self.font_large = pygame.font.SysFont("monospace", 24)

    def draw_frame(
        self,
        entities: list[dict],
        my_entity_id: int | None,
        my_team: int | None,
        phase: int,
        tick: int,
    ) -> None:
        self.screen.fill(COLOR_BG)
        self._draw_grid()
        self._draw_map_border()

        for ent in entities:
            self._draw_entity(ent, ent["id"] == my_entity_id if my_entity_id else False)

        self._draw_hud(entities, my_entity_id, my_team, phase, tick)
        pygame.display.flip()

    def _draw_grid(self) -> None:
        """Draw a subtle grid to show movement."""
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

    def _draw_map_border(self) -> None:
        """Draw the map boundary."""
        corners = [
            self.camera.world_to_screen(0, 0),
            self.camera.world_to_screen(MAP_WIDTH, 0),
            self.camera.world_to_screen(MAP_WIDTH, MAP_HEIGHT),
            self.camera.world_to_screen(0, MAP_HEIGHT),
        ]
        pygame.draw.lines(self.screen, (100, 100, 100), True, corners, 2)

    def _draw_entity(self, ent: dict, is_me: bool) -> None:
        if not ent.get("a", True):
            return  # dead

        sx, sy = self.camera.world_to_screen(ent["x"], ent["y"])
        radius = int(ent.get("r", 20))

        # Skip if off screen
        if sx < -radius or sx > SCREEN_WIDTH + radius:
            return
        if sy < -radius or sy > SCREEN_HEIGHT + radius:
            return

        # Team color
        team = ent.get("tm", 0)
        color = COLOR_TEAM1 if team == Team.TEAM1 else COLOR_TEAM2
        if team == Team.NONE:
            color = (180, 180, 180)

        # Draw hero circle
        pygame.draw.circle(self.screen, color, (sx, sy), radius)
        if is_me:
            # Highlight ring for your hero
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), radius + 3, 2)

        # Health bar
        hp = ent.get("hp", 0)
        max_hp = ent.get("mhp", 1)
        bar_w = radius * 2 + 10
        bar_h = 4
        bar_x = sx - bar_w // 2
        bar_y = sy - radius - 10
        pygame.draw.rect(self.screen, COLOR_HEALTH_BG, (bar_x, bar_y, bar_w, bar_h))
        hp_w = int(bar_w * hp / max(max_hp, 1))
        pygame.draw.rect(self.screen, COLOR_HEALTH, (bar_x, bar_y, hp_w, bar_h))

        # Name label
        name = ent.get("name")
        if name:
            label = self.font.render(name, True, COLOR_TEXT)
            self.screen.blit(label, (sx - label.get_width() // 2, bar_y - 16))

    def _draw_hud(
        self,
        entities: list[dict],
        my_entity_id: int | None,
        my_team: int | None,
        phase: int,
        tick: int,
    ) -> None:
        # Phase indicator
        phase_names = {0: "WAITING", 1: "PLAYING", 2: "FINISHED"}
        phase_text = phase_names.get(phase, "???")
        label = self.font.render(
            f"Phase: {phase_text}  |  Tick: {tick}  |  Players: {len(entities)}",
            True,
            COLOR_TEXT,
        )
        self.screen.blit(label, (10, 10))

        # Team indicator
        if my_team is not None:
            team_color = COLOR_TEAM1 if my_team == Team.TEAM1 else COLOR_TEAM2
            team_label = self.font.render(
                f"Team {my_team}", True, team_color
            )
            self.screen.blit(team_label, (10, 30))

        # My hero stats
        if my_entity_id is not None:
            for ent in entities:
                if ent["id"] == my_entity_id:
                    hp_text = f"HP: {ent.get('hp', 0)}/{ent.get('mhp', 0)}"
                    gold_text = f"Gold: {ent.get('gold', 0)}"
                    stats = self.font.render(f"{hp_text}  |  {gold_text}", True, COLOR_TEXT)
                    self.screen.blit(stats, (10, SCREEN_HEIGHT - 30))
                    break

        # Instructions
        if phase == GamePhase.WAITING:
            hint = self.font_large.render(
                "Press SPACE to start the game", True, (200, 200, 100)
            )
            self.screen.blit(
                hint,
                (SCREEN_WIDTH // 2 - hint.get_width() // 2, SCREEN_HEIGHT // 2),
            )
        else:
            hint = self.font.render(
                "Right-click to move", True, (150, 150, 150)
            )
            self.screen.blit(hint, (SCREEN_WIDTH - hint.get_width() - 10, 10))
