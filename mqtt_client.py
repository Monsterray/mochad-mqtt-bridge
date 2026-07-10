"""
MQTT transport client.

This module owns MQTT connection management, subscriptions, publishing,
callbacks, and Last Will setup. It does not parse mochad, generate discovery
payloads, or modify bridge state.
"""

from __future__ import annotations

import json
import logging
import ssl
from dataclasses import dataclass
from typing import Callable, Protocol

from config import MqttTlsConfig
from models import Command, DeviceConfig, DiscoveryMessage
from mqtt_tls import build_mqtt_ssl_context
from topics import Topics


_LOG = logging.getLogger(__name__)
_LOG.addHandler(logging.NullHandler())


Payload = str | bytes | int | float | bool | dict | list | None


@dataclass(slots=True, frozen=True)
class MqttCommandMessage:
    """Inbound MQTT command message."""

    device: str
    payload: str
    topic: str


@dataclass(slots=True, frozen=True)
class MqttBridgeCommandMessage:
    """Inbound MQTT bridge command message."""

    payload: str
    topic: str


class PahoClientProtocol(Protocol):
    on_connect: Callable | None
    on_disconnect: Callable | None
    on_message: Callable | None

    def username_pw_set(
        self,
        username: str,
        password: str | None = None,
    ) -> None:
        ...

    def will_set(
        self,
        topic: str,
        payload: str | bytes | None = None,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        ...

    def tls_set_context(
        self,
        context: ssl.SSLContext,
    ) -> None:
        ...

    def connect(
        self,
        host: str,
        port: int = 1883,
        keepalive: int = 60,
    ):
        ...

    def disconnect(self):
        ...

    def loop_start(self) -> None:
        ...

    def loop_stop(self) -> None:
        ...

    def publish(
        self,
        topic: str,
        payload: str | bytes | None = None,
        qos: int = 0,
        retain: bool = False,
    ):
        ...

    def subscribe(
        self,
        topic: str,
        qos: int = 0,
    ):
        ...


ClientFactory = Callable[[str], PahoClientProtocol]
TlsContextFactory = Callable[[MqttTlsConfig], ssl.SSLContext | None]
CommandCallback = Callable[[MqttCommandMessage], None]
BridgeCommandCallback = Callable[[MqttBridgeCommandMessage], None]
ConnectionCallback = Callable[[], None]
DisconnectCallback = Callable[[int | None], None]


class MqttClient:
    """
    Thin MQTT transport wrapper.
    """

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        base_topic: str = "x10",
        client_id: str = "mqtt-mochad-bridge",
        keepalive: int = 60,
        debug_wire: bool = False,
        tls_config: MqttTlsConfig | None = None,
        ssl_context_factory: TlsContextFactory = build_mqtt_ssl_context,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.base_topic = base_topic
        self.client_id = client_id
        self.keepalive = keepalive
        self.debug_wire = debug_wire
        self.tls_config = tls_config or MqttTlsConfig()
        self._ssl_context_factory = ssl_context_factory

        factory = client_factory or self._default_client_factory
        self._client = factory(client_id)
        self._command_callback: CommandCallback | None = None
        self._bridge_command_callback: BridgeCommandCallback | None = None
        self._connect_callback: ConnectionCallback | None = None
        self._disconnect_callback: DisconnectCallback | None = None
        self._connected = False

        self._configure_client()

    @property
    def connected(self) -> bool:
        return self._connected

    def set_command_callback(
        self,
        callback: CommandCallback,
    ) -> None:
        self._command_callback = callback

    def set_bridge_command_callback(
        self,
        callback: BridgeCommandCallback,
    ) -> None:
        self._bridge_command_callback = callback

    def set_connect_callback(
        self,
        callback: ConnectionCallback,
    ) -> None:
        self._connect_callback = callback

    def set_disconnect_callback(
        self,
        callback: DisconnectCallback,
    ) -> None:
        self._disconnect_callback = callback

    def connect(self) -> None:
        _LOG.info(
            "Connecting to MQTT broker host=%s port=%s username_configured=%s tls_enabled=%s",
            self.host,
            self.port,
            bool(self.username),
            self.tls_config.enabled,
        )
        self._client.connect(
            self.host,
            self.port,
            self.keepalive,
        )
        self._client.loop_start()

    def disconnect(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()

    def subscribe_commands(self) -> None:
        # The device command wildcard also receives x10/bridge/command.
        # _on_message routes the bridge topic first so it is not treated as a
        # device command, and avoiding an overlapping exact subscription keeps
        # brokers from delivering duplicate bridge commands.
        self._client.subscribe(
            Topics.command_filter(self.base_topic),
            qos=0,
        )

    def publish(
        self,
        topic: str,
        payload: Payload,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        serialized = self._serialize_payload(payload)

        if self.debug_wire:
            _LOG.info(
                "MQTT publish topic=%s retain=%s qos=%s payload=%s",
                topic,
                retain,
                qos,
                serialized,
            )

        self._client.publish(
            topic,
            serialized,
            qos=qos,
            retain=retain,
        )

    def publish_discovery(
        self,
        message: DiscoveryMessage,
    ) -> None:
        self.publish(
            message.topic,
            message.payload,
            retain=message.retain,
        )

    def publish_state(
        self,
        device: DeviceConfig | str,
        state: Command | str,
        retain: bool = True,
    ) -> None:
        self.publish(
            Topics.state(
                device,
                base_topic=self.base_topic,
            ),
            self._command_payload(state),
            retain=retain,
        )

    def publish_event(
        self,
        device: DeviceConfig | str,
        payload: Payload,
        retain: bool = False,
    ) -> None:
        self.publish(
            Topics.event(
                device,
                base_topic=self.base_topic,
            ),
            payload,
            retain=retain,
        )

    def publish_attributes(
        self,
        device: DeviceConfig | str,
        payload: Payload,
        retain: bool = True,
    ) -> None:
        self.publish(
            Topics.attributes(
                device,
                base_topic=self.base_topic,
            ),
            payload,
            retain=retain,
        )

    def publish_availability(
        self,
        online: bool,
        retain: bool = True,
    ) -> None:
        self.publish(
            Topics.availability(base_topic=self.base_topic),
            "online" if online else "offline",
            retain=retain,
        )

    def publish_status(
        self,
        payload: Payload,
        retain: bool = True,
    ) -> None:
        self.publish(
            Topics.status(base_topic=self.base_topic),
            payload,
            retain=retain,
        )

    def publish_bridge_response(
        self,
        payload: Payload,
        retain: bool = False,
    ) -> None:
        self.publish(
            Topics.bridge_response(base_topic=self.base_topic),
            payload,
            retain=retain,
        )

    def _configure_client(self) -> None:
        self._configure_tls()

        if self.username:
            _LOG.info("MQTT username configured")
            self._client.username_pw_set(
                self.username,
                self.password,
            )
        else:
            _LOG.warning(
                "MQTT username is empty; broker authentication may fail"
            )

        self._client.will_set(
            Topics.availability(base_topic=self.base_topic),
            payload="offline",
            qos=0,
            retain=True,
        )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def _configure_tls(self) -> None:
        if not self.tls_config.enabled:
            return

        context = self._ssl_context_factory(self.tls_config)

        if context is None:
            raise RuntimeError(
                "MQTT TLS is enabled but no SSL context was created."
            )

        self._client.tls_set_context(context)
        _LOG.info(
            "MQTT TLS configured custom_ca=%s client_certificate=%s",
            bool(self.tls_config.ca_file),
            bool(self.tls_config.cert_file),
        )

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        *args,
    ) -> None:
        self._connected = True
        self.subscribe_commands()

        if self._connect_callback:
            try:
                self._connect_callback()
            except Exception:
                _LOG.exception("MQTT connect callback failed")

    def _on_disconnect(
        self,
        client,
        userdata,
        *args,
    ) -> None:
        self._connected = False
        reason_code = self._disconnect_reason_code(args)
        reason_label = self._reason_code_label(reason_code)
        reason_number = self._reason_code_as_int(reason_code)

        _LOG.warning(
            "MQTT disconnected reason=%s",
            reason_label,
        )

        if self._is_authorization_failure(reason_code, reason_label):
            _LOG.error(
                "MQTT authorization failed; check MQTT_USERNAME, "
                "MQTT_PASSWORD, and broker ACLs."
            )

        if self._disconnect_callback:
            try:
                self._disconnect_callback(
                    reason_number
                )
            except Exception:
                _LOG.exception("MQTT disconnect callback failed")

    def _on_message(
        self,
        client,
        userdata,
        message,
    ) -> None:
        _LOG.debug(
            "MQTT message received topic=%s payload_bytes=%d",
            message.topic,
            len(message.payload),
        )

        payload = message.payload.decode(
            "utf-8",
            errors="replace",
        ).strip()

        if self.debug_wire:
            _LOG.info(
                "MQTT message received topic=%s payload=%s",
                message.topic,
                payload,
            )

        if self._handle_bridge_command_message(message.topic, payload):
            return

        if self._handle_device_command_message(message.topic, payload):
            return

        _LOG.warning(
            "Ignoring MQTT message on unexpected topic %s",
            message.topic,
        )

    def _handle_device_command_message(
        self,
        topic: str,
        payload: str,
    ) -> bool:
        try:
            device = Topics.parse_command_topic(
                topic,
                base_topic=self.base_topic,
            )
        except ValueError:
            return False

        _LOG.debug(
            "MQTT command message parsed device=%s payload=%s topic=%s",
            device,
            payload,
            topic,
        )

        if self._command_callback:
            try:
                self._command_callback(
                    MqttCommandMessage(
                        device=device,
                        payload=payload,
                        topic=topic,
                    )
                )
            except Exception:
                _LOG.exception(
                    "MQTT command callback failed topic=%s",
                    topic,
                )

        return True

    def _handle_bridge_command_message(
        self,
        topic: str,
        payload: str,
    ) -> bool:
        try:
            Topics.parse_bridge_command_topic(
                topic,
                base_topic=self.base_topic,
            )
        except ValueError:
            return False

        _LOG.debug(
            "MQTT bridge command message routed payload=%s topic=%s",
            payload,
            topic,
        )

        if self._bridge_command_callback:
            try:
                self._bridge_command_callback(
                    MqttBridgeCommandMessage(
                        payload=payload,
                        topic=topic,
                    )
                )
            except Exception:
                _LOG.exception(
                    "MQTT bridge command callback failed topic=%s",
                    topic,
                )

        return True

    @staticmethod
    def _serialize_payload(payload: Payload) -> str:
        if payload is None:
            return ""

        if isinstance(payload, str):
            return payload

        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace")

        if isinstance(payload, (dict, list)):
            return json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            )

        return str(payload)

    @staticmethod
    def _command_payload(state: Command | str) -> str:
        if isinstance(state, Command):
            return state.name

        return state

    @staticmethod
    def _reason_code_as_int(reason_code) -> int | None:
        try:
            return int(reason_code)
        except (TypeError, ValueError):
            value = getattr(reason_code, "value", None)

            if value is None:
                return None

            try:
                return int(value)
            except (TypeError, ValueError):
                return None

    @staticmethod
    def _disconnect_reason_code(args) -> object | None:
        if not args:
            return None

        if len(args) == 1:
            return args[0]

        # Paho MQTT v2 may call disconnect callbacks as:
        # client, userdata, disconnect_flags, reason_code, properties
        return args[1]

    @staticmethod
    def _reason_code_label(reason_code) -> str:
        if reason_code is None:
            return "unknown"

        for attr in ("getName", "get_name"):
            getter = getattr(reason_code, attr, None)

            if callable(getter):
                try:
                    name = getter()
                except Exception:
                    name = None

                if name:
                    return str(name)

        name = getattr(reason_code, "name", None)

        if name:
            return str(name)

        return str(reason_code)

    @classmethod
    def _is_authorization_failure(
        cls,
        reason_code,
        reason_label: str,
    ) -> bool:
        normalized = reason_label.strip().lower().replace("_", " ")

        return (
            cls._reason_code_as_int(reason_code) == 128
            or "not authorised" in normalized
            or "not authorized" in normalized
            or "bad user name or password" in normalized
        )

    @staticmethod
    def _default_client_factory(client_id: str) -> PahoClientProtocol:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError(
                "paho-mqtt is required to use MqttClient."
            ) from exc

        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
