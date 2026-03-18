"""
Network protocol: length-prefixed msgpack messages over TCP.

Wire format: [2-byte big-endian length][msgpack payload]
Payload is always a dict with at least a "t" (type) key.
"""

import struct
import msgpack

HEADER_FMT = "!H"  # unsigned short, big-endian
HEADER_SIZE = struct.calcsize(HEADER_FMT)
MAX_MSG_SIZE = 65535


def pack_message(msg: dict) -> bytes:
    """Serialize a message dict to a length-prefixed bytes buffer."""
    payload = msgpack.packb(msg, use_bin_type=True)
    length = len(payload)
    if length > MAX_MSG_SIZE:
        raise ValueError(f"Message too large: {length} bytes")
    return struct.pack(HEADER_FMT, length) + payload


def unpack_from_buffer(buf: bytearray) -> list[dict]:
    """Extract all complete messages from a byte buffer.

    Consumes the bytes of complete messages from `buf` in-place.
    Returns a list of decoded message dicts.
    """
    messages = []
    while len(buf) >= HEADER_SIZE:
        (length,) = struct.unpack(HEADER_FMT, buf[:HEADER_SIZE])
        total = HEADER_SIZE + length
        if len(buf) < total:
            break  # incomplete message
        payload = buf[HEADER_SIZE:total]
        del buf[:total]
        messages.append(msgpack.unpackb(payload, raw=False))
    return messages
