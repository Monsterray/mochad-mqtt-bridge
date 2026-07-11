import json
import os
from pathlib import Path
import tempfile
import unittest

from discovery_registry import DiscoveryRegistry, DiscoveryRegistryError


class DiscoveryRegistryTests(unittest.TestCase):
    def test_missing_file_loads_empty_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = DiscoveryRegistry(Path(directory) / "registry.json")

            self.assertEqual(registry.load(), set())

    def test_save_and_load_versioned_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            registry = DiscoveryRegistry(path)

            registry.save(
                {
                    "homeassistant/light/x10_A1/config",
                    "homeassistant/switch/x10_A2/config",
                }
            )

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 1)
            self.assertEqual(
                payload["topics"],
                [
                    {"topic": "homeassistant/light/x10_A1/config"},
                    {"topic": "homeassistant/switch/x10_A2/config"},
                ],
            )
            self.assertEqual(
                registry.load(),
                {
                    "homeassistant/light/x10_A1/config",
                    "homeassistant/switch/x10_A2/config",
                },
            )

    def test_empty_file_is_quarantined_and_loads_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discovery_registry.json"
            path.write_text("", encoding="utf-8")
            registry = DiscoveryRegistry(path)

            self.assertEqual(registry.load(), set())
            self.assertFalse(path.exists())
            self.assertEqual(
                len(list(Path(directory).glob("discovery_registry.json.invalid.*"))),
                1,
            )

    def test_invalid_json_is_quarantined_and_loads_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discovery_registry.json"
            path.write_text("{not-json", encoding="utf-8")
            registry = DiscoveryRegistry(path)

            self.assertEqual(registry.load(), set())
            self.assertFalse(path.exists())
            self.assertEqual(
                len(list(Path(directory).glob("discovery_registry.json.invalid.*"))),
                1,
            )

    def test_wrong_shape_is_quarantined_and_loads_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discovery_registry.json"
            path.write_text("[]", encoding="utf-8")
            registry = DiscoveryRegistry(path)

            self.assertEqual(registry.load(), set())
            self.assertFalse(path.exists())
            self.assertEqual(
                len(list(Path(directory).glob("discovery_registry.json.invalid.*"))),
                1,
            )

    def test_wrong_version_is_quarantined_and_loads_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discovery_registry.json"
            path.write_text(
                json.dumps({"version": 999, "topics": []}),
                encoding="utf-8",
            )
            registry = DiscoveryRegistry(path)

            self.assertEqual(registry.load(), set())
            self.assertFalse(path.exists())

    def test_wrong_topic_value_type_is_quarantined_and_loads_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discovery_registry.json"
            path.write_text(
                json.dumps({"version": 1, "topics": [{"topic": 123}]}),
                encoding="utf-8",
            )
            registry = DiscoveryRegistry(path)

            self.assertEqual(registry.load(), set())
            self.assertFalse(path.exists())

    def test_temp_file_is_ignored_when_registry_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discovery_registry.json"
            temp_path = Path(directory) / "discovery_registry.json.tmp"
            temp_path.write_text("{not-json", encoding="utf-8")
            registry = DiscoveryRegistry(path)

            self.assertEqual(registry.load(), set())
            self.assertTrue(temp_path.exists())

    def test_create_if_missing_writes_versioned_empty_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discovery_registry.json"
            registry = DiscoveryRegistry(path)

            self.assertTrue(registry.create_if_missing())
            self.assertFalse(registry.create_if_missing())
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"topics": [], "version": 1},
            )

    def test_save_failure_raises_registry_error(self):
        with tempfile.TemporaryDirectory() as directory:
            blocking_file = Path(directory) / "not-a-directory"
            blocking_file.write_text("block", encoding="utf-8")
            registry = DiscoveryRegistry(blocking_file / "registry.json")

            with self.assertRaises(DiscoveryRegistryError):
                registry.save({"homeassistant/light/x10_A1/config"})

    def test_read_only_directory_save_failure_raises_registry_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "discovery_registry.json"
            os.chmod(directory, 0o500)

            try:
                registry = DiscoveryRegistry(path)
                try:
                    registry.save({"homeassistant/light/x10_A1/config"})
                except DiscoveryRegistryError:
                    return
                self.skipTest("filesystem allowed write to read-only directory")
            finally:
                os.chmod(directory, 0o700)


if __name__ == "__main__":
    unittest.main()
