#!/usr/bin/env python3
"""
Validate OCI image labels for release builds.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys


REQUIRED_LABELS = (
    "org.opencontainers.image.title",
    "org.opencontainers.image.description",
    "org.opencontainers.image.created",
    "org.opencontainers.image.version",
    "org.opencontainers.image.revision",
    "org.opencontainers.image.source",
    "org.opencontainers.image.licenses",
)

FORBIDDEN_VALUES = {
    "",
    "dev",
    "develop",
    "development",
    "latest",
    "local",
    "master",
    "unknown",
}

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
ISO_8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$"
)
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def validate_labels(labels: dict[str, str]) -> list[str]:
    errors: list[str] = []

    for name in REQUIRED_LABELS:
        value = labels.get(name, "")
        if value.strip().lower() in FORBIDDEN_VALUES:
            errors.append(f"{name} must be populated with release metadata")

    version = labels.get("org.opencontainers.image.version", "")
    if version and not SEMVER_RE.match(version):
        errors.append(
            "org.opencontainers.image.version must be a plain semantic version"
        )

    created = labels.get("org.opencontainers.image.created", "")
    if created and not ISO_8601_RE.match(created):
        errors.append(
            "org.opencontainers.image.created must be an ISO-8601 Git timestamp"
        )

    revision = labels.get("org.opencontainers.image.revision", "")
    if revision and not GIT_SHA_RE.match(revision):
        errors.append(
            "org.opencontainers.image.revision must be a full Git commit SHA"
        )

    source = labels.get("org.opencontainers.image.source", "")
    if source and not source.startswith("https://github.com/"):
        errors.append(
            "org.opencontainers.image.source must be the GitHub repository URL"
        )

    return errors


def inspect_labels(image: str) -> dict[str, str]:
    output = subprocess.check_output(
        [
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            "{{ json .Config.Labels }}",
        ],
        text=True,
    )
    labels = json.loads(output)
    if not isinstance(labels, dict):
        return {}
    return {str(key): str(value) for key, value in labels.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    args = parser.parse_args()

    errors = validate_labels(inspect_labels(args.image))
    for error in errors:
        print(f"image label error: {error}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
