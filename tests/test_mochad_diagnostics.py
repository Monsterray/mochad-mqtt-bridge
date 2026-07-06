import unittest
from types import SimpleNamespace

from bridge import Bridge
from models import MochadDiagnostics


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


if __name__ == "__main__":
    unittest.main()
