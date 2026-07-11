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
