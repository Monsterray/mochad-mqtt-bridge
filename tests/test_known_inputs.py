"""Deterministic fixture coverage for bridge protocol boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from bridge import Bridge
from config import Config, MqttTlsConfig
from discovery_registry import DiscoveryRegistry
from models import Command, DeviceConfig, DeviceEvent, DeviceType
from mqtt_client import MqttCommandMessage
from protocol import ProtocolParser


FIXTURES = Path(__file__).parent / "fixtures"


class RecordingMqtt:
    connected = True

    def __init__(self) -> None:
        self.events: list[tuple[str, dict, bool]] = []
        self.states: list[tuple[str, Command, bool]] = []
        self.discovery = []

    def set_command_callback(self, callback): self.command_callback = callback
    def set_bridge_command_callback(self, callback): self.bridge_callback = callback
    def set_connect_callback(self, callback): self.connect_callback = callback
    def set_disconnect_callback(self, callback): self.disconnect_callback = callback
    def publish_event(self, device, payload, retain=False): self.events.append((device, payload, retain))
    def publish_state(self, device, state, retain=True): self.states.append((device, state, retain))
    def publish_attributes(self, *args, **kwargs): pass
    def publish_discovery(self, message): self.discovery.append(message)
    def publish_availability(self, *args, **kwargs): pass
    def publish_status(self, *args, **kwargs): pass
    def publish_bridge_response(self, *args, **kwargs): pass


class RecordingMochad:
    connected = True

    def __init__(self) -> None:
        self.lines: list[str] = []

    def set_line_callback(self, callback): self.line_callback = callback
    def set_connect_callback(self, callback): self.connect_callback = callback
    def set_disconnect_callback(self, callback): self.disconnect_callback = callback
    def send_line(self, line): self.lines.append(line)
    def request_status(self): self.lines.append("st")


def _config(*devices: DeviceConfig) -> Config:
    return Config(
        mochad_host="127.0.0.1",
        mochad_port=1099,
        mqtt_host="127.0.0.1",
        mqtt_port=1883,
        mqtt_username=None,
        mqtt_password=None,
        mqtt_tls=MqttTlsConfig(),
        mqtt_base_topic="x10",
        mqtt_discovery_prefix="homeassistant",
        log_level="INFO",
        devices={device.address: device for device in devices},
    )


@pytest.mark.known_inputs
def test_basic_rf_fixture_parses_to_expected_event():
    line = (FIXTURES / "mochad_lines" / "basic_rf_receive.txt").read_text().strip()
    event = ProtocolParser().parse_line(line)

    assert isinstance(event, DeviceEvent)
    assert event.address == "A1"
    assert event.command is Command.ON


@pytest.mark.known_inputs
def test_transmitted_rf_fixture_is_reported_as_unconfirmed():
    mqtt = RecordingMqtt()
    bridge = Bridge(_config(), mqtt_client=mqtt, mochad_client=RecordingMochad())
    line = (FIXTURES / "mochad_lines" / "transmitted_rf_unconfirmed.txt").read_text().strip()

    bridge._on_mochad_line(line)

    assert mqtt.events[0][1]["direction"] == "TX"
    assert mqtt.events[0][1]["confirmed"] is False


@pytest.mark.known_inputs
def test_interrupted_status_fixture_publishes_interleaved_rf_once():
    mqtt = RecordingMqtt()
    bridge = Bridge(_config(), mqtt_client=mqtt, mochad_client=RecordingMochad())
    lines = (FIXTURES / "mochad_lines" / "interrupted_status_with_rf.txt").read_text().splitlines()

    for line in lines:
        bridge._on_mochad_line(line)

    assert [(event[0], event[1]["command"]) for event in mqtt.events] == [("A2", "ON")]


@pytest.mark.known_inputs
def test_invalid_command_topic_fixture_never_creates_state_or_sends_command():
    mqtt = RecordingMqtt()
    mochad = RecordingMochad()
    bridge = Bridge(_config(), mqtt_client=mqtt, mochad_client=mochad)

    for topic in (FIXTURES / "mqtt_commands" / "invalid_topics.txt").read_text().splitlines():
        if topic == "x10/bridge/command":
            continue
        parts = topic.split("/")
        device = parts[1] if len(parts) > 1 else ""
        bridge._on_mqtt_command(MqttCommandMessage(device, "ON", topic))

    assert bridge.state.snapshot() == {}
    assert mochad.lines == []


@pytest.mark.known_inputs
def test_chime_fixture_allows_repeated_on_without_retained_state():
    mqtt = RecordingMqtt()
    mochad = RecordingMochad()
    bridge = Bridge(
        _config(DeviceConfig("A2", "Door Chime", entity_type=DeviceType.CHIME)),
        mqtt_client=mqtt,
        mochad_client=mochad,
    )

    for line in (FIXTURES / "mqtt_commands" / "chime_repeated_on.txt").read_text().splitlines():
        topic, payload = line.split("|", 1)
        bridge._on_mqtt_command(MqttCommandMessage("A2", payload, topic))

    assert mochad.lines == ["rf A2 on", "rf A2 on"]
    assert mqtt.states == []
    assert [event[2] for event in mqtt.events] == [False, False]
    assert all(event[1]["confirmed"] is False for event in mqtt.events)


@pytest.mark.known_inputs
@pytest.mark.parametrize("fixture_name", ["invalid.json", "wrong_shape.json"])
def test_bad_registry_fixture_is_quarantined(tmp_path, fixture_name):
    path = tmp_path / "discovery_registry.json"
    path.write_text((FIXTURES / "discovery_registry" / fixture_name).read_text())

    assert DiscoveryRegistry(path).load() == set()
    assert not path.exists()
    assert list(tmp_path.glob("discovery_registry.json.invalid.*"))
