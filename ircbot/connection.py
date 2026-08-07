"""Async IRC connection with automatic reconnect and exponential backoff.

Owns the TCP socket lifecycle. Knows nothing about IRC semantics beyond
sending/receiving raw lines.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import AsyncGenerator
from typing import Callable, Awaitable

log = logging.getLogger(__name__)

# Backoff parameters
_BACKOFF_BASE = 5
_BACKOFF_MAX = 300
_BACKOFF_MULTIPLIER = 2


class IRCConnection:
    """Manages an async TCP connection to an IRC server."""

    def __init__(
        self,
        host: str,
        port: int,
        use_tls: bool = False,
        encoding: str = "utf-8",
    ) -> None:
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.encoding = encoding

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._stopping = False

    @property
    def connected(self) -> bool:
        return self._connected

    # -- connect / disconnect --

    async def connect(self) -> None:
        """Open the TCP connection."""
        ssl_ctx: ssl.SSLContext | None = None
        if self.use_tls:
            ssl_ctx = ssl.create_default_context()

        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port, ssl=ssl_ctx,
        )
        self._connected = True
        log.info("Connected to %s:%d (tls=%s)", self.host, self.port, self.use_tls)

    async def stop(self) -> None:
        """Disconnect and end the run_forever reconnect loop."""
        self._stopping = True
        await self.disconnect()

    async def disconnect(self) -> None:
        """Close the TCP connection gracefully."""
        self._connected = False
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                # The socket is already gone; we are tearing it down anyway.
                pass
            self._writer = None
        self._reader = None
        log.info("Disconnected")

    # -- send / receive --

    async def _write(self, line: str) -> bool:
        """Write a line to the socket. Returns False when disconnected.

        Logs nothing about the payload, so callers holding a credential can
        use it without the secret reaching the log.
        """
        if self._writer is None:
            return False
        data = (line + "\r\n").encode(self.encoding)
        self._writer.write(data)
        await self._writer.drain()
        return True

    async def send(self, line: str) -> None:
        """Send a single IRC line (appends CRLF).

        Never use this for a line carrying a password -- the line is written
        to the debug log verbatim. Use :meth:`send_secret` instead.
        """
        if self._writer is None:
            log.warning("send() called while disconnected: %s", line)
            return
        await self._write(line)
        log.debug(">> %s", line)

    async def send_secret(self, line: str, description: str) -> None:
        """Send a line whose parameters are credentials.

        Args:
            line: The raw IRC line, including the secret.
            description: A literal stand-in logged in place of the line; it
                must not be derived from the secret.
        """
        if not await self._write(line):
            log.warning("send_secret() called while disconnected: %s", description)
            return
        log.debug(">> %s", description)

    async def read_lines(self) -> AsyncGenerator[str, None]:
        """Yield decoded IRC lines until the connection drops."""
        if self._reader is None:
            raise RuntimeError("read_lines() called before connect()")
        while self._connected:
            try:
                raw = await self._reader.readline()
            except (ConnectionResetError, asyncio.IncompleteReadError, OSError, ValueError):
                break
            if not raw:
                break
            line = raw.decode(self.encoding, errors="replace").rstrip("\r\n")
            log.debug("<< %s", line)
            yield line
        self._connected = False

    # -- reconnect loop --

    async def run_forever(
        self,
        on_connect: Callable[[], Awaitable[None]],
        on_line: Callable[[str], Awaitable[None]],
    ) -> None:
        """Connect, read lines, and reconnect on failure with exponential backoff.

        Args:
            on_connect: Called after each successful TCP connect (send NICK/USER here).
            on_line: Called for every raw IRC line received.
        """
        backoff = _BACKOFF_BASE
        self._stopping = False

        while not self._stopping:
            try:
                await self.connect()
                backoff = _BACKOFF_BASE  # reset on successful connect
                await on_connect()

                async for line in self.read_lines():
                    await on_line(line)

            except (ConnectionResetError, OSError) as exc:
                log.warning("Connection error: %s", exc)

            finally:
                await self.disconnect()

            if self._stopping:
                break

            log.info("Reconnecting in %ds...", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * _BACKOFF_MULTIPLIER, _BACKOFF_MAX)
