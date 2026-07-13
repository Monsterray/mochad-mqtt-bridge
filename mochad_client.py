"""
mochad TCP transport client.

This module owns TCP connection management, line-oriented reading, sending raw
commands, and callbacks. It does not parse the mochad protocol or modify state.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Callable


_LOG = logging.getLogger(__name__)
_LOG.addHandler(logging.NullHandler())


LineCallback = Callable[[str], None]
ConnectionCallback = Callable[[], None]
DisconnectCallback = Callable[[Exception | None], None]
SocketFactory = Callable[[tuple[str, int], float | None], socket.socket]


class MochadClient:
    """
    Thin line-oriented TCP client for mochad.
    """

    def __init__(
        self,
        host: str,
        port: int = 1099,
        reconnect_delay: float = 5.0,
        connect_timeout: float = 2.0,
        read_timeout: float = 1.0,
        debug_wire: bool = False,
        socket_factory: SocketFactory | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.debug_wire = debug_wire
        self._socket_factory = socket_factory or socket.create_connection
        self._socket: socket.socket | None = None
        self._socket_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._running = False
        self._thread: threading.Thread | None = None
        self._line_callback: LineCallback | None = None
        self._connect_callback: ConnectionCallback | None = None
        self._disconnect_callback: DisconnectCallback | None = None

    @property
    def connected(self) -> bool:
        with self._socket_lock:
            return self._socket is not None

    def set_line_callback(
        self,
        callback: LineCallback,
    ) -> None:
        self._line_callback = callback

    def set_connect_callback(
        self,
        callback: ConnectionCallback,
    ) -> None:
        self._connect_callback = callback

    def set_disconnect_callback(
        self,
        callback: DisconnectCallback,
    ) -> None:
        self._disconnect_callback = callback

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="mochad-client",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        self.disconnect()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def connect(self) -> None:
        sock = self._socket_factory(
            (self.host, self.port),
            self.connect_timeout,
        )
        sock.settimeout(self.read_timeout)

        with self._socket_lock:
            if self._stop_event.is_set():
                sock.close()
                return

            self._socket = sock

        if self._connect_callback:
            try:
                self._connect_callback()
            except Exception:
                _LOG.exception("mochad connect callback failed")

    def disconnect(self) -> None:
        with self._socket_lock:
            sock = self._socket
            self._socket = None

        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def send_line(
        self,
        line: str,
    ) -> None:
        line = line.rstrip("\r\n")

        with self._socket_lock:
            sock = self._socket

        if sock is None:
            raise ConnectionError("mochad is not connected.")

        if self.debug_wire:
            _LOG.info("mochad tcp write line=%s", line)

        sock.sendall((line + "\n").encode("utf-8"))

    def request_status(self) -> None:
        self.send_line("st")

    def _run(self) -> None:
        while self._running and not self._stop_event.is_set():
            error: Exception | None = None

            try:
                self.connect()
                if self.connected:
                    self._read_loop()
            except Exception as exc:
                error = exc
                _LOG.warning("mochad transport disconnected: %s", exc)
            finally:
                self.disconnect()

                if self._disconnect_callback:
                    try:
                        self._disconnect_callback(error)
                    except Exception:
                        _LOG.exception("mochad disconnect callback failed")

            if self._running:
                self._stop_event.wait(self.reconnect_delay)

    def _read_loop(self) -> None:
        buffer = ""

        while self._running and not self._stop_event.is_set():
            with self._socket_lock:
                sock = self._socket

            if sock is None:
                return

            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue

            if not data:
                return

            chunk = data.decode("utf-8", errors="replace")

            if self.debug_wire:
                _LOG.info(
                    "mochad tcp read bytes=%d data=%r",
                    len(data),
                    chunk,
                )

            buffer += chunk

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip("\r\n")

                if self.debug_wire:
                    _LOG.info(
                        "mochad tcp line line=%s",
                        line,
                    )

                if self._line_callback:
                    try:
                        self._line_callback(line)
                    except Exception:
                        _LOG.exception("mochad line callback failed")
