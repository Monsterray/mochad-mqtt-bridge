import unittest
from unittest.mock import patch

from bridge import Bridge
from config import Config, MqttTlsConfig
from mqtt_client import MqttCommandMessage
from models import BridgeCommand, DeviceConfig, DeviceType


class FakeMqttClient:
    connected = True

    def __init__(self):
        self.discovery_messages = []
        self.states = []
        self.attributes = []
        self.events = []

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

    def publish_attributes(self, device, payload, retain=True):
        self.attributes.append((device, payload, retain))

    def publish_event(self, device, payload, retain=False):
        self.events.append((device, payload, retain))


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
        self.assertEqual(mqtt.attributes[-1][0], "A1")
        self.assertEqual(
            mqtt.attributes[-1][1]["last_command_sent"],
            "ON",
        )
        self.assertTrue(mqtt.attributes[-1][1]["optimistic"])

    def test_repeats_on_off_commands_for_configured_device(self):
        mqtt = FakeMqttClient()
        mochad = FakeMochadClient()
        bridge = Bridge(
            minimal_config(
                devices={
                    "A1": DeviceConfig(
                        address="A1",
                        name="Lamp",
                        entity_type=DeviceType.LIGHT,
                        command_repeats=3,
                        command_repeat_delay_ms=150,
                    )
                }
            ),
            mqtt_client=mqtt,
            mochad_client=mochad,
        )

        with patch("bridge.time.sleep") as sleep:
            bridge._on_mqtt_command(
                MqttCommandMessage(
                    device="A1",
                    payload="OFF",
                    topic="x10/A1/command",
                )
            )

        self.assertEqual(
            mochad.sent_lines,
            [
                "rf A1 off",
                "rf A1 off",
                "rf A1 off",
            ],
        )
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(0.15)

    def test_does_not_repeat_dim_or_bright_commands(self):
        mqtt = FakeMqttClient()
        mochad = FakeMochadClient()
        bridge = Bridge(
            minimal_config(
                devices={
                    "A1": DeviceConfig(
                        address="A1",
                        name="Lamp",
                        entity_type=DeviceType.LIGHT,
                        command_repeats=3,
                        command_repeat_delay_ms=150,
                    )
                }
            ),
            mqtt_client=mqtt,
            mochad_client=mochad,
        )

        with patch("bridge.time.sleep") as sleep:
            bridge._on_mqtt_command(
                MqttCommandMessage(
                    device="A1",
                    payload="DIM",
                    topic="x10/A1/command",
                )
            )

        self.assertEqual(mochad.sent_lines, ["rf A1 dim"])
        sleep.assert_not_called()

    def test_chime_repeated_on_commands_each_reach_mochad(self):
        mqtt = FakeMqttClient()
        mochad = FakeMochadClient()
        bridge = Bridge(
            minimal_config(
                devices={
                    "A2": DeviceConfig(
                        address="A2",
                        name="Door Chime",
                        entity_type=DeviceType.CHIME,
                    )
                }
            ),
            mqtt_client=mqtt,
            mochad_client=mochad,
        )

        for _ in range(2):
            bridge._on_mqtt_command(
                MqttCommandMessage(
                    device="A2",
                    payload="ON",
                    topic="x10/A2/command",
                )
            )

        self.assertEqual(mochad.sent_lines, ["rf A2 on", "rf A2 on"])
        self.assertEqual(mqtt.states, [])
        self.assertEqual(mqtt.attributes, [])
        self.assertEqual(len(mqtt.events), 2)
        self.assertEqual(mqtt.events[0][0], "A2")
        self.assertFalse(mqtt.events[0][2])
        self.assertEqual(
            mqtt.events[0][1]["transmission"],
            "unconfirmed",
        )
        self.assertFalse(mqtt.events[0][1]["confirmed"])

    def test_chime_rejects_non_on_commands(self):
        mqtt = FakeMqttClient()
        mochad = FakeMochadClient()
        bridge = Bridge(
            minimal_config(
                devices={
                    "A2": DeviceConfig(
                        address="A2",
                        name="Door Chime",
                        entity_type=DeviceType.CHIME,
                    )
                }
            ),
            mqtt_client=mqtt,
            mochad_client=mochad,
        )

        for payload in ("OFF", "DIM", "BRIGHT"):
            bridge._on_mqtt_command(
                MqttCommandMessage(
                    device="A2",
                    payload=payload,
                    topic="x10/A2/command",
                )
            )

        self.assertEqual(mochad.sent_lines, [])
        self.assertEqual(mqtt.states, [])
        self.assertEqual(mqtt.events, [])

    def test_chime_mochad_echo_does_not_publish_state(self):
        mqtt = FakeMqttClient()
        bridge = Bridge(
            minimal_config(
                devices={
                    "A2": DeviceConfig(
                        address="A2",
                        name="Door Chime",
                        entity_type=DeviceType.CHIME,
                    )
                }
            ),
            mqtt_client=mqtt,
            mochad_client=FakeMochadClient(),
        )

        bridge._on_mochad_line(
            "07/10 15:28:31 Tx RF HouseUnit: A2 Func: On"
        )

        self.assertEqual(mqtt.states, [])
        self.assertEqual(len(mqtt.events), 1)
        self.assertEqual(mqtt.events[0][0], "A2")

if __name__ == "__main__":
    unittest.main()
