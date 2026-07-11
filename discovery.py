"""
Home Assistant MQTT discovery payload generation.

DiscoveryManager is pure and deterministic. It builds discovery messages from
device configuration and never publishes MQTT or modifies runtime state.
"""

from __future__ import annotations

import re

from models import (
    BridgeCommand,
    DeviceConfig,
    DiscoveryMessage,
    DeviceType,
    MochadDiagnostics,
)
from topics import TopicError, Topics
from version import BRIDGE_AUTHOR, BRIDGE_VERSION


BRIDGE_DEVICE_IDENTIFIER = "mqtt_mochad_bridge"
BRIDGE_DISPLAY_NAME = "MQTT Mochad Bridge"
BRIDGE_MODEL = "X10 MQTT Bridge"
DEFAULT_SUPPORT_URL = "https://github.com/Monsterray/mochad-mqtt-bridge"
MOCHAD_REDUX_URL = "https://github.com/Monsterray/mochad-redux"


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
        mochad_diagnostics: MochadDiagnostics | None = None,
    ) -> list[DiscoveryMessage]:
        self._validate_device(device)

        payload = self._payload(device, mochad_diagnostics)
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

    def bridge_diagnostic_messages(
        self,
        mochad_diagnostics: MochadDiagnostics | None = None,
    ) -> list[DiscoveryMessage]:
        messages = [
            self._bridge_status_sensor_message(mochad_diagnostics),
            self._bridge_connectivity_sensor_message(
                object_id="mqtt_mochad_bridge_mochad_connected",
                name="Mochad Connected",
                value_key="mochad_connected",
                mochad_diagnostics=mochad_diagnostics,
            ),
            self._bridge_usb_sensor_message(mochad_diagnostics),
            self._bridge_value_sensor_message(
                object_id="mqtt_mochad_bridge_controller",
                name="Controller Type",
                value_template=(
                    "{{ value_json.mochad.health.controller | default('unknown') }}"
                ),
                mochad_diagnostics=mochad_diagnostics,
            ),
            self._bridge_value_sensor_message(
                object_id="mqtt_mochad_bridge_mochad_version",
                name="Mochad Version",
                value_template=(
                    "{{ value_json.mochad.version | default('unknown') }}"
                ),
                mochad_diagnostics=mochad_diagnostics,
            ),
            self._bridge_command_button_message(
                command=BridgeCommand.SYNC,
                object_id="mqtt_mochad_bridge_sync",
                name="Sync X10 Status",
                mochad_diagnostics=mochad_diagnostics,
            ),
            self._bridge_command_button_message(
                command=BridgeCommand.REDISCOVER,
                object_id="mqtt_mochad_bridge_rediscover",
                name="Rediscover X10 Entities",
                mochad_diagnostics=mochad_diagnostics,
            ),
        ]

        if self.enable_maintenance_buttons:
            messages.extend(
                [
                    self._bridge_command_button_message(
                        command=BridgeCommand.PRUNE_DISCOVERY,
                        object_id="mqtt_mochad_bridge_prune_discovery",
                        name="Prune Discovery",
                        mochad_diagnostics=mochad_diagnostics,
                    ),
                    self._bridge_command_button_message(
                        command=BridgeCommand.RESET_DISCOVERY,
                        object_id="mqtt_mochad_bridge_reset_discovery",
                        name="Reset Discovery",
                        mochad_diagnostics=mochad_diagnostics,
                    ),
                ]
            )

        for message in messages:
            self._validate_bridge_message(message)

        return messages

    def _payload(
        self,
        device: DeviceConfig,
        mochad_diagnostics: MochadDiagnostics | None,
    ) -> dict:
        if device.entity_type == DeviceType.CHIME:
            return self._button_payload(device, mochad_diagnostics)

        return {
            "name": device.name,
            "unique_id": Topics.unique_id(device),
            "default_entity_id": self._default_entity_id(
                Topics.entity_type(device),
                Topics.unique_id(device),
            ),
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
            "device": self._device_block(mochad_diagnostics),
            "origin": self._origin_block(mochad_diagnostics),
        }

    def _button_payload(
        self,
        device: DeviceConfig,
        mochad_diagnostics: MochadDiagnostics | None,
    ) -> dict:
        return {
            "name": device.name,
            "unique_id": Topics.unique_id(device),
            "default_entity_id": self._default_entity_id(
                "button",
                Topics.unique_id(device),
            ),
            "command_topic": Topics.command(
                device,
                base_topic=self.base_topic,
                friendly_topics=self.friendly_topics,
            ),
            "payload_press": "ON",
            "availability_topic": Topics.availability(
                base_topic=self.base_topic,
            ),
            "device": self._device_block(mochad_diagnostics),
            "origin": self._origin_block(mochad_diagnostics),
        }

    def _bridge_status_sensor_message(
        self,
        mochad_diagnostics: MochadDiagnostics | None,
    ) -> DiscoveryMessage:
        return DiscoveryMessage(
            topic=Topics.bridge_discovery(
                "sensor",
                "mqtt_mochad_bridge_status",
                discovery_prefix=self.discovery_prefix,
            ),
            payload={
                "name": "Bridge Status",
                "unique_id": "mqtt_mochad_bridge_status",
                "default_entity_id": self._default_entity_id(
                    "sensor",
                    "mqtt_mochad_bridge_status",
                ),
                "state_topic": Topics.status(
                    base_topic=self.base_topic,
                ),
                "value_template": "{{ value_json.status }}",
                "availability_topic": Topics.availability(
                    base_topic=self.base_topic,
                ),
                "entity_category": "diagnostic",
                "device": self._device_block(mochad_diagnostics),
                "origin": self._origin_block(mochad_diagnostics),
            },
            retain=True,
        )

    def _bridge_connectivity_sensor_message(
        self,
        object_id: str,
        name: str,
        value_key: str,
        mochad_diagnostics: MochadDiagnostics | None,
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
                "default_entity_id": self._default_entity_id(
                    "binary_sensor",
                    object_id,
                ),
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
                "device": self._device_block(mochad_diagnostics),
                "origin": self._origin_block(mochad_diagnostics),
            },
            retain=True,
        )

    def _bridge_usb_sensor_message(
        self,
        mochad_diagnostics: MochadDiagnostics | None,
    ) -> DiscoveryMessage:
        return DiscoveryMessage(
            topic=Topics.bridge_discovery(
                "binary_sensor",
                "mqtt_mochad_bridge_usb_connected",
                discovery_prefix=self.discovery_prefix,
            ),
            payload={
                "name": "USB Connected",
                "unique_id": "mqtt_mochad_bridge_usb_connected",
                "default_entity_id": self._default_entity_id(
                    "binary_sensor",
                    "mqtt_mochad_bridge_usb_connected",
                ),
                "state_topic": Topics.status(
                    base_topic=self.base_topic,
                ),
                "value_template": (
                    "{{ 'ON' if value_json.mochad.health.usb_connected else 'OFF' }}"
                ),
                "payload_on": "ON",
                "payload_off": "OFF",
                "device_class": "connectivity",
                "availability_topic": Topics.availability(
                    base_topic=self.base_topic,
                ),
                "entity_category": "diagnostic",
                "device": self._device_block(mochad_diagnostics),
                "origin": self._origin_block(mochad_diagnostics),
            },
            retain=True,
        )

    def _bridge_value_sensor_message(
        self,
        object_id: str,
        name: str,
        value_template: str,
        mochad_diagnostics: MochadDiagnostics | None,
    ) -> DiscoveryMessage:
        return DiscoveryMessage(
            topic=Topics.bridge_discovery(
                "sensor",
                object_id,
                discovery_prefix=self.discovery_prefix,
            ),
            payload={
                "name": name,
                "unique_id": object_id,
                "default_entity_id": self._default_entity_id(
                    "sensor",
                    object_id,
                ),
                "state_topic": Topics.status(
                    base_topic=self.base_topic,
                ),
                "value_template": value_template,
                "availability_topic": Topics.availability(
                    base_topic=self.base_topic,
                ),
                "entity_category": "diagnostic",
                "device": self._device_block(mochad_diagnostics),
                "origin": self._origin_block(mochad_diagnostics),
            },
            retain=True,
        )

    def _bridge_command_button_message(
        self,
        command: BridgeCommand,
        object_id: str,
        name: str,
        mochad_diagnostics: MochadDiagnostics | None,
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
                "default_entity_id": self._default_entity_id(
                    "button",
                    object_id,
                ),
                "command_topic": Topics.bridge_command(
                    base_topic=self.base_topic,
                ),
                "payload_press": command.name,
                "availability_topic": Topics.availability(
                    base_topic=self.base_topic,
                ),
                "entity_category": "diagnostic",
                "device": self._device_block(mochad_diagnostics),
                "origin": self._origin_block(mochad_diagnostics),
            },
            retain=True,
        )

    def _device_block(
        self,
        mochad_diagnostics: MochadDiagnostics | None = None,
    ) -> dict:
        payload = {
            "identifiers": [
                BRIDGE_DEVICE_IDENTIFIER,
            ],
            "name": BRIDGE_DISPLAY_NAME,
            "manufacturer": BRIDGE_AUTHOR,
            "model": self._device_model(mochad_diagnostics),
            "sw_version": self._device_sw_version(mochad_diagnostics),
            "configuration_url": self.support_url,
        }

        controller = self._clean_diag_value(
            mochad_diagnostics.controller if mochad_diagnostics else None
        )
        daemon = self._clean_diag_value(
            mochad_diagnostics.daemon if mochad_diagnostics else None
        )
        version = self._clean_diag_value(
            mochad_diagnostics.version if mochad_diagnostics else None
        )

        if daemon:
            payload["model_id"] = daemon

        if controller:
            payload["hw_version"] = controller

        if version:
            payload["configuration_url"] = MOCHAD_REDUX_URL

        return payload

    def _origin_block(
        self,
        mochad_diagnostics: MochadDiagnostics | None = None,
    ) -> dict:
        version = self._clean_diag_value(
            mochad_diagnostics.version if mochad_diagnostics else None
        )
        return {
            "name": BRIDGE_DISPLAY_NAME,
            "sw_version": self._origin_version(version),
            "support_url": self.support_url,
        }

    @staticmethod
    def _device_model(
        mochad_diagnostics: MochadDiagnostics | None,
    ) -> str:
        controller = DiscoveryManager._clean_diag_value(
            mochad_diagnostics.controller if mochad_diagnostics else None
        )

        if controller:
            return f"{controller} MQTT Bridge"

        return BRIDGE_MODEL

    @staticmethod
    def _device_sw_version(
        mochad_diagnostics: MochadDiagnostics | None,
    ) -> str:
        daemon = DiscoveryManager._clean_diag_value(
            mochad_diagnostics.daemon if mochad_diagnostics else None
        )
        version = DiscoveryManager._clean_diag_value(
            mochad_diagnostics.version if mochad_diagnostics else None
        )

        if daemon and version:
            return f"bridge {BRIDGE_VERSION}; {daemon} {version}"

        if version:
            return f"bridge {BRIDGE_VERSION}; mochad {version}"

        return BRIDGE_VERSION

    @staticmethod
    def _origin_version(
        mochad_version: str | None,
    ) -> str:
        if mochad_version:
            return f"{BRIDGE_VERSION}; mochad {mochad_version}"

        return BRIDGE_VERSION

    @staticmethod
    def _clean_diag_value(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = str(value).strip()

        if not value or value.lower() in {"none", "unknown"}:
            return None

        return value

    @staticmethod
    def _default_entity_id(
        component: str,
        unique_id: str,
    ) -> str:
        slug = unique_id.strip().lower()
        slug = re.sub(r"[^a-z0-9_]+", "_", slug)
        slug = re.sub(r"_+", "_", slug).strip("_")

        return f"{component}.{slug}"

    def _validate_device(
        self,
        device: DeviceConfig,
    ) -> None:
        if device.entity_type not in {
            DeviceType.LIGHT,
            DeviceType.SWITCH,
            DeviceType.CHIME,
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
            "command_topic",
            "availability_topic",
            "device",
            "origin",
        }

        if message.topic.split("/")[1] == "button":
            required_payload_fields.add("payload_press")
        else:
            required_payload_fields.update(
                {
                    "state_topic",
                    "payload_on",
                    "payload_off",
                }
            )

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

        if "state_topic" in message.payload and not message.payload["state_topic"]:
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
