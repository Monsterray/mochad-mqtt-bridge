import unittest
from pathlib import Path

from scripts.validate.image_labels import validate_labels

ROOT = Path(__file__).resolve().parents[1]

VALID_LABELS = {
    "org.opencontainers.image.title": "mochad-mqtt-bridge",
    "org.opencontainers.image.description": "MQTT bridge",
    "org.opencontainers.image.created": "2026-07-13T12:34:56-07:00",
    "org.opencontainers.image.version": "0.1.0",
    "org.opencontainers.image.revision": "a" * 40,
    "org.opencontainers.image.source": (
        "https://github.com/Monsterray/mochad-mqtt-bridge"
    ),
    "org.opencontainers.image.licenses": "MIT",
}


class ImageLabelValidationTests(unittest.TestCase):
    def test_accepts_release_labels(self) -> None:
        self.assertEqual(validate_labels(dict(VALID_LABELS)), [])

    def test_rejects_empty_labels(self) -> None:
        labels = dict(VALID_LABELS)
        labels["org.opencontainers.image.revision"] = ""

        self.assertTrue(validate_labels(labels))

    def test_rejects_branch_names_as_label_values(self) -> None:
        for value in ("master", "develop", "latest", "unknown"):
            labels = dict(VALID_LABELS)
            labels["org.opencontainers.image.version"] = value

            self.assertTrue(validate_labels(labels))

    def test_rejects_short_revision(self) -> None:
        labels = dict(VALID_LABELS)
        labels["org.opencontainers.image.revision"] = "abc123"

        self.assertTrue(validate_labels(labels))


class ReleaseImageInputTests(unittest.TestCase):
    def test_versions_file_pins_digest_qualified_base_image(self) -> None:
        versions = (ROOT / "release" / "versions.env").read_text()

        self.assertIn("PYTHON_BASE_IMAGE=python:3.12-alpine@sha256:", versions)
        self.assertIn("IMAGE_NAME=ghcr.io/monsterray/mochad-mqtt-bridge", versions)

    def test_release_requirements_are_hash_checked(self) -> None:
        requirements = (ROOT / "requirements.release.txt").read_text()

        self.assertIn("paho-mqtt==2.1.0", requirements)
        self.assertIn("--hash=sha256:", requirements)

    def test_dockerfile_uses_release_requirements_and_label_args(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text()

        self.assertIn("ARG PYTHON_BASE_IMAGE=", dockerfile)
        self.assertIn("FROM ${PYTHON_BASE_IMAGE}", dockerfile)
        self.assertIn("--require-hashes -r requirements.release.txt", dockerfile)
        self.assertIn('LABEL org.opencontainers.image.created="${IMAGE_CREATED}"', dockerfile)
        self.assertIn('LABEL org.opencontainers.image.revision="${IMAGE_REVISION}"', dockerfile)

    def test_dockerfile_collects_apk_evidence_without_repository_cache_access(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text()

        self.assertIn("apk info > /usr/share/mochad-mqtt-bridge/apk-info.txt", dockerfile)
        self.assertNotIn("apk info -vv", dockerfile)


if __name__ == "__main__":
    unittest.main()
