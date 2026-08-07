"""Per-client connection handler for the server."""

from __future__ import annotations

import asyncio
import socket
from shared.protocol import (
    MessageTooLarge, pack_message, unpack_from_buffer)


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
        #: What this client last received, keyed by entity id. The baseline the
        #: per-tick delta is computed against; None means "send a full one".
        self.last_snapshot: dict[int, dict] | None = None
        #: Set once the client passes the version handshake.
        self.player_name: str = ""
        self._reader_task: asyncio.Task | None = None

        # Disable Nagle: our messages are small and latency-sensitive, and
        # coalescing them adds up to ~40ms of input delay on a real WAN link.
        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

    def start_reader(self) -> None:
        """Begin pumping this connection into `incoming` on its own task.

        Reads used to happen inline in the tick: the loop asked each client for
        messages with a 1ms timeout, so ten players burned up to 10ms of a 50ms
        budget waiting on sockets that had nothing to say. A dedicated task per
        connection lets the kernel wake us only when bytes actually arrive, and
        the tick just drains a list.
        """
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        """Read this connection until it closes, decoding into `incoming`."""
        try:
            while self.connected:
                data = await self.reader.read(65536)
                if not data:
                    break                      # clean EOF: peer closed
                self.buffer.extend(data)
                try:
                    self.incoming.extend(unpack_from_buffer(self.buffer))
                except MessageTooLarge:
                    # A corrupt or hostile length prefix: drop the client
                    # rather than buffering bytes that will never arrive.
                    print(f"[SERVER] client {self.client_id} sent a bad frame; "
                          f"dropping")
                    break
        except asyncio.CancelledError:
            raise
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            self.connected = False

    def take_messages(self) -> list[dict]:
        """Hand over everything received since the last call. Never blocks."""
        if not self.incoming:
            return []
        messages, self.incoming = self.incoming, []
        return messages

    def send(self, msg: dict) -> None:
        """Queue a message to send to this client."""
        if not self.connected:
            return
        try:
            data = pack_message(msg)
            self.writer.write(data)
        except MessageTooLarge:
            # Never let this escape into the game-loop task: that used to kill
            # the simulation silently while the socket stayed open.
            print(f"[SERVER] dropped oversized message to client "
                  f"{self.client_id}; forcing a full resync next tick")
            self.last_snapshot = None
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
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None
        try:
            self.writer.close()
        except OSError:
            pass
