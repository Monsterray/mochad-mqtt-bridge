"""
config.py

Configuration loading and validation.

This module is the ONLY place that reads environment variables.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

from models import DeviceConfig, DeviceType


###############################################################################
# Defaults
###############################################################################

DEFAULT_MOCHAD_HOST = "mochad"
DEFAULT_MOCHAD_PORT = 1099

DEFAULT_MQTT_HOST = "mosquitto"
DEFAULT_MQTT_PORT = 1883

DEFAULT_DISCOVERY_PREFIX = "homeassistant"
DEFAULT_BASE_TOPIC = "x10"

DEFAULT_LOG_LEVEL = "INFO"

LOG_FORMAT = (
    "%(asctime)s "
    "%(name)s "
    "[%(levelname)s]: "
    "%(message)s"
)


###############################################################################
# Configuration Exception
###############################################################################


class ConfigError(RuntimeError):
    """Raised when configuration is invalid."""


###############################################################################
# Main Configuration
###############################################################################


@dataclass(slots=True, frozen=True)
class Config:

    mochad_host: str
    mochad_port: int

    mqtt_host: str
    mqtt_port: int

    mqtt_username: str | None
    mqtt_password: str | None

    mqtt_base_topic: str
    mqtt_discovery_prefix: str

    log_level: str

    devices: dict[str, DeviceConfig] = field(default_factory=dict)

    optimistic_updates: bool = True

    status_refresh_on_connect: bool = True

    discovery_enabled: bool = True

    discovery_republish: bool = True

    debug_wire: bool = False


###############################################################################
# Environment Helpers
###############################################################################


def _get_env(
    name: str,
    default: str | None = None,
) -> str | None:
    """
    Read an environment variable.

    Empty strings are treated as unset.
    """

    value = os.getenv(name)

    if value is None:
        return default

    value = value.strip()

    if value == "":
        return default

    return value


def _get_int(
    name: str,
    default: int,
) -> int:

    value = _get_env(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(
            f"{name} must be an integer. Got '{value}'."
        ) from exc


def _get_bool(
    name: str,
    default: bool = False,
) -> bool:

    value = _get_env(name)

    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ConfigError(
        f"{name} must be a boolean. Got '{value}'."
    )


###############################################################################
# Device Parsing
###############################################################################


DEVICE_RE = re.compile(r"^[A-P](?:[1-9]|1[0-6])$", re.IGNORECASE)


def _normalize_address(address: str) -> str:

    address = address.strip().upper()

    if not DEVICE_RE.fullmatch(address):
        raise ConfigError(
            f"Invalid X10 address '{address}'."
        )

    return address


def _parse_device_type(value: str) -> DeviceType:

    value = value.strip().lower()

    if value == "light":
        return DeviceType.LIGHT

    if value == "switch":
        return DeviceType.SWITCH

    raise ConfigError(
        f"Unknown device type '{value}'."
    )


def parse_devices(raw: str | None) -> dict[str, DeviceConfig]:

    devices: dict[str, DeviceConfig] = {}

    if not raw:
        return devices

    for entry in raw.split(","):

        entry = entry.strip()

        if not entry:
            continue

        parts = [x.strip() for x in entry.split(":")]

        #
        # Supported formats:
        #
        # A1
        #
        # A1:Living Room Lamp
        #
        # A1:Living Room Lamp:light
        #

        if len(parts) == 1:

            address = _normalize_address(parts[0])

            devices[address] = DeviceConfig(
                address=address,
                name=address,
            )

            continue

        if len(parts) == 2:

            address = _normalize_address(parts[0])

            devices[address] = DeviceConfig(
                address=address,
                name=parts[1],
            )

            continue

        if len(parts) == 3:

            address = _normalize_address(parts[0])

            devices[address] = DeviceConfig(
                address=address,
                name=parts[1],
                entity_type=_parse_device_type(parts[2]),
            )

            continue

        raise ConfigError(
            f"Invalid X10_DEVICES entry '{entry}'."
        )

    return devices


###############################################################################
# Loader
###############################################################################


def load_config() -> Config:

    config = Config(

        mochad_host=_get_env(
            "MOCHAD_HOST",
            DEFAULT_MOCHAD_HOST,
        ),

        mochad_port=_get_int(
            "MOCHAD_PORT",
            DEFAULT_MOCHAD_PORT,
        ),

        mqtt_host=_get_env(
            "MQTT_HOST",
            DEFAULT_MQTT_HOST,
        ),

        mqtt_port=_get_int(
            "MQTT_PORT",
            DEFAULT_MQTT_PORT,
        ),

        mqtt_username=_get_env(
            "MQTT_USERNAME",
        ),

        mqtt_password=_get_env(
            "MQTT_PASSWORD",
        ),

        mqtt_base_topic=_get_env(
            "MQTT_BASE_TOPIC",
            DEFAULT_BASE_TOPIC,
        ),

        mqtt_discovery_prefix=_get_env(
            "MQTT_DISCOVERY_PREFIX",
            DEFAULT_DISCOVERY_PREFIX,
        ),

        log_level=_get_env(
            "LOG_LEVEL",
            DEFAULT_LOG_LEVEL,
        ),

        devices=parse_devices(
            _get_env("X10_DEVICES")
        ),

        debug_wire=_get_bool(
            "BRIDGE_DEBUG_WIRE",
            False,
        ),
    )

    return config


###############################################################################
# Logging
###############################################################################


def configure_logging(config: Config) -> None:

    logging.basicConfig(
        level=getattr(
            logging,
            config.log_level.upper(),
        ),
        format=LOG_FORMAT,
    )
