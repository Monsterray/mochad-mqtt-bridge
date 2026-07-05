import unittest

from discovery import DiscoveryManager


class DiscoveryButtonTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
