"""
Retained Home Assistant discovery registry.

The registry records discovery topics that this bridge published previously.
It does not inspect MQTT state or scan broker topics.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Iterable


class DiscoveryRegistryError(RuntimeError):
    """Raised when the discovery registry cannot be read or written."""


REGISTRY_VERSION = 1


class DiscoveryRegistry:
    """Persist and load known Home Assistant discovery topics."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> set[str]:
        if not self.path.exists():
            return set()

        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DiscoveryRegistryError(
                f"Could not load discovery registry {self.path}: {exc}"
            ) from exc

        try:
            data = json.loads(raw)
            return self._parse_registry_data(data)
        except (json.JSONDecodeError, DiscoveryRegistryError):
            self._quarantine_invalid_file()
            return set()

    def _parse_registry_data(
        self,
        data: object,
    ) -> set[str]:
        if not isinstance(data, dict):
            raise DiscoveryRegistryError(
                f"Discovery registry {self.path} must contain a JSON object."
            )

        if data.get("version") != REGISTRY_VERSION:
            raise DiscoveryRegistryError(
                f"Discovery registry {self.path} has unsupported version."
            )

        topics = data.get("topics")

        if not isinstance(topics, list):
            raise DiscoveryRegistryError(
                f"Discovery registry {self.path} must contain a topics list."
            )

        parsed: set[str] = set()

        for entry in topics:
            if not isinstance(entry, dict):
                raise DiscoveryRegistryError(
                    f"Discovery registry {self.path} topic entries must be objects."
                )

            topic = entry.get("topic")

            if not isinstance(topic, str) or not topic.strip():
                raise DiscoveryRegistryError(
                    f"Discovery registry {self.path} topic values must be strings."
                )

            parsed.add(topic.strip())

        return parsed

    def _quarantine_invalid_file(self) -> None:
        timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        quarantine_path = self.path.with_name(
            f"{self.path.name}.invalid.{timestamp}"
        )

        counter = 1
        while quarantine_path.exists():
            quarantine_path = self.path.with_name(
                f"{self.path.name}.invalid.{timestamp}.{counter}"
            )
            counter += 1

        try:
            os.replace(self.path, quarantine_path)
        except OSError as exc:
            raise DiscoveryRegistryError(
                f"Could not quarantine invalid discovery registry {self.path}: {exc}"
            ) from exc

    def create_if_missing(self) -> bool:
        if self.path.exists():
            return False

        self.save(set())
        return True

    def save(self, topics: Iterable[str]) -> None:
        payload = {
            "version": REGISTRY_VERSION,
            "topics": [
                {"topic": topic}
                for topic in sorted(
                    topic.strip()
                    for topic in set(topics)
                    if isinstance(topic, str) and topic.strip()
                )
            ],
        }
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
        except OSError as exc:
            raise DiscoveryRegistryError(
                f"Could not save discovery registry {self.path}: {exc}"
            ) from exc
