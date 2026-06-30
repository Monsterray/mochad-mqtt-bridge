"""
Home Assistant MQTT discovery payload generation.

DiscoveryManager is pure and deterministic. It builds discovery messages from
device configuration and never publishes MQTT or modifies runtime state.
"""

from __future__ import annotations

from models import DeviceConfig, DiscoveryMessage, DeviceType
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
    ) -> None:
        self.discovery_prefix = discovery_prefix
        self.base_topic = base_topic
        # Deprecated: kept for compatibility, but Topics always uses stable
        # address-based MQTT device topics.
        self.friendly_topics = friendly_topics
        self.support_url = support_url

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
