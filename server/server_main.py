"""Authoritative game server using asyncio."""

from __future__ import annotations

import asyncio
import sys
import time

from shared.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    SERVER_TICK_RATE,
    TICK_DURATION,
    MAP_WIDTH,
    MAP_HEIGHT,
)
from shared.game_types import MsgType, GamePhase
from server.game_state import GameState
from server.net_handler import ClientHandler
from server.systems import system_movement


class GameServer:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self.state = GameState()
        self.clients: dict[int, ClientHandler] = {}
        self._next_client_id = 1

    async def start(self) -> None:
        server = await asyncio.start_server(
            self._on_connect, self.host, self.port
        )
        addr = server.sockets[0].getsockname()
        print(f"[SERVER] Listening on {addr[0]}:{addr[1]}")
        print(f"[SERVER] Tick rate: {SERVER_TICK_RATE}/s | Map: {MAP_WIDTH}x{MAP_HEIGHT}")
        print("[SERVER] Waiting for players to connect...")

        asyncio.create_task(self._game_loop())
        async with server:
            await server.serve_forever()

    async def _on_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        client_id = self._next_client_id
        self._next_client_id += 1
        handler = ClientHandler(client_id, reader, writer)
        self.clients[client_id] = handler
        addr = writer.get_extra_info("peername")
        print(f"[SERVER] Client {client_id} connected from {addr}")

    async def _game_loop(self) -> None:
        """Fixed-timestep game loop."""
        while True:
            tick_start = time.monotonic()

            # Read inputs from all clients
            await self._process_inputs()

            # Remove disconnected clients
            self._cleanup_disconnected()

            # Run game systems
            if self.state.phase == GamePhase.PLAYING:
                system_movement(self.state, TICK_DURATION)
                self.state.tick += 1

            # Broadcast state to all clients
            await self._broadcast_snapshot()

            # Sleep until next tick
            elapsed = time.monotonic() - tick_start
            sleep_time = max(0, TICK_DURATION - elapsed)
            await asyncio.sleep(sleep_time)

    async def _process_inputs(self) -> None:
        for client_id, handler in list(self.clients.items()):
            messages = await handler.read_messages()
            for msg in messages:
                self._handle_message(client_id, msg)

    def _handle_message(self, client_id: int, msg: dict) -> None:
        msg_type = msg.get("t")

        if msg_type == MsgType.JOIN:
            self._handle_join(client_id, msg)
        elif msg_type == MsgType.MOVE:
            self._handle_move(client_id, msg)
        elif msg_type == MsgType.START_GAME:
            self._handle_start_game()

    def _handle_join(self, client_id: int, msg: dict) -> None:
        name = msg.get("name", f"Player{client_id}")
        team = self.state.assign_team()
        hero = self.state.add_hero(client_id, name, team)
        print(f"[SERVER] {name} joined Team {int(team)} (hero id={hero.entity_id})")

        handler = self.clients.get(client_id)
        if handler:
            handler.send({
                "t": int(MsgType.JOIN_ACK),
                "eid": hero.entity_id,
                "team": int(team),
                "name": name,
            })

    def _handle_move(self, client_id: int, msg: dict) -> None:
        hero = self.state.get_hero(client_id)
        if hero is None or not hero.alive:
            return
        tx = msg.get("tx")
        ty = msg.get("ty")
        if tx is not None and ty is not None:
            # Clamp target to map bounds
            hero.target_x = max(0, min(MAP_WIDTH, float(tx)))
            hero.target_y = max(0, min(MAP_HEIGHT, float(ty)))

    def _handle_start_game(self) -> None:
        if self.state.phase == GamePhase.WAITING and len(self.state.player_heroes) >= 1:
            self.state.phase = GamePhase.PLAYING
            print(f"[SERVER] Game started with {len(self.state.player_heroes)} players!")

    def _cleanup_disconnected(self) -> None:
        to_remove = [cid for cid, h in self.clients.items() if not h.connected]
        for cid in to_remove:
            print(f"[SERVER] Client {cid} disconnected")
            self.state.remove_hero(cid)
            handler = self.clients.pop(cid)
            handler.close()

    async def _broadcast_snapshot(self) -> None:
        if not self.clients:
            return
        snapshot = self.state.build_snapshot()
        msg = {
            "t": int(MsgType.SNAPSHOT),
            "tick": self.state.tick,
            "phase": int(self.state.phase),
            "entities": snapshot,
        }
        for handler in self.clients.values():
            handler.send(msg)
        # Flush all writers
        for handler in self.clients.values():
            await handler.flush()


def run_server() -> None:
    host = DEFAULT_HOST
    port = DEFAULT_PORT

    # Parse --host and --port from sys.argv
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--host" and i + 1 < len(args):
            host = args[i + 1]
        elif arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])

    server = GameServer(host=host, port=port)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down.")
