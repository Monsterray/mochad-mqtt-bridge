#!/usr/bin/env python3
"""Offline backup and isolated restore for bridge-owned configuration."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import config as bridge_config
from discovery_registry import DiscoveryRegistry, DiscoveryRegistryError
from version import BRIDGE_VERSION

MANIFEST_SCHEMA_VERSION = 1
DISCOVERY_REGISTRY_VERSION = 1
MAX_ARCHIVE_MEMBER_BYTES = 10 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MODE_RE = re.compile(r"^0[0-7]{3}$")
SECRET_KEY_RE = re.compile(
    r"(^|_)(credential|password|private_key|secret|token)(_|$)",
    re.IGNORECASE,
)
PRIVATE_KEY_RE = re.compile(br"-----BEGIN [A-Z ]*PRIVATE KEY-----")
URL_CREDENTIAL_RE = re.compile(
    br"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@",
    re.IGNORECASE,
)

OWNED_FILES = (
    {
        "name": "bridge.json",
        "role": "bridge_configuration",
        "required": True,
        "restore_order": 10,
        "stable_identity_role": "device addresses and named-profile selection",
    },
    {
        "name": "discovery_registry.json",
        "role": "discovery_cleanup_history",
        "required": False,
        "restore_order": 20,
        "stable_identity_role": "rebuildable retained-discovery topic history",
    },
)

SECRET_PLACEHOLDERS = (
    {
        "name": "MQTT_PASSWORD_FILE",
        "required_when": "MQTT password authentication is configured",
        "value": None,
    },
    {
        "name": "MQTT_TLS_CA_FILE",
        "required_when": "a custom MQTT certificate authority is configured",
        "value": None,
    },
    {
        "name": "MQTT_TLS_CERT_FILE",
        "required_when": "MQTT mutual TLS is configured",
        "value": None,
    },
    {
        "name": "MQTT_TLS_KEY_FILE",
        "required_when": "MQTT mutual TLS is configured",
        "value": None,
    },
    {
        "name": "MQTT_TLS_KEY_PASSWORD_FILE",
        "required_when": "the MQTT private key is encrypted",
        "value": None,
    },
)


class BackupRestoreError(RuntimeError):
    """Raised when backup or restore validation fails."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _validate_repository_sha(value: str) -> str:
    normalized = value.strip().lower()
    if not GIT_SHA_RE.fullmatch(normalized):
        raise BackupRestoreError(
            "repository SHA must be exactly 40 hexadecimal characters"
        )
    return normalized


def discover_repository_sha() -> str:
    repository = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BackupRestoreError(
            "could not determine repository SHA; pass --repository-sha"
        ) from exc
    return _validate_repository_sha(result.stdout)


def _read_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupRestoreError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BackupRestoreError(f"{label} must contain a JSON object")
    return parsed


def _find_secret_key(value: object, path: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if SECRET_KEY_RE.search(key_text):
                return f"{path}.{key_text}"
            found = _find_secret_key(child, f"{path}.{key_text}")
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_secret_key(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _validate_bridge_json(data: bytes) -> None:
    parsed = _read_json(data, "bridge.json")
    secret_key = _find_secret_key(parsed)
    if secret_key or PRIVATE_KEY_RE.search(data) or URL_CREDENTIAL_RE.search(data):
        location = secret_key or (
            "URL credentials" if URL_CREDENTIAL_RE.search(data) else "private-key content"
        )
        raise BackupRestoreError(
            f"bridge.json contains secret material at {location}; "
            "store secrets separately and use *_FILE settings"
        )

    try:
        friendly_names = bridge_config._file_bool(
            parsed,
            "use_friendly_names",
            True,
        )
        profile_options = parsed.get("profiles", {})
        if not isinstance(profile_options, dict):
            raise bridge_config.ConfigError(
                "Config file field 'profiles' must be an object."
            )
        allow_experimental = bridge_config._file_bool(
            profile_options,
            "allow_experimental",
            False,
        )
        if "devices" in parsed and "x10_devices" in parsed:
            raise bridge_config.ConfigError(
                "Set only one of 'devices' or 'x10_devices' in bridge.json."
            )
        if "devices" in parsed:
            bridge_config.parse_device_config(
                parsed["devices"],
                use_friendly_names=friendly_names,
                allow_experimental_profiles=allow_experimental,
            )
        elif "x10_devices" in parsed:
            bridge_config.parse_devices(
                str(parsed["x10_devices"]),
                use_friendly_names=friendly_names,
                allow_experimental_profiles=allow_experimental,
            )
    except bridge_config.ConfigError as exc:
        raise BackupRestoreError(f"bridge.json configuration is invalid: {exc}") from exc


def _validate_discovery_registry(data: bytes) -> None:
    parsed = _read_json(data, "discovery_registry.json")
    try:
        DiscoveryRegistry("discovery_registry.json")._parse_registry_data(parsed)
    except DiscoveryRegistryError as exc:
        raise BackupRestoreError(f"discovery registry is invalid: {exc}") from exc


def _validate_owned_file(name: str, data: bytes) -> None:
    if name == "bridge.json":
        _validate_bridge_json(data)
    elif name == "discovery_registry.json":
        _validate_discovery_registry(data)
    else:
        raise BackupRestoreError(f"unsupported backup entry {name!r}")


def _tar_add_bytes(
    archive: tarfile.TarFile,
    name: str,
    data: bytes,
    *,
    mode: int = 0o600,
) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    archive.addfile(info, io.BytesIO(data))


def create_backup(
    config_root: str | Path,
    output_path: str | Path,
    *,
    repository_sha: str,
    installation_method: str = "unknown",
) -> dict[str, Any]:
    """Create an unsanitized archive containing only bridge-owned config."""

    source_root = Path(config_root).resolve()
    output = Path(output_path).resolve()
    if output.exists():
        raise BackupRestoreError(f"backup archive already exists: {output}")

    entries: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for definition in OWNED_FILES:
        source = source_root / definition["name"]
        if not source.exists():
            if definition["required"]:
                raise BackupRestoreError(f"required file is missing: {source}")
            continue
        if not source.is_file() or source.is_symlink():
            raise BackupRestoreError(f"backup source must be a regular file: {source}")

        data = source.read_bytes()
        _validate_owned_file(definition["name"], data)
        file_stat = source.stat()
        archive_path = f"files/config/{definition['name']}"
        payloads[archive_path] = data
        entries.append(
            {
                "logical_role": definition["role"],
                "owning_repository": "mochad-mqtt-bridge",
                "original_path": f"/config/{definition['name']}",
                "archive_path": archive_path,
                "sha256": _sha256(data),
                "owner": str(file_stat.st_uid),
                "group": str(file_stat.st_gid),
                "mode": f"0{stat.S_IMODE(file_stat.st_mode):03o}",
                "required": definition["required"],
                "secret_classification": "non-secret",
                "restore_order": definition["restore_order"],
                "stable_identity_role": definition["stable_identity_role"],
                "compatibility_constraints": {
                    "backup_manifest_schema": MANIFEST_SCHEMA_VERSION,
                    "discovery_registry_schema": DISCOVERY_REGISTRY_VERSION,
                },
            }
        )

    repository_sha = _validate_repository_sha(repository_sha)
    created_at = _utc_now()
    backup_id = _sha256(
        (
            created_at
            + repository_sha
            + "".join(entry["sha256"] for entry in entries)
        ).encode("utf-8")
    )[:20]
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "backup_id": backup_id,
        "created_at": created_at,
        "classification": "UNSANITIZED OPERATIONAL BACKUP",
        "source": {
            "repository": "mochad-mqtt-bridge",
            "version": BRIDGE_VERSION,
            "sha": repository_sha,
            "platform": {
                "system": platform.system(),
                "machine": platform.machine(),
            },
            "installation_method": installation_method,
        },
        "compatibility_contract_versions": {
            "backup_manifest": MANIFEST_SCHEMA_VERSION,
            "command_evidence": 1,
            "device_profile": 2,
            "diagnostics": 1,
            "discovery_registry": DISCOVERY_REGISTRY_VERSION,
        },
        "entries": entries,
        "external_secret_placeholders": list(SECRET_PLACEHOLDERS),
        "restore_prerequisites": [
            "Use an isolated target root.",
            "Recreate MQTT and TLS secrets separately.",
            "Stop the isolated bridge before activation.",
        ],
        "rollback": [
            "Retain the archive and pre-restore files until validation passes.",
            "If activation fails, the tool restores every replaced file.",
            "Do not copy restored files into production until isolated validation passes.",
        ],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            _tar_add_bytes(
                archive,
                "manifest.json",
                (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(
                    "utf-8"
                ),
            )
            for archive_path, data in payloads.items():
                _tar_add_bytes(archive, archive_path, data)
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    except (OSError, tarfile.TarError) as exc:
        temporary.unlink(missing_ok=True)
        raise BackupRestoreError(f"could not create backup archive: {exc}") from exc

    return manifest


def _validated_archive_path(value: object) -> str:
    if not isinstance(value, str):
        raise BackupRestoreError("entry archive_path must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise BackupRestoreError(f"unsafe archive path: {value!r}")
    return value


def _validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise BackupRestoreError("unsupported backup manifest schema_version")
    if not isinstance(manifest.get("backup_id"), str) or not manifest["backup_id"]:
        raise BackupRestoreError("manifest backup_id must be a non-empty string")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise BackupRestoreError("manifest source must be an object")
    if source.get("repository") != "mochad-mqtt-bridge":
        raise BackupRestoreError("backup is not owned by mochad-mqtt-bridge")
    _validate_repository_sha(str(source.get("sha", "")))

    compatibility = manifest.get("compatibility_contract_versions")
    if not isinstance(compatibility, dict):
        raise BackupRestoreError(
            "manifest compatibility_contract_versions must be an object"
        )
    if compatibility.get("backup_manifest") != MANIFEST_SCHEMA_VERSION:
        raise BackupRestoreError("incompatible backup manifest contract")
    if compatibility.get("device_profile") not in (1, 2):
        raise BackupRestoreError("unsupported device profile contract")
    if compatibility.get("discovery_registry") != DISCOVERY_REGISTRY_VERSION:
        raise BackupRestoreError("unsupported discovery registry contract")

    placeholders = manifest.get("external_secret_placeholders")
    expected_placeholders = {item["name"] for item in SECRET_PLACEHOLDERS}
    if (
        not isinstance(placeholders, list)
        or {
            item.get("name")
            for item in placeholders
            if isinstance(item, dict) and item.get("value") is None
        }
        != expected_placeholders
    ):
        raise BackupRestoreError(
            "manifest external secret placeholders are missing or invalid"
        )

    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise BackupRestoreError("manifest entries must be a list")

    definitions = {item["name"]: item for item in OWNED_FILES}
    entries: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_orders: set[int] = set()
    for entry in raw_entries:
        if not isinstance(entry, dict):
            raise BackupRestoreError("manifest entries must be objects")
        original = entry.get("original_path")
        if not isinstance(original, str):
            raise BackupRestoreError("entry original_path must be a string")
        name = PurePosixPath(original).name
        definition = definitions.get(name)
        if (
            definition is None
            or original != f"/config/{name}"
            or entry.get("owning_repository") != "mochad-mqtt-bridge"
        ):
            raise BackupRestoreError(f"unsupported manifest entry: {original!r}")
        if name in seen_names:
            raise BackupRestoreError(f"duplicate manifest entry: {name}")
        seen_names.add(name)

        archive_path = _validated_archive_path(entry.get("archive_path"))
        if archive_path != f"files/config/{name}":
            raise BackupRestoreError(f"unexpected archive path for {name}")
        if not SHA256_RE.fullmatch(str(entry.get("sha256", ""))):
            raise BackupRestoreError(f"invalid sha256 for {name}")
        if not MODE_RE.fullmatch(str(entry.get("mode", ""))):
            raise BackupRestoreError(f"invalid mode for {name}")
        if not str(entry.get("owner", "")).isdigit():
            raise BackupRestoreError(f"invalid owner for {name}")
        if not str(entry.get("group", "")).isdigit():
            raise BackupRestoreError(f"invalid group for {name}")
        if entry.get("required") is not definition["required"]:
            raise BackupRestoreError(f"invalid required flag for {name}")
        if entry.get("secret_classification") != "non-secret":
            raise BackupRestoreError(f"invalid secret classification for {name}")
        restore_order = entry.get("restore_order")
        if (
            not isinstance(restore_order, int)
            or restore_order != definition["restore_order"]
            or restore_order in seen_orders
        ):
            raise BackupRestoreError(f"invalid restore_order for {name}")
        seen_orders.add(restore_order)
        entries.append(entry)

    if "bridge.json" not in seen_names:
        raise BackupRestoreError("required bridge.json entry is missing")
    return sorted(entries, key=lambda item: item["restore_order"])


def inspect_backup(path: str | Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Inspect and validate an archive without extracting it."""

    archive_path = Path(path)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise BackupRestoreError("backup archive contains duplicate members")
            for member in members:
                _validated_archive_path(member.name)
                if not member.isfile():
                    raise BackupRestoreError(
                        f"backup member must be a regular file: {member.name}"
                    )
                if member.size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise BackupRestoreError(
                        f"backup member exceeds size limit: {member.name}"
                    )
            if "manifest.json" not in names:
                raise BackupRestoreError("backup archive has no manifest.json")

            manifest_file = archive.extractfile("manifest.json")
            if manifest_file is None:
                raise BackupRestoreError("could not read manifest.json")
            manifest = _read_json(manifest_file.read(), "manifest.json")
            entries = _validate_manifest(manifest)
            expected_names = {"manifest.json"} | {
                entry["archive_path"] for entry in entries
            }
            if set(names) != expected_names:
                raise BackupRestoreError(
                    "backup archive contains undeclared or missing members"
                )

            payloads: dict[str, bytes] = {}
            for entry in entries:
                member_file = archive.extractfile(entry["archive_path"])
                if member_file is None:
                    raise BackupRestoreError(
                        f"could not read {entry['archive_path']}"
                    )
                data = member_file.read()
                if _sha256(data) != entry["sha256"]:
                    raise BackupRestoreError(
                        f"checksum mismatch for {entry['original_path']}"
                    )
                name = PurePosixPath(entry["original_path"]).name
                _validate_owned_file(name, data)
                payloads[entry["archive_path"]] = data
    except (OSError, tarfile.TarError) as exc:
        raise BackupRestoreError(f"could not inspect backup archive: {exc}") from exc

    return manifest, payloads


def _target_destination(root: Path, original_path: str) -> Path:
    destination = root / original_path.lstrip("/")
    if not destination.resolve(strict=False).is_relative_to(root):
        raise BackupRestoreError(f"restore path escapes target root: {original_path}")
    return destination


def plan_restore(
    manifest: dict[str, Any],
    payloads: dict[str, bytes],
    target_root: str | Path,
    *,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    root = Path(target_root).resolve()
    if root == Path("/"):
        raise BackupRestoreError("target root '/' is not isolated")

    plan: list[dict[str, Any]] = []
    for entry in _validate_manifest(manifest):
        destination = _target_destination(root, entry["original_path"])
        if destination.is_symlink():
            raise BackupRestoreError(f"restore destination is a symlink: {destination}")
        if destination.exists():
            if not destination.is_file():
                raise BackupRestoreError(
                    f"restore destination is not a regular file: {destination}"
                )
            action = (
                "unchanged"
                if _sha256(destination.read_bytes()) == entry["sha256"]
                else "replace"
            )
            if action == "replace" and not overwrite:
                raise BackupRestoreError(
                    f"{destination} exists with different content; "
                    "pass --overwrite to approve replacement"
                )
        else:
            action = "create"
        plan.append(
            {
                "entry": entry,
                "data": payloads[entry["archive_path"]],
                "destination": destination,
                "action": action,
            }
        )
    return plan


def _apply_metadata(path: Path, entry: dict[str, Any]) -> None:
    uid = int(entry["owner"])
    gid = int(entry["group"])
    current = path.stat()
    if (current.st_uid, current.st_gid) != (uid, gid):
        try:
            os.chown(path, uid, gid)
        except PermissionError as exc:
            raise BackupRestoreError(
                f"cannot restore owner {uid}:{gid} for {path}"
            ) from exc
    os.chmod(path, int(entry["mode"], 8))


def _verify_file(path: Path, entry: dict[str, Any]) -> None:
    if _sha256(path.read_bytes()) != entry["sha256"]:
        raise BackupRestoreError(f"post-stage checksum mismatch for {path}")
    file_stat = path.stat()
    if stat.S_IMODE(file_stat.st_mode) != int(entry["mode"], 8):
        raise BackupRestoreError(f"post-stage mode mismatch for {path}")
    if (file_stat.st_uid, file_stat.st_gid) != (
        int(entry["owner"]),
        int(entry["group"]),
    ):
        raise BackupRestoreError(f"post-stage ownership mismatch for {path}")


def _rollback(states: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for state in reversed(states):
        destination = state["destination"]
        rollback_path = state["rollback"]
        try:
            destination.unlink(missing_ok=True)
            if state["had_original"] and rollback_path.exists():
                os.replace(rollback_path, destination)
        except OSError as exc:
            failures.append(f"{destination}: {exc}")
    return failures


def restore_backup(
    archive_path: str | Path,
    target_root: str | Path,
    *,
    apply: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Inspect, validate, plan, and optionally activate an isolated restore."""

    manifest, payloads = inspect_backup(archive_path)
    plan = plan_restore(
        manifest,
        payloads,
        target_root,
        overwrite=overwrite or not apply,
    )
    public_plan = [
        {
            "path": item["entry"]["original_path"],
            "action": item["action"],
            "required": item["entry"]["required"],
        }
        for item in plan
    ]
    if not apply:
        return {
            "status": "PASS",
            "mode": "dry-run",
            "stages": ["inspect", "validate", "plan"],
            "plan": public_plan,
        }

    root = Path(target_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stage_root = root / f".mochad-bridge-restore-{manifest['backup_id']}"
    if stage_root.exists():
        raise BackupRestoreError(
            f"restore staging path already exists; inspect and remove it: {stage_root}"
        )
    payload_root = stage_root / "payload"
    rollback_root = stage_root / "rollback"
    states: list[dict[str, Any]] = []
    rollback_failed = False
    try:
        for item in plan:
            if item["action"] == "unchanged":
                continue
            staged = payload_root / item["entry"]["archive_path"]
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(item["data"])
            _apply_metadata(staged, item["entry"])
            _verify_file(staged, item["entry"])
            item["staged"] = staged

        for item in plan:
            if item["action"] == "unchanged":
                continue
            destination = item["destination"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            rollback_path = rollback_root / item["entry"]["archive_path"]
            rollback_path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "destination": destination,
                "rollback": rollback_path,
                "had_original": destination.exists(),
            }
            if state["had_original"]:
                os.replace(destination, rollback_path)
            states.append(state)
            os.replace(item["staged"], destination)

        for item in plan:
            _verify_file(item["destination"], item["entry"])
    except (OSError, BackupRestoreError) as exc:
        failures = _rollback(states)
        rollback_failed = bool(failures)
        detail = f"; rollback failures: {', '.join(failures)}" if failures else ""
        raise BackupRestoreError(f"restore activation failed: {exc}{detail}") from exc
    finally:
        if stage_root.exists() and not rollback_failed:
            shutil.rmtree(stage_root)

    return {
        "status": "PASS",
        "mode": "apply",
        "stages": ["inspect", "validate", "plan", "stage", "verify", "activate"],
        "plan": public_plan,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline bridge configuration backup and isolated restore"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="create an unsanitized backup")
    backup.add_argument("--config-root", default="/config")
    backup.add_argument("--output", required=True)
    backup.add_argument("--repository-sha")
    backup.add_argument(
        "--installation-method",
        choices=("docker", "native", "unknown"),
        default="unknown",
    )

    restore = subparsers.add_parser("restore", help="validate or restore a backup")
    restore.add_argument("archive")
    restore.add_argument("--target-root", required=True)
    restore.add_argument(
        "--apply",
        action="store_true",
        help="activate into the isolated target (default: dry-run)",
    )
    restore.add_argument(
        "--overwrite",
        action="store_true",
        help="approve replacement of different existing files",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.command == "backup":
            manifest = create_backup(
                args.config_root,
                args.output,
                repository_sha=args.repository_sha or discover_repository_sha(),
                installation_method=args.installation_method,
            )
            result = {
                "status": "PASS",
                "archive": str(Path(args.output).resolve()),
                "backup_id": manifest["backup_id"],
                "classification": manifest["classification"],
            }
        else:
            result = restore_backup(
                args.archive,
                args.target_root,
                apply=args.apply,
                overwrite=args.overwrite,
            )
    except BackupRestoreError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
