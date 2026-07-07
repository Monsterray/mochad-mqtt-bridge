import ssl
import unittest
from unittest.mock import Mock, patch

from config import MqttTlsConfig
from mqtt_tls import MqttTlsError, build_mqtt_ssl_context


class MqttTlsContextTests(unittest.TestCase):
    def test_disabled_tls_returns_no_context(self):
        with patch("mqtt_tls.ssl.create_default_context") as create_context:
            context = build_mqtt_ssl_context(MqttTlsConfig())

        self.assertIsNone(context)
        create_context.assert_not_called()

    def test_enabled_tls_uses_system_trust_with_verification(self):
        fake_context = Mock()

        with patch(
            "mqtt_tls.ssl.create_default_context",
            return_value=fake_context,
        ) as create_context:
            context = build_mqtt_ssl_context(
                MqttTlsConfig(enabled=True)
            )

        self.assertIs(context, fake_context)
        create_context.assert_called_once_with(cafile=None)
        self.assertTrue(fake_context.check_hostname)
        self.assertEqual(fake_context.verify_mode, ssl.CERT_REQUIRED)
        fake_context.load_cert_chain.assert_not_called()

    def test_custom_ca_and_mutual_tls_are_loaded(self):
        fake_context = Mock()

        with patch(
            "mqtt_tls.ssl.create_default_context",
            return_value=fake_context,
        ) as create_context:
            context = build_mqtt_ssl_context(
                MqttTlsConfig(
                    enabled=True,
                    ca_file="/run/secrets/ca.crt",
                    cert_file="/run/secrets/client.crt",
                    key_file="/run/secrets/client.key",
                    key_password="secret",
                )
            )

        self.assertIs(context, fake_context)
        create_context.assert_called_once_with(
            cafile="/run/secrets/ca.crt",
        )
        fake_context.load_cert_chain.assert_called_once_with(
            certfile="/run/secrets/client.crt",
            keyfile="/run/secrets/client.key",
            password="secret",
        )

    def test_tls_context_errors_are_wrapped(self):
        with patch(
            "mqtt_tls.ssl.create_default_context",
            side_effect=OSError("missing CA"),
        ):
            with self.assertRaises(MqttTlsError):
                build_mqtt_ssl_context(
                    MqttTlsConfig(
                        enabled=True,
                        ca_file="/run/secrets/missing-ca.crt",
                    )
                )


if __name__ == "__main__":
    unittest.main()
