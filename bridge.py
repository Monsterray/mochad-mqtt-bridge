"""
Thin bridge orchestrator.

bridge.py wires the transport, protocol, state, and discovery layers together.
It does not own device state, parse mochad text directly, generate discovery
payloads, or construct MQTT topics.
"""

from __future__ import annotations

import logging
import json
import os
import signal
import time
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from config import (
    Config,
    ConfigError,
    ConfigFileWriteError,
    create_config_file_if_missing,
    load_config,
)
from discovery import DiscoveryManager
from discovery_registry import DiscoveryRegistry, DiscoveryRegistryError
from device_registry import configured_profile_diagnostics
from models import (
    BridgeAction,
    BridgeCommand,
    Command,
    DeviceConfig,
    DiscoveryMessage,
    LogUnknownEventAction,
    MochadDiagnostics,
    PublishAttributesAction,
    PublishAvailabilityAction,
    PublishBridgeResponseAction,
    PublishCommandEventAction,
    PublishDiscoveryAction,
    PublishEventAction,
    PublishStateAction,
    PublishStatusAction,
    RequestStatusAction,
    SendDeviceCommandAction,
    SendMochadCommandAction,
)
from mochad_client import MochadClient
from mqtt_client import MqttBridgeCommandMessage, MqttClient, MqttCommandMessage
from protocol import ProtocolParser, encode_rf_command
from protocol.validation import normalize_address
from state import StateManager
from topics import Topics
from version import BRIDGE_NAME, BRIDGE_VERSION


_LOG = logging.getLogger(__name__)

DEFAULT_HEALTH_FILE = "/config/mqtt-mochad-bridge.health"


COMMAND_PAYLOADS = {
    "ON": Command.ON,
    "OFF": Command.OFF,
    "DIM": Command.DIM,
    "BRIGHT": Command.BRIGHT,
}

BRIDGE_COMMAND_ALIASES = {
    "PRUNE_ENTITIES": BridgeCommand.PRUNE_DISCOVERY,
    "PRUNE": BridgeCommand.PRUNE_DISCOVERY,
}

REPEATABLE_COMMANDS = {
    Command.ON,
    Command.OFF,
}

MAX_QUEUED_DEVICE_COMMANDS = 100


@dataclass(slots=True)
class BridgeClients:
    mqtt: MqttClient
    mochad: MochadClient


class Bridge:
    """
    Coordinate the bridge components without taking ownership of their logic.
    """

    def __init__(
        self,
        config: Config,
        mqtt_client: MqttClient | None = None,
        mochad_client: MochadClient | None = None,
        parser: ProtocolParser | None = None,
        state: StateManager | None = None,
        discovery: DiscoveryManager | None = None,
    ) -> None:
        started = time.monotonic()
        _LOG.info("Initializing bridge")
        self.config = config
        self._config_file_path = (
            Path(config.config_file) if config.config_file else None
        )
        self._config_file_signature = self._read_config_file_signature()
        self._next_config_reload_check = (
            time.monotonic() + config.config_reload_interval_seconds
        )
        self.devices = {
            address: device
            for address, device in config.devices.items()
            if self._address_allowed_by_config(address)
        }
        _LOG.info(
            "Loaded %d configured X10 device(s)",
            len(self.devices),
        )
        _LOG.info(
            "Friendly names enabled=%s",
            config.use_friendly_names,
        )
        if self._config_file_path is not None:
            _LOG.info(
                "Config file watching enabled path=%s interval=%.3fs",
                self._config_file_path,
                config.config_reload_interval_seconds,
            )
        self.parser = parser or ProtocolParser()
        _LOG.info("Protocol parser ready")
        self.state = state or StateManager(
            devices=self.devices,
            optimistic_updates=config.optimistic_updates,
            allowed_housecodes=config.x10_housecodes,
        )
        _LOG.info(
            "State manager ready optimistic_updates=%s housecodes=%s",
            config.optimistic_updates,
            ",".join(sorted(config.x10_housecodes))
            if config.x10_housecodes is not None
            else "all",
        )
        self.discovery = discovery or DiscoveryManager(
            discovery_prefix=config.mqtt_discovery_prefix,
            base_topic=config.mqtt_base_topic,
            enable_maintenance_buttons=config.enable_maintenance_buttons,
        )
        _LOG.info(
            "Discovery manager ready prefix=%s base_topic=%s maintenance_buttons=%s",
            config.mqtt_discovery_prefix,
            config.mqtt_base_topic,
            config.enable_maintenance_buttons,
        )
        _LOG.info(
            "Configuring transports mqtt=%s:%s mochad=%s:%s",
            config.mqtt_host,
            config.mqtt_port,
            config.mochad_host,
            config.mochad_port,
        )
        self.clients = BridgeClients(
            mqtt=mqtt_client
            or MqttClient(
                host=config.mqtt_host,
                port=config.mqtt_port,
                username=config.mqtt_username,
                password=config.mqtt_password,
                tls_config=config.mqtt_tls,
                base_topic=config.mqtt_base_topic,
                debug_wire=config.debug_wire,
            ),
            mochad=mochad_client
            or MochadClient(
                host=config.mochad_host,
                port=config.mochad_port,
                debug_wire=config.debug_wire,
            ),
        )
        self.discovery_registry = DiscoveryRegistry(
            config.discovery_registry_path
        )
        self._ensure_runtime_config_files()
        self._mochad_diagnostics = MochadDiagnostics()
        _LOG.info(
            "Discovery cleanup enabled=%s registry_path=%s",
            config.discovery_cleanup,
            config.discovery_registry_path,
        )
        if config.debug_wire:
            _LOG.info("Wire debug logging enabled")

        self._running = False
        self._stopping = False
        self._dropped_mqtt_publishes = 0
        self._queued_device_commands: deque[SendDeviceCommandAction] = deque()
        self._dropped_device_commands = 0
        self._health_file = Path(
            os.getenv("BRIDGE_HEALTH_FILE", DEFAULT_HEALTH_FILE)
        )
        self._wire_callbacks()
        _LOG.info(
            "Bridge initialized successfully elapsed=%.3fs",
            time.monotonic() - started,
        )

    def _ensure_runtime_config_files(self) -> None:
        try:
            created = create_config_file_if_missing(self.config)
        except ConfigFileWriteError as exc:
            _LOG.warning("%s", exc)
        else:
            if created:
                _LOG.info(
                    "Created editable bridge config file path=%s",
                    self.config.config_file,
                )

        if self.config.config_file is not None:
            try:
                created = self.discovery_registry.create_if_missing()
            except DiscoveryRegistryError as exc:
                _LOG.warning("%s", exc)
            else:
                if created:
                    _LOG.info(
                        "Created discovery registry file path=%s",
                        self.config.discovery_registry_path,
                    )

    def start(self) -> None:
        started = time.monotonic()
        _LOG.info("Starting bridge transports")
        self._running = True
        _LOG.info(
            "Connecting to MQTT broker %s:%s",
            self.config.mqtt_host,
            self.config.mqtt_port,
        )
        self.clients.mqtt.connect()
        _LOG.info(
            "MQTT connection initiated elapsed=%.3fs",
            time.monotonic() - started,
        )
        _LOG.info(
            "Starting mochad client %s:%s",
            self.config.mochad_host,
            self.config.mochad_port,
        )
        self.clients.mochad.start()
        _LOG.info(
            "mochad client started elapsed=%.3fs",
            time.monotonic() - started,
        )
        _LOG.info(
            "Bridge Running elapsed=%.3fs",
            time.monotonic() - started,
        )
        self._write_health("starting")

    def stop(self) -> None:
        started = time.monotonic()
        _LOG.info("Stopping bridge transports")
        self._running = False
        self._stopping = True
        self.clients.mochad.stop()
        _LOG.info(
            "mochad client stopped elapsed=%.3fs",
            time.monotonic() - started,
        )
        self._publish_shutdown_status()
        self.clients.mqtt.disconnect()
        _LOG.info(
            "MQTT client stopped elapsed=%.3fs",
            time.monotonic() - started,
        )
        self._write_health("stopped")

    def _publish_shutdown_status(self) -> None:
        if not self.clients.mqtt.connected:
            _LOG.info("Skipping MQTT shutdown status because MQTT is disconnected")
            return

        payload = self._bridge_status_payload(
            status="shutdown",
            mqtt_connected=True,
            mochad_connected=False,
        )
        payload["available"] = False
        _LOG.info("MQTT publish shutdown status")
        self.clients.mqtt.publish_status(
            payload,
            retain=True,
            qos=1,
            wait=True,
        )
        self.clients.mqtt.publish_availability(
            False,
            retain=True,
            qos=1,
            wait=True,
        )

    def run_forever(self) -> None:
        self.start()

        while self._running:
            self._check_config_file_reload()
            self._write_health(
                "running" if self.state.available else "starting"
            )
            time.sleep(1)

    def run(self) -> None:
        self._install_signal_handlers()
        self.run_forever()

    def execute_actions(
        self,
        actions: Iterable[BridgeAction],
    ) -> None:
        for action in actions:
            try:
                self.execute_action(action)
            except (ConnectionError, OSError) as exc:
                _LOG.warning(
                    "Bridge action failed action=%s error=%s",
                    type(action).__name__,
                    exc,
                )

                if isinstance(
                    action,
                    (
                        RequestStatusAction,
                        SendDeviceCommandAction,
                        SendMochadCommandAction,
                    ),
                ):
                    break

    def execute_action(
        self,
        action: BridgeAction,
    ) -> None:
        if self._drop_mqtt_publish_if_disconnected(action):
            return

        if isinstance(action, PublishStateAction):
            _LOG.info(
                "MQTT publish state address=%s state=%s retain=%s",
                action.address,
                action.state.name,
                action.retain,
            )
            self.clients.mqtt.publish_state(
                action.address,
                action.state,
                retain=action.retain,
            )
            return

        if isinstance(action, PublishEventAction):
            _LOG.info(
                "MQTT publish event address=%s command=%s",
                action.event.address,
                action.event.command.name,
            )
            self.clients.mqtt.publish_event(
                action.event.address,
                {
                    "timestamp": action.event.timestamp.isoformat(),
                    "direction": action.event.direction.name,
                    "transport": action.event.transport.name,
                    "device": action.event.address,
                    "command": action.event.command.name,
                    # A CM19A/CM15A Tx line confirms bridge transmission,
                    # not that the physical X10 device acted on it.
                    "confirmed": action.event.direction.name != "TX",
                },
                retain=False,
            )
            return

        if isinstance(action, PublishCommandEventAction):
            _LOG.info(
                "MQTT publish command event address=%s command=%s retain=%s",
                action.address,
                action.payload.get("command"),
                action.retain,
            )
            self.clients.mqtt.publish_event(
                action.address,
                action.payload,
                retain=action.retain,
            )
            return

        if isinstance(action, PublishAttributesAction):
            _LOG.info(
                "MQTT publish attributes address=%s retain=%s",
                action.address,
                action.retain,
            )
            self.clients.mqtt.publish_attributes(
                action.address,
                action.payload,
                retain=action.retain,
            )
            return

        if isinstance(action, PublishDiscoveryAction):
            device = self._device_config(action.address)

            for message in self.discovery.discovery_messages(
                device,
                self._mochad_diagnostics,
            ):
                _LOG.info(
                    "MQTT publish discovery address=%s topic=%s retain=%s",
                    action.address,
                    message.topic,
                    message.retain,
                )
                self.clients.mqtt.publish_discovery(message)

            return

        if isinstance(action, PublishAvailabilityAction):
            _LOG.info(
                "MQTT publish availability online=%s",
                action.online,
            )
            self.clients.mqtt.publish_availability(action.online)
            return

        if isinstance(action, PublishStatusAction):
            _LOG.info(
                "MQTT publish status status=%s mqtt_connected=%s mochad_connected=%s",
                action.status,
                action.mqtt_connected,
                action.mochad_connected,
            )
            self.clients.mqtt.publish_status(
                self._bridge_status_payload(
                    status=action.status,
                    mqtt_connected=action.mqtt_connected,
                    mochad_connected=action.mochad_connected,
                ),
                retain=action.retain,
            )
            return

        if isinstance(action, PublishBridgeResponseAction):
            payload = {
                "command": action.command.name
                if action.command is not None
                else None,
                "success": action.success,
                "message": action.message,
                "timestamp": time.time(),
            }
            payload.update(action.payload)
            _LOG.info(
                "MQTT publish bridge response command=%s success=%s",
                payload["command"],
                action.success,
            )
            self.clients.mqtt.publish_bridge_response(
                payload,
                retain=action.retain,
            )
            return

        if isinstance(action, SendMochadCommandAction):
            self.clients.mochad.send_line(action.command)
            return

        if isinstance(action, SendDeviceCommandAction):
            queue_reason = self._device_command_queue_reason()
            if queue_reason is not None:
                self._queue_device_command(
                    action,
                    reason=queue_reason,
                )
                return

            self._send_device_command(action)
            return

        if isinstance(action, RequestStatusAction):
            self.clients.mochad.request_status()
            return

        if isinstance(action, LogUnknownEventAction):
            _LOG.warning(
                "Unknown mochad packet: %s",
                action.event.raw,
            )
            return

        raise TypeError(
            f"Unhandled bridge action {type(action).__name__}."
        )

    def _drop_mqtt_publish_if_disconnected(
        self,
        action: BridgeAction,
    ) -> bool:
        if not isinstance(
            action,
            (
                PublishAttributesAction,
                PublishAvailabilityAction,
                PublishBridgeResponseAction,
                PublishCommandEventAction,
                PublishDiscoveryAction,
                PublishEventAction,
                PublishStateAction,
                PublishStatusAction,
            ),
        ):
            return False

        if self.clients.mqtt.connected:
            return False

        self._dropped_mqtt_publishes += 1
        _LOG.warning(
            "Dropping MQTT publish while broker is disconnected action=%s dropped=%d",
            type(action).__name__,
            self._dropped_mqtt_publishes,
        )
        return True

    def _send_device_command(
        self,
        action: SendDeviceCommandAction,
    ) -> None:
        device = self._device_config(action.address)
        repeats = (
            device.command_repeats
            if action.command in REPEATABLE_COMMANDS
            else 1
        )
        delay_seconds = device.command_repeat_delay_ms / 1000.0
        line = encode_rf_command(
            action.address,
            action.command,
        )

        for attempt in range(1, repeats + 1):
            _LOG.debug(
                "Executing SendDeviceCommandAction address=%s command=%s attempt=%d repeats=%d",
                action.address,
                action.command.name,
                attempt,
                repeats,
            )
            self.clients.mochad.send_line(line)

            if attempt < repeats and delay_seconds > 0:
                time.sleep(delay_seconds)

    def _device_command_queue_reason(self) -> str | None:
        if not self.clients.mochad.connected:
            return "mochad disconnected"

        diagnostics = self._mochad_diagnostics
        if diagnostics.usb_connected is False:
            return "mochad USB disconnected"

        if diagnostics.endpoints_ready is False:
            return "mochad USB endpoints not ready"

        if diagnostics.transfers_ready is False:
            return "mochad USB transfers not ready"

        return None

    def _queue_device_command(
        self,
        action: SendDeviceCommandAction,
        reason: str,
    ) -> None:
        if len(self._queued_device_commands) >= MAX_QUEUED_DEVICE_COMMANDS:
            dropped = self._queued_device_commands.popleft()
            self._dropped_device_commands += 1
            _LOG.warning(
                "Dropping oldest queued device command address=%s command=%s dropped=%d",
                dropped.address,
                dropped.command.name,
                self._dropped_device_commands,
            )

        self._queued_device_commands.append(action)
        _LOG.warning(
            "Queued device command until mochad USB is ready address=%s command=%s reason=%s queued=%d",
            action.address,
            action.command.name,
            reason,
            len(self._queued_device_commands),
        )

        if self.clients.mqtt.connected:
            self.clients.mqtt.publish_status(
                self._bridge_status_payload(),
                retain=True,
            )

    def _flush_queued_device_commands(self) -> None:
        if not self._queued_device_commands:
            return

        queue_reason = self._device_command_queue_reason()
        if queue_reason is not None:
            _LOG.info(
                "Device command queue still waiting reason=%s queued=%d",
                queue_reason,
                len(self._queued_device_commands),
            )
            return

        _LOG.info(
            "Flushing queued device commands queued=%d",
            len(self._queued_device_commands),
        )

        while self._queued_device_commands:
            action = self._queued_device_commands.popleft()
            try:
                self._send_device_command(action)
            except (ConnectionError, OSError) as exc:
                self._queued_device_commands.appendleft(action)
                _LOG.warning(
                    "Paused queued device command flush address=%s command=%s error=%s queued=%d",
                    action.address,
                    action.command.name,
                    exc,
                    len(self._queued_device_commands),
                )
                return

        if self.clients.mqtt.connected:
            self.clients.mqtt.publish_status(
                self._bridge_status_payload(),
                retain=True,
            )

    def _wire_callbacks(self) -> None:
        _LOG.info("Wiring bridge callbacks")
        self.clients.mqtt.set_command_callback(self._on_mqtt_command)
        self.clients.mqtt.set_bridge_command_callback(
            self._on_mqtt_bridge_command
        )
        self.clients.mqtt.set_connect_callback(self._on_mqtt_connected)
        self.clients.mqtt.set_disconnect_callback(self._on_mqtt_disconnected)
        self.clients.mochad.set_line_callback(self._on_mochad_line)
        self.clients.mochad.set_connect_callback(self._on_mochad_connected)
        self.clients.mochad.set_disconnect_callback(self._on_mochad_disconnected)
        _LOG.info("Bridge callbacks wired")

    def _install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)

    def _handle_shutdown_signal(
        self,
        signum,
        frame,
    ) -> None:
        _LOG.info("Stopping bridge")
        self.stop()

    def _on_mqtt_command(
        self,
        message: MqttCommandMessage,
    ) -> None:
        try:
            topic_address = Topics.parse_command_topic(
                message.topic,
                base_topic=self.config.mqtt_base_topic,
            )
        except ValueError:
            _LOG.warning(
                "Ignoring MQTT command with invalid topic %s",
                message.topic,
            )
            return

        if topic_address != message.device:
            _LOG.warning(
                "Ignoring MQTT command with mismatched topic device=%s topic=%s",
                message.device,
                message.topic,
            )
            return

        _LOG.info(
            "MQTT command received device=%s payload=%s topic=%s",
            message.device,
            message.payload,
            message.topic,
        )
        command = self._parse_command_payload(message.payload)
        _LOG.debug(
            "MQTT payload parsed payload=%s command=%s",
            message.payload,
            command.name if command is not None else None,
        )

        if command is None:
            _LOG.warning(
                "Ignoring unsupported MQTT command payload %r on %s",
                message.payload,
                message.topic,
            )
            return

        try:
            address = normalize_address(message.device)
        except ValueError:
            _LOG.warning(
                "Ignoring MQTT command with invalid X10 address device=%s topic=%s",
                message.device,
                message.topic,
            )
            return

        device = self._device_config(address)
        if command not in device.supported_commands:
            _LOG.warning(
                "Ignoring unsupported command device=%s type=%s command=%s",
                device.address,
                device.entity_type.name,
                command.name,
            )
            return

        try:
            encode_rf_command(address, command)
        except ValueError as exc:
            _LOG.warning(
                "Ignoring MQTT command that cannot be encoded device=%s command=%s error=%s",
                address,
                command.name,
                exc,
            )
            return

        self.execute_actions(
            self.state.optimistic_update(
                address,
                command,
            )
        )

    def _on_mqtt_bridge_command(
        self,
        message: MqttBridgeCommandMessage,
    ) -> None:
        _LOG.info(
            "MQTT bridge command received payload=%s topic=%s",
            message.payload,
            message.topic,
        )
        command = self._parse_bridge_command_payload(message.payload)
        _LOG.debug(
            "MQTT bridge payload parsed payload=%s command=%s",
            message.payload,
            command.name if command is not None else None,
        )

        if command is None:
            warning = (
                f"Ignoring unsupported MQTT bridge command payload "
                f"{message.payload!r} on {message.topic}"
            )
            _LOG.warning(warning)
            self.execute_action(
                self._bridge_response(
                    command=None,
                    success=False,
                    message=warning,
                )
            )
            return

        self._handle_bridge_command(command)

    def _handle_bridge_command(
        self,
        command: BridgeCommand,
    ) -> None:
        if command in {
            BridgeCommand.PRUNE_DISCOVERY,
            BridgeCommand.RESET_DISCOVERY,
        } and not self.config.enable_maintenance_buttons:
            self.execute_action(
                self._bridge_response(
                    command=command,
                    success=False,
                    message=(
                        "Maintenance command disabled; set "
                        "ENABLE_MAINTENANCE_BUTTONS=true to enable it."
                    ),
                )
            )
            return

        if command == BridgeCommand.PING:
            self.execute_action(
                self._bridge_response(
                    command=command,
                    success=True,
                    message="pong",
                )
            )
            return

        if command == BridgeCommand.STATUS:
            self.execute_action(
                self._bridge_response(
                    command=command,
                    success=True,
                    message="Bridge status returned.",
                    payload=self._bridge_status_payload(),
                )
            )
            return

        if command == BridgeCommand.SYNC:
            if not self.clients.mochad.connected:
                self.execute_action(
                    self._bridge_response(
                        command=command,
                        success=False,
                        message="Cannot sync because mochad is not connected.",
                    )
                )
                return

            try:
                self.execute_action(RequestStatusAction())
            except (ConnectionError, OSError) as exc:
                self.execute_action(
                    self._bridge_response(
                        command=command,
                        success=False,
                        message=f"Status sync request failed: {exc}",
                    )
                )
                return

            self.execute_action(
                self._bridge_response(
                    command=command,
                    success=True,
                    message="Status sync requested from mochad.",
                )
            )
            return

        if command == BridgeCommand.REDISCOVER:
            published = self._publish_current_discovery()
            self._save_discovery_registry(self._desired_discovery_topics())
            self.execute_action(
                self._bridge_response(
                    command=command,
                    success=True,
                    message="Discovery messages republished.",
                    payload={"published": published},
                )
            )
            return

        if command == BridgeCommand.PRUNE_DISCOVERY:
            result = self._run_discovery_cleanup(force=True)
            self.execute_action(
                self._bridge_response(
                    command=command,
                    success=result.get("success", False),
                    message=result.get("message", "Discovery prune completed."),
                    payload=result,
                )
            )
            return

        if command == BridgeCommand.RESET_DISCOVERY:
            result = self._reset_discovery()
            self.execute_action(
                self._bridge_response(
                    command=command,
                    success=result.get("success", False),
                    message=result.get("message", "Discovery reset completed."),
                    payload=result,
                )
            )
            return

        raise TypeError(
            f"Unhandled bridge command {command.name}."
        )

    def _on_mqtt_connected(self) -> None:
        _LOG.info("MQTT connected")
        self.execute_actions(self.state.mqtt_connected())
        self._publish_bridge_diagnostic_discovery()
        self._run_discovery_cleanup(force=False)
        self._write_health(
            "running" if self.state.available else "starting"
        )

    def _on_mqtt_disconnected(
        self,
        reason_code: int | None = None,
    ) -> None:
        _LOG.warning(
            "MQTT disconnected reason_code=%s",
            reason_code,
        )
        if self._stopping:
            _LOG.info("MQTT disconnected during bridge shutdown")
            return

        self.execute_actions(self.state.mqtt_disconnected())
        self._write_health("starting")

    def _on_mochad_connected(self) -> None:
        _LOG.info("mochad connected")
        self.execute_actions(self.state.mochad_connected())
        self._request_mochad_diagnostics()
        self._write_health(
            "running" if self.state.available else "starting"
        )

    def _on_mochad_disconnected(
        self,
        error: Exception | None = None,
    ) -> None:
        if error is not None:
            _LOG.warning("mochad disconnected: %s", error)
        else:
            _LOG.warning("mochad disconnected")

        self._mochad_diagnostics.usb_connected = None
        self._mochad_diagnostics.endpoints_ready = None
        self._mochad_diagnostics.transfers_ready = None
        self._mochad_diagnostics.last_updated = time.time()
        self.execute_actions(self.state.mochad_disconnected())
        self._write_health("starting")

    def _on_mochad_line(
        self,
        line: str,
    ) -> None:
        line = line.strip("\r\n")
        _LOG.info("mochad line received raw=%s", line)

        if self._handle_mochad_diagnostic_line(line):
            return

        event = self.parser.parse_line(line)
        _LOG.info(
            "mochad line parsed event_type=%s",
            type(event).__name__ if event is not None else "None",
        )
        self.execute_actions(self.state.apply(event))

    def _write_health(
        self,
        status: str,
    ) -> None:
        try:
            self._health_file.write_text(
                f"{status} {time.time():.3f}\n",
                encoding="utf-8",
            )
        except OSError as exc:
            _LOG.warning(
                "Could not write bridge health file path=%s error=%s",
                self._health_file,
                exc,
            )

    def _check_config_file_reload(
        self,
        force: bool = False,
    ) -> None:
        if self._config_file_path is None:
            return

        now = time.monotonic()

        if not force and now < self._next_config_reload_check:
            return

        self._next_config_reload_check = (
            now + self.config.config_reload_interval_seconds
        )
        signature = self._read_config_file_signature()

        if not force and signature == self._config_file_signature:
            return

        try:
            new_config = load_config()
        except ConfigError as exc:
            _LOG.warning(
                "Config file reload skipped path=%s error=%s",
                self._config_file_path,
                exc,
            )
            return

        self._apply_runtime_config(new_config)
        self._config_file_signature = signature

    def _apply_runtime_config(
        self,
        new_config: Config,
    ) -> None:
        old_devices = self.devices
        old_use_friendly_names = self.config.use_friendly_names
        old_allow_experimental = self.config.allow_experimental_profiles
        new_devices = {
            address: device
            for address, device in new_config.devices.items()
            if self._address_allowed_by_config(address)
        }

        if (
            new_devices == old_devices
            and new_config.use_friendly_names == old_use_friendly_names
            and new_config.allow_experimental_profiles
            == old_allow_experimental
        ):
            _LOG.info("Config file reloaded with no runtime changes")
            return

        self.config = replace(
            self.config,
            devices=new_config.devices,
            use_friendly_names=new_config.use_friendly_names,
            allow_experimental_profiles=(
                new_config.allow_experimental_profiles
            ),
        )
        self.devices = new_devices
        _LOG.info(
            "Config file reloaded devices=%d friendly_names=%s "
            "allow_experimental_profiles=%s",
            len(self.devices),
            self.config.use_friendly_names,
            self.config.allow_experimental_profiles,
        )

        if self.clients.mqtt.connected:
            published = self._publish_current_discovery()
            cleanup = self._run_discovery_cleanup(force=False)
            self.clients.mqtt.publish_status(
                self._bridge_status_payload(),
                retain=True,
            )
            _LOG.info(
                "Config reload discovery updated published=%d cleanup_success=%s",
                published,
                cleanup.get("success"),
            )

    def _read_config_file_signature(
        self,
    ) -> tuple[int, int] | None:
        if self._config_file_path is None:
            return None

        try:
            stat = self._config_file_path.stat()
        except OSError:
            return None

        return (stat.st_mtime_ns, stat.st_size)

    def _device_config(
        self,
        address: str,
    ) -> DeviceConfig:
        address = address.strip().upper()

        try:
            return self.devices[address]
        except KeyError:
            device = DeviceConfig(
                address=address,
                name=address,
            )
            self.devices[address] = device
            return device

    def _address_allowed_by_config(
        self,
        address: str,
    ) -> bool:
        if self.config.x10_housecodes is None:
            return True

        address = address.strip().upper()

        if not address:
            return False

        return address[0] in self.config.x10_housecodes

    def _publish_bridge_diagnostic_discovery(self) -> None:
        for message in self.discovery.bridge_diagnostic_messages(
            self._mochad_diagnostics
        ):
            _LOG.info(
                "MQTT publish bridge discovery topic=%s retain=%s",
                message.topic,
                message.retain,
            )
            self.clients.mqtt.publish_discovery(message)

    def _publish_current_discovery(self) -> int:
        messages: list[DiscoveryMessage] = []

        for device in self.devices.values():
            messages.extend(
                self.discovery.discovery_messages(
                    device,
                    self._mochad_diagnostics,
                )
            )

        messages.extend(
            self.discovery.bridge_diagnostic_messages(
                self._mochad_diagnostics
            )
        )

        for message in messages:
            _LOG.info(
                "MQTT publish discovery topic=%s retain=%s",
                message.topic,
                message.retain,
            )
            self.clients.mqtt.publish_discovery(message)

        return len(messages)

    def _run_discovery_cleanup(
        self,
        force: bool,
    ) -> dict:
        desired_topics = self._desired_discovery_topics()

        if not force and not self.config.discovery_cleanup:
            try:
                previous_topics = self.discovery_registry.load()
            except DiscoveryRegistryError as exc:
                _LOG.warning(
                    "Discovery registry load failed while cleanup disabled: %s",
                    exc,
                )
                previous_topics = set()

            saved = self._save_discovery_registry(
                previous_topics | desired_topics
            )
            _LOG.info(
                "Discovery registry updated desired=%d tracked=%d cleanup_enabled=%s registry=%s",
                len(desired_topics),
                len(previous_topics | desired_topics),
                self.config.discovery_cleanup,
                self.config.discovery_registry_path,
            )
            return {
                "success": saved,
                "message": "Discovery registry updated.",
                "desired": len(desired_topics),
                "tracked": len(previous_topics | desired_topics),
                "stale": len(previous_topics - desired_topics),
                "cleanup_enabled": self.config.discovery_cleanup,
            }

        try:
            previous_topics = self.discovery_registry.load()
        except DiscoveryRegistryError as exc:
            _LOG.warning(
                "Discovery cleanup skipped: %s",
                exc,
            )
            return {
                "success": False,
                "message": f"Discovery cleanup skipped: {exc}",
                "desired": len(desired_topics),
                "stale": 0,
                "cleanup_enabled": self.config.discovery_cleanup,
            }

        stale_topics = sorted(previous_topics - desired_topics)

        for topic in stale_topics:
            _LOG.info(
                "MQTT clear stale discovery topic=%s",
                topic,
            )
            self.clients.mqtt.publish_discovery(
                self._empty_discovery_message(topic)
            )

        if not self._save_discovery_registry(desired_topics):
            return {
                "success": False,
                "message": "Discovery cleanup ran but registry save failed.",
                "desired": len(desired_topics),
                "stale": len(stale_topics),
                "cleanup_enabled": self.config.discovery_cleanup,
            }

        _LOG.info(
            "Discovery cleanup complete desired=%d stale=%d registry=%s",
            len(desired_topics),
            len(stale_topics),
            self.config.discovery_registry_path,
        )
        return {
            "success": True,
            "message": "Discovery cleanup complete.",
            "desired": len(desired_topics),
            "stale": len(stale_topics),
            "cleanup_enabled": self.config.discovery_cleanup,
        }

    def _reset_discovery(self) -> dict:
        desired_topics = self._desired_discovery_topics()

        try:
            registry_topics = self.discovery_registry.load()
        except DiscoveryRegistryError as exc:
            _LOG.warning(
                "Discovery registry load failed before reset: %s",
                exc,
            )
            registry_topics = set()

        topics_to_clear = sorted(desired_topics | registry_topics)

        for topic in topics_to_clear:
            _LOG.info(
                "MQTT clear discovery topic=%s",
                topic,
            )
            self.clients.mqtt.publish_discovery(
                self._empty_discovery_message(topic)
            )

        saved = self._save_discovery_registry(set())

        return {
            "success": saved,
            "message": "Discovery reset complete."
            if saved
            else "Discovery reset ran but registry save failed.",
            "cleared": len(topics_to_clear),
        }

    def _desired_discovery_topics(self) -> set[str]:
        messages = []

        for device in self.devices.values():
            messages.extend(
                self.discovery.discovery_messages(
                    device,
                    self._mochad_diagnostics,
                )
            )

        messages.extend(
            self.discovery.bridge_diagnostic_messages(
                self._mochad_diagnostics
            )
        )

        return {message.topic for message in messages}

    def _save_discovery_registry(
        self,
        desired_topics: set[str],
    ) -> bool:
        try:
            self.discovery_registry.save(desired_topics)
        except DiscoveryRegistryError as exc:
            _LOG.warning(
                "Discovery registry save failed: %s",
                exc,
            )
            return False

        return True

    @staticmethod
    def _empty_discovery_message(
        topic: str,
    ) -> DiscoveryMessage:
        return DiscoveryMessage(
            topic=topic,
            payload="",
            retain=True,
        )

    def _request_mochad_diagnostics(self) -> None:
        for command in ("hello", "capabilities", "health"):
            try:
                _LOG.info("Requesting mochad diagnostic command=%s", command)
                self.execute_action(
                    SendMochadCommandAction(command=command)
                )
            except (ConnectionError, OSError) as exc:
                _LOG.warning(
                    "mochad diagnostic request failed command=%s error=%s",
                    command,
                    exc,
                )
                return

    def _handle_mochad_diagnostic_line(
        self,
        line: str,
    ) -> bool:
        if not line.startswith("{"):
            return False

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return False

        if not isinstance(payload, dict):
            return False

        kind = self._mochad_diagnostic_kind(payload)

        if kind is None:
            return False

        self._merge_mochad_diagnostics(payload)
        _LOG.info(
            "mochad diagnostic received kind=%s version=%s controller=%s usb_connected=%s",
            kind,
            self._mochad_diagnostics.version,
            self._mochad_diagnostics.controller,
            self._mochad_diagnostics.usb_connected,
        )

        if self.clients.mqtt.connected:
            self.clients.mqtt.publish_status(
                self._bridge_status_payload(),
                retain=True,
            )

            if kind in {"hello", "health"}:
                self._publish_current_discovery()
                self._save_discovery_registry(
                    self._desired_discovery_topics()
                )

        if kind == "health":
            self._flush_queued_device_commands()

        return True

    @staticmethod
    def _mochad_diagnostic_kind(
        payload: dict,
    ) -> str | None:
        if payload.get("diagnostics") is True and "daemon" in payload:
            return "hello"

        if payload.get("json") is True and "commands" in payload:
            return "capabilities"

        if "usb_connected" in payload or "controller" in payload:
            return "health"

        return None

    def _merge_mochad_diagnostics(
        self,
        payload: dict,
    ) -> None:
        diagnostics = self._mochad_diagnostics
        diagnostics.last_updated = time.time()

        for field_name in (
            "daemon",
            "version",
            "upstream_base",
            "diagnostics",
            "json",
            "single_line",
            "raw_data",
            "uptime_seconds",
            "usb_connected",
            "controller",
            "endpoints_ready",
            "transfers_ready",
            "clients_total",
            "listeners",
        ):
            if field_name in payload:
                setattr(diagnostics, field_name, payload[field_name])

        for field_name in ("commands", "legacy_commands"):
            if field_name in payload and isinstance(payload[field_name], list):
                setattr(
                    diagnostics,
                    field_name,
                    tuple(str(item) for item in payload[field_name]),
                )

    def _bridge_status_payload(
        self,
        status: str | None = None,
        mqtt_connected: bool | None = None,
        mochad_connected: bool | None = None,
    ) -> dict:
        snapshot = self.state.snapshot()
        status = status or ("online" if self.state.available else "offline")

        return {
            "bridge": {
                "name": BRIDGE_NAME,
                "version": BRIDGE_VERSION,
            },
            "status": status,
            "available": self.state.available,
            "mqtt_connected": (
                self.clients.mqtt.connected
                if mqtt_connected is None
                else mqtt_connected
            ),
            "mochad_connected": (
                self.clients.mochad.connected
                if mochad_connected is None
                else mochad_connected
            ),
            "configured_devices": len(self.devices),
            "known_devices": len(snapshot),
            "dropped_mqtt_publishes": getattr(
                self,
                "_dropped_mqtt_publishes",
                0,
            ),
            "queued_device_commands": len(
                getattr(self, "_queued_device_commands", ())
            ),
            "dropped_device_commands": getattr(
                self,
                "_dropped_device_commands",
                0,
            ),
            "mqtt": self._mqtt_status_payload(),
            "mochad": self._mochad_diagnostics_payload(),
            "device_profiles": {
                "allow_experimental": (
                    getattr(
                        self.config,
                        "allow_experimental_profiles",
                        False,
                    )
                ),
                "configured": configured_profile_diagnostics(self.devices),
            },
        }

    def _mqtt_status_payload(self) -> dict:
        tls_config = self.config.mqtt_tls

        return {
            "tls": {
                "enabled": tls_config.enabled,
                "custom_ca": bool(tls_config.ca_file),
                "client_certificate": bool(
                    tls_config.cert_file and tls_config.key_file
                ),
            },
        }

    def _mochad_diagnostics_payload(self) -> dict:
        diagnostics = self._mochad_diagnostics

        return {
            "daemon": diagnostics.daemon,
            "version": diagnostics.version,
            "upstream_base": diagnostics.upstream_base,
            "features": {
                "diagnostics": diagnostics.diagnostics,
                "json": diagnostics.json,
                "single_line": diagnostics.single_line,
                "raw_data": diagnostics.raw_data,
            },
            "health": {
                "uptime_seconds": diagnostics.uptime_seconds,
                "usb_connected": diagnostics.usb_connected,
                "controller": diagnostics.controller,
                "endpoints_ready": diagnostics.endpoints_ready,
                "transfers_ready": diagnostics.transfers_ready,
            },
            "last_updated": diagnostics.last_updated,
        }

    @staticmethod
    def _bridge_response(
        command: BridgeCommand | None,
        success: bool,
        message: str,
        payload: dict | None = None,
    ) -> PublishBridgeResponseAction:
        return PublishBridgeResponseAction(
            command=command,
            success=success,
            message=message,
            payload=payload or {},
        )

    @staticmethod
    def _parse_command_payload(
        payload: str,
    ) -> Command | None:
        return COMMAND_PAYLOADS.get(
            payload.strip().upper()
        )

    @staticmethod
    def _parse_bridge_command_payload(
        payload: str,
    ) -> BridgeCommand | None:
        normalized = payload.strip().upper()

        if not normalized:
            return None

        normalized = normalized.replace("-", "_").replace(" ", "_")

        try:
            return BridgeCommand[normalized]
        except KeyError:
            return BRIDGE_COMMAND_ALIASES.get(normalized)
