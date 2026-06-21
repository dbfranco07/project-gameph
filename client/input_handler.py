"""Capture keyboard/mouse input and convert to server messages."""

from __future__ import annotations

import math
import pygame

from shared.game_types import MsgType, CastType
from shared.config import ATTACK_CLICK_PIXELS
from client.camera import Camera

# Ability keys mapped to their ability "key" label sent to the server.
_ABILITY_KEYS = {
    pygame.K_q: "Q",
    pygame.K_w: "W",
    pygame.K_e: "E",
    pygame.K_r: "R",
}

# Digit keys 1..9 (shop: buy that catalog row).
_DIGIT_KEYS = {getattr(pygame, f"K_{i}"): i for i in range(1, 10)}

# Function keys F1..F6 map to inventory slots 0..5 (use active / sell in shop).
_ITEM_SLOT_KEYS = {getattr(pygame, f"K_F{i}"): i - 1 for i in range(1, 7)}


class InputHandler:
    def __init__(self, camera: Camera) -> None:
        self.camera = camera
        # True after pressing 'A': the next left-click issues an attack command.
        self.attack_armed = False
        # Per-ability cast-type metadata (key -> CastType int), from JOIN_ACK.
        self.ability_cast_types: dict[str, int] = {}
        # Key of an ability awaiting a target click (None = not targeting).
        self.pending_cast: str | None = None
        # Shop state + catalog (item metadata) delivered in JOIN_ACK.
        self.shop_open = False
        self.item_catalog: list[dict] = []

    def set_hero_abilities(self, abilities: list[dict]) -> None:
        self.ability_cast_types = {
            ab["key"]: ab.get("cast", int(CastType.POINT))
            for ab in (abilities or [])
        }

    def set_item_catalog(self, catalog: list[dict]) -> None:
        self.item_catalog = catalog or []

    def process_events(self, events, entities, my_team) -> list[dict]:
        """Process Pygame events and return messages to send to the server.

        `entities` is the current interpolated entity list, used to resolve which
        enemy (if any) sits under the cursor for an 'A + click' attack command or
        a unit-targeted ability.
        """
        messages: list[dict] = []

        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_b:
                    self.shop_open = not self.shop_open
                elif self.shop_open and event.key in _DIGIT_KEYS:
                    self._buy(_DIGIT_KEYS[event.key] - 1, messages)
                elif event.key in _ITEM_SLOT_KEYS:
                    self._on_item_slot(_ITEM_SLOT_KEYS[event.key], messages)
                elif event.key == pygame.K_a:
                    self.attack_armed = True
                    self.pending_cast = None
                elif event.key == pygame.K_s:
                    self.attack_armed = False
                    self.pending_cast = None
                    messages.append({"t": int(MsgType.STOP)})
                elif event.key in _ABILITY_KEYS:
                    if event.mod & pygame.KMOD_ALT:
                        # Alt + Q/W/E/R: spend a skill point to rank it up.
                        messages.append({"t": int(MsgType.LEVEL_ABILITY),
                                         "key": _ABILITY_KEYS[event.key]})
                    else:
                        self._on_ability_key(_ABILITY_KEYS[event.key], messages)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                wx, wy = self.camera.screen_to_world(*event.pos)
                if event.button == 1 and self.pending_cast is not None:
                    self._resolve_cast(entities, my_team, wx, wy, messages)
                elif event.button == 1 and self.attack_armed:
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
                    # Right-click cancels a pending cast; otherwise it moves.
                    self.attack_armed = False
                    if self.pending_cast is not None:
                        self.pending_cast = None
                    else:
                        messages.append({"t": int(MsgType.MOVE), "tx": wx, "ty": wy})

        return messages

    def _on_ability_key(self, key: str, messages: list[dict]) -> None:
        """Press an ability: self-cast fires now; targeted casts arm a pending
        state resolved by the next left-click. Re-pressing the same key cancels."""
        self.attack_armed = False
        cast = self.ability_cast_types.get(key, int(CastType.POINT))
        if cast == int(CastType.PASSIVE):
            return  # passives can't be cast
        if cast == int(CastType.NONE):
            self.pending_cast = None
            messages.append({"t": int(MsgType.USE_ABILITY), "key": key,
                             "tx": 0.0, "ty": 0.0, "tid": None})
        elif self.pending_cast == key:
            self.pending_cast = None  # toggle off
        else:
            self.pending_cast = key

    def _buy(self, index: int, messages: list[dict]) -> None:
        """Shop is open: buy the catalog row at `index`."""
        if 0 <= index < len(self.item_catalog):
            messages.append({"t": int(MsgType.BUY_ITEM),
                             "item": self.item_catalog[index]["item_id"]})

    def _on_item_slot(self, slot: int, messages: list[dict]) -> None:
        """F-key on an inventory slot: sell it while shopping, else use its active."""
        if self.shop_open:
            messages.append({"t": int(MsgType.SELL_ITEM), "slot": slot})
        else:
            # Item actives use slot keys "I1".."I6" on the ability cast path.
            messages.append({"t": int(MsgType.USE_ABILITY),
                             "key": f"I{slot + 1}", "tx": 0.0, "ty": 0.0,
                             "tid": None})

    def _resolve_cast(self, entities, my_team, wx, wy, messages: list[dict]) -> None:
        """Left-click while targeting: send the queued ability at the click."""
        key = self.pending_cast
        self.pending_cast = None
        cast = self.ability_cast_types.get(key, int(CastType.POINT))
        tid = None
        if cast == int(CastType.UNIT):
            tid = self._enemy_under_cursor(entities, my_team, wx, wy)
        messages.append({"t": int(MsgType.USE_ABILITY), "key": key,
                         "tx": wx, "ty": wy, "tid": tid})

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
