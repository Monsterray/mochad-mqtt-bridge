"""
Central MQTT topic construction.

All MQTT topic strings should be built here so the bridge has one consistent
namespace and topic changes stay localized.
"""

from __future__ import annotations

import re

from models import DeviceConfig, DeviceType


DEFAULT_BASE_TOPIC = "x10"
DEFAULT_DISCOVERY_PREFIX = "homeassistant"


class TopicError(ValueError):
    """Raised when a topic cannot be constructed safely."""


class Topics:
    """
    Central MQTT topic helper.
    """

    @staticmethod
    def state(
        device: DeviceConfig | str,
        base_topic: str = DEFAULT_BASE_TOPIC,
        friendly_topics: bool = False,
    ) -> str:
        return Topics.device_topic(
            device,
            "state",
            base_topic=base_topic,
            friendly_topics=friendly_topics,
        )

    @staticmethod
    def command(
        device: DeviceConfig | str,
        base_topic: str = DEFAULT_BASE_TOPIC,
        friendly_topics: bool = False,
    ) -> str:
        return Topics.device_topic(
            device,
            "command",
            base_topic=base_topic,
            friendly_topics=friendly_topics,
        )

    @staticmethod
    def command_filter(
        base_topic: str = DEFAULT_BASE_TOPIC,
    ) -> str:
        return "/".join(
            [
                Topics._clean_segment(base_topic),
                "+",
                "command",
            ]
        )

    @staticmethod
    def event(
        device: DeviceConfig | str,
        base_topic: str = DEFAULT_BASE_TOPIC,
        friendly_topics: bool = False,
    ) -> str:
        return Topics.device_topic(
            device,
            "event",
            base_topic=base_topic,
            friendly_topics=friendly_topics,
        )

    @staticmethod
    def availability(
        device: DeviceConfig | str | None = None,
        base_topic: str = DEFAULT_BASE_TOPIC,
    ) -> str:
        return Topics.bridge_topic("availability", base_topic)

    @staticmethod
    def status(
        base_topic: str = DEFAULT_BASE_TOPIC,
    ) -> str:
        return Topics.bridge_topic("status", base_topic)

    @staticmethod
    def bridge_topic(
        suffix: str,
        base_topic: str = DEFAULT_BASE_TOPIC,
    ) -> str:
        return "/".join(
            [
                Topics._clean_segment(base_topic),
                "bridge",
                Topics._clean_segment(suffix),
            ]
        )

    @staticmethod
    def attributes(
        device: DeviceConfig | str,
        base_topic: str = DEFAULT_BASE_TOPIC,
        friendly_topics: bool = False,
    ) -> str:
        return Topics.device_topic(
            device,
            "attributes",
            base_topic=base_topic,
            friendly_topics=friendly_topics,
        )

    @staticmethod
    def discovery(
        device: DeviceConfig,
        discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX,
    ) -> str:
        return "/".join(
            [
                Topics._clean_segment(discovery_prefix),
                Topics.entity_type(device),
                Topics.unique_id(device),
                "config",
            ]
        )

    @staticmethod
    def device_topic(
        device: DeviceConfig | str,
        suffix: str,
        base_topic: str = DEFAULT_BASE_TOPIC,
        friendly_topics: bool = False,
    ) -> str:
        return "/".join(
            [
                Topics._clean_segment(base_topic),
                Topics.device_segment(
                    device,
                    friendly_topics=friendly_topics,
                ),
                Topics._clean_segment(suffix),
            ]
        )

    @staticmethod
    def parse_command_topic(
        topic: str,
        base_topic: str = DEFAULT_BASE_TOPIC,
    ) -> str:
        base = Topics._clean_segment(base_topic)
        parts = topic.strip("/").split("/")

        if len(parts) != 3:
            raise TopicError(
                f"Invalid command topic '{topic}'."
            )

        if parts[0] != base or parts[2] != "command":
            raise TopicError(
                f"Invalid command topic '{topic}'."
            )

        return parts[1]

    @staticmethod
    def unique_id(device: DeviceConfig) -> str:
        address = Topics._address(device)
        return f"x10_{address}"

    @staticmethod
    def entity_type(device: DeviceConfig) -> str:
        if device.entity_type == DeviceType.LIGHT:
            return "light"

        if device.entity_type == DeviceType.SWITCH:
            return "switch"

        raise TopicError(
            f"Unsupported Home Assistant entity type {device.entity_type}."
        )

    @staticmethod
    def device_segment(
        device: DeviceConfig | str,
        friendly_topics: bool = False,
    ) -> str:
        # Deprecated: friendly_topics is intentionally ignored. MQTT device
        # identity must remain address-based even when display names change.
        return Topics._address(device)

    @staticmethod
    def _address(device: DeviceConfig | str) -> str:
        if isinstance(device, DeviceConfig):
            address = device.address
        else:
            address = device

        address = address.strip().upper()

        if not re.fullmatch(r"[A-P](?:[1-9]|1[0-6])", address):
            raise TopicError(
                f"Invalid X10 device address '{address}'."
            )

        return address

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
        slug = slug.strip("_")

        if not slug:
            raise TopicError("Friendly topic segment cannot be empty.")

        return slug

    @staticmethod
    def _clean_segment(value: str) -> str:
        value = value.strip().strip("/")

        if not value:
            raise TopicError("MQTT topic segment cannot be empty.")

        if "#" in value or "+" in value:
            raise TopicError(
                f"MQTT topic segment '{value}' cannot contain wildcards."
            )

        return value
