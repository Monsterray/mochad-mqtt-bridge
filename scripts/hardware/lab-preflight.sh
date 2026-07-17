#!/usr/bin/env bash
set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
lock_path=${X10_HARDWARE_LOCK_PATH:-/run/lock/x10-hardware.lock}
mochad_port=${MOCHAD_LAB_PORT:-19099}
mqtt_port=${MQTT_LAB_PORT:-11883}
mqtt_topic=${MQTT_BASE_TOPIC:-}

fail() { echo "FAIL: $*" >&2; exit 1; }
for port in "$mochad_port" "$mqtt_port"; do
    case "$port" in 1[0-9][0-9][0-9][0-9]) ;; *) fail "lab port must be in 10000-19999: $port" ;; esac
done
[ -n "$mqtt_topic" ] || fail "MQTT_BASE_TOPIC must be set to a test topic"
case "$mqtt_topic" in x10-test/*) ;; *) fail "MQTT_BASE_TOPIC must begin with x10-test/" ;; esac
[ "${MQTT_DISCOVERY_ENABLED:-}" = false ] || fail "MQTT_DISCOVERY_ENABLED must be false"

git -C "$repo_root" diff --quiet || fail "working tree has unstaged changes"
git -C "$repo_root" diff --cached --quiet || fail "working tree has staged changes"
[ -z "$(git -C "$repo_root" status --porcelain --untracked-files=normal)" ] || fail "working tree has untracked files"
id -nG | tr ' ' '\n' | grep -Fx x10 >/dev/null || fail "current account is not in x10"
id -nG | tr ' ' '\n' | grep -Fx x10dev >/dev/null || fail "current account is not in x10dev"
[ -e "$lock_path" ] && [ -w "$lock_path" ] || fail "hardware lock must exist and be writable: $lock_path"

node=
for device in /sys/bus/usb/devices/*; do
    [ -r "$device/idVendor" ] && [ -r "$device/idProduct" ] || continue
    [ "$(cat "$device/idVendor")" = 0bc7 ] && [ "$(cat "$device/idProduct")" = 0002 ] || continue
    node=$(printf '/dev/bus/usb/%03d/%03d' "$(cat "$device/busnum")" "$(cat "$device/devnum")")
    break
done
[ -n "${node:-}" ] && [ -r "$node" ] && [ -w "$node" ] || fail "CM19A 0bc7:0002 is unavailable or inaccessible"

echo "PASS: bridge hardware lab preflight"
echo "repository_sha=$(git -C "$repo_root" rev-parse HEAD)"
echo "controller_node=$node permissions=$(stat -c '%U:%G %a' "$node")"
