"""
Retained Home Assistant discovery registry.

The registry records discovery topics that this bridge published previously.
It does not inspect MQTT state or scan broker topics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class DiscoveryRegistryError(RuntimeError):
    """Raised when the discovery registry cannot be read or written."""


class DiscoveryRegistry:
    """Persist and load known Home Assistant discovery topics."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> set[str]:
        if not self.path.exists():
            return set()

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscoveryRegistryError(
                f"Could not load discovery registry {self.path}: {exc}"
            ) from exc

        topics = data.get("topics")

        if not isinstance(topics, list):
            raise DiscoveryRegistryError(
                f"Discovery registry {self.path} must contain a topics list."
            )

        return {
            topic
            for topic in topics
            if isinstance(topic, str) and topic.strip()
        }

    def create_if_missing(self) -> bool:
        if self.path.exists():
            return False

        self.save(set())
        return True

    def save(self, topics: Iterable[str]) -> None:
        payload = {
            "topics": sorted(set(topics)),
        }
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        except OSError as exc:
            raise DiscoveryRegistryError(
                f"Could not save discovery registry {self.path}: {exc}"
            ) from exc
