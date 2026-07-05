import unittest

from topics import Topics


class TopicTests(unittest.TestCase):
    def test_bridge_command_and_response_topics(self):
        self.assertEqual(
            Topics.bridge_command(),
            "x10/bridge/command",
        )
        self.assertEqual(
            Topics.bridge_command_filter(),
            "x10/bridge/command",
        )
        self.assertEqual(
            Topics.bridge_response(),
            "x10/bridge/response",
        )

    def test_bridge_command_parser_accepts_only_central_topic(self):
        self.assertIsNone(
            Topics.parse_bridge_command_topic("x10/bridge/command")
        )

        with self.assertRaises(ValueError):
            Topics.parse_bridge_command_topic(
                "x10/bridge/prune_entities/command"
            )


if __name__ == "__main__":
    unittest.main()
