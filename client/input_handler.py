"""Capture keyboard/mouse input and convert to server messages."""

from __future__ import annotations

import pygame
from shared.game_types import MsgType
from client.camera import Camera


class InputHandler:
    def __init__(self, camera: Camera) -> None:
        self.camera = camera

    def process_events(self, events: list[pygame.event.Event]) -> list[dict]:
        """Process Pygame events and return a list of messages to send to server."""
        messages = []

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                # Right-click: move command
                wx, wy = self.camera.screen_to_world(*event.pos)
                messages.append({
                    "t": int(MsgType.MOVE),
                    "tx": wx,
                    "ty": wy,
                })

        return messages
