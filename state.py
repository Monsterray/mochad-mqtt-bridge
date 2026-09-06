"""
Central state authority for the bridge.

The StateManager owns all mutable bridge state. It accepts typed events and
connection notifications, then returns typed actions for bridge.py to execute.
It does not know about MQTT topics, Home Assistant payloads, sockets, regexes,
or environment variables.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock

from models import (
    BridgeAction,
    BridgeStatistics,
    Command,
    DeviceConfig,
    DeviceEvent,
    DeviceState,
    Direction,
    HouseEvent,
    LogUnknownEventAction,
    PhysicalConfirmation,
    PublishAttributesAction,
    PublishAvailabilityAction,
    PublishCommandEventAction,
    PublishDiscoveryAction,
    PublishEventAction,
    PublishStateAction,
    PublishStatusAction,
    RequestStatusAction,
    SendDeviceCommandAction,
    StateConfidence,
    StateProvenance,
    StatusSnapshot,
    UnknownEvent,
)

STATE_COMMANDS = {
    Command.ON,
    Command.OFF,
    Command.DIM,
    Command.BRIGHT,
    Command.STATUS_ON,
    Command.STATUS_OFF,
}

ON_COMMANDS = {
    Command.ON,
    Command.BRIGHT,
    Command.STATUS_ON,
}

OFF_COMMANDS = {
    Command.OFF,
    Command.STATUS_OFF,
}


class StateManager:
    """
    Own all bridge state and emit actions for side effects.
    """

    def __init__(
        self,
        devices: Iterable[DeviceConfig] | dict[str, DeviceConfig] | None = None,
        optimistic_updates: bool = True,
        allowed_housecodes: Iterable[str] | None = None,
        stale_after: timedelta | None = None,
    ) -> None:
        self._lock = RLock()
        self._devices: dict[str, DeviceState] = {}
        self._device_configs: dict[str, DeviceConfig] = {}
        self._statistics = BridgeStatistics()
        self._mqtt_connected = False
        self._mqtt_has_connected = False
        self._mochad_connected = False
        self._available = False
        self._mqtt_generation = 0
        self._optimistic_updates = optimistic_updates
        self._stale_after = stale_after
        self._allowed_housecodes = self._normalize_housecodes(
            allowed_housecodes
        )

        if isinstance(devices, dict):
            devices = devices.values()

        for device in devices or ():
            if self._address_allowed(device.address):
                self._device_configs[device.address.strip().upper()] = device
                self._ensure_device(device.address)

    def apply(
        self,
        event: DeviceEvent | HouseEvent | StatusSnapshot | UnknownEvent | None,
    ) -> list[BridgeAction]:
        """
        Apply one inbound event and return actions for the bridge to execute.
        """

        if event is None:
            return []

        with self._lock:
            if isinstance(event, DeviceEvent):
                return self._apply_device_event(event)

            if isinstance(event, HouseEvent):
                return self._apply_house_event(event)

            if isinstance(event, StatusSnapshot):
                return self._apply_status_snapshot(event)

            if isinstance(event, UnknownEvent):
                self._statistics.unknown_packets += 1
                return [LogUnknownEventAction(event=event)]

            raise TypeError(
                f"Unsupported state event {type(event).__name__}."
            )

    def optimistic_update(
        self,
        address: str,
        command: Command,
    ) -> list[BridgeAction]:
        """
        Record a requested outbound device command.
        """

        with self._lock:
            if not self._address_allowed(address):
                return []

            state = self._ensure_device(address)
            device = self._device_config(state.address)
            if command not in device.supported_commands:
                return []

            state.pending_command = command
            state.last_command_sent = command
            self._statistics.commands_sent += 1

            actions = self._discovery_actions(state)
            actions.append(
                SendDeviceCommandAction(
                    address=state.address,
                    command=command,
                )
            )

            if not device.stateful:
                actions.append(
                    PublishCommandEventAction(
                        address=state.address,
                        payload={
                            "timestamp": self._now().isoformat(),
                            "device": state.address,
                            "command": command.name,
                            "stateful": False,
                            "transmission": "unconfirmed",
                            "confirmed": False,
                            "message": (
                                "Command sent to mochad; physical device "
                                "state is unconfirmed."
                            ),
                        },
                        retain=False,
                    )
                )
                return actions

            if self._optimistic_updates:
                actions.extend(
                    self._set_device_state(
                        state=state,
                        command=command,
                        now=self._now(),
                        retain=True,
                        clear_pending=False,
                        confidence=StateConfidence.ASSUMED,
                        provenance=StateProvenance.MQTT_COMMAND,
                    )
                )
            else:
                actions.append(self._attributes_action(state))

            return actions

    def mqtt_connected(self) -> list[BridgeAction]:
        with self._lock:
            was_connected = self._mqtt_connected
            self._mqtt_connected = True
            self._mqtt_generation += 1

            if self._mqtt_has_connected and not was_connected:
                self._statistics.mqtt_reconnects += 1

            self._mqtt_has_connected = True
            self._statistics.mqtt_connections += 1

            actions: list[BridgeAction] = self._bridge_status_actions()

            for state in self._devices.values():
                state.discovered = False
                actions.append(
                    PublishDiscoveryAction(address=state.address)
                )
                self._statistics.discovery_messages += 1
                state.discovered = True

                if state.current_state is not None:
                    actions.append(
                        PublishStateAction(
                            address=state.address,
                            state=state.current_state,
                            retain=True,
                        )
                    )
                    actions.append(self._attributes_action(state))

            return actions

    def mqtt_disconnected(self) -> list[BridgeAction]:
        with self._lock:
            if self._mqtt_connected:
                self._statistics.mqtt_disconnects += 1

            self._mqtt_connected = False
            return self._bridge_status_actions()

    def mochad_connected(self) -> list[BridgeAction]:
        with self._lock:
            self._mochad_connected = True
            self._statistics.mochad_reconnects += 1
            actions: list[BridgeAction] = self._bridge_status_actions()
            actions.append(RequestStatusAction())
            return actions

    def mochad_disconnected(self) -> list[BridgeAction]:
        with self._lock:
            self._mochad_connected = False

            for state in self._devices.values():
                state.available = False

            return self._bridge_status_actions()

    def snapshot(self) -> dict[str, DeviceState]:
        with self._lock:
            self._refresh_staleness(self._now())
            return deepcopy(self._devices)

    def statistics(self) -> BridgeStatistics:
        with self._lock:
            return deepcopy(self._statistics)

    @property
    def mqtt_generation(self) -> int:
        with self._lock:
            return self._mqtt_generation

    @property
    def available(self) -> bool:
        with self._lock:
            return self._bridge_available()

    def _apply_device_event(
        self,
        event: DeviceEvent,
    ) -> list[BridgeAction]:
        if not self._address_allowed(event.address):
            return []

        self._statistics.events_received += 1

        state = self._ensure_device(event.address)
        device = self._device_config(state.address)
        state.available = True
        state.last_seen = event.timestamp

        actions = self._discovery_actions(state)
        actions.append(
            PublishEventAction(event=event)
        )

        if not device.stateful or event.command not in STATE_COMMANDS:
            return actions

        if event.direction is Direction.RX:
            confidence = StateConfidence.REPORTED
            provenance = StateProvenance.DEVICE_EVENT
            observed_at = event.timestamp
        else:
            # A Tx echo is transport evidence, not a device state report.
            same_value = (
                state.current_state
                == self._authoritative_state(event.command)
            )
            confidence = (
                state.confidence
                if same_value
                else StateConfidence.UNKNOWN
            )
            provenance = (
                state.provenance
                if same_value
                else StateProvenance.TRANSMITTED_EVENT
            )
            observed_at = state.observed_at if same_value else None

        actions.extend(
            self._set_device_state(
                state=state,
                command=event.command,
                now=event.timestamp,
                retain=True,
                clear_pending=True,
                confidence=confidence,
                provenance=provenance,
                observed_at=observed_at,
            )
        )

        return actions

    def _apply_house_event(
        self,
        event: HouseEvent,
    ) -> list[BridgeAction]:
        if not self._house_allowed(event.house):
            return []

        self._statistics.events_received += 1

        if event.command not in {
            Command.ALL_UNITS_OFF,
            Command.ALL_LIGHTS_OFF,
            Command.ALL_LIGHTS_ON,
        }:
            return []

        actions: list[BridgeAction] = []

        for state in self._devices_for_house(event.house):
            device = self._device_config(state.address)
            if not device.stateful:
                continue

            if not self._device_responds_to_house_command(
                device,
                event.command,
            ):
                continue

            state.available = True
            state.last_seen = event.timestamp

            if event.command in {
                Command.ALL_UNITS_OFF,
                Command.ALL_LIGHTS_OFF,
            }:
                command = Command.OFF
            else:
                command = Command.ON

            if event.direction is Direction.RX:
                confidence = StateConfidence.INFERRED
                provenance = StateProvenance.PROFILE_INFERENCE
            else:
                same_value = state.current_state is command
                confidence = (
                    state.confidence
                    if same_value
                    else StateConfidence.UNKNOWN
                )
                provenance = (
                    state.provenance
                    if same_value
                    else StateProvenance.TRANSMITTED_EVENT
                )

            actions.extend(
                self._set_device_state(
                    state=state,
                    command=command,
                    now=event.timestamp,
                    retain=True,
                    clear_pending=True,
                    confidence=confidence,
                    provenance=provenance,
                )
            )

        return actions

    @staticmethod
    def _device_responds_to_house_command(
        device: DeviceConfig,
        command: Command,
    ) -> bool:
        if command == Command.ALL_UNITS_OFF:
            return device.all_units_off_response

        if command == Command.ALL_LIGHTS_OFF:
            return device.all_lights_off_response

        if command == Command.ALL_LIGHTS_ON:
            return device.all_lights_on_response

        return False

    def _apply_status_snapshot(
        self,
        snapshot: StatusSnapshot,
    ) -> list[BridgeAction]:
        self._statistics.status_syncs += 1

        now = self._now()
        actions: list[BridgeAction] = []

        for address, command in snapshot.devices.items():
            if not self._address_allowed(address):
                continue

            state = self._ensure_device(address)
            device = self._device_config(state.address)
            if not device.stateful:
                continue

            state.available = True
            state.last_seen = now

            actions.extend(
                self._set_device_state(
                    state=state,
                    command=command,
                    now=now,
                    retain=True,
                    clear_pending=True,
                    confidence=StateConfidence.INFERRED,
                    provenance=StateProvenance.STATUS_SYNC,
                )
            )

        return actions

    def _set_device_state(
        self,
        state: DeviceState,
        command: Command,
        now: datetime,
        retain: bool,
        clear_pending: bool,
        confidence: StateConfidence,
        provenance: StateProvenance,
        observed_at: datetime | None = None,
    ) -> list[BridgeAction]:
        command = self._authoritative_state(command)
        value_changed = state.current_state != command
        previous_evidence = (
            state.confidence,
            state.provenance,
            state.updated_at,
            state.observed_at,
            state.expires_at,
            state.stale,
        )

        state.confidence = confidence
        state.provenance = provenance
        state.updated_at = now
        state.observed_at = observed_at
        state.expires_at = (
            now + self._stale_after
            if self._stale_after is not None
            else None
        )
        state.stale = False
        if value_changed and state.physical_confirmation in {
            PhysicalConfirmation.NOT_OBSERVED,
            PhysicalConfirmation.OBSERVED,
            PhysicalConfirmation.CONTRADICTED,
        }:
            state.physical_confirmation = PhysicalConfirmation.UNKNOWN

        if not value_changed:
            self._statistics.duplicates += 1
            state.last_seen = now
            if clear_pending:
                self._clear_confirmed_pending(state, command)
            current_evidence = (
                state.confidence,
                state.provenance,
                state.updated_at,
                state.observed_at,
                state.expires_at,
                state.stale,
            )
            if current_evidence != previous_evidence:
                return [self._attributes_action(state)]
            return []

        state.previous_state = state.current_state
        state.current_state = command
        state.last_seen = now
        state.last_changed = now
        if clear_pending:
            self._clear_confirmed_pending(state, command)
        self._statistics.state_changes += 1

        return [
            PublishStateAction(
                address=state.address,
                state=command,
                retain=retain,
            ),
            self._attributes_action(state),
        ]

    def _attributes_action(
        self,
        state: DeviceState,
    ) -> PublishAttributesAction:
        return PublishAttributesAction(
            address=state.address,
            payload={
                "last_command_sent": (
                    state.last_command_sent.name
                    if state.last_command_sent is not None
                    else None
                ),
                "optimistic": self._optimistic_updates,
                "state": (
                    state.current_state.name
                    if state.current_state is not None
                    else None
                ),
                "confidence": state.confidence.value,
                "provenance": state.provenance.value,
                "updated_at": self._isoformat(state.updated_at),
                "observed_at": self._isoformat(state.observed_at),
                "expires_at": self._isoformat(state.expires_at),
                "stale": state.stale,
                "physical_confirmation": state.physical_confirmation.value,
            },
            retain=True,
        )

    def _refresh_staleness(self, now: datetime) -> None:
        for state in self._devices.values():
            if state.expires_at is not None and now >= state.expires_at:
                state.stale = True

    def _discovery_actions(
        self,
        state: DeviceState,
    ) -> list[BridgeAction]:
        if not self._mqtt_connected or state.discovered:
            return []

        state.discovered = True
        self._statistics.discovery_messages += 1

        return [
            PublishDiscoveryAction(address=state.address)
        ]

    def _ensure_device(self, address: str) -> DeviceState:
        address = address.strip().upper()

        try:
            return self._devices[address]
        except KeyError:
            state = DeviceState(address=address)
            self._devices[address] = state
            return state

    def _device_config(self, address: str) -> DeviceConfig:
        address = address.strip().upper()
        try:
            return self._device_configs[address]
        except KeyError:
            return DeviceConfig(
                address=address,
                name=address,
            )

    def _address_allowed(
        self,
        address: str,
    ) -> bool:
        address = address.strip().upper()

        if not address:
            return False

        return self._house_allowed(address[0])

    def _house_allowed(
        self,
        house: str,
    ) -> bool:
        if self._allowed_housecodes is None:
            return True

        return house.strip().upper() in self._allowed_housecodes

    @staticmethod
    def _normalize_housecodes(
        housecodes: Iterable[str] | None,
    ) -> frozenset[str] | None:
        if housecodes is None:
            return None

        normalized = frozenset(
            code.strip().upper()
            for code in housecodes
            if code.strip()
        )

        if not normalized:
            return None

        return normalized

    def _devices_for_house(self, house: str) -> list[DeviceState]:
        house = house.strip().upper()
        return [
            state
            for address, state in self._devices.items()
            if address.startswith(house)
        ]

    def _clear_confirmed_pending(
        self,
        state: DeviceState,
        command: Command,
    ) -> None:
        if state.pending_command == command:
            state.pending_command = None

    def _bridge_available(self) -> bool:
        self._available = self._mqtt_connected and self._mochad_connected
        return self._available

    def _bridge_status_actions(self) -> list[BridgeAction]:
        online = self._bridge_available()
        return [
            PublishAvailabilityAction(online=online),
            PublishStatusAction(
                status="online" if online else "offline",
                mqtt_connected=self._mqtt_connected,
                mochad_connected=self._mochad_connected,
            ),
        ]

    @staticmethod
    def _authoritative_state(command: Command) -> Command:
        if command in ON_COMMANDS:
            return Command.ON

        if command in OFF_COMMANDS:
            return Command.OFF

        return command

    @staticmethod
    def _isoformat(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
