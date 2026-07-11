"""
Parser orchestration for the mochad protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from models import (
    DeviceEvent,
    Direction,
    HouseEvent,
    StatusSnapshot,
    Transport,
    UnknownEvent,
)

from .mappings import COMMAND_MAP, DIRECTION_MAP, TRANSPORT_MAP
from .regex import DEVICE_EVENT_RE, HOUSE_EVENT_RE
from .status import StatusParser
from .validation import normalize_address, normalize_house, normalize_token


@dataclass(slots=True)
class ProtocolCapabilities:
    """Features detected from mochad traffic during runtime."""

    rf: bool = False
    pl: bool = False
    rf_security: bool = False
    cameras: bool = False
    status: bool = False


class ProtocolParser:
    """Parse one mochad line into a typed event or status snapshot."""

    def __init__(self) -> None:
        self.capabilities = ProtocolCapabilities()
        self.status = StatusParser()

    def parse_line(
        self,
        line: str,
    ) -> DeviceEvent | HouseEvent | StatusSnapshot | UnknownEvent | None:
        line = line.strip()

        if not line:
            return None

        if self.status.is_status_line(line):
            snapshot = self.status.feed(line)

            if snapshot is not None:
                self.capabilities.status = True
                return snapshot

            return None

        match = DEVICE_EVENT_RE.match(line)

        if match:
            transport = TRANSPORT_MAP[
                normalize_token(match.group("transport"))
            ]
            self._record_transport(transport)

            return DeviceEvent(
                timestamp=datetime.now(UTC),
                direction=DIRECTION_MAP[
                    normalize_token(match.group("direction"))
                ],
                transport=transport,
                command=COMMAND_MAP.get(
                    normalize_token(match.group("command")),
                    COMMAND_MAP["UNKNOWN"],
                ),
                address=normalize_address(match.group("address")),
            )

        match = HOUSE_EVENT_RE.match(line)

        if match:
            transport = TRANSPORT_MAP[
                normalize_token(match.group("transport"))
            ]
            self._record_transport(transport)

            return HouseEvent(
                timestamp=datetime.now(UTC),
                direction=DIRECTION_MAP[
                    normalize_token(match.group("direction"))
                ],
                transport=transport,
                command=COMMAND_MAP.get(
                    normalize_token(match.group("command")),
                    COMMAND_MAP["UNKNOWN"],
                ),
                house=normalize_house(match.group("house")),
            )

        return UnknownEvent(
            timestamp=datetime.now(UTC),
            raw=line,
        )

    def _record_transport(self, transport: Transport) -> None:
        if transport == Transport.RF:
            self.capabilities.rf = True

        if transport == Transport.PL:
            self.capabilities.pl = True
