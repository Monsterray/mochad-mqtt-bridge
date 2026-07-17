from __future__ import annotations

import time

import pytest

import healthcheck


@pytest.mark.lifecycle
@pytest.mark.parametrize("status", ["starting", "running"])
def test_recent_bridge_heartbeat_is_healthy_while_reconnecting(tmp_path, monkeypatch, status):
    path = tmp_path / "bridge.health"
    path.write_text(f"{status} {time.time():.3f}\n", encoding="utf-8")
    monkeypatch.setenv("BRIDGE_HEALTH_FILE", str(path))
    monkeypatch.setenv("BRIDGE_HEALTH_MAX_AGE_SECONDS", "30")

    assert healthcheck.main() == 0


@pytest.mark.lifecycle
def test_stopped_bridge_heartbeat_is_unhealthy(tmp_path, monkeypatch):
    path = tmp_path / "bridge.health"
    path.write_text(f"stopped {time.time():.3f}\n", encoding="utf-8")
    monkeypatch.setenv("BRIDGE_HEALTH_FILE", str(path))

    assert healthcheck.main() == 1
