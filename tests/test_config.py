import os
import tempfile
import unittest
from unittest.mock import patch

from config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def test_maintenance_buttons_default_to_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(load_config().enable_maintenance_buttons)

    def test_maintenance_buttons_can_be_enabled(self):
        with patch.dict(
            os.environ,
            {"ENABLE_MAINTENANCE_BUTTONS": "true"},
            clear=True,
        ):
            self.assertTrue(load_config().enable_maintenance_buttons)

    def test_mqtt_tls_defaults_to_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            config = load_config()

        self.assertFalse(config.mqtt_tls.enabled)
        self.assertIsNone(config.mqtt_tls.ca_file)
        self.assertIsNone(config.mqtt_tls.cert_file)
        self.assertIsNone(config.mqtt_tls.key_file)
        self.assertIsNone(config.mqtt_tls.key_password)

    def test_mqtt_tls_system_trust_can_be_enabled(self):
        with patch.dict(
            os.environ,
            {"MQTT_TLS_ENABLED": "true"},
            clear=True,
        ):
            config = load_config()

        self.assertTrue(config.mqtt_tls.enabled)
        self.assertIsNone(config.mqtt_tls.ca_file)

    def test_mqtt_tls_custom_ca_and_mutual_tls_are_parsed(self):
        with patch.dict(
            os.environ,
            {
                "MQTT_TLS_ENABLED": "true",
                "MQTT_TLS_CA_FILE": "/run/secrets/mqtt_ca.crt",
                "MQTT_TLS_CERT_FILE": "/run/secrets/mqtt_client.crt",
                "MQTT_TLS_KEY_FILE": "/run/secrets/mqtt_client.key",
                "MQTT_TLS_KEY_PASSWORD": "key-secret",
            },
            clear=True,
        ):
            config = load_config()

        self.assertTrue(config.mqtt_tls.enabled)
        self.assertEqual(config.mqtt_tls.ca_file, "/run/secrets/mqtt_ca.crt")
        self.assertEqual(
            config.mqtt_tls.cert_file,
            "/run/secrets/mqtt_client.crt",
        )
        self.assertEqual(
            config.mqtt_tls.key_file,
            "/run/secrets/mqtt_client.key",
        )
        self.assertEqual(config.mqtt_tls.key_password, "key-secret")

    def test_mqtt_password_file_is_supported(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as secret:
            secret.write("mqtt-secret\n")
            secret.flush()

            with patch.dict(
                os.environ,
                {"MQTT_PASSWORD_FILE": secret.name},
                clear=True,
            ):
                config = load_config()

        self.assertEqual(config.mqtt_password, "mqtt-secret")

    def test_mqtt_password_and_file_conflict_is_rejected(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as secret:
            secret.write("mqtt-secret\n")
            secret.flush()

            with patch.dict(
                os.environ,
                {
                    "MQTT_PASSWORD": "direct-secret",
                    "MQTT_PASSWORD_FILE": secret.name,
                },
                clear=True,
            ):
                with self.assertRaises(ConfigError):
                    load_config()

    def test_mqtt_tls_key_password_file_is_supported(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as secret:
            secret.write("key-secret\n")
            secret.flush()

            with patch.dict(
                os.environ,
                {
                    "MQTT_TLS_ENABLED": "true",
                    "MQTT_TLS_CERT_FILE": "/run/secrets/mqtt_client.crt",
                    "MQTT_TLS_KEY_FILE": "/run/secrets/mqtt_client.key",
                    "MQTT_TLS_KEY_PASSWORD_FILE": secret.name,
                },
                clear=True,
            ):
                config = load_config()

        self.assertEqual(config.mqtt_tls.key_password, "key-secret")

    def test_mqtt_tls_key_password_and_file_conflict_is_rejected(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as secret:
            secret.write("key-secret\n")
            secret.flush()

            with patch.dict(
                os.environ,
                {
                    "MQTT_TLS_ENABLED": "true",
                    "MQTT_TLS_CERT_FILE": "/run/secrets/mqtt_client.crt",
                    "MQTT_TLS_KEY_FILE": "/run/secrets/mqtt_client.key",
                    "MQTT_TLS_KEY_PASSWORD": "direct-secret",
                    "MQTT_TLS_KEY_PASSWORD_FILE": secret.name,
                },
                clear=True,
            ):
                with self.assertRaises(ConfigError):
                    load_config()

    def test_tls_settings_without_tls_enabled_are_rejected(self):
        with patch.dict(
            os.environ,
            {"MQTT_TLS_CA_FILE": "/run/secrets/mqtt_ca.crt"},
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                load_config()

    def test_mtls_requires_cert_and_key_together(self):
        with patch.dict(
            os.environ,
            {
                "MQTT_TLS_ENABLED": "true",
                "MQTT_TLS_CERT_FILE": "/run/secrets/mqtt_client.crt",
            },
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                load_config()


if __name__ == "__main__":
    unittest.main()
