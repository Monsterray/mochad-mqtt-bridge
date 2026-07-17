"""Small scripted newline-delimited mochad TCP server for bridge tests."""

from __future__ import annotations

from dataclasses import dataclass
import socket
import threading
import time
from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class ScriptedLine:
    """A line emitted after a client connects."""

    line: str
    delay: float = 0.0
    partial_at: int | None = None


class FakeMochadServer:
    """Record bridge commands and emit deterministic mochad text lines."""

    def __init__(
        self,
        lines: Iterable[ScriptedLine | str] = (),
        *,
        port: int = 0,
        startup_delay: float = 0.0,
        disconnect_after_script: bool = False,
    ) -> None:
        self._lines = [
            item if isinstance(item, ScriptedLine) else ScriptedLine(item)
            for item in lines
        ]
        self.startup_delay = startup_delay
        self.disconnect_after_script = disconnect_after_script
        self.host = "127.0.0.1"
        self.port = port
        self.commands: list[str] = []
        self.client_connected = threading.Event()
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._listener: socket.socket | None = None
        self._client: socket.socket | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> "FakeMochadServer":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def wait_until_ready(self, timeout: float = 2.0) -> None:
        if not self._ready.wait(timeout):
            raise TimeoutError("fake mochad server did not start")

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            sockets = (self._client, self._listener)
            self._client = None
            self._listener = None
        for sock in sockets:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def __enter__(self) -> "FakeMochadServer":
        return self.start()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.stop()

    def emit(self, line: str, *, partial_at: int | None = None) -> None:
        with self._lock:
            client = self._client
        if client is None:
            raise ConnectionError("fake mochad has no connected client")
        self._send_line(client, ScriptedLine(line, partial_at=partial_at))

    def disconnect_client(self) -> None:
        with self._lock:
            client = self._client
            self._client = None
        if client is not None:
            client.close()

    def _run(self) -> None:
        if self.startup_delay:
            self._stop.wait(self.startup_delay)
        if self._stop.is_set():
            return

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(1)
        listener.settimeout(0.1)
        with self._lock:
            self._listener = listener
            self.port = listener.getsockname()[1]
        self._ready.set()

        while not self._stop.is_set():
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return

            with self._lock:
                self._client = client
            client.settimeout(0.1)
            self.client_connected.set()

            writer = threading.Thread(
                target=self._emit_script,
                args=(client,),
                daemon=True,
            )
            writer.start()
            self._read_commands(client)
            writer.join(timeout=1.0)
            with self._lock:
                if self._client is client:
                    self._client = None
            try:
                client.close()
            except OSError:
                pass

    def _emit_script(self, client: socket.socket) -> None:
        for line in self._lines:
            if self._stop.wait(line.delay):
                return
            try:
                self._send_line(client, line)
            except OSError:
                return
        if self.disconnect_after_script:
            self.disconnect_client()

    def _read_commands(self, client: socket.socket) -> None:
        buffer = ""
        while not self._stop.is_set():
            try:
                data = client.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            if not data:
                return
            buffer += data.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                self.commands.append(line.rstrip("\r"))

    @staticmethod
    def _send_line(client: socket.socket, item: ScriptedLine) -> None:
        data = (item.line.rstrip("\r\n") + "\n").encode("utf-8")
        if item.partial_at is None:
            client.sendall(data)
            return
        client.sendall(data[: item.partial_at])
        time.sleep(0.01)
        client.sendall(data[item.partial_at :])
