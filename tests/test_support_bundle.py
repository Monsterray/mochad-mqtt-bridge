import io
import json
from pathlib import Path
import stat
import tarfile

import pytest

from tools.support_bundle import (
    SupportBundleError,
    create_bundle,
    scan_archive,
)


SHA = "a" * 40


def _members(path: Path) -> dict[str, bytes]:
    with tarfile.open(path, "r:gz") as archive:
        return {
            member.name: archive.extractfile(member).read()
            for member in archive.getmembers()
            if member.isfile()
        }


def test_bundle_is_sanitized_bounded_and_manifested(tmp_path):
    config = tmp_path / "bridge.json"
    config.write_text(
        json.dumps(
            {
                "profile_schema_version": 2,
                "profiles": {"allow_experimental": True},
                "devices": [
                    {
                        "address": "A1",
                        "name": "Living Room",
                        "type": "switch",
                        "profile": "generic_switch",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    status = tmp_path / "status.json"
    status.write_text(
        json.dumps({"device": "A1", "host": "192.168.8.99"}),
        encoding="utf-8",
    )
    log = tmp_path / "bridge.log.input"
    log.write_text(
        "old line\nA1 connected to 192.168.8.99\npassword=hunter2\n"
        '"MQTT_PASSWORD": "json hunter2"\n',
        encoding="utf-8",
    )
    output = tmp_path / "support.tar.gz"

    create_bundle(
        output,
        repository_sha=SHA,
        config_path=config,
        status_path=status,
        log_path=log,
        max_log_lines=3,
    )

    members = _members(output)
    manifest = json.loads(members["manifest.json"])
    scan_result = json.loads(members["scan-result.json"])
    combined = b"\n".join(members.values()).decode()
    assert manifest["schema_version"] == 1
    assert manifest["components"][0]["sha"] == SHA
    assert manifest["secret_scan"]["status"] == "PASS"
    assert scan_result == manifest["secret_scan"]
    assert scan_result["archive_scanned"] is True
    assert scan_result["unresolved_findings"] == 0
    assert manifest["entries"][0]["repository_owner"] == "mochad-mqtt-bridge"
    assert "hunter2" not in combined
    assert "json hunter2" not in combined
    assert "192.168.8.99" not in combined
    assert '"A1"' not in combined
    assert "HOST_1" in combined
    assert "DEVICE_1" in combined
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert scan_archive(output) == []


def test_archive_scan_fails_closed_and_output_is_removed(tmp_path, monkeypatch):
    output = tmp_path / "support.tar.gz"

    monkeypatch.setattr(
        "tools.support_bundle.scan_archive",
        lambda path: ["manifest.json: synthetic secret"],
    )

    with pytest.raises(SupportBundleError, match="secret scan failed"):
        create_bundle(output, repository_sha=SHA)
    assert not output.exists()


def test_archive_scanner_checks_names_and_contents(tmp_path):
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        content = b'"MQTT_PASSWORD": "not redacted"\n'
        info = tarfile.TarInfo("safe.txt")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))

    assert scan_archive(archive_path)
