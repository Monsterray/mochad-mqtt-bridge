#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
version="$(tr -d '\n' < VERSION)"
fail() { echo "FAIL: $*" >&2; exit 1; }

[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-dev|-rc[1-9][0-9]*)?$ ]] || fail "VERSION must be a supported semantic version"
grep -Fq "BRIDGE_VERSION = \"$version\"" version.py || fail "version.py does not match VERSION"
set -a
. release/versions.env
set +a
[ "$IMAGE_VERSION" = "$version" ] || fail "release IMAGE_VERSION does not match VERSION"
[[ "$PYTHON_BASE_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || fail "PYTHON_BASE_IMAGE must be digest-qualified"
grep -Fq 'ARG IMAGE_VERSION' Dockerfile || fail "Dockerfile does not accept IMAGE_VERSION"
grep -Fq 'org.opencontainers.image.version="${IMAGE_VERSION}"' Dockerfile || fail "Docker label does not use IMAGE_VERSION"
grep -Fq '"bridge": {' bridge.py || fail "bridge status does not include bridge metadata"
grep -Fq '"version": BRIDGE_VERSION' bridge.py || fail "bridge status does not use runtime version"
grep -Fq '"sw_version": self._device_sw_version' discovery.py || fail "discovery does not use bridge version metadata"

evidence_version="${version%-dev}"
grep -Fq "## [$version]" CHANGELOG.md || fail "CHANGELOG.md has no heading for $version"
evidence="validation/releases/v${evidence_version}.md"
[ -f "$evidence" ] || fail "missing release evidence template or record: $evidence"
grep -Fq -- "- Release: v$evidence_version" "$evidence" || fail "release evidence does not declare v$evidence_version"
if git describe --tags --exact-match >/dev/null 2>&1; then
    [ "$(git describe --tags --exact-match)" = "v$version" ] || fail "checked-out tag does not match VERSION"
fi
echo "PASS: version consistency completed for mqtt-mochad-bridge $version"
