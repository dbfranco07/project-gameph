"""In-game chat box: text entry + a fading message log.

Flow (matches the client keybinds):
  * Enter                -> open the input line, addressed to ALLIES (team).
  * Cmd+Enter (mac) /
    Alt+Enter (win/linux)-> open the input line, addressed to EVERYONE.
  * While typing: printable keys append, Backspace deletes, Enter sends,
    Escape cancels. All other input is swallowed so gameplay keys (Q/W/E,
    move clicks, ...) never fire while you're composing a message.
"""

from __future__ import annotations

import sys
import time
import pygame

from shared.game_types import MsgType

# Modifier that selects all-chat (and matches the item-activation modifier):
# Cmd on macOS, Alt elsewhere.
_IS_MAC = sys.platform == "darwin"
_ALL_CHAT_MOD = (pygame.KMOD_GUI | pygame.KMOD_META) if _IS_MAC else pygame.KMOD_ALT

_MAX_LEN = 200          # cap a single message
_LOG_KEEP = 8           # most recent messages retained
_LOG_FADE = 12.0        # seconds a message stays fully/partly visible
_ENTER_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER)

_COLOR_ALL = (225, 225, 225)
_COLOR_TEAM = (140, 225, 150)
_COLOR_INPUT_BG = (10, 14, 22)


class ChatBox:
    def __init__(self) -> None:
        self.active = False
        self.scope_all = False          # True = all-chat, False = team-only
        self.buffer = ""
        # Log entries: {"name", "text", "all", "born"}.
        self.log: list[dict] = []

    # ----- input ------------------------------------------------------------
    def handle(self, events) -> tuple[list, list[dict]]:
        """Process events. Returns (leftover_events, messages_to_send).

        While the chat line is active every event is consumed (gameplay frozen).
        While inactive only an Enter press is consumed (to open the line); all
        other events pass through untouched.
        """
        if not self.active:
            return self._handle_closed(events)

        messages: list[dict] = []
        for event in events:
            if event.type == pygame.TEXTINPUT:
                if len(self.buffer) < _MAX_LEN:
                    self.buffer += event.text
            elif event.type == pygame.KEYDOWN:
                if event.key in _ENTER_KEYS:
                    msg = self._compose_send()
                    if msg is not None:
                        messages.append(msg)
                    self._close()
                elif event.key == pygame.K_ESCAPE:
                    self._close()
                elif event.key == pygame.K_BACKSPACE:
                    self.buffer = self.buffer[:-1]
            # everything else is swallowed while composing
        return [], messages

    def _handle_closed(self, events):
        leftover = []
        for event in events:
            if event.type == pygame.KEYDOWN and event.key in _ENTER_KEYS:
                self._open(all_chat=bool(event.mod & _ALL_CHAT_MOD))
                continue  # consume the opening Enter
            if event.type == pygame.TEXTINPUT:
                continue  # not typing yet; drop stray text events
            leftover.append(event)
        return leftover, []

    def _open(self, all_chat: bool) -> None:
        self.active = True
        self.scope_all = all_chat
        self.buffer = ""
        pygame.key.start_text_input()

    def _close(self) -> None:
        self.active = False
        self.buffer = ""
        pygame.key.stop_text_input()

    def _compose_send(self) -> dict | None:
        text = self.buffer.strip()
        if not text:
            return None
        return {"t": int(MsgType.CHAT), "text": text[:_MAX_LEN],
                "all": self.scope_all}

    # ----- incoming ---------------------------------------------------------
    def add_message(self, name: str, text: str, all_chat: bool) -> None:
        self.log.append({"name": name, "text": text, "all": all_chat,
                         "born": time.monotonic()})
        if len(self.log) > _LOG_KEEP:
            self.log = self.log[-_LOG_KEEP:]

    # ----- drawing ----------------------------------------------------------
    def draw(self, screen: pygame.Surface, font: pygame.font.Font,
             bottom_y: int) -> None:
        """Draw the message log stacked upward from `bottom_y`, with the input
        line (when active) anchored at the bottom."""
        now = time.monotonic()
        y = bottom_y

        if self.active:
            prefix = "[ALL] " if self.scope_all else "[TEAM] "
            label = font.render(prefix + self.buffer + "_", True,
                                _COLOR_ALL if self.scope_all else _COLOR_TEAM)
            bg = pygame.Rect(8, y - 2, max(260, label.get_width() + 12),
                             label.get_height() + 4)
            panel = pygame.Surface(bg.size, pygame.SRCALPHA)
            panel.fill((*_COLOR_INPUT_BG, 200))
            screen.blit(panel, bg.topleft)
            screen.blit(label, (12, y))
            y -= label.get_height() + 6

        # Log: newest at the bottom, drawn upward; old ones fade out.
        for entry in reversed(self.log):
            age = now - entry["born"]
            # Keep messages visible while you're typing so you can read context.
            if not self.active and age > _LOG_FADE:
                continue
            color = _COLOR_ALL if entry["all"] else _COLOR_TEAM
            tag = "[ALL] " if entry["all"] else ""
            label = font.render(f"{tag}{entry['name']}: {entry['text']}",
                                True, color)
            if not self.active and age > _LOG_FADE - 3.0:
                fade = max(0.0, (_LOG_FADE - age) / 3.0)
                label.set_alpha(int(255 * fade))
            y -= label.get_height() + 2
            screen.blit(label, (12, y))
