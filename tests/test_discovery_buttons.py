import unittest

from discovery import DiscoveryManager
from models import DeviceConfig, DeviceType, MochadDiagnostics


class DiscoveryButtonTests(unittest.TestCase):
    def test_chime_device_discovers_as_button(self):
        message = DiscoveryManager(
            discovery_prefix="homeassistant",
            base_topic="x10",
        ).discovery_messages(
            DeviceConfig(
                address="A2",
                name="Door Chime",
                entity_type=DeviceType.CHIME,
            )
        )[0]

        self.assertEqual(
            message.topic,
            "homeassistant/button/x10_A2/config",
        )
        self.assertEqual(message.payload["name"], "Door Chime")
        self.assertEqual(message.payload["unique_id"], "x10_A2")
        self.assertEqual(
            message.payload["default_entity_id"],
            "button.x10_a2",
        )
        self.assertEqual(
            message.payload["command_topic"],
            "x10/A2/command",
        )
        self.assertEqual(message.payload["payload_press"], "ON")
        self.assertNotIn("state_topic", message.payload)
        self.assertNotIn("payload_off", message.payload)
        self.assertEqual(
            message.payload["device"]["identifiers"],
            ["mqtt_mochad_bridge"],
        )

    def test_safe_bridge_buttons_are_discovered_by_default(self):
        messages = DiscoveryManager(
            discovery_prefix="homeassistant",
            base_topic="x10",
        ).bridge_diagnostic_messages()

        buttons = {
            message.payload["payload_press"]: message.payload
            for message in messages
            if message.topic.startswith("homeassistant/button/")
        }

        self.assertEqual(
            buttons["SYNC"]["command_topic"],
            "x10/bridge/command",
        )
        self.assertEqual(
            buttons["REDISCOVER"]["command_topic"],
            "x10/bridge/command",
        )
        self.assertNotIn("RESET_DISCOVERY", buttons)

    def test_maintenance_buttons_are_opt_in(self):
        messages = DiscoveryManager(
            discovery_prefix="homeassistant",
            base_topic="x10",
            enable_maintenance_buttons=True,
        ).bridge_diagnostic_messages()

        button_payloads = {
            message.payload["payload_press"]
            for message in messages
            if message.topic.startswith("homeassistant/button/")
        }

        self.assertIn("PRUNE_DISCOVERY", button_payloads)
        self.assertIn("RESET_DISCOVERY", button_payloads)

    def test_bridge_buttons_have_stable_default_entity_ids(self):
        messages = DiscoveryManager(
            discovery_prefix="homeassistant",
            base_topic="x10",
        ).bridge_diagnostic_messages()

        buttons = {
            message.payload["payload_press"]: message.payload
            for message in messages
            if message.topic.startswith("homeassistant/button/")
        }

        self.assertEqual(
            buttons["SYNC"]["default_entity_id"],
            "button.mqtt_mochad_bridge_sync",
        )
        self.assertEqual(
            buttons["REDISCOVER"]["default_entity_id"],
            "button.mqtt_mochad_bridge_rediscover",
        )

    def test_minimal_bridge_diagnostics_are_discovered(self):
        messages = DiscoveryManager(
            discovery_prefix="homeassistant",
            base_topic="x10",
        ).bridge_diagnostic_messages()

        topics = {message.topic for message in messages}

        self.assertIn(
            "homeassistant/sensor/mqtt_mochad_bridge_status/config",
            topics,
        )
        self.assertIn(
            "homeassistant/binary_sensor/mqtt_mochad_bridge_mochad_connected/config",
            topics,
        )
        self.assertIn(
            "homeassistant/binary_sensor/mqtt_mochad_bridge_usb_connected/config",
            topics,
        )
        self.assertIn(
            "homeassistant/sensor/mqtt_mochad_bridge_controller/config",
            topics,
        )
        self.assertIn(
            "homeassistant/sensor/mqtt_mochad_bridge_mochad_version/config",
            topics,
        )
        self.assertNotIn(
            "homeassistant/binary_sensor/mqtt_mochad_bridge_mqtt_connected/config",
            topics,
        )

        for message in messages:
            self.assertEqual(
                message.payload["entity_category"],
                "diagnostic",
            )
            self.assertNotIn("object_id", message.payload)
            self.assertIn("default_entity_id", message.payload)

    def test_mochad_diagnostics_enrich_device_metadata(self):
        diagnostics = MochadDiagnostics(
            daemon="mochad-redux",
            version="0.4.0",
            upstream_base="mochad 0.1.18",
            diagnostics=True,
            json=True,
            single_line=True,
            raw_data=False,
            controller="CM19A",
            endpoints_ready=True,
            transfers_ready=True,
        )
        message = DiscoveryManager(
            discovery_prefix="homeassistant",
            base_topic="x10",
        ).discovery_messages(
            DeviceConfig(
                address="A1",
                name="Living Room Lamp",
                entity_type=DeviceType.LIGHT,
            ),
            diagnostics,
        )[0]

        device = message.payload["device"]
        origin = message.payload["origin"]

        self.assertEqual(message.payload["default_entity_id"], "light.x10_a1")
        self.assertEqual(device["model"], "CM19A MQTT Bridge")
        self.assertEqual(device["model_id"], "mochad-redux")
        self.assertIn("mochad-redux 0.4.0", device["sw_version"])
        self.assertEqual(device["hw_version"], "CM19A")
        self.assertIn("mochad 0.4.0", origin["sw_version"])
        self.assertNotIn("object_id", message.payload)


if __name__ == "__main__":
    unittest.main()
