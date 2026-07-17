"""End-to-end MQTT bridge coverage with Mosquitto and scripted mochad input."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import threading
import time
import uuid

import paho.mqtt.client as paho
import pytest

from bridge import Bridge
from config import Config, MqttTlsConfig
from models import DeviceConfig
from tests.support.fake_mochad_server import FakeMochadServer, ScriptedLine


pytestmark = [pytest.mark.integration, pytest.mark.known_inputs]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with contextlib.suppress(OSError):
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        time.sleep(0.02)
    raise TimeoutError(f"service did not listen on port {port}")


@contextlib.contextmanager
def _mosquitto(tmp_path: Path, port: int):
    if shutil.which("mosquitto") is None:
        pytest.skip("mosquitto is required for bridge MQTT integration tests")

    config = tmp_path / "mosquitto.conf"
    config.write_text(
        "\n".join(
            (
                "persistence false",
                "allow_anonymous true",
                f"listener {port} 127.0.0.1",
                "",
            )
        )
    )
    process = subprocess.Popen(
        ["mosquitto", "-c", str(config)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_port(port)
        yield
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=3)
        if process.poll() is None:
            process.kill()


@pytest.mark.integration
def test_known_mochad_input_publishes_mqtt_and_mqtt_command_reaches_mochad(tmp_path):
    mqtt_port = _free_port()
    received: queue.Queue[tuple[str, str, bool]] = queue.Queue()
    subscribed = threading.Event()
    subscriber = paho.Client(
        paho.CallbackAPIVersion.VERSION2,
        client_id=f"bridge-test-sub-{uuid.uuid4()}",
    )

    def on_message(client, userdata, message):
        received.put((message.topic, message.payload.decode(), message.retain))

    def on_subscribe(*args):
        subscribed.set()

    subscriber.on_message = on_message
    subscriber.on_subscribe = on_subscribe

    with _mosquitto(tmp_path, mqtt_port), FakeMochadServer(
        [
            ScriptedLine(
                "07/11 12:00:01 Rx RF HouseUnit: A1 Func: On",
                delay=0.05,
                partial_at=18,
            )
        ]
    ) as fake_mochad:
        fake_mochad.wait_until_ready()
        subscriber.connect("127.0.0.1", mqtt_port)
        subscriber.loop_start()
        subscriber.subscribe("#")
        assert subscribed.wait(3.0)
        bridge = Bridge(
            Config(
                mochad_host=fake_mochad.host,
                mochad_port=fake_mochad.port,
                mqtt_host="127.0.0.1",
                mqtt_port=mqtt_port,
                mqtt_username=None,
                mqtt_password=None,
                mqtt_tls=MqttTlsConfig(),
                mqtt_base_topic="x10",
                mqtt_discovery_prefix="homeassistant",
                log_level="INFO",
                config_file=str(tmp_path / "bridge.json"),
                discovery_registry_path=str(tmp_path / "registry.json"),
                devices={"A1": DeviceConfig("A1", "Fixture Lamp")},
            )
        )
        try:
            bridge.start()
            deadline = time.monotonic() + 5.0
            messages: list[tuple[str, str, bool]] = []
            while time.monotonic() < deadline:
                try:
                    messages.append(received.get(timeout=0.1))
                except queue.Empty:
                    continue
                topics = {topic for topic, _, _ in messages}
                if {
                    "x10/A1/event",
                    "homeassistant/switch/x10_A1/config",
                } <= topics:
                    break

            event_messages = [item for item in messages if item[0] == "x10/A1/event"]
            assert len(event_messages) == 1
            assert json.loads(event_messages[0][1])["command"] == "ON"
            assert event_messages[0][2] is False
            assert any(topic == "homeassistant/switch/x10_A1/config" for topic, _, _ in messages)

            publisher = paho.Client(
                paho.CallbackAPIVersion.VERSION2,
                client_id=f"bridge-test-pub-{uuid.uuid4()}",
            )
            publisher.connect("127.0.0.1", mqtt_port)
            publisher.loop_start()
            publisher.publish("x10/A1/command", "OFF")
            deadline = time.monotonic() + 5.0
            while "rf A1 off" not in fake_mochad.commands and time.monotonic() < deadline:
                time.sleep(0.02)
            publisher.disconnect()
            publisher.loop_stop()
            assert "rf A1 off" in fake_mochad.commands
        finally:
            bridge.stop()
            subscriber.disconnect()
            subscriber.loop_stop()
