"""Tests for ircbot.connection -- IRCConnection send, recv, disconnect, backoff.

Coverage strategy:
- send: appends CRLF, encodes, calls writer.write + drain; no-op when disconnected
- read_lines: yields decoded lines, strips CRLF, stops on empty read or exception
- disconnect: sets connected=False, closes writer, tolerates OSError
- connected property: reflects state
- run_forever: backoff logic (reset on connect, exponential growth, capped at max)
- connect is mocked to avoid real sockets; we test the orchestration around it

We mock asyncio.open_connection to provide fake StreamReader/StreamWriter objects.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

from ircbot.connection import IRCConnection, _BACKOFF_BASE, _BACKOFF_MAX, _BACKOFF_MULTIPLIER


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_reader(lines: list[bytes]) -> AsyncMock:
    """Create a fake StreamReader that yields the given lines then empty bytes."""
    reader = AsyncMock()
    responses = [line for line in lines] + [b""]
    reader.readline = AsyncMock(side_effect=responses)
    return reader


def _make_writer() -> MagicMock:
    """Create a fake StreamWriter with async drain and close."""
    writer = MagicMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    return writer


# ── send ─────────────────────────────────────────────────────────────


class TestSend:
    def test_send_encodes_and_appends_crlf(self):
        conn = IRCConnection("host", 6667)
        writer = _make_writer()
        conn._writer = writer
        conn._connected = True

        _run(conn.send("PRIVMSG #test :hello"))

        writer.write.assert_called_once_with(b"PRIVMSG #test :hello\r\n")
        writer.drain.assert_awaited_once()

    def test_send_when_disconnected_is_noop(self):
        conn = IRCConnection("host", 6667)
        conn._writer = None
        conn._connected = False

        # Should not raise
        _run(conn.send("PING :test"))

    def test_send_uses_configured_encoding(self):
        conn = IRCConnection("host", 6667, encoding="latin-1")
        writer = _make_writer()
        conn._writer = writer
        conn._connected = True

        _run(conn.send("PRIVMSG #test :caf\u00e9"))
        expected = "PRIVMSG #test :caf\u00e9\r\n".encode("latin-1")
        writer.write.assert_called_once_with(expected)


# ── read_lines ───────────────────────────────────────────────────────


class TestReadLines:
    def test_yields_decoded_stripped_lines(self):
        conn = IRCConnection("host", 6667)
        reader = _make_reader([
            b"PING :server\r\n",
            b":alice PRIVMSG #test :hello\r\n",
        ])
        conn._reader = reader
        conn._connected = True

        lines = []

        async def collect():
            async for line in conn.read_lines():
                lines.append(line)

        _run(collect())

        assert lines == ["PING :server", ":alice PRIVMSG #test :hello"]

    def test_stops_on_empty_read(self):
        conn = IRCConnection("host", 6667)
        reader = _make_reader([b"line1\r\n"])  # then b"" from _make_reader
        conn._reader = reader
        conn._connected = True

        lines = []

        async def collect():
            async for line in conn.read_lines():
                lines.append(line)

        _run(collect())
        assert lines == ["line1"]
        assert conn.connected is False

    def test_stops_on_connection_reset(self):
        conn = IRCConnection("host", 6667)
        reader = AsyncMock()
        reader.readline = AsyncMock(side_effect=ConnectionResetError("reset"))
        conn._reader = reader
        conn._connected = True

        lines = []

        async def collect():
            async for line in conn.read_lines():
                lines.append(line)

        _run(collect())
        assert lines == []
        assert conn.connected is False

    def test_stops_on_os_error(self):
        conn = IRCConnection("host", 6667)
        reader = AsyncMock()
        reader.readline = AsyncMock(side_effect=OSError("broken"))
        conn._reader = reader
        conn._connected = True

        lines = []

        async def collect():
            async for line in conn.read_lines():
                lines.append(line)

        _run(collect())
        assert lines == []

    def test_raises_if_called_before_connect(self):
        conn = IRCConnection("host", 6667)
        conn._reader = None

        import pytest

        async def try_read():
            async for _ in conn.read_lines():
                pass

        with pytest.raises(RuntimeError, match="read_lines.*before connect"):
            _run(try_read())

    def test_handles_decode_errors_with_replace(self):
        conn = IRCConnection("host", 6667)
        # Invalid UTF-8 byte sequence
        reader = _make_reader([b"hello \xff world\r\n"])
        conn._reader = reader
        conn._connected = True

        lines = []

        async def collect():
            async for line in conn.read_lines():
                lines.append(line)

        _run(collect())
        assert len(lines) == 1
        assert "hello" in lines[0]
        assert "\ufffd" in lines[0]  # replacement character


# ── disconnect ───────────────────────────────────────────────────────


class TestDisconnect:
    def test_disconnect_closes_writer_and_resets_state(self):
        conn = IRCConnection("host", 6667)
        writer = _make_writer()
        conn._writer = writer
        conn._reader = AsyncMock()
        conn._connected = True

        _run(conn.disconnect())

        assert conn.connected is False
        assert conn._writer is None
        assert conn._reader is None
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()

    def test_disconnect_tolerates_os_error_on_close(self):
        conn = IRCConnection("host", 6667)
        writer = _make_writer()
        writer.close = MagicMock(side_effect=OSError("already closed"))
        conn._writer = writer
        conn._reader = AsyncMock()
        conn._connected = True

        # Should not raise
        _run(conn.disconnect())
        assert conn.connected is False

    def test_disconnect_when_already_disconnected(self):
        conn = IRCConnection("host", 6667)
        conn._writer = None
        conn._reader = None
        conn._connected = False

        # Should not raise
        _run(conn.disconnect())


# ── connected property ───────────────────────────────────────────────


class TestConnectedProperty:
    def test_initially_false(self):
        conn = IRCConnection("host", 6667)
        assert conn.connected is False

    def test_reflects_internal_state(self):
        conn = IRCConnection("host", 6667)
        conn._connected = True
        assert conn.connected is True
        conn._connected = False
        assert conn.connected is False


# ── run_forever backoff logic ────────────────────────────────────────


class TestRunForeverBackoff:
    def test_backoff_resets_on_successful_connect(self):
        """After a successful connect, backoff should reset to base."""
        conn = IRCConnection("host", 6667)
        iterations = []
        sleep_values = []

        call_count = 0

        async def fake_connect():
            nonlocal call_count
            call_count += 1
            conn._connected = True
            conn._reader = _make_reader([])  # immediately EOF
            conn._writer = _make_writer()

        async def fake_on_connect():
            pass

        async def fake_on_line(line):
            pass

        original_connect = conn.connect
        conn.connect = fake_connect

        original_disconnect = conn.disconnect

        async def fake_disconnect():
            conn._connected = False
            conn._writer = None
            conn._reader = None

        conn.disconnect = fake_disconnect

        async def fake_sleep(seconds):
            sleep_values.append(seconds)
            if len(sleep_values) >= 3:
                raise KeyboardInterrupt("stop test")

        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                _run(conn.run_forever(fake_on_connect, fake_on_line))
            except KeyboardInterrupt:
                pass

        # Each connect succeeds, so backoff should always reset to base
        assert all(s == _BACKOFF_BASE for s in sleep_values), \
            f"Expected all sleeps to be {_BACKOFF_BASE}, got {sleep_values}"

    def test_backoff_grows_exponentially_on_connect_failure(self):
        """When connect fails, backoff should grow exponentially."""
        conn = IRCConnection("host", 6667)
        sleep_values = []

        async def failing_connect():
            raise OSError("connection refused")

        conn.connect = failing_connect

        async def fake_disconnect():
            conn._connected = False
            conn._writer = None
            conn._reader = None

        conn.disconnect = fake_disconnect

        async def fake_sleep(seconds):
            sleep_values.append(seconds)
            if len(sleep_values) >= 4:
                raise KeyboardInterrupt("stop test")

        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                _run(conn.run_forever(AsyncMock(), AsyncMock()))
            except KeyboardInterrupt:
                pass

        # First sleep is base (set before the loop, connect fails so no reset)
        # Then grows: base, base*2, base*4, base*8...
        assert sleep_values[0] == _BACKOFF_BASE
        assert sleep_values[1] == _BACKOFF_BASE * _BACKOFF_MULTIPLIER
        assert sleep_values[2] == _BACKOFF_BASE * _BACKOFF_MULTIPLIER ** 2

    def test_backoff_capped_at_max(self):
        """Backoff should never exceed _BACKOFF_MAX."""
        conn = IRCConnection("host", 6667)
        sleep_values = []

        async def failing_connect():
            raise OSError("connection refused")

        conn.connect = failing_connect

        async def fake_disconnect():
            conn._connected = False
            conn._writer = None
            conn._reader = None

        conn.disconnect = fake_disconnect

        async def fake_sleep(seconds):
            sleep_values.append(seconds)
            if len(sleep_values) >= 15:
                raise KeyboardInterrupt("stop test")

        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                _run(conn.run_forever(AsyncMock(), AsyncMock()))
            except KeyboardInterrupt:
                pass

        assert all(s <= _BACKOFF_MAX for s in sleep_values), \
            f"Backoff exceeded max: {max(sleep_values)} > {_BACKOFF_MAX}"
        # Verify it actually reached the cap
        assert _BACKOFF_MAX in sleep_values

    def test_on_line_called_for_each_received_line(self):
        """on_line callback should be called for every line read."""
        conn = IRCConnection("host", 6667)
        received_lines = []

        async def fake_connect():
            conn._connected = True
            conn._reader = _make_reader([
                b"PING :server\r\n",
                b":nick PRIVMSG #test :hi\r\n",
            ])
            conn._writer = _make_writer()

        conn.connect = fake_connect

        call_count = [0]

        async def fake_disconnect():
            conn._connected = False
            conn._writer = None
            conn._reader = None

        conn.disconnect = fake_disconnect

        async def fake_on_line(line):
            received_lines.append(line)

        async def fake_sleep(seconds):
            raise KeyboardInterrupt("stop after first cycle")

        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                _run(conn.run_forever(AsyncMock(), fake_on_line))
            except KeyboardInterrupt:
                pass

        assert received_lines == ["PING :server", ":nick PRIVMSG #test :hi"]

    def test_on_connect_called_each_cycle(self):
        """on_connect should be called after each successful TCP connect."""
        conn = IRCConnection("host", 6667)
        connect_count = [0]

        async def fake_connect():
            conn._connected = True
            conn._reader = _make_reader([])  # immediate EOF
            conn._writer = _make_writer()

        conn.connect = fake_connect

        async def fake_disconnect():
            conn._connected = False
            conn._writer = None
            conn._reader = None

        conn.disconnect = fake_disconnect

        async def fake_on_connect():
            connect_count[0] += 1

        cycle = [0]

        async def fake_sleep(seconds):
            cycle[0] += 1
            if cycle[0] >= 3:
                raise KeyboardInterrupt("stop")

        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                _run(conn.run_forever(fake_on_connect, AsyncMock()))
            except KeyboardInterrupt:
                pass

        assert connect_count[0] == 3


# ── Constructor ──────────────────────────────────────────────────────


class TestConstructor:
    def test_stores_parameters(self):
        conn = IRCConnection("irc.example.com", 6697, use_tls=True, encoding="latin-1")
        assert conn.host == "irc.example.com"
        assert conn.port == 6697
        assert conn.use_tls is True
        assert conn.encoding == "latin-1"

    def test_defaults(self):
        conn = IRCConnection("host", 6667)
        assert conn.use_tls is False
        assert conn.encoding == "utf-8"
        assert conn.connected is False
