"""
Network protocol: length-prefixed msgpack messages over TCP.

Wire format: [4-byte big-endian length][msgpack payload]
Payload is always a dict with at least a "t" (type) key.

The header used to be 2 bytes, capping a frame at 65535 — reachable in a long
5v5 once the entity count climbed. `pack_message` raised `ValueError` there and
nothing caught it, so the exception propagated out of the fire-and-forget game
loop task: the simulation died silently while the listening socket stayed open
and the server merely appeared to freeze. Four bytes puts the ceiling far out of
reach, and `MAX_MSG_SIZE` stays as a sanity bound against a malformed length
prefix causing a huge allocation.
"""

import struct
import msgpack

#: Bumped whenever the wire format or message semantics change in a way that
#: makes an older client misbehave rather than merely miss a feature. The server
#: rejects a mismatch on JOIN with a clear message instead of letting the client
#: fail in a confusing way later. Client and server ship together, so this is
#: about catching a stale install, not about supporting old versions.
PROTOCOL_VERSION = 2

HEADER_FMT = "!I"  # unsigned int, big-endian
HEADER_SIZE = struct.calcsize(HEADER_FMT)
MAX_MSG_SIZE = 16 * 1024 * 1024  # 16 MB: a bound on hostile input, not a budget


class MessageTooLarge(ValueError):
    """A frame exceeded `MAX_MSG_SIZE`. Callers must handle this rather than
    letting it escape into a background task."""


def pack_message(msg: dict) -> bytes:
    """Serialize a message dict to a length-prefixed bytes buffer."""
    payload = msgpack.packb(msg, use_bin_type=True)
    length = len(payload)
    if length > MAX_MSG_SIZE:
        raise MessageTooLarge(f"Message too large: {length} bytes")
    return struct.pack(HEADER_FMT, length) + payload


def unpack_from_buffer(buf: bytearray) -> list[dict]:
    """Extract all complete messages from a byte buffer.

    Consumes the bytes of complete messages from `buf` in-place.
    Returns a list of decoded message dicts.

    Raises:
        MessageTooLarge: if a declared length exceeds `MAX_MSG_SIZE`, which
            means the stream is corrupt or hostile — continuing would buffer
            unboundedly waiting for bytes that will never arrive.
    """
    messages = []
    while len(buf) >= HEADER_SIZE:
        (length,) = struct.unpack(HEADER_FMT, buf[:HEADER_SIZE])
        if length > MAX_MSG_SIZE:
            raise MessageTooLarge(
                f"Declared frame of {length} bytes exceeds the limit")
        total = HEADER_SIZE + length
        if len(buf) < total:
            break  # incomplete message
        payload = buf[HEADER_SIZE:total]
        del buf[:total]
        messages.append(msgpack.unpackb(payload, raw=False))
    return messages
