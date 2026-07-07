import unittest

from mochad_client import MochadClient


class FakeSocket:
    def __init__(self):
        self.sent = []

    def sendall(self, data):
        self.sent.append(data)


class MochadClientTests(unittest.TestCase):
    def test_defaults_to_main_newline_delimited_listener(self):
        client = MochadClient(host="mochad")

        self.assertEqual(client.port, 1099)

    def test_diagnostic_commands_are_sent_as_newline_delimited_lines(self):
        sock = FakeSocket()
        client = MochadClient(host="mochad")
        client._socket = sock

        for command in ("hello", "capabilities", "health"):
            client.send_line(command)

        self.assertEqual(
            sock.sent,
            [
                b"hello\n",
                b"capabilities\n",
                b"health\n",
            ],
        )
        self.assertTrue(all(b"\0" not in data for data in sock.sent))


if __name__ == "__main__":
    unittest.main()
