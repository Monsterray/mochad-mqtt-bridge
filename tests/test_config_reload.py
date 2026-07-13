import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bridge import Bridge
from config import load_config


class FakeMqttClient:
    connected = True

    def __init__(self):
        self.discovery_messages = []
        self.status_payloads = []

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

    def publish_status(self, payload, retain=True):
        self.status_payloads.append((payload, retain))


class FakeMochadClient:
    connected = True

    def set_line_callback(self, callback):
        self.line_callback = callback

    def set_connect_callback(self, callback):
        self.connect_callback = callback

    def set_disconnect_callback(self, callback):
        self.disconnect_callback = callback


class ConfigReloadTests(unittest.TestCase):
    def test_bridge_creates_missing_runtime_config_files(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "bridge.json"
            registry_path = Path(directory) / "discovery_registry.json"

            with patch.dict(
                os.environ,
                {
                    "BRIDGE_CONFIG_FILE": str(config_path),
                    "DISCOVERY_REGISTRY_PATH": str(registry_path),
                    "X10_DEVICES": "A1:Living Room Lamp:light:2:150",
                },
                clear=True,
            ):
                config = load_config()
                Bridge(
                    config,
                    mqtt_client=FakeMqttClient(),
                    mochad_client=FakeMochadClient(),
                )

            bridge_config = json.loads(
                config_path.read_text(encoding="utf-8")
            )
            registry = json.loads(
                registry_path.read_text(encoding="utf-8")
            )

        self.assertEqual(
            bridge_config["devices"][0]["address"],
            "A1",
        )
        self.assertEqual(
            bridge_config["devices"][0]["command_repeats"],
            2,
        )
        self.assertEqual(registry, {"topics": [], "version": 1})

    def test_bridge_reloads_config_file_and_republishes_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "bridge.json"
            registry_path = Path(directory) / "discovery_registry.json"
            config_path.write_text(
                json.dumps(
                    {
                        "use_friendly_names": True,
                        "devices": [
                            {
                                "address": "A1",
                                "name": "Living Room Lamp",
                                "type": "light",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "BRIDGE_CONFIG_FILE": str(config_path),
                    "DISCOVERY_REGISTRY_PATH": str(registry_path),
                },
                clear=True,
            ):
                config = load_config()
                mqtt = FakeMqttClient()
                bridge = Bridge(
                    config,
                    mqtt_client=mqtt,
                    mochad_client=FakeMochadClient(),
                )

                self.assertEqual(
                    bridge.devices["A1"].name,
                    "Living Room Lamp",
                )

                config_path.write_text(
                    json.dumps(
                        {
                            "use_friendly_names": False,
                            "devices": [
                                {
                                    "address": "A1",
                                    "name": "Living Room Lamp",
                                    "type": "light",
                                },
                                {
                                    "address": "A2",
                                    "name": "Coffee Maker",
                                    "type": "switch",
                                },
                            ],
                        }
                    ),
                    encoding="utf-8",
                )

                bridge._check_config_file_reload(force=True)

        self.assertEqual(bridge.devices["A1"].name, "A1")
        self.assertEqual(bridge.devices["A2"].name, "A2")
        self.assertTrue(mqtt.discovery_messages)
        device_names = {
            message.payload["unique_id"]: message.payload["name"]
            for message in mqtt.discovery_messages
            if isinstance(message.payload, dict)
            and str(message.payload.get("unique_id", "")).startswith("x10_")
        }
        self.assertEqual(
            device_names,
            {
                "x10_A1": "A1",
                "x10_A2": "A2",
            },
        )
        self.assertTrue(mqtt.status_payloads)


if __name__ == "__main__":
    unittest.main()
