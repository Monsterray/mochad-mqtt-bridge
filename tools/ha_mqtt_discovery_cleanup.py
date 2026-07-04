#!/usr/bin/env python3
"""
Find and optionally clear Home Assistant MQTT discovery configs owned by this
bridge.

This is a standalone maintenance helper. It is not imported by normal bridge
runtime and does not use the Home Assistant API.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any


BRIDGE_DEVICE_IDENTIFIER = "mqtt_mochad_bridge"
BRIDGE_UNIQUE_ID_PREFIX = "mqtt_mochad_bridge_"
X10_UNIQUE_ID_RE = re.compile(r"^x10_[A-P](?:[1-9]|1[0-6])$")


@dataclass(slots=True, frozen=True)
class DiscoveryConfig:
    topic: str
    payload: dict[str, Any]


def parse_discovery_payload(payload: bytes) -> dict[str, Any] | None:
    text = payload.decode("utf-8", errors="replace").strip()

    if not text:
        return None

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    return parsed


def is_bridge_owned_discovery(
    topic: str,
    payload: dict[str, Any],
    discovery_prefix: str = "homeassistant",
) -> bool:
    if not is_discovery_config_topic(topic, discovery_prefix):
        return False

    unique_id = payload.get("unique_id")

    if isinstance(unique_id, str):
        if X10_UNIQUE_ID_RE.fullmatch(unique_id):
            return True

        if unique_id.startswith(BRIDGE_UNIQUE_ID_PREFIX):
            return True

    if topic_has_bridge_owned_object_id(topic, discovery_prefix):
        return True

    return payload_has_bridge_identifier(payload)


def is_cleanup_target(
    topic: str,
    payload: dict[str, Any],
    discovery_prefix: str = "homeassistant",
    match_topic: str | None = None,
) -> bool:
    if match_topic and topic_matches_pattern(topic, match_topic):
        return is_discovery_config_topic(topic, discovery_prefix)

    return is_bridge_owned_discovery(
        topic,
        payload,
        discovery_prefix=discovery_prefix,
    )


def topic_matches_pattern(
    topic: str,
    pattern: str,
) -> bool:
    topic = topic.strip("/")
    pattern = pattern.strip("/")

    if not pattern:
        return False

    regex = []

    for character in pattern:
        if character == "+":
            regex.append(r"[^/]+")
        elif character == "#":
            regex.append(r".*")
        else:
            regex.append(re.escape(character))

    return re.fullmatch("".join(regex), topic) is not None


def is_discovery_config_topic(
    topic: str,
    discovery_prefix: str = "homeassistant",
) -> bool:
    prefix = discovery_prefix.strip("/")
    parts = topic.strip("/").split("/")

    return (
        len(parts) == 4
        and parts[0] == prefix
        and parts[-1] == "config"
    )


def topic_has_bridge_owned_object_id(
    topic: str,
    discovery_prefix: str = "homeassistant",
) -> bool:
    if not is_discovery_config_topic(topic, discovery_prefix):
        return False

    object_id = topic.strip("/").split("/")[2]

    return (
        X10_UNIQUE_ID_RE.fullmatch(object_id) is not None
        or object_id.startswith(BRIDGE_UNIQUE_ID_PREFIX)
    )


def payload_has_bridge_identifier(payload: dict[str, Any]) -> bool:
    device = payload.get("device")

    if not isinstance(device, dict):
        return False

    identifiers = device.get("identifiers")

    if isinstance(identifiers, str):
        return identifiers == BRIDGE_DEVICE_IDENTIFIER

    if isinstance(identifiers, list):
        return BRIDGE_DEVICE_IDENTIFIER in identifiers

    return False


def reason_code_as_int(reason_code) -> int | None:
    try:
        return int(reason_code)
    except (TypeError, ValueError):
        value = getattr(reason_code, "value", None)

        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None


def reason_code_label(reason_code) -> str:
    if reason_code is None:
        return "unknown"

    for attr in ("getName", "get_name"):
        getter = getattr(reason_code, attr, None)

        if callable(getter):
            try:
                name = getter()
            except Exception:
                name = None

            if name:
                return str(name)

    name = getattr(reason_code, "name", None)

    if name:
        return str(name)

    return str(reason_code)


class DiscoveryCleanupClient:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        discovery_prefix: str,
        match_topic: str | None,
        wait_seconds: float,
        apply: bool,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.discovery_prefix = discovery_prefix
        self.match_topic = match_topic
        self.wait_seconds = wait_seconds
        self.apply = apply
        self._connected = threading.Event()
        self._configs: dict[str, DiscoveryConfig] = {}

    def run(self) -> int:
        client = self._make_client()

        if self.username:
            client.username_pw_set(self.username, self.password)

        client.on_connect = self._on_connect
        client.on_message = self._on_message

        print(
            "Connecting to MQTT "
            f"{self.host}:{self.port} "
            f"username_configured={bool(self.username)}"
        )
        client.connect(self.host, self.port, 60)
        client.loop_start()

        try:
            if not self._connected.wait(timeout=10):
                print("FAIL MQTT connection timed out", file=sys.stderr)
                return 1

            time.sleep(self.wait_seconds)
            matches = sorted(self._configs.values(), key=lambda item: item.topic)
            self._print_matches(matches)

            if self.apply:
                publish_results = []

                for config in matches:
                    publish_results.append(
                        client.publish(
                            config.topic,
                            payload="",
                            qos=0,
                            retain=True,
                        )
                    )

                for result in publish_results:
                    wait_for_publish = getattr(result, "wait_for_publish", None)

                    if callable(wait_for_publish):
                        wait_for_publish()

                print(f"Cleared {len(matches)} retained discovery config(s).")
            else:
                print("Dry run only. Re-run with --apply to clear these topics.")

            return 0
        finally:
            client.disconnect()
            client.loop_stop()

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties=None,
    ) -> None:
        reason_number = reason_code_as_int(reason_code)

        if reason_number != 0:
            print(
                "FAIL MQTT connection refused "
                f"reason={reason_code_label(reason_code)}",
                file=sys.stderr,
            )
            return

        client.subscribe(f"{self.discovery_prefix.strip('/')}/#", qos=0)
        self._connected.set()

    def _on_message(
        self,
        client,
        userdata,
        message,
    ) -> None:
        if not getattr(message, "retain", False):
            return

        payload = parse_discovery_payload(message.payload)

        if payload is None:
            return

        if not is_cleanup_target(
            message.topic,
            payload,
            discovery_prefix=self.discovery_prefix,
            match_topic=self.match_topic,
        ):
            return

        self._configs[message.topic] = DiscoveryConfig(
            topic=message.topic,
            payload=payload,
        )

    @staticmethod
    def _make_client():
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError(
                "paho-mqtt is required. Install project requirements first."
            ) from exc

        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="ha-mqtt-discovery-cleanup",
        )

    @staticmethod
    def _print_matches(
        matches: list[DiscoveryConfig],
    ) -> None:
        print(f"Found {len(matches)} matching discovery config(s).")

        for config in matches:
            unique_id = config.payload.get("unique_id", "")
            name = config.payload.get("name", "")
            print(f"- {config.topic} unique_id={unique_id} name={name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find and optionally clear retained Home Assistant MQTT discovery "
            "configs owned by MQTT Mochad Bridge."
        )
    )
    parser.add_argument("--host", default=os.getenv("MQTT_HOST", "mosquitto"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MQTT_PORT", "1883")),
    )
    parser.add_argument("--username", default=os.getenv("MQTT_USERNAME"))
    parser.add_argument("--password", default=os.getenv("MQTT_PASSWORD"))
    parser.add_argument(
        "--prefix",
        default=os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant"),
        help="Home Assistant MQTT discovery prefix.",
    )
    parser.add_argument(
        "--match-topic",
        help=(
            "Optional aggressive topic pattern, for example "
            "homeassistant/+/x10_+/config. + matches non-slash characters."
        ),
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=3.0,
        help="Seconds to wait for retained discovery messages after subscribing.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching topics without clearing them. This is the default.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Publish empty retained payloads to matching discovery config topics.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = DiscoveryCleanupClient(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        discovery_prefix=args.prefix,
        match_topic=args.match_topic,
        wait_seconds=args.wait,
        apply=args.apply,
    )
    return client.run()


if __name__ == "__main__":
    raise SystemExit(main())
