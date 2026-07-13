import unittest
import threading
import time

from mochad_client import MochadClient


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.timeout = None
        self.closed = False

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv(self, size):
        return b""

    def close(self):
        self.closed = True


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

    def test_connect_uses_short_timeout_and_read_timeout(self):
        sock = FakeSocket()
        seen = {}

        def factory(address, timeout):
            seen["address"] = address
            seen["timeout"] = timeout
            return sock

        client = MochadClient(
            host="mochad",
            port=1099,
            connect_timeout=1.25,
            read_timeout=0.5,
            socket_factory=factory,
        )

        client.connect()

        self.assertEqual(seen["address"], ("mochad", 1099))
        self.assertEqual(seen["timeout"], 1.25)
        self.assertEqual(sock.timeout, 0.5)
        client.disconnect()

    def test_stop_interrupts_reconnect_sleep(self):
        attempted = threading.Event()

        def factory(address, timeout):
            attempted.set()
            raise OSError("down")

        client = MochadClient(
            host="mochad",
            reconnect_delay=30.0,
            socket_factory=factory,
        )

        client.start()
        self.assertTrue(attempted.wait(timeout=1.0))
        started = time.monotonic()
        client.stop()

        self.assertLess(time.monotonic() - started, 1.0)

    def test_later_mochad_connection_after_initial_failure(self):
        attempted = threading.Event()
        connected = threading.Event()
        calls = {"count": 0}

        def factory(address, timeout):
            calls["count"] += 1
            attempted.set()
            if calls["count"] == 1:
                raise OSError("down")
            return FakeSocket()

        client = MochadClient(
            host="mochad",
            reconnect_delay=0.01,
            socket_factory=factory,
        )
        client.set_connect_callback(connected.set)

        client.start()
        self.assertTrue(attempted.wait(timeout=1.0))
        self.assertTrue(connected.wait(timeout=1.0))
        client.stop()

        self.assertGreaterEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
