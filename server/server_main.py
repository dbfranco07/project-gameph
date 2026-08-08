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
from shared.game_types import MsgType, GamePhase, Team
from shared.protocol import PROTOCOL_VERSION
from shared.config import ITEM_SLOTS, MAX_LEVEL
from server.heroes import validate_all
from server.items import (
    validate_all as validate_items, 
    get_item_def, 
    item_catalog,
    purchase_plan, 
    apply_inventory_change
)
from server.entity import Hero
from server.game_state import GameState
from server.net_handler import ClientHandler
from server.systems import step, sandbox_set_level


class GameServer:
    """Authoritative TCP game server.

    Owns the single source of truth for the match (``GameState``) and drives a
    fixed-timestep simulation. Clients only send inputs; the server simulates,
    then broadcasts an authoritative snapshot every tick. This prevents clients
    from cheating by mutating their own game state.

    Networking is handled with ``asyncio``: each connection gets a
    ``ClientHandler``, and a background game-loop task advances the simulation
    independently of connection setup.

    Attributes:
        host: Interface address the server listens on.
        port: TCP port the server listens on.
        state: The authoritative game state shared by all clients.
        clients: Connected clients keyed by their server-assigned client id.
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 sandbox: bool = False) -> None:
        """Initializes the server without binding to the network yet.

        Args:
            host: Interface address to bind to. Defaults to ``DEFAULT_HOST``.
            port: TCP port to bind to. Defaults to ``DEFAULT_PORT``.
            sandbox: Enable chat cheat-commands for hero testing (default off).
        """
        self.host = host
        self.port = port
        self.state = GameState()
        self.state.sandbox = sandbox
        self.clients: dict[int, ClientHandler] = {}
        self._next_client_id = 1
        self._loop_task: asyncio.Task | None = None
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        """Binds the listening socket and runs the server until cancelled.

        Validates hero definitions first (failing fast on bad data), starts
        accepting connections, schedules the game loop as a background task,
        and then serves forever. This coroutine only returns when the server is
        shut down (e.g. via ``KeyboardInterrupt``).

        Raises:
            Exception: Propagated from ``validate_all`` if any hero definition
                is malformed.
        """
        validate_all()    # fail fast on malformed hero definitions
        validate_items()  # fail fast on malformed item definitions
        server = await asyncio.start_server(self._on_connect, 
                                            self.host, 
                                            self.port)
        addr = server.sockets[0].getsockname()
        print(f"[SERVER] Listening on {addr[0]}:{addr[1]}")
        print(f"[SERVER] Tick rate: {SERVER_TICK_RATE}/s | Map: {MAP_WIDTH}x{MAP_HEIGHT}")
        print("[SERVER] Waiting for players to connect...")

        self._server = server
        # Keep a handle: the simulation loop used to be fire-and-forget, so
        # there was no way to stop the server cleanly (or to tear it down in a
        # test) and an exception inside it vanished silently.
        self._loop_task = asyncio.create_task(self._game_loop())
        async with server:
            await server.serve_forever()

    async def stop(self) -> None:
        """Shut the server down: stop simulating, drop clients, close the port.
        """
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):
                pass
            self._loop_task = None
        for handler in list(self.clients.values()):
            handler.close()
        self.clients.clear()
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None

    async def _on_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Registers a newly accepted client connection.

        Called by ``asyncio.start_server`` for every incoming connection. It
        assigns the next client id, wraps the stream pair in a
        ``ClientHandler``, and records it. Actual input reads happen later
        inside the game loop, not here.

        Args:
            reader: Stream to read bytes from this client.
            writer: Stream to write bytes to this client.
        """
        client_id = self._next_client_id
        self._next_client_id += 1
        handler = ClientHandler(client_id, reader, writer)
        handler.start_reader()
        self.clients[client_id] = handler
        addr = writer.get_extra_info("peername")
        print(f"[SERVER] Client {client_id} connected from {addr}")

    async def _game_loop(self) -> None:
        """Runs the fixed-timestep simulation loop forever.

        Each iteration is one tick: read client inputs, drop disconnected
        clients, advance the simulation while the match is in progress, then
        broadcast a snapshot. It sleeps for the remainder of the tick budget so
        the loop runs at a steady ``SERVER_TICK_RATE``, yielding control back to
        the event loop while it waits.
        """
        while True:
            tick_start = time.monotonic()

            # Read inputs from all clients
            self._process_inputs()

            # Remove disconnected clients
            self._cleanup_disconnected()

            # Run game systems
            if self.state.phase == GamePhase.PLAYING:
                step(self.state, TICK_DURATION)
                self.state.tick += 1
                if self.state.phase == GamePhase.FINISHED:
                    self._announce_game_over()

            # Broadcast state to all clients
            await self._broadcast_snapshot()

            # Sleep until next tick
            elapsed = time.monotonic() - tick_start
            sleep_time = max(0, TICK_DURATION - elapsed)
            await asyncio.sleep(sleep_time)

    def _process_inputs(self) -> None:
        """Dispatches all messages that arrived since the last tick.

        Each connection has its own reader task filling a queue, so this only
        drains what already arrived and never waits on a socket.
        """
        for client_id, handler in list(self.clients.items()):
            for msg in handler.take_messages():
                self._handle_message(client_id, msg)

    def _handle_message(self, client_id: int, msg: dict) -> None:
        """Routes a single decoded message to its specific handler.

        Args:
            client_id: Server-assigned id of the sending client.
            msg: Decoded message; its ``"t"`` field selects the handler.
        """
        msg_type = msg.get("t")

        if msg_type == MsgType.JOIN:
            self._handle_join(client_id, msg)
        elif msg_type == MsgType.MOVE:
            self._handle_move(client_id, msg)
        elif msg_type == MsgType.ATTACK:
            self._handle_attack(client_id, msg)
        elif msg_type == MsgType.STOP:
            self._handle_stop(client_id)
        elif msg_type == MsgType.USE_ABILITY:
            self._handle_use_ability(client_id, msg)
        elif msg_type == MsgType.BUY_ITEM:
            self._handle_buy_item(client_id, msg)
        elif msg_type == MsgType.SELL_ITEM:
            self._handle_sell_item(client_id, msg)
        elif msg_type == MsgType.SELECT_TEAM:
            self._handle_select_team(client_id, msg)
        elif msg_type == MsgType.SELECT_HERO:
            self._handle_select_hero(client_id, msg)
        elif msg_type == MsgType.LEVEL_ABILITY:
            self._handle_level_ability(client_id, msg)
        elif msg_type == MsgType.START_GAME:
            self._handle_start_game(client_id, msg)
        elif msg_type == MsgType.CHAT:
            self._handle_chat(client_id, msg)

    def _handle_join(self, client_id: int, msg: dict) -> None:
        """Registers a joining client.

        While waiting in the lobby the client is added to the roster (no hero
        spawned yet) and sent a ``LOBBY_WELCOME``; everyone then gets the updated
        roster. If a match is already in progress the client is spawned right
        away as a late joiner and bound with a ``JOIN_ACK``.

        Args:
            client_id: Server-assigned id of the joining client.
            msg: ``JOIN`` message; reads optional ``"name"`` and ``"hero"``.
        """
        name = msg.get("name") or f"Player{client_id}"
        handler = self.clients.get(client_id)

        # Version handshake: a stale client gets one clear sentence instead of
        # desyncing or crashing on a field it does not understand.
        client_version = msg.get("pv")
        if client_version != PROTOCOL_VERSION:
            reason = (
                f"Version mismatch: this server speaks protocol "
                f"v{PROTOCOL_VERSION}, your client speaks "
                f"v{client_version if client_version is not None else '?'}. "
                f"Please update the game.")
            print(f"[SERVER] rejected client {client_id}: {reason}")
            if handler is not None:
                handler.send({"t": int(MsgType.REJECTED), "reason": reason,
                              "server_pv": PROTOCOL_VERSION})
                handler.connected = False
            return

        if handler is not None:
            handler.player_name = name

        hero_choice = msg.get("hero")
        if hero_choice:
            self.state.set_hero_choice(client_id, hero_choice)

        if self.state.phase != GamePhase.WAITING:
            # An in-progress match: reclaim this player's hero if they are
            # reconnecting, otherwise spawn them as a late joiner.
            hero = self.state.reclaim_hero(client_id, name)
            if hero is not None:
                print(f"[SERVER] {name} reconnected as {hero.hero_id} "
                      f"(level {hero.level}, {hero.gold}g)")
            else:
                team = self.state.assign_team()
                hero = self.state.add_hero(client_id, name, team, 
                                           hero_id=hero_choice)
                print(f"[SERVER] {name} late-joined Team {int(team)} as "
                      f"{hero.hero_id}")
            self._send_join_ack(client_id, hero)
            return

        info = self.state.add_to_lobby(client_id, name)
        print(f"[SERVER] {name} joined the lobby (Team {info['team']}"
              f"{', host' if info['is_host'] else ''})")
        handler = self.clients.get(client_id)
        if handler:
            handler.send({
                "t": int(MsgType.LOBBY_WELCOME),
                "cid": client_id,
                "host": info["is_host"],
                "heroes": self.state.available_heroes(),
                "items": item_catalog(),
            })
        self._broadcast_lobby()

    def _send_join_ack(self, client_id: int, hero) -> None:
        """Bind a client's local view to its spawned server hero entity."""
        handler = self.clients.get(client_id)
        if not handler:
            return
        handler.send({
            "t": int(MsgType.JOIN_ACK),
            "eid": hero.entity_id,
            "team": int(hero.team),
            "name": hero.name,
            "hero": hero.hero_id,
            # Ability metadata (key/name/cd/mana/cast-type) so the client can
            # draw the ability bar and drive targeting without server code.
            "hero_def": hero.hero_def.describe() if hero.hero_def else None,
            # Shop catalog (item metadata) so the client can show the shop.
            "items": item_catalog(),
        })

    def _broadcast_lobby(self) -> None:
        """Send the current lobby roster to every connected client."""
        msg = {
            "t": int(MsgType.PLAYER_LIST),
            "players": self.state.lobby_roster(),
        }
        for handler in self.clients.values():
            handler.send(msg)

    def _handle_chat(self, client_id: int, msg: dict) -> None:
        """Relay a chat line. All-chat goes to everyone; otherwise only to the
        sender's teammates."""
        text = (msg.get("text") or "").strip()[:200]
        if not text:
            return
        # Sandbox cheat commands (e.g. "/gold 9999") never relay as chat.
        if self.state.sandbox and text.startswith("/"):
            self._handle_sandbox_command(client_id, text)
            return
        all_chat = bool(msg.get("all"))
        hero = self.state.get_hero(client_id)
        if hero is not None:
            name, team = hero.name, hero.team
        else:  # not spawned yet (lobby/spectator): fall back to lobby roster
            name = self.state.lobby.get(client_id, {}).get("name", f"Player{client_id}")
            team = None
        out = {
            "t": int(MsgType.CHAT),
            "name": name,
            "text": text,
            "all": all_chat,
        }
        for cid, handler in self.clients.items():
            if all_chat:
                handler.send(out)
            elif team is not None:
                other = self.state.get_hero(cid)
                if other is not None and other.team == team:
                    handler.send(out)

    def _sandbox_reply(self, client_id: int, text: str) -> None:
        """Echo a sandbox-command result back to just the caller."""
        handler = self.clients.get(client_id)
        if handler is not None:
            handler.send({"t": int(MsgType.CHAT), "name": "[sandbox]",
                          "text": text, "all": False})

    def _handle_sandbox_command(self, client_id: int, text: str) -> None:
        """Apply a sandbox cheat command to the caller's hero. Only reachable
        when the server runs with --sandbox. Supported:
          /gold N  /level N  /refresh  /heal  /kill  /item <item_id>
        """
        parts = text[1:].split()
        if not parts:
            return
        cmd = parts[0].lower()

        def int_arg(default: int) -> int:
            try:
                return int(parts[1])
            except (IndexError, ValueError):
                return default

        hero = self.state.get_hero(client_id)
        if hero is None:
            self._sandbox_reply(client_id, "sandbox: join a match first")
            return
        if cmd == "gold":
            hero.gold = max(0, int_arg(99999))
            self._sandbox_reply(client_id, f"gold = {hero.gold}")
        elif cmd == "level":
            sandbox_set_level(hero, int_arg(MAX_LEVEL))
            self._sandbox_reply(client_id, f"level = {hero.level}")
        elif cmd == "refresh":
            hero.cooldowns.clear()
            hero.item_cooldowns.clear()
            hero.tp_cooldown = 0.0
            hero.mana = hero.effective_max_mana()
            self._sandbox_reply(client_id, "cooldowns refreshed")
        elif cmd == "heal":
            hero.hp = hero.effective_max_hp()
            hero.mana = hero.effective_max_mana()
            self._sandbox_reply(client_id, "healed to full")
        elif cmd == "kill":
            # Route through the normal death path (respawn timer, bounties skip).
            self.state.damage_events.append(
                {"src": hero.entity_id, "tgt": hero.entity_id,
                 "amt": hero.hp + 99999, "dtype": "true"})
            self._sandbox_reply(client_id, "killed")
        elif cmd == "item":
            item = get_item_def(parts[1]) if len(parts) > 1 else None
            if item is None:
                self._sandbox_reply(client_id, "usage: /item <item_id>")
            elif getattr(item, "is_charge", False):
                hero.tp_charges += 1
                self._sandbox_reply(client_id, f"granted {item.name}")
            elif len(hero.inventory) >= ITEM_SLOTS:
                self._sandbox_reply(client_id, "inventory full")
            else:
                apply_inventory_change(
                    hero, self.state,
                    lambda: hero.inventory.append(item.item_id))
                self._sandbox_reply(client_id, f"granted {item.name}")
        else:
            self._sandbox_reply(client_id, f"unknown command: /{cmd}")

    def _handle_select_team(self, client_id: int, msg: dict) -> None:
        if self.state.set_lobby_team(client_id, msg.get("team")):
            self._broadcast_lobby()

    def _handle_select_hero(self, client_id: int, msg: dict) -> None:
        if self.state.set_lobby_hero(client_id, msg.get("hero")):
            self._broadcast_lobby()

    def _handle_move(self, client_id: int, msg: dict) -> None:
        """Sets a hero's move destination from a right-click move command.

        Ignored if the hero is missing or dead. The target point is clamped to
        the map bounds.

        Args:
            client_id: Server-assigned id of the commanding client.
            msg: ``MOVE`` message with target coords ``"tx"`` and ``"ty"``.
        """
        hero = self.state.get_hero(client_id)
        if hero is None or not hero.alive:
            return
        tx = msg.get("tx")
        ty = msg.get("ty")
        if tx is not None and ty is not None:
            # A manual move command cancels any focus target and just moves
            # (never auto-attacks en route).
            hero.forced_target_id = None
            hero.attack_move = False
            hero.attack_move_x = hero.attack_move_y = None
            hero.target_x = max(0, min(MAP_WIDTH, float(tx)))
            hero.target_y = max(0, min(MAP_HEIGHT, float(ty)))

    def _handle_attack(self, client_id: int, msg: dict) -> None:
        """Handles an 'A + click' attack command.

        If an enemy entity was clicked, the hero focuses it (chases and
        attacks). Otherwise it attack-moves toward the clicked point, auto
        attacking any enemy encountered en route. Ignored if the hero is
        missing or dead.

        Args:
            client_id: Server-assigned id of the commanding client.
            msg: ``ATTACK`` message with optional point ``"tx"``/``"ty"`` and
                optional target entity id ``"tid"``.
        """
        hero = self.state.get_hero(client_id)
        if (hero is None) or (not hero.alive):
            return
        tx = msg.get("tx")
        ty = msg.get("ty")
        tid = msg.get("tid")
        target = self.state.entities.get(tid) if tid is not None else None
        if (target is not None) and (target.team != hero.team) and target.alive:
            hero.forced_target_id = tid
            hero.attack_move = False
            hero.attack_move_x = hero.attack_move_y = None
            hero.target_x = target.x
            hero.target_y = target.y
        else:
            # Attack-move: clear focus, advance to the point but stop to attack
            # any enemy that comes into range (handled in _update_attack_move).
            hero.forced_target_id = None
            if tx is not None and ty is not None:
                px = max(0, min(MAP_WIDTH, float(tx)))
                py = max(0, min(MAP_HEIGHT, float(ty)))
                hero.attack_move = True
                hero.attack_move_x, hero.attack_move_y = px, py
                hero.target_x, hero.target_y = px, py

    def _handle_stop(self, client_id: int) -> None:
        """Halts a hero, clearing its focus target and move destination.

        Ignored if the hero is missing or dead.

        Args:
            client_id: Server-assigned id of the commanding client.
        """
        hero = self.state.get_hero(client_id)
        if hero is None or not hero.alive:
            return
        hero.forced_target_id = None
        hero.target_x = None
        hero.target_y = None
        hero.attack_move = False
        hero.attack_move_x = hero.attack_move_y = None

    def _handle_use_ability(self, client_id: int, msg: dict) -> None:
        """Queues an ability cast to be resolved by the simulation step.

        The cast is appended to ``state.ability_casts`` rather than applied
        immediately, so all casts in a tick are resolved together by the
        systems. Ignored if the hero is missing/dead or no key was supplied.

        Args:
            client_id: Server-assigned id of the casting client.
            msg: ``USE_ABILITY`` message with ability ``"key"`` and optional
                target point ``"tx"``/``"ty"`` and target entity id ``"tid"``.
        """
        hero = self.state.get_hero(client_id)
        if hero is None or not hero.alive:
            return
        key = msg.get("key")
        if not key:
            return
        self.state.ability_casts.append({
            "caster": hero.entity_id,
            "key": key,
            "tx": float(msg.get("tx", hero.x)),
            "ty": float(msg.get("ty", hero.y)),
            "tid": msg.get("tid"),
        })

    def _handle_level_ability(self, client_id: int, msg: dict) -> None:
        """Spend a skill point to rank up an ability (Q/W/E/R)."""
        key = msg.get("key")
        if key:
            self.state.level_ability(client_id, key)

    def _handle_buy_item(self, client_id: int, msg: dict) -> None:
        """Buys an item, consuming any components the hero already owns.

        Args:
            client_id: Server-assigned id of the buying client.
            msg: ``BUY_ITEM`` message with ``"item"`` (item_id).
        """
        hero = self.state.get_hero(client_id)
        if hero is None:
            return
        item = get_item_def(msg.get("item"))
        if item is None:
            return
        if getattr(item, "is_charge", False):
            # Charge item (TP scroll): stack onto the dedicated slot. The shared
            # cooldown is set on *use* and is deliberately NOT reset by rebuying.
            if hero.gold < item.cost:
                return
            hero.gold -= item.cost
            hero.tp_charges += 1
            return

        plan = purchase_plan(hero, item)
        if plan is None:
            return  # no room for the result
        price, component_slots = plan
        if hero.gold < price:
            return
        hero.gold -= price

        def buy():
            # Consume the components (highest slot first so the earlier
            # indices stay valid as we remove them), then add the result.
            for slot in sorted(component_slots, reverse=True):
                hero.inventory.pop(slot)
            hero.inventory.append(item.item_id)

        apply_inventory_change(hero, self.state, buy)

    def _handle_sell_item(self, client_id: int, msg: dict) -> None:
        """Sells the item in a given inventory slot for a partial refund.

        Args:
            client_id: Server-assigned id of the selling client.
            msg: ``SELL_ITEM`` message with ``"slot"`` (inventory index).
        """
        hero = self.state.get_hero(client_id)
        if hero is None:
            return
        slot = msg.get("slot")
        if not isinstance(slot, int) or slot < 0 or slot >= len(hero.inventory):
            return
        item = get_item_def(hero.inventory[slot])
        if item is None:
            return
        hero.gold += item.cost // 2  # 50% refund
        apply_inventory_change(hero, self.state, lambda: hero.inventory.pop(slot))
        # Only forget the cooldown if no copy of the item remains.
        if item.item_id not in hero.inventory:
            hero.item_cooldowns.pop(item.item_id, None)

    def _handle_start_game(self, client_id: int, msg: dict) -> None:
        """Spawns lobby players and transitions to an active match.

        Only the host may start, only from the lobby, and only with at least one
        player. Each lobby player is spawned on their chosen team/hero, then bound
        to its server entity with a ``JOIN_ACK``.

        Args:
            client_id: Server-assigned id of the requesting client.
            msg: ``START_GAME`` message with optional kill target ``"ktarget"``.
        """
        if self.state.phase != GamePhase.WAITING:
            return
        if not self.state.is_host(client_id) or not self.state.lobby:
            return
        self.state.spawn_from_lobby()
        kill_target = msg.get("ktarget")
        self.state.start_match(kill_target=kill_target)
        for cid in list(self.state.player_heroes.keys()):
            hero = self.state.get_hero(cid)
            if hero is not None:
                self._send_join_ack(cid, hero)
        print(f"[SERVER] Game started with {len(self.state.player_heroes)} "
              f"players! (first to {self.state.kill_target} kills)")

    def _announce_game_over(self) -> None:
        """Broadcasts a ``GAME_OVER`` message naming the winning team."""
        winner = int(self.state.winner) if self.state.winner else 0
        print(f"[SERVER] Game over! Team {winner} wins.")
        for handler in self.clients.values():
            handler.send({"t": int(MsgType.GAME_OVER), "winner": winner})

    def _cleanup_disconnected(self) -> None:
        """Removes clients that have dropped, freeing their hero and socket."""
        to_remove = [cid for cid, h in self.clients.items() if not h.connected]
        for cid in to_remove:
            handler = self.clients[cid]
            name = handler.player_name
            print(f"[SERVER] Client {cid} disconnected"
                  + (f" ({name}); hero parked for reconnect" if name else ""))
            # During a match the hero is parked under the player's name so a
            # brief drop does not cost them the game.
            self.state.remove_hero(cid, keep_for_reconnect=name)
            self.state.remove_from_lobby(cid)
            handler = self.clients.pop(cid)
            handler.close()
        # Keep the lobby roster fresh while players are still picking.
        if to_remove and self.state.phase == GamePhase.WAITING:
            self._broadcast_lobby()

    def _event_visible(self, ev: dict, team, vis) -> bool:
        """Whether a combat event should reach `team`. gold/xp reveal only by the
        source entity's visibility; fx/hit also reveal by their world position, so
        AoE telegraphs and damage near you show even if the caster is fogged."""
        if ev.get("eid") in vis:
            return True
        if ev.get("k") in ("fx", "hit"):
            return self.state.point_visible_for(team, ev["x"], ev["y"])
        return False

    async def _broadcast_snapshot(self) -> None:
        """Sends the current authoritative state to every connected client.

        Builds one snapshot (entities, tick, phase, score, win state), queues
        it on each client's writer, then awaits all writers draining so a slow
        client applies backpressure instead of letting buffers grow unbounded.
        No-op when there are no clients.
        """
        if not self.clients:
            return
        base = {
            "t": int(MsgType.SNAPSHOT),
            "tick": self.state.tick,
            "phase": int(self.state.phase),
            "score": {
                "1": self.state.team_kills[Team.TEAM1],
                "2": self.state.team_kills[Team.TEAM2],
            },
            "ktarget": self.state.kill_target,
            "winner": int(self.state.winner) if self.state.winner else 0,
            "clock": round(self.state.match_clock, 1),
        }
        # Fog-of-war: compute each team's visible set once, reuse per client.
        events = self.state.combat_events
        per_team = {}
        for team in (Team.TEAM1, Team.TEAM2):
            # Reuse the line-of-sight already computed while stepping: it is
            # the most expensive query in the game and was being run twice per
            # frame per team (the cache is keyed on the simulation epoch, so it
            # survives the tick counter incrementing before we get here).
            vis = self.state.visible_ids_cached(team)
            ents = {e.entity_id: e.to_snapshot(private=False)
                    if isinstance(e, Hero) else e.to_snapshot()
                    for e in self.state.entities.values()
                    if e.entity_id in vis}
            evs = [ev for ev in events if self._event_visible(ev, team, vis)]
            per_team[team] = (ents, evs)

        for client_id, handler in self.clients.items():
            hero = self.state.get_hero(client_id)
            if hero is not None and hero.team in per_team:
                ents, evs = per_team[hero.team]
                # Splice the owner's private HUD payload over its public entry.
                ents = dict(ents)
                ents[hero.entity_id] = hero.to_snapshot(private=True)
            else:  # spectator: everything, no fog
                ents = {e.entity_id: e.to_snapshot()
                        for e in self.state.entities.values()}
                evs = events
            handler.send({**base, **self._delta_for(handler, ents),
                          "events": evs})

        # Flush every writer concurrently. Sequentially awaiting each drain
        # meant the worst-connected player stalled the tick for everyone.
        await asyncio.gather(*(h.flush() for h in self.clients.values()),
                             return_exceptions=True)

    def _delta_for(self, handler, ents: dict) -> dict:
        """Reduce a full entity map to what actually changed for this client.

        Most of a snapshot is unchanged frame to frame — static walls and trees
        never move at all, and idle units repeat byte for byte. Sending only
        entries that differ from what this client last received, plus the ids
        that dropped out of view, is what makes a 5v5 fit a home uplink.

        The first snapshot after connecting (or after a client reconnects) is a
        full one, flagged so the client replaces its world rather than merging.
        """
        previous = handler.last_snapshot
        if previous is None:
            handler.last_snapshot = ents
            return {"entities": list(ents.values()), "full": True}
        changed = [snap for eid, snap in ents.items()
                   if previous.get(eid) != snap]
        gone = [eid for eid in previous if eid not in ents]
        handler.last_snapshot = ents
        out = {"entities": changed}
        if gone:
            out["gone"] = gone
        return out


def run_server() -> None:
    """Parses CLI arguments and runs the server until interrupted.

    Reads optional ``--host`` and ``--port`` from ``sys.argv``, then runs the
    asyncio event loop. A ``KeyboardInterrupt`` (Ctrl-C) shuts down cleanly.
    """
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    sandbox = False

    # Parse --host, --port and --sandbox from sys.argv
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--host" and i + 1 < len(args):
            host = args[i + 1]
        elif arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        elif arg == "--sandbox":
            sandbox = True

    if sandbox:
        print("[SERVER] SANDBOX mode ON — chat cheats enabled "
              "(/gold /level /refresh /heal /kill /item)")
    server = GameServer(host=host, port=port, sandbox=sandbox)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down.")
