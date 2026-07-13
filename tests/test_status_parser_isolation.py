import unittest

from bridge import Bridge
from config import Config, MqttTlsConfig
from models import Command, DeviceEvent, StatusSnapshot, UnknownEvent
from protocol import ProtocolParser


class FakeMqttClient:
    connected = True

    def __init__(self):
        self.events = []
        self.states = []
        self.status_payloads = []

    def set_command_callback(self, callback):
        self.command_callback = callback

    def set_bridge_command_callback(self, callback):
        self.bridge_command_callback = callback

    def set_connect_callback(self, callback):
        self.connect_callback = callback

    def set_disconnect_callback(self, callback):
        self.disconnect_callback = callback

    def publish_event(self, device, payload, retain=False):
        self.events.append((device, payload, retain))

    def publish_state(self, device, state, retain=True):
        self.states.append((device, state, retain))

    def publish_attributes(self, device, payload, retain=True):
        pass

    def publish_discovery(self, message):
        pass

    def publish_availability(self, online, retain=True, qos=0, wait=False):
        pass

    def publish_status(self, payload, retain=True, qos=0, wait=False):
        self.status_payloads.append((payload, retain, qos, wait))


class FakeMochadClient:
    connected = True

    def set_line_callback(self, callback):
        self.line_callback = callback

    def set_connect_callback(self, callback):
        self.connect_callback = callback

    def set_disconnect_callback(self, callback):
        self.disconnect_callback = callback

    def send_line(self, line):
        pass


def minimal_config() -> Config:
    return Config(
        mochad_host="mochad",
        mochad_port=1099,
        mqtt_host="mosquitto",
        mqtt_port=1883,
        mqtt_username=None,
        mqtt_password=None,
        mqtt_tls=MqttTlsConfig(),
        mqtt_base_topic="x10",
        mqtt_discovery_prefix="homeassistant",
        log_level="INFO",
    )


class ProtocolStatusIsolationTests(unittest.TestCase):
    def test_rf_event_is_parsed_while_status_collection_is_active(self):
        parser = ProtocolParser()

        self.assertIsNone(parser.parse_line("07/11 12:00:00 Device selected"))
        event = parser.parse_line("07/11 12:00:01 Rx RF HouseUnit: A2 Func: On")

        self.assertIsInstance(event, DeviceEvent)
        self.assertEqual(event.address, "A2")
        self.assertEqual(event.command, Command.ON)

    def test_malformed_status_like_line_becomes_unknown_not_sticky_state(self):
        parser = ProtocolParser()

        self.assertIsNone(parser.parse_line("07/11 12:00:00 Device selected"))
        unknown = parser.parse_line("07/11 12:00:01 House A: not-valid")
        event = parser.parse_line("07/11 12:00:02 Rx RF HouseUnit: A3 Func: Off")

        self.assertIsInstance(unknown, UnknownEvent)
        self.assertIsInstance(event, DeviceEvent)
        self.assertEqual(event.address, "A3")
        self.assertEqual(event.command, Command.OFF)

    def test_interleaved_status_and_rf_event_complete_independently(self):
        parser = ProtocolParser()

        lines = [
            "07/11 12:00:00 Device selected",
            "07/11 12:00:00 Device status",
            "07/11 12:00:00 House A: 2",
            "07/11 12:00:01 House A: 1=1,2=0",
            "07/11 12:00:02 Rx RF HouseUnit: A4 Func: On",
            "07/11 12:00:03 End status",
        ]
        parsed = [parser.parse_line(line) for line in lines]

        events = [item for item in parsed if isinstance(item, DeviceEvent)]
        snapshots = [item for item in parsed if isinstance(item, StatusSnapshot)]

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].address, "A4")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(
            snapshots[0].devices,
            {
                "A1": Command.ON,
                "A2": Command.OFF,
            },
        )

    def test_later_status_start_recovers_after_interrupted_status(self):
        parser = ProtocolParser()

        self.assertIsNone(parser.parse_line("07/11 12:00:00 Device selected"))
        self.assertIsNone(parser.parse_line("07/11 12:00:01 House A: 1=1"))
        event = parser.parse_line("07/11 12:00:02 Rx RF HouseUnit: A5 Func: On")
        self.assertIsInstance(event, DeviceEvent)

        self.assertIsNone(parser.parse_line("07/11 12:01:00 Device selected"))
        self.assertIsNone(parser.parse_line("07/11 12:01:01 House B: 3=1"))
        snapshot = parser.parse_line("07/11 12:01:02 End status")

        self.assertIsInstance(snapshot, StatusSnapshot)
        self.assertEqual(snapshot.devices, {"B3": Command.ON})


class BridgeStatusIsolationTests(unittest.TestCase):
    def test_bridge_publishes_interleaved_rf_event_exactly_once(self):
        mqtt = FakeMqttClient()
        bridge = Bridge(
            minimal_config(),
            mqtt_client=mqtt,
            mochad_client=FakeMochadClient(),
        )

        for line in (
            "07/11 12:00:00 Device selected",
            "07/11 12:00:00 Device status",
            "07/11 12:00:01 House A: 1=1",
            "07/11 12:00:02 Rx RF HouseUnit: A2 Func: On",
            "07/11 12:00:03 End status",
            "07/11 12:00:04 Rx RF HouseUnit: A2 Func: Off",
        ):
            bridge._on_mochad_line(line)

        self.assertEqual(
            [event[1]["command"] for event in mqtt.events],
            ["ON", "OFF"],
        )
        self.assertEqual(len(mqtt.events), 2)

    def test_bridge_continues_after_malformed_interrupted_status(self):
        mqtt = FakeMqttClient()
        bridge = Bridge(
            minimal_config(),
            mqtt_client=mqtt,
            mochad_client=FakeMochadClient(),
        )

        for line in (
            "07/11 12:00:00 Device selected",
            "07/11 12:00:01 House A: broken",
            "07/11 12:00:02 Rx RF HouseUnit: A6 Func: On",
            "07/11 12:00:03 Rx RF HouseUnit: A6 Func: Off",
        ):
            bridge._on_mochad_line(line)

        self.assertEqual(
            [event[1]["command"] for event in mqtt.events],
            ["ON", "OFF"],
        )
        self.assertEqual(len(mqtt.events), 2)


if __name__ == "__main__":
    unittest.main()
