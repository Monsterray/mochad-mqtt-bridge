#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
release="${1:-}"
[[ "$release" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-rc[1-9][0-9]*)?$ ]] || { echo "Usage: $0 <release-version>" >&2; exit 64; }
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "FAIL: clean tree required" >&2
    exit 1
fi

previous="$(tr -d '\n' < VERSION)"
today="$(date +%F)"
printf '%s\n' "$release" > VERSION
scripts/release/sync-version-files.sh
sed -i.bak "s/^## \[$previous\] - Unreleased/## [$release] - $today/" CHANGELOG.md
rm CHANGELOG.md.bak
if ! grep -Fq "## [$release]" CHANGELOG.md; then
    temporary="$(mktemp "${TMPDIR:-/tmp}/bridge-changelog.XXXXXX")"
    awk -v heading="## [$release] - $today" '!done && /^## / { print heading; print ""; print "- Release preparation in progress."; print ""; done=1 } { print }' CHANGELOG.md > "$temporary"
    mv "$temporary" CHANGELOG.md
fi

evidence="validation/releases/v${release}.md"
if [ ! -f "$evidence" ]; then
    sed -e "s/^# Release Evidence: vX.Y.Z/# Release Evidence: v$release/" \
        -e "s/^- Release:$/- Release: v$release/" \
        validation/releases/template.md > "$evidence"
fi
scripts/validate/version-consistency.sh
echo "Prepared $release. No tag, push, publish, or release was created."
