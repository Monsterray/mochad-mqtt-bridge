"""
Status response parsing for the mochad protocol.
"""

from __future__ import annotations

from models import Command, StatusSnapshot

from .regex import DEVICE_SELECTED_RE, END_STATUS_RE, HOUSE_STATUS_RE
from .validation import normalize_address


class StatusParser:
    """
    Stateful parser for mochad "st" output.
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
        line = line.strip()

        if DEVICE_SELECTED_RE.match(line):
            self.reset()
            self._active = True
            return None

        if not self._active:
            return None

        match = HOUSE_STATUS_RE.match(line)

        if match and "=" in match.group("devices"):
            house = match.group("house").upper()

            for entry in match.group("devices").split(","):
                if "=" not in entry:
                    continue

                unit, value = entry.split("=", 1)
                address = normalize_address(f"{house}{unit.strip()}")

                self._snapshot.devices[address] = (
                    Command.ON
                    if value.strip() == "1"
                    else Command.OFF
                )

            return None

        if END_STATUS_RE.match(line):
            self._snapshot.completed = True
            snapshot = self._snapshot
            self.reset()
            return snapshot

        return None
