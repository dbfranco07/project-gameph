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


#: A Terraria "Connect Request" packet: [u16 LE total length][msg type 1]
#: [7-bit-length-prefixed version string].
#:
#: playit.gg's free tier only offers game-preset tunnels, and a preset edge
#: *sniffs the first packet* — a connection whose opening bytes aren't a valid
#: handshake for that game is reset before it ever reaches the agent, which is
#: why a tunnelled client saw an empty lobby forever. Sending this as the first
#: thing on the wire gets us past the sniffer; the edge then forwards it
#: verbatim and pipes the rest of the connection transparently, so the server
#: only has to consume these 15 bytes before the real stream begins.
#:
#: This is a tunnel workaround, not part of the game protocol — it carries no
#: information and deliberately sits outside `PROTOCOL_VERSION`.
TUNNEL_PRELUDE = b"\x0f\x00\x01\x0bTerraria279"


def take_tunnel_prelude(buf: bytearray) -> bool | None:
    """Consume a leading `TUNNEL_PRELUDE` from `buf`, if one is there.

    Returns True if the prelude was consumed, False if `buf` definitively does
    not start with one (a direct connection — the caller should stop checking),
    and None if there aren't enough bytes to tell yet.
    """
    n = min(len(buf), len(TUNNEL_PRELUDE))
    if bytes(buf[:n]) != TUNNEL_PRELUDE[:n]:
        return False
    if len(buf) < len(TUNNEL_PRELUDE):
        return None  # a partial match so far; wait for the rest
    del buf[:len(TUNNEL_PRELUDE)]
    return True
