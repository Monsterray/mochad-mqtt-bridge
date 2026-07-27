#!/usr/bin/env python3
"""Create a local, sanitized bridge support bundle."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


SCHEMA_VERSION = 1
MAX_LOG_LINES = 1000
SECRET_RULES = (
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(
        r"(?i)\b(password|passwd|token|authorization|api[_-]?key|secret)"
        r"\s*[:=]\s*(?!\[REDACTED:)[^\s,;]+"
    ),
    re.compile(r"(?i)\bmqtts?://[^/\s:@]+:[^@\s]+@"),
)
SECRET_NAME_RULE = re.compile(
    r"(^|[._-])(\.env|id_rsa|private|secret|password|token|credentials?|key)"
    r"($|[._-])",
    re.IGNORECASE,
)
ADDRESS_RE = re.compile(r"\b[A-P](?:[1-9]|1[0-6])\b")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HOME_PATH_RE = re.compile(r"(?:/Users|/home)/[^/\s]+")


class SupportBundleError(RuntimeError):
    pass


class Redactor:
    def __init__(self) -> None:
        self._aliases: dict[tuple[str, str], str] = {}

    def text(self, value: str) -> str:
        value = re.sub(
            r"-----BEGIN [^-]*PRIVATE KEY-----.*?"
            r"-----END [^-]*PRIVATE KEY-----",
            "[REDACTED:private_key]",
            value,
            flags=re.IGNORECASE | re.DOTALL,
        )
        value = re.sub(
            r"(?i)(\b(?:password|passwd|token|authorization|api[_-]?key|secret)"
            r"\s*[:=]\s*)[^\s,;]+",
            r"\1[REDACTED:secret]",
            value,
        )
        value = re.sub(
            r"(?i)(\bmqtts?://)[^/\s:@]+:[^@\s]+@",
            r"\1[REDACTED:credentials]@",
            value,
        )
        value = ADDRESS_RE.sub(
            lambda match: self._alias("DEVICE", match.group(0)),
            value,
        )
        value = IPV4_RE.sub(
            lambda match: self._alias("HOST", match.group(0)),
            value,
        )
        return HOME_PATH_RE.sub(
            lambda match: self._alias("PATH", match.group(0)),
            value,
        )

    def aliases(self) -> dict[str, str]:
        return {
            alias: category
            for (category, _), alias in sorted(
                self._aliases.items(),
                key=lambda item: item[1],
            )
        }

    def _alias(self, category: str, value: str) -> str:
        key = (category, value)
        if key not in self._aliases:
            count = sum(
                existing_category == category
                for existing_category, _ in self._aliases
            )
            self._aliases[key] = f"{category}_{count + 1}"
        return self._aliases[key]


def create_bundle(
    output: Path,
    *,
    repository_sha: str,
    config_path: Path | None = None,
    status_path: Path | None = None,
    log_path: Path | None = None,
    max_log_lines: int = 200,
) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", repository_sha):
        raise SupportBundleError("repository SHA must be 40 lowercase hex characters")
    if not 1 <= max_log_lines <= MAX_LOG_LINES:
        raise SupportBundleError(
            f"max log lines must be between 1 and {MAX_LOG_LINES}"
        )

    output = output.resolve()
    if _scan_name(output.name):
        raise SupportBundleError("output archive name contains a sensitive term")
    output.parent.mkdir(parents=True, exist_ok=True)
    redactor = Redactor()
    staging = Path(
        tempfile.mkdtemp(prefix=".bridge-support-", dir=output.parent)
    )
    staging.chmod(0o700)
    temporary_archive = output.with_suffix(output.suffix + ".tmp")
    entries: list[dict[str, object]] = []

    try:
        _collect_config(staging, entries, config_path, redactor)
        if status_path is None or not status_path.exists():
            _omitted(entries, "bridge-status.json", "input not provided")
        else:
            _collect_json(
                staging,
                entries,
                "bridge-status.json",
                _read_json(status_path),
                "operational",
                redactor,
            )
        _collect_log(
            staging,
            entries,
            log_path,
            max_log_lines,
            redactor,
        )
        scan_result = {
            "scanner": "mochad-mqtt-bridge-stdlib-scanner",
            "version": "1",
            "rule_set_sha256": _ruleset_hash(),
            "files_scanned": 0,
            "findings_by_class": {},
            "unresolved_findings": 0,
            "archive_scanned": False,
            "status": "PASS",
        }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "bundle_id": hashlib.sha256(
                f"{repository_sha}:{_utc_now()}".encode()
            ).hexdigest()[:20],
            "created_at": _utc_now(),
            "generator": {
                "name": "mochad-mqtt-bridge-support-bundle",
                "version": "1",
                "repository_sha": repository_sha,
            },
            "components": [
                {
                    "repository": "mochad-mqtt-bridge",
                    "version": _project_version(),
                    "sha": repository_sha,
                }
            ],
            "redaction": {
                "rules_version": 1,
                "aliases": redactor.aliases(),
            },
            "entries": entries,
            "secret_scan": scan_result,
        }
        _write_text(
            staging / "manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        _write_text(
            staging / "scan-result.json",
            json.dumps(scan_result, indent=2, sort_keys=True) + "\n",
        )
        findings = scan_directory(staging)
        if findings:
            raise SupportBundleError(_finding_message(findings))

        _create_archive(staging, temporary_archive)
        findings = scan_archive(temporary_archive)
        if findings:
            raise SupportBundleError(_finding_message(findings))

        scan_result["files_scanned"] = sum(
            path.is_file() for path in staging.rglob("*")
        )
        scan_result["archive_scanned"] = True
        _write_text(
            staging / "manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        _write_text(
            staging / "scan-result.json",
            json.dumps(scan_result, indent=2, sort_keys=True) + "\n",
        )
        findings = scan_directory(staging)
        if findings:
            raise SupportBundleError(_finding_message(findings))

        _create_archive(staging, temporary_archive)
        findings = scan_archive(temporary_archive)
        if findings:
            raise SupportBundleError(_finding_message(findings))
        temporary_archive.replace(output)
        output.chmod(0o600)
        return output
    finally:
        temporary_archive.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)


def _create_archive(staging: Path, output: Path) -> None:
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(staging))
    output.chmod(0o600)


def scan_directory(root: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        findings.extend(_scan_name(str(relative)))
        findings.extend(_scan_bytes(str(relative), path.read_bytes()))
    return findings


def scan_archive(path: Path) -> list[str]:
    findings: list[str] = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            findings.extend(_scan_name(member.name))
            extracted = archive.extractfile(member)
            if extracted is not None:
                findings.extend(_scan_bytes(member.name, extracted.read()))
    return findings


def _collect_config(
    staging: Path,
    entries: list[dict[str, object]],
    path: Path | None,
    redactor: Redactor,
) -> None:
    if path is None or not path.exists():
        _omitted(entries, "configuration-summary.json", "config not provided")
        return
    data = _read_json(path)
    devices = data.get("devices", [])
    if isinstance(devices, dict):
        devices = list(devices.values())
    if not isinstance(devices, list):
        devices = []
    type_counts = Counter(
        str(device.get("type", device.get("entity_type", "unknown")))
        for device in devices
        if isinstance(device, dict)
    )
    profile_ids = sorted(
        {
            str(device["profile"])
            for device in devices
            if isinstance(device, dict) and device.get("profile")
        }
    )
    _collect_json(
        staging,
        entries,
        "configuration-summary.json",
        {
            "profile_schema_version": data.get("profile_schema_version", 1),
            "device_count": len(devices),
            "device_types": dict(sorted(type_counts.items())),
            "profile_ids": profile_ids,
            "experimental_profiles_enabled": bool(
                data.get("profiles", {}).get("allow_experimental", False)
            )
            if isinstance(data.get("profiles", {}), dict)
            else False,
        },
        "operational",
        redactor,
    )


def _collect_log(
    staging: Path,
    entries: list[dict[str, object]],
    path: Path | None,
    max_lines: int,
    redactor: Redactor,
) -> None:
    name = "bridge.log"
    if path is None or not path.exists():
        _omitted(entries, name, "bounded log input not provided")
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    content = redactor.text("\n".join(lines[-max_lines:]) + "\n")
    target = staging / name
    _write_text(target, content)
    entries.append(_entry(target, staging, "operational"))


def _collect_json(
    staging: Path,
    entries: list[dict[str, object]],
    name: str,
    payload: object,
    classification: str,
    redactor: Redactor,
) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    target = staging / name
    _write_text(target, redactor.text(serialized))
    entries.append(_entry(target, staging, classification))


def _entry(path: Path, root: Path, classification: str) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "logical_name": path.name,
        "repository_owner": "mochad-mqtt-bridge",
        "category": path.stem,
        "collection_command": "read explicitly selected local input",
        "status": "collected",
        "reason": None,
        "path": str(path.relative_to(root)),
        "media_type": (
            "application/json" if path.suffix == ".json" else "text/plain"
        ),
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "sensitivity": classification,
        "redactions": ["deterministic_pseudonyms", "secret_rules"],
    }


def _omitted(
    entries: list[dict[str, object]],
    name: str,
    reason: str,
) -> None:
    entries.append(
        {
            "logical_name": name,
            "repository_owner": "mochad-mqtt-bridge",
            "category": Path(name).stem,
            "status": "omitted",
            "reason": reason,
            "path": None,
            "media_type": None,
            "size": None,
            "sha256": None,
            "sensitivity": "operational",
            "collection_command": None,
            "redactions": [],
        }
    )


def _scan_name(name: str) -> list[str]:
    return [f"{name}: sensitive filename"] if SECRET_NAME_RULE.search(name) else []


def _scan_bytes(name: str, content: bytes) -> list[str]:
    if b"\0" in content:
        return [f"{name}: binary content is not allowlisted"]
    text = content.decode("utf-8", errors="replace")
    return [
        f"{name}: matched secret rule {index}"
        for index, rule in enumerate(SECRET_RULES, start=1)
        if rule.search(text)
    ]


def _finding_message(findings: list[str]) -> str:
    return "secret scan failed: " + "; ".join(findings[:5])


def _ruleset_hash() -> str:
    rules = [
        *(rule.pattern for rule in SECRET_RULES),
        SECRET_NAME_RULE.pattern,
        ADDRESS_RE.pattern,
        IPV4_RE.pattern,
        HOME_PATH_RE.pattern,
    ]
    return hashlib.sha256("\n".join(rules).encode()).hexdigest()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SupportBundleError(f"cannot read JSON input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SupportBundleError(f"JSON input {path} must contain an object")
    return value


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def _project_version() -> str:
    return (Path(__file__).parents[1] / "VERSION").read_text(
        encoding="utf-8"
    ).strip()


def _git_sha() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository-sha", default=_git_sha())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--status", type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--max-log-lines", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("Would collect bridge identity, config summary, status, and bounded logs.")
        return 0
    try:
        output = create_bundle(
            args.output,
            repository_sha=args.repository_sha or "",
            config_path=args.config,
            status_path=args.status,
            log_path=args.log,
            max_log_lines=args.max_log_lines,
        )
    except SupportBundleError as exc:
        parser.error(str(exc))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
