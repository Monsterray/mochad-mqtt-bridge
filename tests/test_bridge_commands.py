import unittest

from bridge import Bridge
from models import BridgeCommand


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


if __name__ == "__main__":
    unittest.main()
