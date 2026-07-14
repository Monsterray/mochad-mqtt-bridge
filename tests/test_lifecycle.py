"""Lifecycle tests using only deterministic local TCP and MQTT doubles."""

from __future__ import annotations

import socket
import threading
import time

import pytest

from mochad_client import MochadClient
from mqtt_client import MqttClient
from tests.support.fake_mochad_server import FakeMochadServer, ScriptedLine


def _unused_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class UnavailablePaho:
    on_connect = None
    on_disconnect = None
    on_message = None

    def will_set(self, *args, **kwargs): pass
    def reconnect_delay_set(self, *args, **kwargs): pass
    def connect_async(self, *args, **kwargs): raise OSError("broker down")
    def loop_start(self): self.started = True
    def loop_stop(self): self.stopped = True
    def disconnect(self): pass
    def subscribe(self, *args, **kwargs): pass
    def publish(self, *args, **kwargs): return None


@pytest.mark.lifecycle
def test_fake_mochad_down_at_boot_then_recovers_and_reads_partial_line():
    port = _unused_port()
    lines: list[str] = []
    connected = threading.Event()
    server = FakeMochadServer(
        [ScriptedLine("07/11 12:00:01 Rx RF HouseUnit: A1 Func: On", partial_at=12)],
        port=port,
        startup_delay=0.1,
    ).start()
    client = MochadClient(
        "127.0.0.1",
        port=port,
        reconnect_delay=0.02,
        connect_timeout=0.05,
        read_timeout=0.05,
    )
    client.set_connect_callback(connected.set)
    client.set_line_callback(lines.append)

    try:
        client.start()
        assert connected.wait(2.0)
        deadline = time.monotonic() + 2.0
        while not lines and time.monotonic() < deadline:
            time.sleep(0.01)
        assert lines == ["07/11 12:00:01 Rx RF HouseUnit: A1 Func: On"]
    finally:
        client.stop()
        server.stop()


@pytest.mark.lifecycle
def test_mqtt_broker_down_at_boot_does_not_raise_or_block_shutdown():
    unavailable = UnavailablePaho()
    client = MqttClient(
        "127.0.0.1",
        port=1,
        client_factory=lambda _client_id: unavailable,
    )

    client.connect()
    started = time.monotonic()
    client.disconnect()

    assert unavailable.started is True
    assert unavailable.stopped is True
    assert time.monotonic() - started < 0.25


@pytest.mark.lifecycle
def test_mochad_stop_is_bounded_while_connect_is_pending():
    client = MochadClient(
        "192.0.2.1",
        connect_timeout=0.2,
        reconnect_delay=30.0,
    )
    client.start()
    started = time.monotonic()
    client.stop()

    assert time.monotonic() - started < 1.0
