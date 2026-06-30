"""
Thin bridge orchestrator.

bridge.py wires the transport, protocol, state, and discovery layers together.
It does not own device state, parse mochad text directly, generate discovery
payloads, or construct MQTT topics.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from config import Config
from discovery import DiscoveryManager
from models import (
    BridgeAction,
    Command,
    DeviceConfig,
    LogUnknownEventAction,
    PublishAvailabilityAction,
    PublishDiscoveryAction,
    PublishEventAction,
    PublishStateAction,
    PublishStatusAction,
    RequestStatusAction,
    SendDeviceCommandAction,
    SendMochadCommandAction,
)
from mochad_client import MochadClient
from mqtt_client import MqttClient, MqttCommandMessage
from protocol import ProtocolParser, encode_rf_command
from state import StateManager


_LOG = logging.getLogger(__name__)

DEFAULT_HEALTH_FILE = "/tmp/mqtt-mochad-bridge.health"


COMMAND_PAYLOADS = {
    "ON": Command.ON,
    "OFF": Command.OFF,
    "DIM": Command.DIM,
    "BRIGHT": Command.BRIGHT,
}


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
        self.devices = dict(config.devices)
        _LOG.info(
            "Loaded %d configured X10 device(s)",
            len(self.devices),
        )
        self.parser = parser or ProtocolParser()
        _LOG.info("Protocol parser ready")
        self.state = state or StateManager(
            devices=self.devices,
            optimistic_updates=config.optimistic_updates,
        )
        _LOG.info(
            "State manager ready optimistic_updates=%s",
            config.optimistic_updates,
        )
        self.discovery = discovery or DiscoveryManager(
            discovery_prefix=config.mqtt_discovery_prefix,
            base_topic=config.mqtt_base_topic,
        )
        _LOG.info(
            "Discovery manager ready prefix=%s base_topic=%s",
            config.mqtt_discovery_prefix,
            config.mqtt_base_topic,
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
        if config.debug_wire:
            _LOG.info("Wire debug logging enabled")

        self._running = False
        self._health_file = Path(
            os.getenv("BRIDGE_HEALTH_FILE", DEFAULT_HEALTH_FILE)
        )
        self._wire_callbacks()
        _LOG.info(
            "Bridge initialized successfully elapsed=%.3fs",
            time.monotonic() - started,
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
        self.clients.mochad.stop()
        _LOG.info(
            "mochad client stopped elapsed=%.3fs",
            time.monotonic() - started,
        )
        self.clients.mqtt.disconnect()
        _LOG.info(
            "MQTT client stopped elapsed=%.3fs",
            time.monotonic() - started,
        )
        self._write_health("stopped")

    def run_forever(self) -> None:
        self.start()

        while self._running:
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
                },
                retain=False,
            )
            return

        if isinstance(action, PublishDiscoveryAction):
            device = self._device_config(action.address)

            for message in self.discovery.discovery_messages(device):
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
                {
                    "status": action.status,
                    "mqtt_connected": action.mqtt_connected,
                    "mochad_connected": action.mochad_connected,
                },
                retain=action.retain,
            )
            return

        if isinstance(action, SendMochadCommandAction):
            self.clients.mochad.send_line(action.command)
            return

        if isinstance(action, SendDeviceCommandAction):
            _LOG.debug(
                "Executing SendDeviceCommandAction address=%s command=%s",
                action.address,
                action.command.name,
            )
            self.clients.mochad.send_line(
                encode_rf_command(
                    action.address,
                    action.command,
                )
            )
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

    def _wire_callbacks(self) -> None:
        _LOG.info("Wiring bridge callbacks")
        self.clients.mqtt.set_command_callback(self._on_mqtt_command)
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

        self.execute_actions(
            self.state.optimistic_update(
                message.device,
                command,
            )
        )

    def _on_mqtt_connected(self) -> None:
        _LOG.info("MQTT connected")
        self.execute_actions(self.state.mqtt_connected())
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
        self.execute_actions(self.state.mqtt_disconnected())
        self._write_health("starting")

    def _on_mochad_connected(self) -> None:
        _LOG.info("mochad connected")
        self.execute_actions(self.state.mochad_connected())
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

        self.execute_actions(self.state.mochad_disconnected())
        self._write_health("starting")

    def _on_mochad_line(
        self,
        line: str,
    ) -> None:
        line = line.strip("\r\n")
        _LOG.info("mochad line received raw=%s", line)
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

    @staticmethod
    def _parse_command_payload(
        payload: str,
    ) -> Command | None:
        return COMMAND_PAYLOADS.get(
            payload.strip().upper()
        )
