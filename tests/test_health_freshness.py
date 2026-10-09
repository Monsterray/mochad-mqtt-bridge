import json
import logging
from datetime import datetime
from unittest.mock import patch

from bridge import Bridge
from config import LOG_FORMAT, TimestampFormatter
from models import PublishAvailabilityAction, PublishStatusAction
from mqtt_client import MqttCommandMessage
from tests.test_bridge_commands import FakeMochadClient, FakeMqttClient, minimal_config


def make_bridge():
    return Bridge(
        minimal_config(),
        mqtt_client=FakeMqttClient(),
        mochad_client=FakeMochadClient(),
    )


def health(ready):
    return json.dumps({
        "usb_connected": ready,
        "controller": "CM19A",
        "endpoints_ready": ready,
        "transfers_ready": ready,
    })


def test_periodic_refresh_drains_commands_after_usb_recovery():
    bridge = make_bridge()
    with patch("bridge.time.monotonic", return_value=100):
        bridge._on_mochad_line(health(False))
        bridge._on_mqtt_command(MqttCommandMessage("A1", "ON", "x10/A1/command"))
        bridge._poll_mochad_health()
        bridge._poll_mochad_health()
    assert bridge.clients.mochad.sent_lines == ["health"]
    with patch("bridge.time.monotonic", return_value=131):
        bridge._poll_mochad_health()
        bridge._on_mochad_line(health(True))
    assert bridge.clients.mochad.sent_lines == ["health", "health", "rf A1 on"]
    assert not bridge._queued_device_commands
    assert bridge.clients.mqtt.status_payloads[-1][0]["queued_device_commands"] == 0


def test_stale_health_holds_commands_and_reports_unknown_readiness():
    bridge = make_bridge()
    with patch("bridge.time.monotonic", return_value=100):
        bridge._on_mochad_line(health(True))
    with patch("bridge.time.monotonic", return_value=161):
        bridge._poll_mochad_health()
        bridge._on_mqtt_command(MqttCommandMessage("A1", "OFF", "x10/A1/command"))
        payload = bridge._mochad_diagnostics_payload()
    assert bridge.clients.mochad.sent_lines == ["health"]
    assert payload["health"]["usb_connected"] is None
    assert payload["health"]["fresh"] is False
    assert len(bridge._queued_device_commands) == 1


def test_hello_does_not_refresh_health_age():
    bridge = make_bridge()
    with patch("bridge.time.monotonic", return_value=100):
        bridge._merge_mochad_diagnostics(json.loads(health(True)))
    with patch("bridge.time.monotonic", return_value=161):
        bridge._merge_mochad_diagnostics({"diagnostics": True, "daemon": "mochad-redux"})
        assert not bridge._mochad_health_fresh()


def test_legacy_server_is_not_polled_or_blocked():
    bridge = make_bridge()
    bridge._poll_mochad_health()
    assert bridge.clients.mochad.sent_lines == []
    assert bridge._device_command_queue_reason() is None


def test_advertised_health_requires_response_and_reconnect_requires_fresh_health():
    bridge = make_bridge()
    bridge._merge_mochad_diagnostics({"json": True, "commands": ["health"]})
    assert bridge._device_command_queue_reason() is not None
    bridge._merge_mochad_diagnostics(json.loads(health(True)))
    assert bridge._device_command_queue_reason() is None
    with patch.object(bridge, "execute_actions"), patch.object(bridge, "_write_health"):
        bridge._on_mochad_connected()
    assert bridge._device_command_queue_reason() is not None


def test_malformed_health_cannot_authorize_commands():
    bridge = make_bridge()
    bridge._merge_mochad_diagnostics({"json": True, "commands": ["health"]})
    bridge._merge_mochad_diagnostics(json.loads(health(True)))
    bridge._merge_mochad_diagnostics({"usb_connected": "true", "transfers_ready": 1})
    assert bridge._device_command_queue_reason() is not None
    assert bridge._mochad_diagnostics.usb_connected is None


def test_unchanged_health_does_not_republish_discovery():
    bridge = make_bridge()
    with patch.object(bridge, "_save_discovery_registry"):
        bridge._on_mochad_line(health(True))
        first = len(bridge.clients.mqtt.discovery_messages)
        bridge._on_mochad_line(health(True))
    assert first > 0
    assert len(bridge.clients.mqtt.discovery_messages) == first


def test_replayable_startup_status_is_not_counted_as_a_lost_event():
    bridge = make_bridge()
    bridge.clients.mqtt.connected = False
    bridge.execute_action(PublishAvailabilityAction(False))
    bridge.execute_action(PublishStatusAction("offline", False, False))
    assert bridge._dropped_mqtt_publishes == 0


def test_timestamp_includes_milliseconds_and_timezone_offset():
    record = logging.LogRecord("bridge", logging.INFO, __file__, 1, "ready", (), None)
    formatted = TimestampFormatter(LOG_FORMAT).format(record)
    timestamp = datetime.fromisoformat(formatted.split(" ")[0])
    assert timestamp.tzinfo is not None
    assert "bridge [INFO]: ready" in formatted
