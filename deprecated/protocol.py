"""
protocol.py

Mochad protocol implementation.

This module is the ONLY code that understands mochad's text protocol.

Responsibilities
----------------
* Parse incoming mochad events into typed models.
* Encode outgoing commands.
* Normalize and validate X10 addresses.
* Detect protocol capabilities.
* Parse status ("st") responses.

No networking code belongs here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto

from models import (
    Command,
    DeviceEvent,
    Direction,
    HouseEvent,
    StatusSnapshot,
    Transport,
    UnknownEvent,
)

_LOG = logging.getLogger(__name__)

###############################################################################
# Regular Expressions
###############################################################################

DEVICE_EVENT_RE = re.compile(
    r"""
    ^
    \d\d/\d\d
    \s+
    \d\d:\d\d:\d\d
    \s+
    (?P<direction>Tx|Rx)
    \s+
    (?P<transport>RF|PL)
    \s+
    HouseUnit:
    \s+
    (?P<address>[A-P](?:[1-9]|1[0-6]))
    \s+
    Func:
    \s+
    (?P<command>.+)
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

HOUSE_EVENT_RE = re.compile(
    r"""
    ^
    \d\d/\d\d
    \s+
    \d\d:\d\d:\d\d
    \s+
    (?P<direction>Tx|Rx)
    \s+
    (?P<transport>RF|PL)
    \s+
    House:
    \s+
    (?P<house>[A-P])
    \s+
    Func:
    \s+
    (?P<command>.+)
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

STATUS_LINE_RE = re.compile(
    r"^(?:\d\d/\d\d\s+\d\d:\d\d:\d\d\s+)?House\s+([A-P]):\s+(.*)$",
    re.IGNORECASE,
)

###############################################################################
# Lookup Tables
###############################################################################

COMMAND_MAP = {
    "ON": Command.ON,
    "OFF": Command.OFF,
    "DIM": Command.DIM,
    "BRIGHT": Command.BRIGHT,
    "ALL LIGHTS ON": Command.ALL_LIGHTS_ON,
    "ALL LIGHTS OFF": Command.ALL_LIGHTS_OFF,
    "ALL UNITS OFF": Command.ALL_UNITS_OFF,
    "STATUS ON": Command.STATUS_ON,
    "STATUS OFF": Command.STATUS_OFF,
    "STATUS REQUEST": Command.STATUS_REQUEST,
}

TRANSPORT_MAP = {
    "RF": Transport.RF,
    "PL": Transport.PL,
}

DIRECTION_MAP = {
    "TX": Direction.TX,
    "RX": Direction.RX,
}

###############################################################################
# Protocol Capabilities
###############################################################################


@dataclass(slots=True)
class ProtocolCapabilities:
    """
    Features detected from mochad.
    """

    rf: bool = False

    pl: bool = False

    rf_security: bool = False

    cameras: bool = False

    status: bool = False


###############################################################################
# Status Parser
###############################################################################


class StatusParser:
    """
    Stateful parser for mochad 'st' output.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._snapshot = StatusSnapshot()

        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def feed(self, line: str) -> StatusSnapshot | None:
        """
        Feed one mochad line.

        Returns a StatusSnapshot only after 'End status'.
        """

        line = line.strip()

        #
        # Initial state
        #

        if line.endswith("Device selected"):
            self.reset()
            self._active = True
            return None

        if not self._active:
            return None

        #
        # Parse status lines
        #

        match = STATUS_LINE_RE.search(line)

        if match and "=" in match.group(2):

            house = match.group(1)

            entries = match.group(2).split(",")

            for entry in entries:

                unit, value = entry.split("=", 1)

                address = f"{house}{unit.strip()}"

                self._snapshot.devices[address] = (
                    Command.ON
                    if value.strip() == "1"
                    else Command.OFF
                )

            return None

        #
        # Finished
        #

        if line.endswith("End status"):

            self._snapshot.completed = True

            snapshot = self._snapshot

            self.reset()

            return snapshot

        return None


###############################################################################
# Main Parser
###############################################################################


class ProtocolParser:

    def __init__(self) -> None:

        self.capabilities = ProtocolCapabilities()

        self.status = StatusParser()

    def parse_line(
        self,
        line: str,
    ):
        """
        Parse one mochad line.
        """

        #
        # Status parser has first chance.
        #

        snapshot = self.status.feed(line)

        if snapshot is not None:

            self.capabilities.status = True

            return snapshot

        if self.status.active:
            return None

        #
        # Device event
        #

        match = DEVICE_EVENT_RE.match(line)

        if match:

            direction = DIRECTION_MAP[
                match.group("direction").upper()
            ]

            transport = TRANSPORT_MAP[
                match.group("transport").upper()
            ]

            command = COMMAND_MAP.get(
                match.group("command").upper(),
                Command.UNKNOWN,
            )

            if transport == Transport.RF:
                self.capabilities.rf = True

            if transport == Transport.PL:
                self.capabilities.pl = True

            return DeviceEvent(
                timestamp=datetime.utcnow(),
                direction=direction,
                transport=transport,
                command=command,
                address=match.group("address").upper(),
            )

        #
        # House event
        #

        match = HOUSE_EVENT_RE.match(line)

        if match:

            direction = DIRECTION_MAP[
                match.group("direction").upper()
            ]

            transport = TRANSPORT_MAP[
                match.group("transport").upper()
            ]

            command = COMMAND_MAP.get(
                match.group("command").upper(),
                Command.UNKNOWN,
            )

            return HouseEvent(
                timestamp=datetime.utcnow(),
                direction=direction,
                transport=transport,
                command=command,
                house=match.group("house").upper(),
            )

        #
        # Unknown
        #

        return UnknownEvent(
            timestamp=datetime.utcnow(),
            raw=line,
        )


###############################################################################
# Command Encoding
###############################################################################


def normalize_address(
    address: str,
) -> str:

    address = address.strip().upper()

    if not re.fullmatch(
        r"[A-P](?:[1-9]|1[0-6])",
        address,
    ):
        raise ValueError(
            f"Invalid X10 address '{address}'."
        )

    return address


def encode_rf_command(
    address: str,
    command: Command,
) -> str:

    address = normalize_address(address)

    mapping = {
        Command.ON: "on",
        Command.OFF: "off",
        Command.DIM: "dim",
        Command.BRIGHT: "bright",
    }

    try:
        suffix = mapping[command]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported RF command {command}."
        ) from exc

    return f"rf {address} {suffix}"


def encode_pl_command(
    address: str,
    command: Command,
) -> str:

    address = normalize_address(address)

    mapping = {
        Command.ON: "on",
        Command.OFF: "off",
        Command.DIM: "dim",
        Command.BRIGHT: "bright",
    }

    try:
        suffix = mapping[command]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported PL command {command}."
        ) from exc

    return f"pl {address} {suffix}"
