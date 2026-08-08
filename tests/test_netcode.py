"""Wire format, snapshot deltas, the public/private split, and reconnect.

None of this was covered before, which is how a latent server-freeze bug (an
uncaught `ValueError` on an oversized frame killing the simulation task) sat in
the code unnoticed.
"""

import unittest

from shared.protocol import (
    HEADER_SIZE,
    MAX_MSG_SIZE,
    MessageTooLarge,
    PROTOCOL_VERSION,
    TUNNEL_PRELUDE,
    pack_message,
    take_tunnel_prelude,
    unpack_from_buffer,
)
from shared.game_types import GamePhase, MsgType, Team
from server.game_state import GameState
from server.entity import Hero
from client.interpolation import Interpolator


class TestFraming(unittest.TestCase):
    def test_round_trip(self):
        msg = {"t": int(MsgType.SNAPSHOT), "tick": 7, "entities": [{"id": 1}]}
        buf = bytearray(pack_message(msg))
        self.assertEqual(unpack_from_buffer(buf), [msg])
        self.assertEqual(len(buf), 0)

    def test_header_is_four_bytes(self):
        # Two bytes capped a frame at 65535, which a busy 5v5 could exceed.
        self.assertEqual(HEADER_SIZE, 4)

    def test_frames_larger_than_the_old_cap_are_fine(self):
        big = {"t": 1, "blob": "x" * 200_000}
        buf = bytearray(pack_message(big))
        self.assertEqual(unpack_from_buffer(buf), [big])

    def test_partial_frame_is_buffered_not_consumed(self):
        data = pack_message({"t": 1, "a": 1})
        buf = bytearray(data[:-3])
        self.assertEqual(unpack_from_buffer(buf), [])
        buf.extend(data[-3:])
        self.assertEqual(unpack_from_buffer(buf), [{"t": 1, "a": 1}])

    def test_multiple_frames_in_one_read(self):
        buf = bytearray(pack_message({"t": 1}) + pack_message({"t": 2}))
        self.assertEqual(unpack_from_buffer(buf), [{"t": 1}, {"t": 2}])

    def test_oversized_declared_length_is_rejected(self):
        # A corrupt/hostile prefix must not make us buffer forever.
        import struct
        buf = bytearray(struct.pack("!I", MAX_MSG_SIZE + 1) + b"\x00")
        with self.assertRaises(MessageTooLarge):
            unpack_from_buffer(buf)

    def test_oversized_outgoing_message_raises_the_typed_error(self):
        with self.assertRaises(MessageTooLarge):
            pack_message({"t": 1, "blob": "x" * (MAX_MSG_SIZE + 10)})


class TestTunnelPrelude(unittest.TestCase):
    """playit's free game-preset tunnels sniff the first packet and reset
    anything they don't recognise, so a tunnelled client opens with a Terraria
    handshake. The edge forwards those bytes verbatim, so the server strips
    them before framing."""

    def test_prelude_is_consumed_and_leaves_the_real_stream(self):
        buf = bytearray(TUNNEL_PRELUDE + pack_message({"t": 1}))
        self.assertIs(take_tunnel_prelude(buf), True)
        self.assertEqual(unpack_from_buffer(buf), [{"t": 1}])

    def test_absent_prelude_is_reported_without_consuming(self):
        frame = pack_message({"t": 1})
        buf = bytearray(frame)
        self.assertIs(take_tunnel_prelude(buf), False)
        self.assertEqual(bytes(buf), frame)  # a direct client is untouched

    def test_split_prelude_waits_for_the_rest(self):
        # 15 bytes can arrive across two reads; answering False there would
        # feed the handshake into the framer and corrupt the connection.
        buf = bytearray(TUNNEL_PRELUDE[:6])
        self.assertIsNone(take_tunnel_prelude(buf))
        self.assertEqual(bytes(buf), TUNNEL_PRELUDE[:6])  # nothing consumed
        buf.extend(TUNNEL_PRELUDE[6:])
        self.assertIs(take_tunnel_prelude(buf), True)
        self.assertEqual(bytes(buf), b"")

    def test_short_non_matching_read_is_settled_immediately(self):
        buf = bytearray(b"\x00\x00")  # a real frame header, not the prelude
        self.assertIs(take_tunnel_prelude(buf), False)

    def test_prelude_is_a_valid_terraria_connect_request(self):
        # The edge validates length, message type 1, and the version string.
        self.assertEqual(
            int.from_bytes(TUNNEL_PRELUDE[:2], "little"), len(TUNNEL_PRELUDE))
        self.assertEqual(TUNNEL_PRELUDE[2], 1)
        self.assertEqual(TUNNEL_PRELUDE[3], len(TUNNEL_PRELUDE[4:]))
        self.assertTrue(TUNNEL_PRELUDE[4:].startswith(b"Terraria"))


class TestSnapshotSplit(unittest.TestCase):
    """The owner-only HUD payload is ~3/4 of a hero's bytes and is useless to
    anyone else, so it must not reach other clients."""

    PRIVATE = ("cds", "alvl", "sp", "inv", "icds", "tp", "dlt", "gold",
               "xp", "xpn", "ad", "spa", "pdef", "sdef", "rng", "aspd",
               "ms", "hpr", "mpr")
    PUBLIC = ("id", "x", "y", "hp", "mhp", "name", "hid", "lvl", "mana",
              "mmana", "kills", "deaths", "assists")

    def setUp(self):
        self.state = GameState()
        self.hero = self.state.add_hero(1, "A", Team.TEAM1, hero_id="ranger")

    def test_private_snapshot_has_the_hud_payload(self):
        snap = self.hero.to_snapshot(private=True)
        for key in self.PRIVATE + self.PUBLIC:
            with self.subTest(key=key):
                self.assertIn(key, snap)

    def test_public_snapshot_omits_it(self):
        snap = self.hero.to_snapshot(private=False)
        for key in self.PRIVATE:
            with self.subTest(key=key):
                self.assertNotIn(key, snap)
        for key in self.PUBLIC:
            with self.subTest(key=key):
                self.assertIn(key, snap)

    def test_public_snapshot_keeps_the_ult_summary(self):
        # The ult-readiness column is drawn for every hero, so it gets a compact
        # two-field summary instead of the whole alvl/cds dicts.
        self.hero.ability_levels["R"] = 2
        self.hero.cooldowns["R"] = 12.0
        snap = self.hero.to_snapshot(private=False)
        self.assertEqual(snap["ultr"], 2)
        self.assertEqual(snap["ultcd"], 12.0)

    def test_public_snapshot_is_substantially_smaller(self):
        import msgpack
        pub = len(msgpack.packb(self.hero.to_snapshot(private=False)))
        priv = len(msgpack.packb(self.hero.to_snapshot(private=True)))
        self.assertLess(pub, priv * 0.6)


class _FakeHandler:
    """Just the delta bookkeeping the broadcast touches."""

    def __init__(self):
        self.last_snapshot = None


class TestDelta(unittest.TestCase):
    def setUp(self):
        from server.server_main import GameServer
        self.server = GameServer.__new__(GameServer)   # no socket needed
        self.handler = _FakeHandler()

    def delta(self, ents):
        return self.server._delta_for(self.handler, ents)

    def test_first_snapshot_is_full(self):
        out = self.delta({1: {"id": 1, "x": 0}, 2: {"id": 2, "x": 5}})
        self.assertTrue(out["full"])
        self.assertEqual(len(out["entities"]), 2)

    def test_unchanged_entities_are_not_resent(self):
        ents = {1: {"id": 1, "x": 0}, 2: {"id": 2, "x": 5}}
        self.delta(ents)
        out = self.delta(dict(ents))
        self.assertEqual(out["entities"], [])
        self.assertNotIn("full", out)

    def test_only_changed_entities_are_sent(self):
        self.delta({1: {"id": 1, "x": 0}, 2: {"id": 2, "x": 5}})
        out = self.delta({1: {"id": 1, "x": 9}, 2: {"id": 2, "x": 5}})
        self.assertEqual(out["entities"], [{"id": 1, "x": 9}])

    def test_vanished_entities_are_reported(self):
        self.delta({1: {"id": 1, "x": 0}, 2: {"id": 2, "x": 5}})
        out = self.delta({1: {"id": 1, "x": 0}})
        self.assertEqual(out["gone"], [2])

    def test_new_entities_appear_in_the_delta(self):
        self.delta({1: {"id": 1, "x": 0}})
        out = self.delta({1: {"id": 1, "x": 0}, 3: {"id": 3, "x": 1}})
        self.assertEqual(out["entities"], [{"id": 3, "x": 1}])


class TestDeltaMerge(unittest.TestCase):
    """The client must reconstruct exactly what the server holds."""

    def test_merge_reproduces_the_server_view(self):
        interp = Interpolator()
        interp.push_snapshot([{"id": 1, "x": 0, "y": 0},
                              {"id": 2, "x": 5, "y": 0}], full=True)
        interp.push_snapshot([{"id": 1, "x": 9, "y": 0}])
        world = {e["id"]: e for e in interp.curr_snapshot.values()}
        self.assertEqual(world[1]["x"], 9)
        self.assertEqual(world[2]["x"], 5)   # untouched entry survives

    def test_gone_ids_are_dropped(self):
        interp = Interpolator()
        interp.push_snapshot([{"id": 1, "x": 0, "y": 0},
                              {"id": 2, "x": 5, "y": 0}], full=True)
        interp.push_snapshot([], gone=[2])
        self.assertNotIn(2, interp.curr_snapshot)
        self.assertIn(1, interp.curr_snapshot)

    def test_full_snapshot_replaces_rather_than_merges(self):
        interp = Interpolator()
        interp.push_snapshot([{"id": 1, "x": 0, "y": 0},
                              {"id": 2, "x": 5, "y": 0}], full=True)
        interp.push_snapshot([{"id": 3, "x": 1, "y": 1}], full=True)
        self.assertEqual(set(interp.curr_snapshot), {3})

    def test_previous_frame_is_preserved_for_interpolation(self):
        # Merging must not mutate the previous snapshot, or positions would
        # interpolate from already-updated values and motion would stutter.
        interp = Interpolator()
        interp.push_snapshot([{"id": 1, "x": 0, "y": 0}], full=True)
        interp.push_snapshot([{"id": 1, "x": 100, "y": 0}])
        self.assertEqual(interp.prev_snapshot[1]["x"], 0)
        self.assertEqual(interp.curr_snapshot[1]["x"], 100)

    def test_reset_clears_the_world(self):
        interp = Interpolator()
        interp.push_snapshot([{"id": 1, "x": 0, "y": 0}], full=True)
        interp.reset()
        self.assertEqual(interp.get_entities(), [])


class TestReconnect(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.state.phase = GamePhase.PLAYING
        self.hero = self.state.add_hero(1, "Alice", Team.TEAM1,
                                        hero_id="ranger")
        self.hero.level = 7
        self.hero.gold = 4321
        self.hero.inventory.append("long_sword")

    def test_hero_is_parked_not_deleted_during_a_match(self):
        eid = self.hero.entity_id
        self.state.remove_hero(1, keep_for_reconnect="Alice")
        self.assertIn(eid, self.state.entities)      # still in the world
        self.assertNotIn(1, self.state.player_heroes)

    def test_reconnect_restores_the_same_hero(self):
        self.state.remove_hero(1, keep_for_reconnect="Alice")
        regained = self.state.reclaim_hero(9, "Alice")   # new client id
        self.assertIs(regained, self.hero)
        self.assertEqual(regained.level, 7)
        self.assertEqual(regained.gold, 4321)
        self.assertEqual(regained.inventory, ["long_sword"])
        self.assertEqual(self.state.player_heroes[9], self.hero.entity_id)

    def test_parking_clears_stale_orders(self):
        # A parked hero must not keep walking into a tower while its player
        # is away.
        self.hero.target_x, self.hero.target_y = 5000, 5000
        self.hero.attack_move = True
        self.state.remove_hero(1, keep_for_reconnect="Alice")
        self.assertIsNone(self.hero.target_x)
        self.assertFalse(self.hero.attack_move)

    def test_unknown_name_does_not_reclaim(self):
        self.state.remove_hero(1, keep_for_reconnect="Alice")
        self.assertIsNone(self.state.reclaim_hero(9, "Mallory"))

    def test_a_hero_can_only_be_reclaimed_once(self):
        self.state.remove_hero(1, keep_for_reconnect="Alice")
        self.assertIsNotNone(self.state.reclaim_hero(9, "Alice"))
        self.assertIsNone(self.state.reclaim_hero(10, "Alice"))

    def test_leaving_the_lobby_still_deletes(self):
        # Outside a live match there is nothing worth preserving.
        state = GameState()
        state.phase = GamePhase.WAITING
        hero = state.add_hero(1, "Bob", Team.TEAM1, hero_id="ranger")
        state.remove_hero(1, keep_for_reconnect="Bob")
        self.assertNotIn(hero.entity_id, state.entities)


class TestVersionHandshake(unittest.TestCase):
    def test_protocol_version_is_exported(self):
        self.assertIsInstance(PROTOCOL_VERSION, int)
        self.assertGreaterEqual(PROTOCOL_VERSION, 1)

    def test_rejected_message_type_exists(self):
        self.assertTrue(hasattr(MsgType, "REJECTED"))


if __name__ == "__main__":
    unittest.main()
