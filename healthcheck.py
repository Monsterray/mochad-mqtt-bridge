#!/usr/bin/env python3
"""
Docker health check for the MQTT mochad bridge.

The bridge writes a heartbeat file from its runtime loop. This script checks
that the heartbeat exists, says "running", and is recent.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


DEFAULT_HEALTH_FILE = "/config/mqtt-mochad-bridge.health"
DEFAULT_MAX_AGE_SECONDS = 30.0


def main() -> int:
    health_file = Path(
        os.getenv("BRIDGE_HEALTH_FILE", DEFAULT_HEALTH_FILE)
    )
    max_age = float(
        os.getenv(
            "BRIDGE_HEALTH_MAX_AGE_SECONDS",
            str(DEFAULT_MAX_AGE_SECONDS),
        )
    )

    try:
        text = health_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(
            f"unhealthy: cannot read health file {health_file}: {exc}",
            file=sys.stderr,
        )
        return 1

    parts = text.split()

    if len(parts) != 2:
        print(
            f"unhealthy: invalid health file content {text!r}",
            file=sys.stderr,
        )
        return 1

    status, timestamp = parts

    if status != "running":
        print(f"unhealthy: status={status}", file=sys.stderr)
        return 1

    try:
        age = time.time() - float(timestamp)
    except ValueError:
        print(
            f"unhealthy: invalid timestamp {timestamp!r}",
            file=sys.stderr,
        )
        return 1

    if age > max_age:
        print(
            f"unhealthy: heartbeat stale age={age:.1f}s max={max_age:.1f}s",
            file=sys.stderr,
        )
        return 1

    print(f"healthy: heartbeat age={age:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
