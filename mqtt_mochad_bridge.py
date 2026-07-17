"""
Application entrypoint.

This module composes dependencies and starts the bridge. Runtime behavior lives
in bridge.py and the lower-level components.
"""

from __future__ import annotations

import logging
import sys
import time

from bridge import Bridge
from config import configure_logging, load_config
from version import BRIDGE_NAME, BRIDGE_VERSION


_LOG = logging.getLogger(__name__)


def main() -> None:
    if "--version" in sys.argv[1:]:
        print(BRIDGE_VERSION)
        return

    started = time.monotonic()
    config = load_config()
    configure_logging(config)
    _LOG.info("Starting %s version=%s", BRIDGE_NAME, BRIDGE_VERSION)
    _LOG.info("Configuration loaded elapsed=%.3fs", time.monotonic() - started)
    _LOG.info(
        "MQTT username configured=%s",
        bool(config.mqtt_username),
    )
    _LOG.info(
        "MQTT TLS enabled=%s custom_ca=%s client_certificate=%s",
        config.mqtt_tls.enabled,
        bool(config.mqtt_tls.ca_file),
        bool(config.mqtt_tls.cert_file and config.mqtt_tls.key_file),
    )

    if not config.mqtt_username:
        _LOG.warning(
            "MQTT username is empty; set MQTT_USERNAME if the broker requires authentication"
        )

    _LOG.info("Creating bridge")
    bridge = Bridge(config)
    _LOG.info("Starting bridge runtime elapsed=%.3fs", time.monotonic() - started)
    bridge.run()


if __name__ == "__main__":
    main()
