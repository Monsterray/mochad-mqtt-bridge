#!/usr/bin/env bash
set -euo pipefail

root_dir="$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)"
cd "$root_dir"

shellcheck_bin="${SHELLCHECK:-shellcheck}"
if ! command -v "$shellcheck_bin" >/dev/null 2>&1; then
    printf 'ShellCheck is required; install shellcheck or set SHELLCHECK.\n' >&2
    exit 127
fi

file_list="$(mktemp "${TMPDIR:-/tmp}/mochad-mqtt-bridge-shellcheck.XXXXXX")"
trap 'rm -f "$file_list"' EXIT HUP INT TERM

while IFS= read -r -d '' file; do
    first_line="$(sed -n '1p' "$file")"
    case "$file:$first_line" in
        *.sh:*|*:'#!'*sh*)
            printf '%s\0' "$file" >> "$file_list"
            ;;
    esac
done < <(git ls-files -z)

if [ ! -s "$file_list" ]; then
    printf 'No tracked shell scripts found.\n'
    exit 0
fi

printf 'Checking tracked shell scripts with %s\n' "$shellcheck_bin"
xargs -0 "$shellcheck_bin" -S warning < "$file_list"
