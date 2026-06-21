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
    EDGE_PAN_MARGIN,
    CAMERA_PAN_SPEED,
)
from shared.game_types import MsgType, GamePhase
from shared.protocol import pack_message, unpack_from_buffer
from client.camera import Camera
from client.interpolation import Interpolator
from client.input_handler import InputHandler
from client.renderer import Renderer
from client.menu import MainMenu, LobbyScreen

# Client screen states.
SCREEN_MENU = "menu"
SCREEN_LOBBY = "lobby"
SCREEN_GAME = "game"


class GameClient:
    def __init__(self, host: str, port: int, player_name: str,
                 hero: str = "", kill_target: int = 0,
                 skip_menu: bool = False) -> None:
        self.host = host
        self.port = port
        self.player_name = player_name
        self.hero = hero
        self.kill_target = kill_target
        self.skip_menu = skip_menu

        # Screen / lobby state
        self.screen_state = SCREEN_MENU
        self.screen: pygame.Surface | None = None
        self.menu: MainMenu | None = None
        self.lobby: LobbyScreen | None = None
        self.my_client_id: int | None = None
        self.is_host = False
        self.available_heroes: list[dict] = []
        self.lobby_players: list[dict] = []
        self._centered = False  # camera centered on hero at match start

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
        self.match_clock: float = 0.0

        # Client systems
        self.camera = Camera()
        self.interpolator = Interpolator()
        self.input_handler = InputHandler(self.camera)
        self.renderer: Renderer | None = None

    def connect(self) -> bool:
        """Connect to the game server via TCP."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(3.0)  # don't freeze the menu on a bad address
            self.sock.connect((self.host, self.port))
            self.sock.setblocking(False)  # clears the timeout for in-game use
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
        """Main client loop: menu -> lobby -> in-game."""
        pygame.init()
        # Fullscreen, but keep a fixed logical resolution: SCALED letterboxes /
        # scales to the display so all HUD layout + mouse coords stay in
        # SCREEN_WIDTH x SCREEN_HEIGHT space.
        screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN | pygame.SCALED)
        pygame.display.set_caption("MOBA Lite")
        clock = pygame.time.Clock()
        self.screen = screen
        self.renderer = Renderer(screen, self.camera)
        self.menu = MainMenu(self.player_name, self.host, self.port)
        self.lobby = LobbyScreen()

        if self.skip_menu:
            self._do_connect(self.player_name, self.host, self.port)

        running = True
        while running:
            dt = clock.get_time() / 1000.0  # seconds since last frame
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    running = False
            if not running:
                break

            if self.screen_state == SCREEN_MENU:
                running = self._tick_menu(events)
            elif self.screen_state == SCREEN_LOBBY:
                running = self._tick_lobby(events)
            else:
                running = self._tick_game(events, dt)

            clock.tick(CLIENT_FPS)

        self._disconnect()
        pygame.quit()

    # ----- screen states ----------------------------------------------------
    def _tick_menu(self, events) -> bool:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
        action = self.menu.handle(events)
        if action and action[0] == "connect":
            _, name, host, port = action
            self._do_connect(name, host, port)
        self.menu.draw(self.screen)
        pygame.display.flip()
        return True

    def _do_connect(self, name: str, host: str, port: int) -> None:
        self.player_name = name
        self.host = host
        self.port = port
        if self.connect():
            self.screen_state = SCREEN_LOBBY
            self.lobby.status = f"Connected to {host}:{port}"
        else:
            self.menu.error = f"Could not connect to {host}:{port}"

    def _tick_lobby(self, events) -> bool:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
        for action in self.lobby.handle(events):
            if action[0] == "team":
                self._send({"t": int(MsgType.SELECT_TEAM), "team": action[1]})
            elif action[0] == "hero":
                self._send({"t": int(MsgType.SELECT_HERO), "hero": action[1]})
            elif action[0] == "start":
                msg = {"t": int(MsgType.START_GAME)}
                if self.kill_target:
                    msg["ktarget"] = self.kill_target
                self._send(msg)
        self._receive()  # JOIN_ACK here flips us into SCREEN_GAME
        # Mirror network state into the lobby view.
        self.lobby.players = self.lobby_players
        self.lobby.heroes = self.available_heroes
        self.lobby.my_cid = self.my_client_id
        self.lobby.is_host = self.is_host
        if self.screen_state == SCREEN_LOBBY:
            self.lobby.draw(self.screen)
            pygame.display.flip()
        return True

    def _tick_game(self, events, dt: float) -> bool:
        running = True
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # Minimap clicks recenter the camera (consumed before gameplay input).
        events = self._consume_minimap_clicks(events)

        # Send input messages (needs current entities for targeting).
        entities = self.interpolator.get_entities()
        messages = self.input_handler.process_events(
            events, entities, self.my_team)
        for msg in messages:
            self._send(msg)

        self._receive()

        entities = self.interpolator.get_entities()
        if not self._centered:
            self._center_on_hero(entities)
        self._update_camera(entities, dt)

        self.renderer.pending_cast = self.input_handler.pending_cast
        self.renderer.attack_armed = self.input_handler.attack_armed
        self.renderer.shop_open = self.input_handler.shop_open
        self.renderer.draw_frame(
            entities, self.my_entity_id, self.my_team, self.phase, self.tick,
            self.score, self.ktarget, self.winner, self.match_clock)
        return running

    def _center_on_hero(self, entities) -> None:
        """Snap the camera onto our hero once it appears at match start."""
        if self.my_entity_id is None:
            return
        for ent in entities:
            if ent["id"] == self.my_entity_id:
                self.camera.follow(ent["x"], ent["y"])
                self._centered = True
                return

    def _consume_minimap_clicks(self, events):
        """Recenter the camera on left-clicks inside the minimap; drop those
        events so they don't also trigger a world attack/move."""
        if self.renderer is None:
            return events
        kept = []
        for event in events:
            if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1):
                world = self.renderer.minimap_to_world(*event.pos)
                if world is not None:
                    self.camera.follow(*world)
                    continue
            kept.append(event)
        return kept

    def _update_camera(self, entities, dt: float) -> None:
        """Dota-style free camera: hold/press 1 to recenter on the hero,
        otherwise pan when the mouse is near a screen edge."""
        keys = pygame.key.get_pressed()
        if keys[pygame.K_1] and not self.input_handler.shop_open \
                and self.my_entity_id is not None:
            for ent in entities:
                if ent["id"] == self.my_entity_id:
                    self.camera.follow(ent["x"], ent["y"])
                    return
        # Pause panning only when the window truly loses focus (e.g. alt-tab).
        # Use KEYBOARD focus, not mouse focus: on macOS fullscreen the cursor
        # grazing the top menu-bar zone drops mouse focus for a frame, which
        # would stutter upward panning. Keyboard focus stays put.
        if not pygame.key.get_focused():
            return
        mx, my = pygame.mouse.get_pos()
        # Don't edge-pan while hovering the minimap (it lives in the corner).
        if self.renderer is not None and self.renderer.minimap.collidepoint(mx, my):
            return
        step = CAMERA_PAN_SPEED * dt
        dx = dy = 0.0
        if mx <= EDGE_PAN_MARGIN:
            dx = -step
        elif mx >= SCREEN_WIDTH - EDGE_PAN_MARGIN:
            dx = step
        if my <= EDGE_PAN_MARGIN:
            dy = -step
        elif my >= SCREEN_HEIGHT - EDGE_PAN_MARGIN:
            dy = step
        if dx or dy:
            self.camera.pan(dx, dy)

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

        if msg_type == MsgType.LOBBY_WELCOME:
            self.my_client_id = msg.get("cid")
            self.is_host = msg.get("host", False)
            self.available_heroes = msg.get("heroes", [])
            print(f"[CLIENT] In lobby as client {self.my_client_id}"
                  f"{' (host)' if self.is_host else ''}")

        elif msg_type == MsgType.PLAYER_LIST:
            self.lobby_players = msg.get("players", [])

        elif msg_type == MsgType.JOIN_ACK:
            self.my_entity_id = msg["eid"]
            self.my_team = msg["team"]
            hero_def = msg.get("hero_def") or {}
            abilities = hero_def.get("abilities", [])
            catalog = msg.get("items", [])
            # Hand ability metadata to the renderer (ability bar) and input
            # handler (targeting cast-types), delivered over the wire.
            self.renderer.set_hero_abilities(abilities)
            self.input_handler.set_hero_abilities(abilities)
            self.renderer.set_item_catalog(catalog)
            self.input_handler.set_item_catalog(catalog)
            # Match has begun for us — leave the lobby and bind the in-game view.
            self._centered = False
            self.screen_state = SCREEN_GAME
            print(f"[CLIENT] Joined as entity {self.my_entity_id}, Team {self.my_team}")

        elif msg_type == MsgType.SNAPSHOT:
            self.phase = msg.get("phase", self.phase)
            self.tick = msg.get("tick", self.tick)
            self.score = msg.get("score", self.score)
            self.ktarget = msg.get("ktarget", self.ktarget)
            self.winner = msg.get("winner", self.winner)
            self.match_clock = msg.get("clock", self.match_clock)
            self.interpolator.push_snapshot(msg.get("entities", []))
            if self.renderer is not None:
                self.renderer.add_combat_events(msg.get("events", []))

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
    skip_menu = False

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
        elif arg == "--skip-menu":
            skip_menu = True  # auto-connect straight into the lobby (quick test)

    client = GameClient(host=host, port=port, player_name=name,
                        hero=hero, kill_target=kill_target, skip_menu=skip_menu)
    client.run()
