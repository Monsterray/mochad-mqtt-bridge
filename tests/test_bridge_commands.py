import unittest

from bridge import Bridge
from config import Config, MqttTlsConfig
from mqtt_client import MqttCommandMessage
from models import BridgeCommand


class FakeMqttClient:
    connected = True

    def __init__(self):
        self.discovery_messages = []
        self.states = []

    def set_command_callback(self, callback):
        self.command_callback = callback

    def set_bridge_command_callback(self, callback):
        self.bridge_command_callback = callback

    def set_connect_callback(self, callback):
        self.connect_callback = callback

    def set_disconnect_callback(self, callback):
        self.disconnect_callback = callback

    def publish_discovery(self, message):
        self.discovery_messages.append(message)

    def publish_state(self, device, state, retain=True):
        self.states.append((device, state, retain))


class FakeMochadClient:
    connected = True

    def __init__(self):
        self.sent_lines = []

    def set_line_callback(self, callback):
        self.line_callback = callback

    def set_connect_callback(self, callback):
        self.connect_callback = callback

    def set_disconnect_callback(self, callback):
        self.disconnect_callback = callback

    def send_line(self, line):
        self.sent_lines.append(line)


def minimal_config(
    devices=None,
) -> Config:
    return Config(
        mochad_host="mochad",
        mochad_port=1099,
        mqtt_host="mosquitto",
        mqtt_port=1883,
        mqtt_username=None,
        mqtt_password=None,
        mqtt_tls=MqttTlsConfig(),
        mqtt_base_topic="x10",
        mqtt_discovery_prefix="homeassistant",
        log_level="INFO",
        devices=devices or {},
    )


class BridgeCommandParsingTests(unittest.TestCase):
    def test_parses_supported_bridge_commands(self):
        self.assertEqual(
            Bridge._parse_bridge_command_payload("STATUS"),
            BridgeCommand.STATUS,
        )
        self.assertEqual(
            Bridge._parse_bridge_command_payload("sync"),
            BridgeCommand.SYNC,
        )
        self.assertEqual(
            Bridge._parse_bridge_command_payload("prune-discovery"),
            BridgeCommand.PRUNE_DISCOVERY,
        )

    def test_parses_legacy_prune_payload_alias(self):
        self.assertEqual(
            Bridge._parse_bridge_command_payload("PRUNE_ENTITIES"),
            BridgeCommand.PRUNE_DISCOVERY,
        )

    def test_rejects_unknown_bridge_command(self):
        self.assertIsNone(
            Bridge._parse_bridge_command_payload("not-a-command")
        )


class DeviceCommandRoutingTests(unittest.TestCase):
    def test_mqtt_device_command_sends_mochad_rf_command(self):
        mqtt = FakeMqttClient()
        mochad = FakeMochadClient()
        bridge = Bridge(
            minimal_config(),
            mqtt_client=mqtt,
            mochad_client=mochad,
        )

        bridge._on_mqtt_command(
            MqttCommandMessage(
                device="A1",
                payload="ON",
                topic="x10/A1/command",
            )
        )

        self.assertIn("rf A1 on", mochad.sent_lines)
        self.assertEqual(mqtt.states[-1][0], "A1")

if __name__ == "__main__":
    unittest.main()
