"""
Central state authority for the bridge.

The StateManager owns all mutable bridge state. It accepts typed events and
connection notifications, then returns typed actions for bridge.py to execute.
It does not know about MQTT topics, Home Assistant payloads, sockets, regexes,
or environment variables.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Iterable

from models import (
    BridgeAction,
    BridgeStatistics,
    Command,
    DeviceConfig,
    DeviceEvent,
    DeviceState,
    HouseEvent,
    LogUnknownEventAction,
    PublishAvailabilityAction,
    PublishDiscoveryAction,
    PublishEventAction,
    PublishStateAction,
    PublishStatusAction,
    RequestStatusAction,
    SendDeviceCommandAction,
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
    ) -> None:
        self._lock = RLock()
        self._devices: dict[str, DeviceState] = {}
        self._statistics = BridgeStatistics()
        self._mqtt_connected = False
        self._mqtt_has_connected = False
        self._mochad_connected = False
        self._available = False
        self._mqtt_generation = 0
        self._optimistic_updates = optimistic_updates

        if isinstance(devices, dict):
            devices = devices.values()

        for device in devices or ():
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
            state = self._ensure_device(address)
            state.pending_command = command
            self._statistics.commands_sent += 1

            actions = self._discovery_actions(state)
            actions.append(
                SendDeviceCommandAction(
                    address=state.address,
                    command=command,
                )
            )

            if self._optimistic_updates:
                actions.extend(
                    self._set_device_state(
                        state=state,
                        command=command,
                        now=self._now(),
                        retain=True,
                        clear_pending=False,
                    )
                )

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
        self._statistics.events_received += 1

        state = self._ensure_device(event.address)
        state.available = True
        state.last_seen = event.timestamp

        actions = self._discovery_actions(state)
        actions.append(
            PublishEventAction(event=event)
        )

        if event.command not in STATE_COMMANDS:
            return actions

        actions.extend(
            self._set_device_state(
                state=state,
                command=event.command,
                now=event.timestamp,
                retain=True,
                clear_pending=True,
            )
        )

        return actions

    def _apply_house_event(
        self,
        event: HouseEvent,
    ) -> list[BridgeAction]:
        self._statistics.events_received += 1

        if event.command not in {
            Command.ALL_UNITS_OFF,
            Command.ALL_LIGHTS_OFF,
            Command.ALL_LIGHTS_ON,
        }:
            return []

        actions: list[BridgeAction] = []

        for state in self._devices_for_house(event.house):
            state.available = True
            state.last_seen = event.timestamp

            if event.command in {
                Command.ALL_UNITS_OFF,
                Command.ALL_LIGHTS_OFF,
            }:
                command = Command.OFF
            else:
                command = Command.ON

            actions.extend(
                self._set_device_state(
                    state=state,
                    command=command,
                    now=event.timestamp,
                    retain=True,
                    clear_pending=True,
                )
            )

        return actions

    def _apply_status_snapshot(
        self,
        snapshot: StatusSnapshot,
    ) -> list[BridgeAction]:
        self._statistics.status_syncs += 1

        now = self._now()
        actions: list[BridgeAction] = []

        for address, command in snapshot.devices.items():
            state = self._ensure_device(address)
            state.available = True
            state.last_seen = now

            actions.extend(
                self._set_device_state(
                    state=state,
                    command=command,
                    now=now,
                    retain=True,
                    clear_pending=True,
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
    ) -> list[BridgeAction]:
        command = self._authoritative_state(command)

        if state.current_state == command:
            self._statistics.duplicates += 1
            state.last_seen = now
            if clear_pending:
                self._clear_confirmed_pending(state, command)
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
            )
        ]

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
    def _now() -> datetime:
        return datetime.now(UTC)
