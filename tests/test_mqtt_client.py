import unittest

from config import MqttTlsConfig
from mqtt_client import MqttClient


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload


class FakePublishResult:
    def __init__(self, client):
        self.client = client

    def wait_for_publish(self):
        self.client.calls.append("wait_for_publish")


class FakePahoClient:
    def __init__(self):
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.subscriptions = []
        self.tls_context = None
        self.calls = []
        self.published = []

    def username_pw_set(self, username, password=None):
        pass

    def will_set(self, topic, payload=None, qos=0, retain=False):
        pass

    def tls_set_context(self, context):
        self.calls.append("tls_set_context")
        self.tls_context = context

    def connect(self, host, port=1883, keepalive=60):
        self.calls.append("connect")

    def disconnect(self):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        return FakePublishResult(self)

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))


class AsyncFakePahoClient(FakePahoClient):
    def __init__(self):
        super().__init__()
        self.reconnect_delay = None

    def reconnect_delay_set(self, min_delay=1, max_delay=120):
        self.calls.append("reconnect_delay_set")
        self.reconnect_delay = (min_delay, max_delay)

    def connect_async(self, host, port=1883, keepalive=60):
        self.calls.append("connect_async")
        self.connect_args = (host, port, keepalive)

    def loop_start(self):
        self.calls.append("loop_start")


class FailingFakePahoClient(FakePahoClient):
    def connect(self, host, port=1883, keepalive=60):
        self.calls.append("connect")
        raise OSError("broker down")

    def loop_start(self):
        self.calls.append("loop_start")


class MqttClientRoutingTests(unittest.TestCase):
    def test_device_command_topic_routes_to_device_callback(self):
        fake = FakePahoClient()
        client = MqttClient(
            host="mosquitto",
            client_factory=lambda client_id: fake,
        )
        device_messages = []
        bridge_messages = []
        client.set_command_callback(device_messages.append)
        client.set_bridge_command_callback(bridge_messages.append)

        client._on_message(
            fake,
            None,
            FakeMessage("x10/A1/command", b"ON"),
        )

        self.assertEqual(len(device_messages), 1)
        self.assertEqual(device_messages[0].device, "A1")
        self.assertEqual(device_messages[0].payload, "ON")
        self.assertEqual(bridge_messages, [])

    def test_bridge_command_topic_routes_to_bridge_callback_first(self):
        fake = FakePahoClient()
        client = MqttClient(
            host="mosquitto",
            client_factory=lambda client_id: fake,
        )
        device_messages = []
        bridge_messages = []
        client.set_command_callback(device_messages.append)
        client.set_bridge_command_callback(bridge_messages.append)

        client._on_message(
            fake,
            None,
            FakeMessage("x10/bridge/command", b"STATUS"),
        )

        self.assertEqual(len(bridge_messages), 1)
        self.assertEqual(bridge_messages[0].payload, "STATUS")
        self.assertEqual(device_messages, [])

    def test_subscribes_once_to_command_wildcard(self):
        fake = FakePahoClient()
        client = MqttClient(
            host="mosquitto",
            client_factory=lambda client_id: fake,
        )

        client.subscribe_commands()

        self.assertEqual(fake.subscriptions, [("x10/+/command", 0)])

    def test_tls_context_is_installed_when_enabled(self):
        fake = FakePahoClient()
        context = object()
        tls_config = MqttTlsConfig(
            enabled=True,
            ca_file="/run/secrets/ca.crt",
        )

        MqttClient(
            host="mosquitto",
            tls_config=tls_config,
            ssl_context_factory=lambda config: context,
            client_factory=lambda client_id: fake,
        )

        self.assertIs(fake.tls_context, context)

    def test_tls_context_is_installed_before_connecting(self):
        fake = FakePahoClient()
        context = object()
        client = MqttClient(
            host="mosquitto",
            tls_config=MqttTlsConfig(enabled=True),
            ssl_context_factory=lambda config: context,
            client_factory=lambda client_id: fake,
        )

        client.connect()

        self.assertEqual(
            fake.calls,
            [
                "tls_set_context",
                "connect",
            ],
        )

    def test_tls_context_is_not_installed_by_default(self):
        fake = FakePahoClient()

        MqttClient(
            host="mosquitto",
            client_factory=lambda client_id: fake,
        )

        self.assertIsNone(fake.tls_context)

    def test_connect_prefers_async_reconnecting_startup(self):
        fake = AsyncFakePahoClient()
        client = MqttClient(
            host="mosquitto",
            reconnect_min_delay=2,
            reconnect_max_delay=10,
            client_factory=lambda client_id: fake,
        )

        client.connect()

        self.assertEqual(
            fake.calls,
            [
                "reconnect_delay_set",
                "connect_async",
                "loop_start",
            ],
        )
        self.assertEqual(fake.reconnect_delay, (2, 10))
        self.assertEqual(fake.connect_args, ("mosquitto", 1883, 60))

    def test_broker_down_startup_does_not_raise(self):
        fake = FailingFakePahoClient()
        client = MqttClient(
            host="mosquitto",
            client_factory=lambda client_id: fake,
        )

        client.connect()

        self.assertEqual(fake.calls, ["connect", "loop_start"])
        self.assertFalse(client.connected)

    def test_later_broker_appearance_restores_subscription_and_callback(self):
        fake = AsyncFakePahoClient()
        client = MqttClient(
            host="mosquitto",
            client_factory=lambda client_id: fake,
        )
        connected = []
        client.set_connect_callback(lambda: connected.append(True))
        client.connect()

        client._on_connect(fake, None, None, 0)

        self.assertTrue(client.connected)
        self.assertEqual(fake.subscriptions, [("x10/+/command", 0)])
        self.assertEqual(connected, [True])

    def test_broker_restart_marks_disconnected_then_resubscribes(self):
        fake = AsyncFakePahoClient()
        client = MqttClient(
            host="mosquitto",
            client_factory=lambda client_id: fake,
        )

        client._on_connect(fake, None, None, 0)
        self.assertTrue(client.connected)
        client._on_disconnect(fake, None, 0)
        self.assertFalse(client.connected)
        client._on_connect(fake, None, None, 0)
        self.assertTrue(client.connected)

        self.assertEqual(
            fake.subscriptions,
            [("x10/+/command", 0), ("x10/+/command", 0)],
        )

    def test_publish_can_wait_for_delivery(self):
        fake = FakePahoClient()
        client = MqttClient(
            host="mosquitto",
            client_factory=lambda client_id: fake,
        )

        client.publish_status(
            {"status": "shutdown"},
            retain=True,
            qos=1,
            wait=True,
        )

        self.assertEqual(
            fake.published,
            [("x10/bridge/status", '{"status":"shutdown"}', 1, True)],
        )
        self.assertIn("wait_for_publish", fake.calls)


if __name__ == "__main__":
    unittest.main()
