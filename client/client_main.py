"""Pygame client — connects to the game server and renders the game."""

from __future__ import annotations

import socket
import sys
import pygame

from shared.config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    CLIENT_FPS,
    DEFAULT_HOST,
    DEFAULT_PORT,
)
from shared.game_types import MsgType, GamePhase
from shared.protocol import pack_message, unpack_from_buffer
from client.camera import Camera
from client.interpolation import Interpolator
from client.input_handler import InputHandler
from client.renderer import Renderer


class GameClient:
    def __init__(self, host: str, port: int, player_name: str,
                 hero: str = "", kill_target: int = 0) -> None:
        self.host = host
        self.port = port
        self.player_name = player_name
        self.hero = hero
        self.kill_target = kill_target

        # Network
        self.sock: socket.socket | None = None
        self.recv_buffer = bytearray()

        # Game state from server
        self.my_entity_id: int | None = None
        self.my_team: int | None = None
        self.phase: int = GamePhase.WAITING
        self.tick: int = 0
        self.score: dict = {}
        self.ktarget: int = 0
        self.winner: int = 0

        # Client systems
        self.camera = Camera()
        self.interpolator = Interpolator()
        self.input_handler = InputHandler(self.camera)

    def connect(self) -> bool:
        """Connect to the game server via TCP."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            self.sock.setblocking(False)
            print(f"[CLIENT] Connected to {self.host}:{self.port}")

            # Send join message
            join_msg = pack_message({
                "t": int(MsgType.JOIN),
                "name": self.player_name,
                "hero": self.hero,
            })
            self.sock.sendall(join_msg)
            return True
        except (ConnectionRefusedError, OSError) as e:
            print(f"[CLIENT] Failed to connect: {e}")
            return False

    def run(self) -> None:
        """Main client loop."""
        pygame.init()
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(f"MOBA Lite — {self.player_name}")
        clock = pygame.time.Clock()
        renderer = Renderer(screen, self.camera)

        if not self.connect():
            pygame.quit()
            return

        running = True
        while running:
            # 1. Handle Pygame events
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        msg = {"t": int(MsgType.START_GAME)}
                        if self.kill_target:
                            msg["ktarget"] = self.kill_target
                        self._send(msg)

            # 2. Send input messages to server (needs current entities for targeting)
            entities = self.interpolator.get_entities()
            messages = self.input_handler.process_events(
                events, entities, self.my_team)
            for msg in messages:
                self._send(msg)

            # 3. Receive and process server messages
            self._receive()

            # 4. Update camera to follow our hero
            entities = self.interpolator.get_entities()
            if self.my_entity_id is not None:
                for ent in entities:
                    if ent["id"] == self.my_entity_id:
                        self.camera.follow(ent["x"], ent["y"])
                        break

            # 5. Render
            renderer.draw_frame(
                entities,
                self.my_entity_id,
                self.my_team,
                self.phase,
                self.tick,
                self.score,
                self.ktarget,
                self.winner,
            )

            clock.tick(CLIENT_FPS)

        self._disconnect()
        pygame.quit()

    def _send(self, msg: dict) -> None:
        if self.sock is None:
            return
        try:
            data = pack_message(msg)
            self.sock.sendall(data)
        except (BrokenPipeError, OSError):
            pass

    def _receive(self) -> None:
        if self.sock is None:
            return
        try:
            data = self.sock.recv(65536)
            if not data:
                return
            self.recv_buffer.extend(data)
        except BlockingIOError:
            pass
        except (ConnectionResetError, OSError):
            return

        messages = unpack_from_buffer(self.recv_buffer)
        for msg in messages:
            self._handle_server_message(msg)

    def _handle_server_message(self, msg: dict) -> None:
        msg_type = msg.get("t")

        if msg_type == MsgType.JOIN_ACK:
            self.my_entity_id = msg["eid"]
            self.my_team = msg["team"]
            print(f"[CLIENT] Joined as entity {self.my_entity_id}, Team {self.my_team}")

        elif msg_type == MsgType.SNAPSHOT:
            self.phase = msg.get("phase", self.phase)
            self.tick = msg.get("tick", self.tick)
            self.score = msg.get("score", self.score)
            self.ktarget = msg.get("ktarget", self.ktarget)
            self.winner = msg.get("winner", self.winner)
            self.interpolator.push_snapshot(msg.get("entities", []))

        elif msg_type == MsgType.GAME_OVER:
            self.winner = msg.get("winner", 0)
            print(f"[CLIENT] Game Over! Team {self.winner} wins!")

    def _disconnect(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        print("[CLIENT] Disconnected.")


def run_client() -> None:
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    name = "Player"
    hero = ""
    kill_target = 0

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--host" and i + 1 < len(args):
            host = args[i + 1]
        elif arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        elif arg == "--name" and i + 1 < len(args):
            name = args[i + 1]
        elif arg == "--hero" and i + 1 < len(args):
            hero = args[i + 1]
        elif arg == "--ktarget" and i + 1 < len(args):
            kill_target = int(args[i + 1])

    client = GameClient(host=host, port=port, player_name=name,
                        hero=hero, kill_target=kill_target)
    client.run()
