"""Per-client connection handler for the server."""

from __future__ import annotations

import asyncio
from shared.protocol import pack_message, unpack_from_buffer


class ClientHandler:
    """Manages a single client TCP connection."""

    def __init__(
        self,
        client_id: int,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self.client_id = client_id
        self.reader = reader
        self.writer = writer
        self.buffer = bytearray()
        self.incoming: list[dict] = []
        self.connected = True
        self._addr = writer.get_extra_info("peername")

    async def read_messages(self) -> list[dict]:
        """Non-blocking read of all available messages from this client."""
        try:
            data = await asyncio.wait_for(self.reader.read(4096), timeout=0.001)
            if not data:
                self.connected = False
                return []
            self.buffer.extend(data)
        except (asyncio.TimeoutError, TimeoutError):
            pass
        except (ConnectionResetError, BrokenPipeError, OSError):
            self.connected = False
            return []

        messages = unpack_from_buffer(self.buffer)
        return messages

    def send(self, msg: dict) -> None:
        """Queue a message to send to this client."""
        if not self.connected:
            return
        try:
            data = pack_message(msg)
            self.writer.write(data)
        except (ConnectionResetError, BrokenPipeError, OSError):
            self.connected = False

    async def flush(self) -> None:
        """Flush the write buffer."""
        if not self.connected:
            return
        try:
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            self.connected = False

    def close(self) -> None:
        self.connected = False
        try:
            self.writer.close()
        except OSError:
            pass
