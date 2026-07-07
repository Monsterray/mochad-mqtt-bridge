"""
MQTT TLS context construction.

This module owns SSLContext creation for the MQTT transport. Environment
parsing stays in config.py, and mqtt_client.py only installs the verified
context into Paho.
"""

from __future__ import annotations

import ssl

from config import MqttTlsConfig


class MqttTlsError(RuntimeError):
    """Raised when MQTT TLS configuration cannot produce a safe context."""


def build_mqtt_ssl_context(
    tls_config: MqttTlsConfig,
) -> ssl.SSLContext | None:
    """
    Build a verified SSL context for MQTT.

    System trust is used when no CA file is configured. A custom CA file can be
    supplied, and mutual TLS is enabled when client certificate and key files
    are configured together.
    """

    if not tls_config.enabled:
        return None

    try:
        context = ssl.create_default_context(
            cafile=tls_config.ca_file,
        )
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED

        if hasattr(ssl, "TLSVersion"):
            context.minimum_version = ssl.TLSVersion.TLSv1_2

        if tls_config.cert_file and tls_config.key_file:
            context.load_cert_chain(
                certfile=tls_config.cert_file,
                keyfile=tls_config.key_file,
                password=tls_config.key_password,
            )

    except (OSError, ValueError, ssl.SSLError) as exc:
        raise MqttTlsError(
            f"Unable to configure MQTT TLS: {exc}"
        ) from exc

    return context
