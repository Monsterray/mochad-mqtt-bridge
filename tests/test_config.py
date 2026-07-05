import os
import unittest
from unittest.mock import patch

from config import load_config


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


if __name__ == "__main__":
    unittest.main()
