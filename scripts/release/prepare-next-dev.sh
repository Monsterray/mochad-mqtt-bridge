#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
next_release="${1:-}"
[[ "$next_release" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Usage: $0 <next-release-version>" >&2; exit 64; }
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "FAIL: clean tree required" >&2
    exit 1
fi

version="${next_release}-dev"
printf '%s\n' "$version" > VERSION
scripts/release/sync-version-files.sh
sed -i.bak "s/^## \[Unreleased\]/## [$version] - Unreleased/" CHANGELOG.md
rm CHANGELOG.md.bak

evidence="validation/releases/v${next_release}.md"
if [ ! -f "$evidence" ]; then
    sed -e "s/^# Release Evidence: vX.Y.Z/# Release Evidence: v$next_release/" \
        -e "s/^- Release:$/- Release: v$next_release/" \
        validation/releases/template.md > "$evidence"
fi
scripts/validate/version-consistency.sh
echo "Prepared $version. No tag, push, publish, or release was created."
