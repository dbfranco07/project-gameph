"""Capture keyboard/mouse input and convert to server messages."""

from __future__ import annotations

import math
import pygame

from shared.game_types import MsgType
from shared.config import ATTACK_CLICK_PIXELS
from client.camera import Camera

# Ability keys mapped to their ability "key" label sent to the server.
_ABILITY_KEYS = {
    pygame.K_q: "Q",
    pygame.K_w: "W",
    pygame.K_e: "E",
    pygame.K_r: "R",
}


class InputHandler:
    def __init__(self, camera: Camera) -> None:
        self.camera = camera
        # True after pressing 'A': the next left-click issues an attack command.
        self.attack_armed = False

    def process_events(self, events, entities, my_team) -> list[dict]:
        """Process Pygame events and return messages to send to the server.

        `entities` is the current interpolated entity list, used to resolve which
        enemy (if any) sits under the cursor for an 'A + click' attack command.
        """
        messages: list[dict] = []

        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_a:
                    self.attack_armed = True
                elif event.key == pygame.K_s:
                    self.attack_armed = False
                    messages.append({"t": int(MsgType.STOP)})
                elif event.key in _ABILITY_KEYS:
                    wx, wy = self.camera.screen_to_world(*pygame.mouse.get_pos())
                    messages.append({
                        "t": int(MsgType.USE_ABILITY),
                        "key": _ABILITY_KEYS[event.key],
                        "tx": wx,
                        "ty": wy,
                    })

            elif event.type == pygame.MOUSEBUTTONDOWN:
                wx, wy = self.camera.screen_to_world(*event.pos)
                if event.button == 1 and self.attack_armed:
                    # Attack command: focus an enemy under the cursor, or attack-move.
                    self.attack_armed = False
                    tid = self._enemy_under_cursor(entities, my_team, wx, wy)
                    messages.append({
                        "t": int(MsgType.ATTACK),
                        "tx": wx,
                        "ty": wy,
                        "tid": tid,
                    })
                elif event.button == 3:
                    # Right-click: move command (also cancels a pending attack).
                    self.attack_armed = False
                    messages.append({"t": int(MsgType.MOVE), "tx": wx, "ty": wy})

        return messages

    def _enemy_under_cursor(self, entities, my_team, wx, wy):
        """Return the entity id of the closest enemy near (wx, wy), or None."""
        best_id = None
        best_dist = None
        for ent in entities:
            team = ent.get("tm", 0)
            if team == my_team or team == 0:
                continue
            if not ent.get("a", True):
                continue
            d = math.hypot(ent["x"] - wx, ent["y"] - wy)
            if d <= ent.get("r", 20) + ATTACK_CLICK_PIXELS:
                if best_dist is None or d < best_dist:
                    best_dist, best_id = d, ent["id"]
        return best_id
