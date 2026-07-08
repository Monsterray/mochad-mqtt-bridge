"""
config.py

Configuration loading and validation.

This module is the ONLY place that reads environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from models import DeviceConfig, DeviceType


###############################################################################
# Defaults
###############################################################################

DEFAULT_MOCHAD_HOST = "mochad"
DEFAULT_MOCHAD_PORT = 1099

DEFAULT_MQTT_HOST = "mosquitto"
DEFAULT_MQTT_PORT = 1883

DEFAULT_DISCOVERY_PREFIX = "homeassistant"
DEFAULT_DISCOVERY_REGISTRY_PATH = "/config/discovery_registry.json"
DEFAULT_BASE_TOPIC = "x10"
DEFAULT_CONFIG_RELOAD_INTERVAL_SECONDS = 5.0

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
class MqttTlsConfig:
    """MQTT TLS settings parsed from the environment."""

    enabled: bool = False
    ca_file: str | None = None
    cert_file: str | None = None
    key_file: str | None = None
    key_password: str | None = None


@dataclass(slots=True, frozen=True)
class Config:

    mochad_host: str
    mochad_port: int

    mqtt_host: str
    mqtt_port: int

    mqtt_username: str | None
    mqtt_password: str | None
    mqtt_tls: MqttTlsConfig

    mqtt_base_topic: str
    mqtt_discovery_prefix: str

    log_level: str

    config_file: str | None = None

    config_reload_interval_seconds: float = (
        DEFAULT_CONFIG_RELOAD_INTERVAL_SECONDS
    )

    use_friendly_names: bool = True

    devices: dict[str, DeviceConfig] = field(default_factory=dict)

    optimistic_updates: bool = True

    status_refresh_on_connect: bool = True

    discovery_enabled: bool = True

    discovery_republish: bool = True

    discovery_cleanup: bool = False

    discovery_registry_path: str = DEFAULT_DISCOVERY_REGISTRY_PATH

    enable_maintenance_buttons: bool = False

    x10_housecodes: frozenset[str] | None = None

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


def _get_float(
    name: str,
    default: float,
) -> float:

    value = _get_env(name)

    if value is None:
        return default

    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(
            f"{name} must be a number. Got '{value}'."
        ) from exc

    if parsed <= 0:
        raise ConfigError(
            f"{name} must be greater than zero. Got '{value}'."
        )

    return parsed


def _get_secret(
    name: str,
    file_name: str,
) -> str | None:
    """
    Read a secret value directly or from a Docker-secret-compatible file.

    The secret contents are never logged. Files commonly include a trailing
    newline, so only line endings are removed.
    """

    value = _get_env(name)
    file_path = _get_env(file_name)

    if value is not None and file_path is not None:
        raise ConfigError(
            f"Set only one of {name} or {file_name}."
        )

    if file_path is None:
        return value

    try:
        secret = Path(file_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"{file_name} points to an unreadable file '{file_path}': {exc}"
        ) from exc

    secret = secret.rstrip("\r\n")

    if secret == "":
        return None

    return secret


def _load_mqtt_tls_config() -> MqttTlsConfig:
    enabled = _get_bool("MQTT_TLS_ENABLED", False)
    ca_file = _get_env("MQTT_TLS_CA_FILE")
    cert_file = _get_env("MQTT_TLS_CERT_FILE")
    key_file = _get_env("MQTT_TLS_KEY_FILE")
    key_password = _get_secret(
        "MQTT_TLS_KEY_PASSWORD",
        "MQTT_TLS_KEY_PASSWORD_FILE",
    )

    tls_settings_configured = any(
        (
            ca_file,
            cert_file,
            key_file,
            key_password,
        )
    )

    if tls_settings_configured and not enabled:
        raise ConfigError(
            "MQTT_TLS_ENABLED must be true when MQTT TLS settings are configured."
        )

    if not enabled:
        return MqttTlsConfig()

    if bool(cert_file) != bool(key_file):
        raise ConfigError(
            "MQTT_TLS_CERT_FILE and MQTT_TLS_KEY_FILE must be set together."
        )

    if key_password is not None and key_file is None:
        raise ConfigError(
            "MQTT_TLS_KEY_PASSWORD requires MQTT_TLS_KEY_FILE."
        )

    return MqttTlsConfig(
        enabled=True,
        ca_file=ca_file,
        cert_file=cert_file,
        key_file=key_file,
        key_password=key_password,
    )


###############################################################################
# Device Parsing
###############################################################################


DEVICE_RE = re.compile(r"^[A-P](?:[1-9]|1[0-6])$", re.IGNORECASE)
HOUSE_CODE_RE = re.compile(r"^[A-P]$", re.IGNORECASE)


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


def _display_name(
    address: str,
    name: str | None,
    use_friendly_names: bool,
) -> str:
    if not use_friendly_names:
        return address

    if name is None:
        return address

    name = name.strip()

    return name if name else address


def parse_devices(
    raw: str | None,
    use_friendly_names: bool = True,
) -> dict[str, DeviceConfig]:

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
                name=_display_name(
                    address,
                    parts[1],
                    use_friendly_names,
                ),
            )

            continue

        if len(parts) == 3:

            address = _normalize_address(parts[0])

            devices[address] = DeviceConfig(
                address=address,
                name=_display_name(
                    address,
                    parts[1],
                    use_friendly_names,
                ),
                entity_type=_parse_device_type(parts[2]),
            )

            continue

        raise ConfigError(
            f"Invalid X10_DEVICES entry '{entry}'."
        )

    return devices


def parse_device_config(
    raw: object,
    use_friendly_names: bool = True,
) -> dict[str, DeviceConfig]:
    """
    Parse device configuration from the optional JSON config file.

    Supported forms:

    - "A1:Living Room Lamp:light,A2:Coffee Maker:switch"
    - [{"address": "A1", "name": "Living Room Lamp", "type": "light"}]
    - {"A1": "Living Room Lamp", "A2": {"name": "Coffee Maker", "type": "switch"}}
    """

    if raw is None:
        return {}

    if isinstance(raw, str):
        return parse_devices(raw, use_friendly_names=use_friendly_names)

    if isinstance(raw, list):
        return _parse_device_list(raw, use_friendly_names)

    if isinstance(raw, dict):
        return _parse_device_mapping(raw, use_friendly_names)

    raise ConfigError(
        "Config file field 'devices' must be a string, list, or object."
    )


def _parse_device_list(
    raw: list,
    use_friendly_names: bool,
) -> dict[str, DeviceConfig]:
    devices: dict[str, DeviceConfig] = {}

    for item in raw:
        if not isinstance(item, dict):
            raise ConfigError(
                "Config file device list entries must be objects."
            )

        address = _normalize_address(str(item.get("address", "")))
        name = item.get("name")
        entity_type = item.get("type", item.get("entity_type", "switch"))

        devices[address] = DeviceConfig(
            address=address,
            name=_display_name(
                address,
                None if name is None else str(name),
                use_friendly_names,
            ),
            entity_type=_parse_device_type(str(entity_type)),
        )

    return devices


def _parse_device_mapping(
    raw: dict,
    use_friendly_names: bool,
) -> dict[str, DeviceConfig]:
    devices: dict[str, DeviceConfig] = {}

    for raw_address, value in raw.items():
        address = _normalize_address(str(raw_address))

        if isinstance(value, str):
            devices[address] = DeviceConfig(
                address=address,
                name=_display_name(
                    address,
                    value,
                    use_friendly_names,
                ),
            )
            continue

        if isinstance(value, dict):
            name = value.get("name")
            entity_type = value.get(
                "type",
                value.get("entity_type", "switch"),
            )
            devices[address] = DeviceConfig(
                address=address,
                name=_display_name(
                    address,
                    None if name is None else str(name),
                    use_friendly_names,
                ),
                entity_type=_parse_device_type(str(entity_type)),
            )
            continue

        raise ConfigError(
            "Config file device object values must be strings or objects."
        )

    return devices


def parse_housecodes(raw: str | None) -> frozenset[str] | None:
    if not raw:
        return None

    value = raw.strip().upper()

    if value in {"*", "A-P", "A...P"}:
        return None

    housecodes: set[str] = set()

    for part in re.split(r"[\s,]+", value):
        if not part:
            continue

        if "-" in part:
            start, end = _parse_housecode_range(part)
            housecodes.update(
                chr(code)
                for code in range(ord(start), ord(end) + 1)
            )
            continue

        for character in part:
            if not HOUSE_CODE_RE.fullmatch(character):
                raise ConfigError(
                    f"Invalid X10 house code '{character}' in X10_HOUSECODES."
                )

            housecodes.add(character)

    if not housecodes:
        return None

    return frozenset(sorted(housecodes))


def _parse_housecode_range(value: str) -> tuple[str, str]:
    parts = value.split("-")

    if len(parts) != 2:
        raise ConfigError(
            f"Invalid X10_HOUSECODES range '{value}'."
        )

    start = parts[0].strip()
    end = parts[1].strip()

    if (
        len(start) != 1
        or len(end) != 1
        or not HOUSE_CODE_RE.fullmatch(start)
        or not HOUSE_CODE_RE.fullmatch(end)
        or start > end
    ):
        raise ConfigError(
            f"Invalid X10_HOUSECODES range '{value}'."
        )

    return start, end


###############################################################################
# Loader
###############################################################################


def _load_config_file(path: str | None) -> dict:
    if path is None:
        return {}

    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"BRIDGE_CONFIG_FILE points to an unreadable file '{path}': {exc}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"BRIDGE_CONFIG_FILE '{path}' is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError(
            f"BRIDGE_CONFIG_FILE '{path}' must contain a JSON object."
        )

    return data


def _file_bool(
    data: dict,
    key: str,
    default: bool,
) -> bool:
    if key not in data:
        return default

    value = data[key]

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"1", "true", "yes", "on"}:
            return True

        if normalized in {"0", "false", "no", "off"}:
            return False

    raise ConfigError(
        f"Config file field '{key}' must be a boolean."
    )


def _devices_from_sources(
    file_config: dict,
    use_friendly_names: bool,
) -> dict[str, DeviceConfig]:
    has_devices = "devices" in file_config
    has_x10_devices = "x10_devices" in file_config

    if has_devices and has_x10_devices:
        raise ConfigError(
            "Set only one of 'devices' or 'x10_devices' in BRIDGE_CONFIG_FILE."
        )

    if has_devices:
        return parse_device_config(
            file_config["devices"],
            use_friendly_names=use_friendly_names,
        )

    if has_x10_devices:
        return parse_devices(
            str(file_config["x10_devices"]),
            use_friendly_names=use_friendly_names,
        )

    return parse_devices(
        _get_env("X10_DEVICES"),
        use_friendly_names=use_friendly_names,
    )


def load_config() -> Config:
    config_file = _get_env("BRIDGE_CONFIG_FILE")
    file_config = _load_config_file(config_file)
    use_friendly_names = _file_bool(
        file_config,
        "use_friendly_names",
        _get_bool("X10_USE_FRIENDLY_NAMES", True),
    )

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

        mqtt_password=_get_secret(
            "MQTT_PASSWORD",
            "MQTT_PASSWORD_FILE",
        ),

        mqtt_tls=_load_mqtt_tls_config(),

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

        config_file=config_file,

        config_reload_interval_seconds=_get_float(
            "BRIDGE_CONFIG_RELOAD_INTERVAL_SECONDS",
            DEFAULT_CONFIG_RELOAD_INTERVAL_SECONDS,
        ),

        use_friendly_names=use_friendly_names,

        devices=_devices_from_sources(
            file_config,
            use_friendly_names,
        ),

        discovery_cleanup=_get_bool(
            "DISCOVERY_CLEANUP",
            False,
        ),

        discovery_registry_path=_get_env(
            "DISCOVERY_REGISTRY_PATH",
            DEFAULT_DISCOVERY_REGISTRY_PATH,
        ),

        enable_maintenance_buttons=_get_bool(
            "ENABLE_MAINTENANCE_BUTTONS",
            False,
        ),

        x10_housecodes=parse_housecodes(
            _get_env("X10_HOUSECODES")
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
