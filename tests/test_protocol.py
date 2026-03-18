"""Tests for the network protocol module."""

import unittest
from shared.protocol import pack_message, unpack_from_buffer
from shared.game_types import MsgType


class TestProtocol(unittest.TestCase):
    def test_pack_unpack_roundtrip(self):
        msg = {"t": int(MsgType.JOIN), "name": "TestPlayer"}
        packed = pack_message(msg)
        buf = bytearray(packed)
        messages = unpack_from_buffer(buf)
        self.assertEqual(messages, [msg])
        self.assertEqual(len(buf), 0)  # buffer fully consumed

    def test_multiple_messages(self):
        msgs = [
            {"t": int(MsgType.JOIN), "name": "Alice"},
            {"t": int(MsgType.MOVE), "tx": 100.0, "ty": 200.0},
            {"t": int(MsgType.START_GAME)},
        ]
        packed = b"".join(pack_message(m) for m in msgs)
        buf = bytearray(packed)
        result = unpack_from_buffer(buf)
        self.assertEqual(result, msgs)
        self.assertEqual(len(buf), 0)

    def test_partial_message(self):
        msg = {"t": int(MsgType.SNAPSHOT), "tick": 42, "entities": []}
        packed = pack_message(msg)
        # Only give half the bytes
        buf = bytearray(packed[: len(packed) // 2])
        messages = unpack_from_buffer(buf)
        self.assertEqual(messages, [])
        self.assertGreater(len(buf), 0)  # unconsumed bytes remain

    def test_empty_buffer(self):
        buf = bytearray()
        messages = unpack_from_buffer(buf)
        self.assertEqual(messages, [])

    def test_large_payload(self):
        entities = [{"id": i, "x": float(i), "y": float(i)} for i in range(100)]
        msg = {"t": int(MsgType.SNAPSHOT), "entities": entities}
        packed = pack_message(msg)
        buf = bytearray(packed)
        result = unpack_from_buffer(buf)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["entities"]), 100)


if __name__ == "__main__":
    unittest.main()
