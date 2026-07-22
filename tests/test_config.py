import os
import json
import tempfile
import unittest
from unittest.mock import patch

from config import (
    ConfigError,
    create_config_file_if_missing,
    load_config,
)
from models import Command, DeviceType


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

    def test_config_file_devices_and_friendly_names_are_parsed(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as config_file:
            json.dump(
                {
                    "use_friendly_names": True,
                    "devices": [
                        {
                            "address": "A1",
                            "name": "Living Room Lamp",
                            "type": "light",
                        }
                    ],
                },
                config_file,
            )
            config_file.flush()

            with patch.dict(
                os.environ,
                {"BRIDGE_CONFIG_FILE": config_file.name},
                clear=True,
            ):
                config = load_config()

        self.assertTrue(config.use_friendly_names)
        self.assertEqual(config.devices["A1"].name, "Living Room Lamp")

    def test_missing_optional_config_file_uses_environment_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_config = os.path.join(directory, "bridge.json")

            with patch.dict(
                os.environ,
                {
                    "BRIDGE_CONFIG_FILE": missing_config,
                    "X10_DEVICES": "A1:Living Room Lamp:light",
                },
                clear=True,
            ):
                config = load_config()

        self.assertEqual(config.config_file, missing_config)
        self.assertEqual(config.devices["A1"].name, "Living Room Lamp")

    def test_missing_config_file_can_be_created_from_environment_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, "bridge.json")

            with patch.dict(
                os.environ,
                {
                    "BRIDGE_CONFIG_FILE": config_path,
                    "X10_USE_FRIENDLY_NAMES": "true",
                    "X10_DEVICES": "A1:Living Room Lamp:light:3:150",
                },
                clear=True,
            ):
                config = load_config()

            self.assertTrue(create_config_file_if_missing(config))
            self.assertFalse(create_config_file_if_missing(config))

            with open(config_path, encoding="utf-8") as handle:
                payload = json.load(handle)

        self.assertEqual(
            payload,
            {
                "devices": [
                    {
                        "address": "A1",
                        "command_repeat_delay_ms": 150,
                        "command_repeats": 3,
                        "name": "Living Room Lamp",
                        "type": "light",
                    }
                ],
                "profiles": {"allow_experimental": False},
                "use_friendly_names": True,
            },
        )

    def test_config_file_can_disable_friendly_names(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as config_file:
            json.dump(
                {
                    "use_friendly_names": False,
                    "devices": [
                        {
                            "address": "A1",
                            "name": "Living Room Lamp",
                            "type": "light",
                        }
                    ],
                },
                config_file,
            )
            config_file.flush()

            with patch.dict(
                os.environ,
                {"BRIDGE_CONFIG_FILE": config_file.name},
                clear=True,
            ):
                config = load_config()

        self.assertFalse(config.use_friendly_names)
        self.assertEqual(config.devices["A1"].name, "A1")

    def test_env_can_disable_friendly_names_for_x10_devices(self):
        with patch.dict(
            os.environ,
            {
                "X10_USE_FRIENDLY_NAMES": "false",
                "X10_DEVICES": "A1:Living Room Lamp:light",
            },
            clear=True,
        ):
            config = load_config()

        self.assertFalse(config.use_friendly_names)
        self.assertEqual(config.devices["A1"].name, "A1")

    def test_env_devices_can_configure_command_repeats(self):
        with patch.dict(
            os.environ,
            {
                "X10_DEVICES": "A1:Living Room Lamp:light:3:200",
            },
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.devices["A1"].command_repeats, 3)
        self.assertEqual(config.devices["A1"].command_repeat_delay_ms, 200)

    def test_env_devices_can_define_action_only_chime(self):
        with patch.dict(
            os.environ,
            {
                "X10_DEVICES": "A2:Door Chime:chime",
            },
            clear=True,
        ):
            config = load_config()

        device = config.devices["A2"]
        self.assertEqual(device.entity_type, DeviceType.CHIME)
        self.assertFalse(device.stateful)
        self.assertEqual(device.supported_commands, frozenset({Command.ON}))

    def test_json_devices_can_configure_command_repeats(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as config_file:
            json.dump(
                {
                    "devices": [
                        {
                            "address": "A1",
                            "name": "Living Room Lamp",
                            "type": "light",
                            "command_repeats": 2,
                            "command_repeat_delay_ms": 150,
                        }
                    ],
                },
                config_file,
            )
            config_file.flush()

            with patch.dict(
                os.environ,
                {"BRIDGE_CONFIG_FILE": config_file.name},
                clear=True,
            ):
                config = load_config()

        self.assertEqual(config.devices["A1"].command_repeats, 2)
        self.assertEqual(config.devices["A1"].command_repeat_delay_ms, 150)

    def test_invalid_command_repeats_are_rejected(self):
        with patch.dict(
            os.environ,
            {
                "X10_DEVICES": "A1:Living Room Lamp:light:0:150",
            },
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                load_config()

    def test_invalid_config_file_json_is_rejected(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as config_file:
            config_file.write("{not-json")
            config_file.flush()

            with patch.dict(
                os.environ,
                {"BRIDGE_CONFIG_FILE": config_file.name},
                clear=True,
            ):
                with self.assertRaises(ConfigError):
                    load_config()


if __name__ == "__main__":
    unittest.main()
