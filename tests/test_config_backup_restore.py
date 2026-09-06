import io
import json
import os
import stat
import tarfile
from pathlib import Path

import pytest

from tools.config_backup_restore import (
    BackupRestoreError,
    create_backup,
    inspect_backup,
    restore_backup,
)

REPOSITORY_SHA = "a" * 40


def _write_config(root: Path, name: str = "Lamp") -> bytes:
    config = root / "bridge.json"
    data = (
        json.dumps(
            {
                "devices": [
                    {"address": "A1", "name": name, "type": "switch"}
                ],
                "profiles": {"allow_experimental": False},
                "use_friendly_names": True,
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()
    config.write_bytes(data)
    os.chmod(config, 0o640)
    return data


def _write_registry(root: Path) -> bytes:
    registry = root / "discovery_registry.json"
    data = (
        json.dumps(
            {
                "version": 1,
                "topics": [{"topic": "homeassistant/switch/x10_A1/config"}],
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()
    registry.write_bytes(data)
    os.chmod(registry, 0o600)
    return data


def _rewrite_archive(
    archive_path: Path,
    transform,
) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        members = {
            member.name: archive.extractfile(member).read()
            for member in archive.getmembers()
        }
    transformed = transform(members)
    temporary = archive_path.with_suffix(".tmp")
    with tarfile.open(temporary, "w:gz") as archive:
        for name, data in transformed.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    os.replace(temporary, archive_path)


def test_backup_includes_only_owned_files_and_manifest(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_config(source)
    _write_registry(source)
    for excluded in (
        "bridge.json.tmp",
        "discovery_registry.json.invalid.20260726",
        "health",
        "bridge.log",
        "mqtt_password",
    ):
        (source / excluded).write_text("excluded", encoding="utf-8")
    archive = tmp_path / "bridge-backup.tar.gz"

    manifest = create_backup(
        source,
        archive,
        repository_sha=REPOSITORY_SHA,
        installation_method="docker",
    )

    with tarfile.open(archive, "r:gz") as bundle:
        assert set(bundle.getnames()) == {
            "manifest.json",
            "files/config/bridge.json",
            "files/config/discovery_registry.json",
        }
    assert manifest["schema_version"] == 1
    assert manifest["source"]["sha"] == REPOSITORY_SHA
    assert manifest["source"]["version"]
    assert [entry["required"] for entry in manifest["entries"]] == [True, False]
    assert all(entry["sha256"] for entry in manifest["entries"])
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600


def test_backup_rejects_secret_config_and_manifest_has_empty_placeholders(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_config(source)
    archive = tmp_path / "bridge-backup.tar.gz"
    manifest = create_backup(source, archive, repository_sha=REPOSITORY_SHA)
    assert all(
        placeholder["value"] is None
        for placeholder in manifest["external_secret_placeholders"]
    )

    (source / "bridge.json").write_text(
        '{"devices": [], "mqtt_password": "not-for-backup"}',
        encoding="utf-8",
    )
    rejected = tmp_path / "rejected.tar.gz"
    with pytest.raises(BackupRestoreError, match=r"secret material.*mqtt_password"):
        create_backup(source, rejected, repository_sha=REPOSITORY_SHA)
    assert not rejected.exists()


@pytest.mark.parametrize(
    "secret",
    [
        '"mqtt_password": "not-for-backup"',
        '"broker": "mqtt://user:password@example.invalid"',
        '"material": "-----BEGIN RSA PRIVATE KEY-----"',
    ],
)
def test_backup_rejects_secret_values(tmp_path, secret):
    source = tmp_path / "source"
    source.mkdir()
    (source / "bridge.json").write_text(
        '{"devices": [], ' + secret + "}",
        encoding="utf-8",
    )

    with pytest.raises(BackupRestoreError, match="secret material"):
        create_backup(
            source,
            tmp_path / "rejected.tar.gz",
            repository_sha=REPOSITORY_SHA,
        )


@pytest.mark.parametrize(
    "failure",
    ["checksum", "manifest-schema", "compatibility", "placeholders"],
)
def test_restore_rejects_checksum_and_schema_failures(tmp_path, failure):
    source = tmp_path / "source"
    source.mkdir()
    _write_config(source)
    archive = tmp_path / "bridge-backup.tar.gz"
    create_backup(source, archive, repository_sha=REPOSITORY_SHA)

    def corrupt(members):
        if failure == "checksum":
            members["files/config/bridge.json"] = b'{"devices": []}\n'
        else:
            manifest = json.loads(members["manifest.json"])
            if failure == "manifest-schema":
                manifest["schema_version"] = 99
            elif failure == "compatibility":
                manifest["compatibility_contract_versions"]["backup_manifest"] = 99
            else:
                manifest["external_secret_placeholders"] = []
            members["manifest.json"] = json.dumps(manifest).encode()
        return members

    _rewrite_archive(archive, corrupt)
    with pytest.raises(
        BackupRestoreError,
        match=(
            "checksum mismatch|unsupported backup manifest|"
            "incompatible backup manifest|external secret placeholders"
        ),
    ):
        inspect_backup(archive)


def test_restore_defaults_to_dry_run_without_writing_target(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_config(source)
    archive = tmp_path / "bridge-backup.tar.gz"
    create_backup(source, archive, repository_sha=REPOSITORY_SHA)
    target = tmp_path / "isolated"

    result = restore_backup(archive, target)

    assert result["mode"] == "dry-run"
    assert result["stages"] == ["inspect", "validate", "plan"]
    assert not target.exists()


def test_isolated_restore_preserves_content_mode_and_order(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    bridge_data = _write_config(source)
    registry_data = _write_registry(source)
    archive = tmp_path / "bridge-backup.tar.gz"
    create_backup(source, archive, repository_sha=REPOSITORY_SHA)
    target = tmp_path / "isolated"

    result = restore_backup(archive, target, apply=True)

    assert result["mode"] == "apply"
    assert (target / "config/bridge.json").read_bytes() == bridge_data
    assert (target / "config/discovery_registry.json").read_bytes() == registry_data
    assert stat.S_IMODE((target / "config/bridge.json").stat().st_mode) == 0o640
    assert stat.S_IMODE(
        (target / "config/discovery_registry.json").stat().st_mode
    ) == 0o600


def test_different_existing_file_requires_explicit_overwrite(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    expected = _write_config(source)
    archive = tmp_path / "bridge-backup.tar.gz"
    create_backup(source, archive, repository_sha=REPOSITORY_SHA)
    target_file = tmp_path / "isolated/config/bridge.json"
    target_file.parent.mkdir(parents=True)
    target_file.write_text('{"devices": []}\n', encoding="utf-8")

    dry_run = restore_backup(archive, tmp_path / "isolated")
    assert dry_run["plan"][0]["action"] == "replace"

    with pytest.raises(BackupRestoreError, match="pass --overwrite"):
        restore_backup(archive, tmp_path / "isolated", apply=True)
    assert target_file.read_text(encoding="utf-8") == '{"devices": []}\n'

    restore_backup(
        archive,
        tmp_path / "isolated",
        apply=True,
        overwrite=True,
    )
    assert target_file.read_bytes() == expected


def test_activation_failure_restores_every_original_file(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    _write_config(source, "New")
    _write_registry(source)
    archive = tmp_path / "bridge-backup.tar.gz"
    create_backup(source, archive, repository_sha=REPOSITORY_SHA)
    target = tmp_path / "isolated"
    target_config = target / "config"
    target_config.mkdir(parents=True)
    old_bridge = _write_config(target_config, "Old")
    old_registry = b'{"topics": [], "version": 1}\n'
    (target_config / "discovery_registry.json").write_bytes(old_registry)

    real_replace = os.replace
    failed = False

    def fail_second_activation(source_path, destination_path):
        nonlocal failed
        source_text = str(source_path)
        if (
            not failed
            and "/payload/files/config/discovery_registry.json" in source_text
        ):
            failed = True
            raise OSError("synthetic activation failure")
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(os, "replace", fail_second_activation)
    with pytest.raises(BackupRestoreError, match="synthetic activation failure"):
        restore_backup(archive, target, apply=True, overwrite=True)

    assert (target_config / "bridge.json").read_bytes() == old_bridge
    assert (target_config / "discovery_registry.json").read_bytes() == old_registry


def test_repeated_restore_is_idempotent_without_overwrite(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_config(source)
    archive = tmp_path / "bridge-backup.tar.gz"
    create_backup(source, archive, repository_sha=REPOSITORY_SHA)
    target = tmp_path / "isolated"

    restore_backup(archive, target, apply=True)
    result = restore_backup(archive, target, apply=True)

    assert result["plan"] == [
        {"path": "/config/bridge.json", "action": "unchanged", "required": True}
    ]


def test_restore_refuses_stale_staging_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_config(source)
    archive = tmp_path / "bridge-backup.tar.gz"
    manifest = create_backup(source, archive, repository_sha=REPOSITORY_SHA)
    target = tmp_path / "isolated"
    stale = target / f".mochad-bridge-restore-{manifest['backup_id']}"
    stale.mkdir(parents=True)

    with pytest.raises(BackupRestoreError, match="staging path already exists"):
        restore_backup(archive, target, apply=True)
    assert stale.exists()
