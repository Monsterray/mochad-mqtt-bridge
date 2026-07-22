import json
import unittest
from types import SimpleNamespace

from bridge import Bridge
from config import MqttTlsConfig
from device_registry import apply_profile
from models import DeviceConfig, MochadDiagnostics
from version import BRIDGE_NAME, BRIDGE_VERSION


class FakeMochadClient:
    def __init__(self):
        self.lines = []

    def send_line(self, line):
        self.lines.append(line)


class MochadDiagnosticTests(unittest.TestCase):
    def test_requests_expected_mochad_diagnostic_commands(self):
        mochad = FakeMochadClient()
        bridge = object.__new__(Bridge)
        bridge.clients = SimpleNamespace(mochad=mochad)

        bridge._request_mochad_diagnostics()

        self.assertEqual(
            mochad.lines,
            ["hello", "capabilities", "health"],
        )

    def test_identifies_mochad_redux_diagnostic_responses(self):
        self.assertEqual(
            Bridge._mochad_diagnostic_kind(
                {
                    "ok": True,
                    "daemon": "mochad-redux",
                    "diagnostics": True,
                }
            ),
            "hello",
        )
        self.assertEqual(
            Bridge._mochad_diagnostic_kind(
                {
                    "ok": True,
                    "commands": ["hello", "health"],
                    "json": True,
                }
            ),
            "capabilities",
        )
        self.assertEqual(
            Bridge._mochad_diagnostic_kind(
                {
                    "ok": True,
                    "usb_connected": True,
                    "controller": "CM19A",
                }
            ),
            "health",
        )

    def test_merges_diagnostics_into_minimal_status_payload(self):
        bridge = object.__new__(Bridge)
        bridge._mochad_diagnostics = MochadDiagnostics()

        bridge._merge_mochad_diagnostics(
            {
                "daemon": "mochad-redux",
                "version": "0.4.0",
                "commands": ["hello", "capabilities", "health"],
                "json": True,
                "single_line": True,
            }
        )
        bridge._merge_mochad_diagnostics(
            {
                "usb_connected": True,
                "controller": "CM19A",
                "endpoints_ready": True,
                "transfers_ready": True,
                "clients_total": 2,
                "listeners": {
                    "main": {
                        "enabled": True,
                        "port": 1099,
                    },
                },
            }
        )

        payload = bridge._mochad_diagnostics_payload()

        self.assertEqual(payload["daemon"], "mochad-redux")
        self.assertEqual(payload["version"], "0.4.0")
        self.assertTrue(payload["features"]["json"])
        self.assertTrue(payload["features"]["single_line"])
        self.assertTrue(payload["health"]["usb_connected"])
        self.assertEqual(payload["health"]["controller"], "CM19A")
        self.assertTrue(payload["health"]["endpoints_ready"])
        self.assertTrue(payload["health"]["transfers_ready"])
        self.assertNotIn("commands", payload)
        self.assertNotIn("listeners", payload)
        self.assertNotIn("clients_total", payload)

    def test_bridge_status_payload_contains_only_safe_tls_attributes(self):
        bridge = object.__new__(Bridge)
        bridge.config = SimpleNamespace(
            allow_experimental_profiles=False,
            mqtt_tls=MqttTlsConfig(
                enabled=True,
                ca_file="/run/secrets/mqtt-ca.crt",
                cert_file="/run/secrets/mqtt-client.crt",
                key_file="/run/secrets/mqtt-client.key",
                key_password="secret-password",
            )
        )
        bridge.state = SimpleNamespace(
            available=True,
            snapshot=lambda: {},
        )
        bridge.clients = SimpleNamespace(
            mqtt=SimpleNamespace(connected=True),
            mochad=SimpleNamespace(connected=True),
        )
        bridge.devices = {}
        bridge._mochad_diagnostics = MochadDiagnostics()

        payload = bridge._bridge_status_payload()

        self.assertEqual(
            payload["bridge"],
            {"name": BRIDGE_NAME, "version": BRIDGE_VERSION},
        )

        self.assertEqual(
            payload["mqtt"]["tls"],
            {
                "enabled": True,
                "custom_ca": True,
                "client_certificate": True,
            },
        )
        payload_text = json.dumps(payload)
        self.assertNotIn("/run/secrets", payload_text)
        self.assertNotIn("secret-password", payload_text)

    def test_bridge_status_reports_configured_profile_evidence(self):
        device = apply_profile(
            DeviceConfig("A2", "Door Chime"),
            "sc546a_chime",
            allow_experimental=True,
        )
        bridge = object.__new__(Bridge)
        bridge.config = SimpleNamespace(
            allow_experimental_profiles=True,
            mqtt_tls=MqttTlsConfig(),
        )
        bridge.state = SimpleNamespace(
            available=True,
            snapshot=lambda: {},
        )
        bridge.clients = SimpleNamespace(
            mqtt=SimpleNamespace(connected=True),
            mochad=SimpleNamespace(connected=True),
        )
        bridge.devices = {"A2": device}
        bridge._mochad_diagnostics = MochadDiagnostics()

        profile_status = bridge._bridge_status_payload()["device_profiles"]

        self.assertTrue(profile_status["allow_experimental"])
        self.assertEqual(
            profile_status["configured"][0],
            {
                "address": "A2",
                "profile_id": "sc546a_chime",
                "lifecycle": "experimental",
                "confidence": "well_supported",
                "fixture_verified": True,
                "hardware_verified": False,
                "last_reviewed": "2026-07-21",
            },
        )


if __name__ == "__main__":
    unittest.main()
