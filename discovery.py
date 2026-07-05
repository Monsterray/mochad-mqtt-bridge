"""
Home Assistant MQTT discovery payload generation.

DiscoveryManager is pure and deterministic. It builds discovery messages from
device configuration and never publishes MQTT or modifies runtime state.
"""

from __future__ import annotations

from models import BridgeCommand, DeviceConfig, DiscoveryMessage, DeviceType
from topics import TopicError, Topics
from version import BRIDGE_AUTHOR, BRIDGE_VERSION


BRIDGE_DEVICE_IDENTIFIER = "mqtt_mochad_bridge"
BRIDGE_DISPLAY_NAME = "MQTT Mochad Bridge"
BRIDGE_MODEL = "CM19A MQTT Bridge"
DEFAULT_SUPPORT_URL = "https://github.com/"


class DiscoveryError(ValueError):
    """Raised when discovery data cannot be generated safely."""


class DiscoveryManager:
    """
    Generate Home Assistant MQTT discovery messages.
    """

    def __init__(
        self,
        discovery_prefix: str,
        base_topic: str = "x10",
        friendly_topics: bool = False,
        support_url: str = DEFAULT_SUPPORT_URL,
        enable_maintenance_buttons: bool = False,
    ) -> None:
        self.discovery_prefix = discovery_prefix
        self.base_topic = base_topic
        # Deprecated: kept for compatibility, but Topics always uses stable
        # address-based MQTT device topics.
        self.friendly_topics = friendly_topics
        self.support_url = support_url
        self.enable_maintenance_buttons = enable_maintenance_buttons

    def discovery_messages(
        self,
        device: DeviceConfig,
    ) -> list[DiscoveryMessage]:
        self._validate_device(device)

        payload = self._payload(device)
        message = DiscoveryMessage(
            topic=Topics.discovery(
                device,
                discovery_prefix=self.discovery_prefix,
            ),
            payload=payload,
            retain=True,
        )
        self._validate_message(message)

        return [message]

    def bridge_diagnostic_messages(self) -> list[DiscoveryMessage]:
        messages = [
            self._bridge_status_sensor_message(),
            self._bridge_connectivity_sensor_message(
                object_id="mqtt_mochad_bridge_mqtt_connected",
                name="MQTT Connected",
                value_key="mqtt_connected",
            ),
            self._bridge_connectivity_sensor_message(
                object_id="mqtt_mochad_bridge_mochad_connected",
                name="Mochad Connected",
                value_key="mochad_connected",
            ),
            self._bridge_command_button_message(
                command=BridgeCommand.SYNC,
                object_id="mqtt_mochad_bridge_sync",
                name="Sync X10 Status",
            ),
            self._bridge_command_button_message(
                command=BridgeCommand.REDISCOVER,
                object_id="mqtt_mochad_bridge_rediscover",
                name="Rediscover X10 Entities",
            ),
        ]

        if self.enable_maintenance_buttons:
            messages.extend(
                [
                    self._bridge_command_button_message(
                        command=BridgeCommand.PRUNE_DISCOVERY,
                        object_id="mqtt_mochad_bridge_prune_discovery",
                        name="Prune Discovery",
                    ),
                    self._bridge_command_button_message(
                        command=BridgeCommand.RESET_DISCOVERY,
                        object_id="mqtt_mochad_bridge_reset_discovery",
                        name="Reset Discovery",
                    ),
                ]
            )

        for message in messages:
            self._validate_bridge_message(message)

        return messages

    def _payload(
        self,
        device: DeviceConfig,
    ) -> dict:
        return {
            "name": device.name,
            "unique_id": Topics.unique_id(device),
            "state_topic": Topics.state(
                device,
                base_topic=self.base_topic,
                friendly_topics=self.friendly_topics,
            ),
            "command_topic": Topics.command(
                device,
                base_topic=self.base_topic,
                friendly_topics=self.friendly_topics,
            ),
            "availability_topic": Topics.availability(
                base_topic=self.base_topic,
            ),
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": self._device_block(),
            "origin": self._origin_block(),
        }

    def _bridge_status_sensor_message(self) -> DiscoveryMessage:
        return DiscoveryMessage(
            topic=Topics.bridge_discovery(
                "sensor",
                "mqtt_mochad_bridge_status",
                discovery_prefix=self.discovery_prefix,
            ),
            payload={
                "name": "Bridge Status",
                "unique_id": "mqtt_mochad_bridge_status",
                "state_topic": Topics.status(
                    base_topic=self.base_topic,
                ),
                "value_template": "{{ value_json.status }}",
                "availability_topic": Topics.availability(
                    base_topic=self.base_topic,
                ),
                "entity_category": "diagnostic",
                "device": self._device_block(),
                "origin": self._origin_block(),
            },
            retain=True,
        )

    def _bridge_connectivity_sensor_message(
        self,
        object_id: str,
        name: str,
        value_key: str,
    ) -> DiscoveryMessage:
        return DiscoveryMessage(
            topic=Topics.bridge_discovery(
                "binary_sensor",
                object_id,
                discovery_prefix=self.discovery_prefix,
            ),
            payload={
                "name": name,
                "unique_id": object_id,
                "state_topic": Topics.status(
                    base_topic=self.base_topic,
                ),
                "value_template": (
                    "{{ 'ON' if value_json."
                    + value_key
                    + " else 'OFF' }}"
                ),
                "payload_on": "ON",
                "payload_off": "OFF",
                "device_class": "connectivity",
                "availability_topic": Topics.availability(
                    base_topic=self.base_topic,
                ),
                "entity_category": "diagnostic",
                "device": self._device_block(),
                "origin": self._origin_block(),
            },
            retain=True,
        )

    def _bridge_command_button_message(
        self,
        command: BridgeCommand,
        object_id: str,
        name: str,
    ) -> DiscoveryMessage:
        return DiscoveryMessage(
            topic=Topics.bridge_discovery(
                "button",
                object_id,
                discovery_prefix=self.discovery_prefix,
            ),
            payload={
                "name": name,
                "unique_id": object_id,
                "command_topic": Topics.bridge_command(
                    base_topic=self.base_topic,
                ),
                "payload_press": command.name,
                "availability_topic": Topics.availability(
                    base_topic=self.base_topic,
                ),
                "entity_category": "diagnostic",
                "device": self._device_block(),
                "origin": self._origin_block(),
            },
            retain=True,
        )

    def _device_block(self) -> dict:
        return {
            "identifiers": [
                BRIDGE_DEVICE_IDENTIFIER,
            ],
            "name": BRIDGE_DISPLAY_NAME,
            "manufacturer": BRIDGE_AUTHOR,
            "model": BRIDGE_MODEL,
            "sw_version": BRIDGE_VERSION,
        }

    def _origin_block(self) -> dict:
        return {
            "name": BRIDGE_DISPLAY_NAME,
            "sw_version": BRIDGE_VERSION,
            "support_url": self.support_url,
        }

    def _validate_device(
        self,
        device: DeviceConfig,
    ) -> None:
        if device.entity_type not in {
            DeviceType.LIGHT,
            DeviceType.SWITCH,
        }:
            raise DiscoveryError(
                f"Unsupported entity type {device.entity_type}."
            )

        if not device.name.strip():
            raise DiscoveryError(
                f"Device {device.address} must have a display name."
            )

        try:
            Topics.unique_id(device)
        except TopicError as exc:
            raise DiscoveryError(str(exc)) from exc

    def _validate_message(
        self,
        message: DiscoveryMessage,
    ) -> None:
        required_payload_fields = {
            "name",
            "unique_id",
            "state_topic",
            "command_topic",
            "availability_topic",
            "payload_on",
            "payload_off",
            "device",
            "origin",
        }

        missing = required_payload_fields - set(message.payload)

        if missing:
            raise DiscoveryError(
                "Discovery payload missing required fields: "
                + ", ".join(sorted(missing))
            )

        if not message.topic:
            raise DiscoveryError("Discovery topic cannot be empty.")

        if not message.payload["unique_id"]:
            raise DiscoveryError("Discovery unique_id cannot be empty.")

        if not message.payload["state_topic"]:
            raise DiscoveryError("Discovery state_topic cannot be empty.")

        if not message.payload["command_topic"]:
            raise DiscoveryError("Discovery command_topic cannot be empty.")

        if not message.payload["availability_topic"]:
            raise DiscoveryError(
                "Discovery availability_topic cannot be empty."
            )

        device_block = message.payload["device"]

        for key in {
            "identifiers",
            "name",
            "manufacturer",
            "model",
            "sw_version",
        }:
            if key not in device_block:
                raise DiscoveryError(
                    f"Discovery device block missing {key}."
                )

    def _validate_bridge_message(
        self,
        message: DiscoveryMessage,
    ) -> None:
        if not message.topic:
            raise DiscoveryError("Bridge discovery topic cannot be empty.")

        if not isinstance(message.payload, dict):
            raise DiscoveryError("Bridge discovery payload must be a dict.")

        for key in {
            "name",
            "unique_id",
            "availability_topic",
            "device",
            "origin",
        }:
            if key not in message.payload:
                raise DiscoveryError(
                    f"Bridge discovery payload missing {key}."
                )

        if (
            "state_topic" not in message.payload
            and "command_topic" not in message.payload
        ):
            raise DiscoveryError(
                "Bridge discovery payload must include a state or command topic."
            )
