"""End-to-end over real sockets: the two-terminal flow, exactly as played.

Everything else in the suite exercises the simulation directly. This drives a
real `GameServer` over a real TCP connection with the same messages the pygame
client sends, so the parts that only exist between the two processes — the
lobby handshake, snapshot deltas, the public/private split, reconnect — are
covered too. That seam is where the netcode bugs were.

No pygame: `_NetClient` is the client's network half and nothing more.
"""

import asyncio
import socket
import unittest

from shared.game_types import GamePhase, MsgType
from shared.protocol import PROTOCOL_VERSION, pack_message, unpack_from_buffer
from client.interpolation import Interpolator
from server.server_main import GameServer

_PORT = 7987          # high and fixed; the suite runs one match at a time


class _NetClient:
    """A client's socket plus the delta merge — the network half, no rendering."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.sock = socket.socket()
        self.buf = bytearray()
        self.interp = Interpolator()
        self.cid = None
        self.eid = None
        self.team = None
        self.is_host = False
        self.hero_def = None
        self.rejected = None

    def connect(self, port: int, protocol_version: int = PROTOCOL_VERSION,
                hero: str = "ranger") -> None:
        self.sock.connect(("127.0.0.1", port))
        self.sock.setblocking(False)
        self.send({"t": int(MsgType.JOIN), "name": self.name, "hero": hero,
                   "pv": protocol_version})

    def send(self, msg: dict) -> None:
        self.sock.sendall(pack_message(msg))

    def pump(self) -> None:
        try:
            while True:
                data = self.sock.recv(65536)
                if not data:
                    break
                self.buf.extend(data)
        except (BlockingIOError, OSError):
            pass
        for msg in unpack_from_buffer(self.buf):
            kind = msg.get("t")
            if kind == MsgType.LOBBY_WELCOME:
                self.cid = msg.get("cid")
                self.is_host = bool(msg.get("host"))
            elif kind == MsgType.JOIN_ACK:
                self.eid = msg.get("eid")
                self.team = msg.get("team")
                self.hero_def = msg.get("hero_def")
            elif kind == MsgType.SNAPSHOT:
                self.interp.push_snapshot(msg.get("entities", []),
                                          gone=msg.get("gone", ()),
                                          full=bool(msg.get("full")))
            elif kind == MsgType.REJECTED:
                self.rejected = msg.get("reason")

    @property
    def world(self) -> dict:
        return self.interp.curr_snapshot or {}

    def me(self):
        return self.world.get(self.eid)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class LiveServerTest(unittest.IsolatedAsyncioTestCase):
    """Boots a real server on a loopback port for each test."""

    port = _PORT

    async def asyncSetUp(self):
        type(self).port += 1          # fresh port per test, avoids TIME_WAIT
        self.server = GameServer(host="127.0.0.1", port=self.port)
        self.serve_task = asyncio.create_task(self.server.start())
        self.clients: list[_NetClient] = []
        await asyncio.sleep(0.2)      # let the listener bind

    async def asyncTearDown(self):
        for client in self.clients:
            client.close()
        await self.server.stop()
        self.serve_task.cancel()
        try:
            await self.serve_task
        except (asyncio.CancelledError, Exception):
            pass

    def new_client(self, name: str, **kwargs) -> _NetClient:
        client = _NetClient(name)
        client.connect(self.port, **kwargs)
        self.clients.append(client)
        return client

    async def settle(self, ticks: int = 12) -> None:
        """Let the server run and deliver, pumping every client."""
        for _ in range(ticks):
            await asyncio.sleep(0.05)
            for client in self.clients:
                client.pump()


class TestLocalTwoTerminalFlow(LiveServerTest):
    """`--server` in one terminal, clients in others. The everyday workflow."""

    async def test_lobby_join_start_and_play(self):
        alice = self.new_client("Alice")
        bob = self.new_client("Bob")
        await self.settle()

        # Lobby: both registered, first joiner hosts.
        self.assertIsNotNone(alice.cid)
        self.assertIsNotNone(bob.cid)
        self.assertTrue(alice.is_host)
        self.assertFalse(bob.is_host)

        # The host starts; both get bound to their spawned hero.
        alice.send({"t": int(MsgType.START_GAME)})
        await self.settle()
        self.assertEqual(self.server.state.phase, GamePhase.PLAYING)
        self.assertIsNotNone(alice.eid)
        self.assertIsNotNone(bob.eid)
        # The ability bar is learned entirely from the wire.
        self.assertTrue(alice.hero_def["abilities"])

        # Snapshots arrive and the delta merge reconstructs a world.
        self.assertGreater(len(alice.world), 10)
        self.assertIsNotNone(alice.me())

        # Right-click move round-trips through the server.
        hero = self.server.state.get_hero(alice.cid)
        before = (alice.me()["x"], alice.me()["y"])
        alice.send({"t": int(MsgType.MOVE),
                    "tx": hero.x + 400, "ty": hero.y})
        await self.settle(ticks=20)
        self.assertNotEqual((alice.me()["x"], alice.me()["y"]), before)

    async def test_private_payload_reaches_only_its_owner(self):
        alice = self.new_client("Alice")
        bob = self.new_client("Bob")
        await self.settle()
        alice.send({"t": int(MsgType.START_GAME)})
        await self.settle()

        self.assertIn("cds", alice.me(), "owner must get its HUD payload")
        self.assertIn("inv", alice.me())
        # Any other hero Alice can see must arrive without that payload.
        others = [e for eid, e in alice.world.items()
                  if e.get("hid") and eid != alice.eid]
        for other in others:
            self.assertNotIn("cds", other)
            self.assertNotIn("gold", other)
        # ...but still with the public summary the HUD needs.
        for other in others:
            self.assertIn("ultr", other)


class TestReconnectOverTheWire(LiveServerTest):
    async def test_dropped_player_reclaims_their_hero(self):
        alice = self.new_client("Alice")
        self.new_client("Bob")
        await self.settle()
        alice.send({"t": int(MsgType.START_GAME)})
        await self.settle()

        hero = self.server.state.get_hero(alice.cid)
        hero.gold, hero.level = 4321, 6
        entity_id = hero.entity_id

        alice.close()
        self.clients.remove(alice)
        await self.settle(ticks=10)
        self.assertIn("Alice", self.server.state.disconnected)

        back = self.new_client("Alice")
        await self.settle(ticks=15)
        regained = next((h for h in self.server.state.heroes()
                         if h.name == "Alice"), None)
        self.assertIsNotNone(regained)
        self.assertEqual(regained.entity_id, entity_id)   # the same hero
        self.assertEqual(regained.level, 6)
        self.assertGreaterEqual(regained.gold, 4321)      # passive income only
        self.assertIsNotNone(back.eid)


class TestVersionHandshakeOverTheWire(LiveServerTest):
    async def test_stale_client_is_rejected_with_a_reason(self):
        stale = self.new_client("Stale",
                                protocol_version=PROTOCOL_VERSION - 1)
        await self.settle(ticks=10)
        self.assertIsNotNone(stale.rejected)
        self.assertIn("update", stale.rejected.lower())
        # ...and never gets a hero.
        self.assertEqual(len(self.server.state.lobby), 0)

    async def test_matching_version_is_accepted(self):
        ok = self.new_client("Fresh")
        await self.settle(ticks=10)
        self.assertIsNone(ok.rejected)
        self.assertIsNotNone(ok.cid)


if __name__ == "__main__":
    unittest.main()
