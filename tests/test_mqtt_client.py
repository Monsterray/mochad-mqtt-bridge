import unittest

from mqtt_client import MqttClient


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload


class FakePahoClient:
    def __init__(self):
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.subscriptions = []

    def username_pw_set(self, username, password=None):
        pass

    def will_set(self, topic, payload=None, qos=0, retain=False):
        pass

    def connect(self, host, port=1883, keepalive=60):
        pass

    def disconnect(self):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def publish(self, topic, payload=None, qos=0, retain=False):
        pass

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))


class MqttClientRoutingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
