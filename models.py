"""
models.py

Core data models for the MQTT <-> mochad bridge.

These models intentionally contain no application logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
import json
import re
from abc import ABC



###############################################################################
# Enumerations
###############################################################################


class Direction(Enum):
    """Direction of an X10 event."""

    RX = auto()
    TX = auto()


class Transport(Enum):
    """Transport used for an X10 event."""

    RF = auto()
    PL = auto()
    RFSEC = auto()
    RFCAM = auto()
    UNKNOWN = auto()


class Command(Enum):
    """Supported X10 commands."""

    ON = auto()
    OFF = auto()

    DIM = auto()
    BRIGHT = auto()

    ALL_LIGHTS_ON = auto()
    ALL_LIGHTS_OFF = auto()
    ALL_UNITS_OFF = auto()

    STATUS_REQUEST = auto()
    STATUS_ON = auto()
    STATUS_OFF = auto()

    UNKNOWN = auto()


class DeviceType(Enum):
    """Home Assistant entity type."""

    SWITCH = auto()
    LIGHT = auto()

class DeviceCapability(Enum):
    """Capabilities supported by an X10 device."""

    ON_OFF = auto()

    DIM = auto()

    STATUS = auto()

    ALL_LIGHTS = auto()

    ALL_UNITS = auto()

class BridgeHealth(Enum):
    """Overall bridge health."""

    STARTING = auto()

    MQTT_DISCONNECTED = auto()

    MOCHAD_DISCONNECTED = auto()

    SYNCHRONIZING = auto()

    ONLINE = auto()

    STOPPING = auto()


###############################################################################
# Configuration
###############################################################################


@dataclass(slots=True, frozen=True)
class DeviceConfig:

    address: str

    name: str

    entity_type: DeviceType = DeviceType.SWITCH

    capabilities: frozenset[DeviceCapability] = field(
        default_factory=lambda: frozenset(
            {
                DeviceCapability.ON_OFF,
            }
        )
    )

###############################################################################
# Runtime State
###############################################################################


@dataclass(slots=True)
class DeviceState:
    """
    Current known state of a device.
    """

    address: str

    current_state: Command | None = None

    previous_state: Command | None = None

    last_seen: datetime | None = None

    last_changed: datetime | None = None

    pending_command: Command | None = None

    discovered: bool = False

    available: bool = False


###############################################################################
# Events
###############################################################################


@dataclass(slots=True, frozen=True)
class BridgeEvent:
    """
    One parsed event from mochad.
    """

    timestamp: datetime

    direction: Direction

    transport: Transport

    command: Command


@dataclass(slots=True, frozen=True)
class DeviceEvent(BridgeEvent):
    """
    Event affecting a specific device.

    Example:

        Tx RF HouseUnit: A1 Func: On
    """

    address: str


@dataclass(slots=True, frozen=True)
class HouseEvent(BridgeEvent):
    """
    Event affecting an entire house code.

    Example:

        Tx PL House: A Func: All units off
    """

    house: str

@dataclass(slots=True, frozen=True)
class UnknownEvent:

    timestamp: datetime

    raw: str

###############################################################################
# Status Snapshot
###############################################################################


@dataclass(slots=True)
class StatusSnapshot:
    """
    Result of parsing an 'st' response.
    """

    devices: dict[str, Command] = field(
        default_factory=dict
    )

    completed: bool = False

class ConnectionState(Enum):
    """Connection state for MQTT and mochad."""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    SYNCHRONIZED = auto()

###############################################################################
# Bridge Statistics
###############################################################################


@dataclass(slots=True)
class BridgeStatistics:
    """
    Runtime statistics.
    """

    events_received: int = 0

    commands_sent: int = 0

    duplicates: int = 0

    state_changes: int = 0

    mqtt_connections: int = 0

    mqtt_disconnects: int = 0

    mqtt_reconnects: int = 0

    mochad_reconnects: int = 0

    discovery_messages: int = 0

    status_syncs: int = 0

    unknown_packets: int = 0


BridgeStats = BridgeStatistics


###############################################################################
# MQTT Payloads
###############################################################################


class JSONPayload:
    """Base class for MQTT JSON payloads."""

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

@dataclass(slots=True, frozen=True)
class DiscoveryPayload(JSONPayload):
    """
    Home Assistant MQTT Discovery payload.
    """

    name: str
    unique_id: str

    command_topic: str
    state_topic: str
    availability_topic: str

    payload_on: str = "ON"
    payload_off: str = "OFF"

    retain: bool = True

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


@dataclass(slots=True, frozen=True)
class DiscoveryMessage:
    """
    Home Assistant discovery message ready for MQTT transport.
    """

    topic: str

    payload: dict

    retain: bool = True


@dataclass(slots=True, frozen=True)
class EventPayload(JSONPayload):
    """
    MQTT event payload published to x10/<device>/event.
    """

    timestamp: str

    direction: str

    transport: str

    device: str

    command: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


@dataclass(slots=True, frozen=True)
class AvailabilityPayload(JSONPayload):
    """
    Bridge availability payload.
    """

    status: str

    def to_json(self) -> str:
        return self.status


@dataclass(slots=True, frozen=True)
class StatePayload(JSONPayload):
    """
    Device state payload.
    """

    state: str

    def to_json(self) -> str:
        return self.state

###############################################################################
# Bridge Actions
###############################################################################


@dataclass(slots=True, frozen=True)
class BridgeAction(ABC):
    """Base class for actions emitted by StateManager."""


@dataclass(slots=True, frozen=True)
class PublishStateAction(BridgeAction):

    address: str

    state: Command

    retain: bool = True


@dataclass(slots=True, frozen=True)
class PublishEventAction(BridgeAction):

    event: DeviceEvent


@dataclass(slots=True, frozen=True)
class PublishDiscoveryAction(BridgeAction):

    address: str


@dataclass(slots=True, frozen=True)
class PublishAvailabilityAction(BridgeAction):

    online: bool


@dataclass(slots=True, frozen=True)
class SendMochadCommandAction(BridgeAction):

    command: str


@dataclass(slots=True, frozen=True)
class SendDeviceCommandAction(BridgeAction):

    address: str

    command: Command


@dataclass(slots=True, frozen=True)
class RequestStatusAction(BridgeAction):
    """Issue an 'st' command."""


@dataclass(slots=True, frozen=True)
class LogUnknownEventAction(BridgeAction):

    event: UnknownEvent

@dataclass(
	slots=True,
	frozen=True,
	order=True,
)
class X10Address:
	"""
	Immutable normalized X10 device address.

	Examples

	    A1

	    P16
	"""

	house: str

	unit: int

	def __post_init__(self) -> None:

		object.__setattr__(
			self,
			"house",
			self.house.upper(),
		)

		if len(self.house) != 1:
			raise ValueError(
				f"Invalid house '{self.house}'."
			)

		if self.house < "A" or self.house > "P":
			raise ValueError(
				f"Invalid house '{self.house}'."
			)

		if self.unit < 1 or self.unit > 16:
			raise ValueError(
				f"Invalid unit '{self.unit}'."
			)

	def __str__(
		self,
	) -> str:

		return f"{self.house}{self.unit}"

	@property
	def topic(
		self,
	) -> str:
		"""
		MQTT-safe representation.
		"""

		return str(self)

	@classmethod
	def parse(
		cls,
		value: str,
	) -> "X10Address":

		value = value.strip().upper()

		match = re.fullmatch(
			r"(?P<house>[A-P])(?P<unit>[1-9]|1[0-6])",
			value,
		)

		if match is None:
			raise ValueError(
				f"Invalid X10 address '{value}'."
			)

		return cls(
			house=match.group("house"),
			unit=int(match.group("unit")),
		)
