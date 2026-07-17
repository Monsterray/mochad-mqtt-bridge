#!/usr/bin/env bash
set -euo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
MOCHAD_LAB_HOST=${MOCHAD_LAB_HOST:-127.0.0.1}
MOCHAD_LAB_PORT=${MOCHAD_LAB_PORT:-19099}
MQTT_LAB_PORT=${MQTT_LAB_PORT:-11883}
run_id=$(git -C "$repo_root" rev-parse --short HEAD)
MQTT_BASE_TOPIC=${MQTT_BASE_TOPIC:-"x10-test/$run_id"}
MQTT_DISCOVERY_ENABLED=false
X10_HARDWARE_LOCK_PATH=${X10_HARDWARE_LOCK_PATH:-/run/lock/x10-hardware.lock}
EVIDENCE_FILE=${EVIDENCE_FILE:-"$repo_root/validation/bridge-hardware-$(date -u +%Y%m%dT%H%M%SZ).md"}
tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/bridge-hardware.XXXXXX")
bridge_log="$tmpdir/bridge.log"
broker_log="$tmpdir/mosquitto.log"

record() { "$repo_root/scripts/hardware/record-result.sh" --output "$EVIDENCE_FILE" "$@"; }
cleanup() {
    [ -n "${bridge_pid:-}" ] && kill "$bridge_pid" 2>/dev/null || true
    [ -n "${broker_pid:-}" ] && kill "$broker_pid" 2>/dev/null || true
    [ -n "${bridge_pid:-}" ] && wait "$bridge_pid" 2>/dev/null || true
    [ -n "${broker_pid:-}" ] && wait "$broker_pid" 2>/dev/null || true
    rm -rf "$tmpdir"
}
trap cleanup EXIT INT TERM HUP

export MOCHAD_LAB_PORT MQTT_LAB_PORT MQTT_BASE_TOPIC MQTT_DISCOVERY_ENABLED X10_HARDWARE_LOCK_PATH
"$repo_root/scripts/hardware/lab-preflight.sh"
for command in mosquitto mosquitto_pub mosquitto_sub; do command -v "$command" >/dev/null 2>&1 || { echo "FAIL: $command is required" >&2; exit 127; }; done
command -v python3 >/dev/null 2>&1 || { echo "FAIL: python3 is required" >&2; exit 127; }

exec 9>"$X10_HARDWARE_LOCK_PATH"
flock -n 9 || { echo "FAIL: X10 controller is already claimed" >&2; exit 75; }
cat >"$tmpdir/mosquitto.conf" <<EOF
listener $MQTT_LAB_PORT 127.0.0.1
allow_anonymous true
persistence false
EOF
mosquitto -c "$tmpdir/mosquitto.conf" >"$broker_log" 2>&1 &
broker_pid=$!

for _ in $(seq 1 20); do nc -z 127.0.0.1 "$MQTT_LAB_PORT" >/dev/null 2>&1 && break; sleep 1; done
nc -z 127.0.0.1 "$MQTT_LAB_PORT" >/dev/null 2>&1 || { record --check "isolated MQTT broker" --status FAIL --note "listener did not start"; exit 1; }

config_file="$tmpdir/bridge.json"
cat >"$config_file" <<'EOF'
{"devices":[{"address":"A2","name":"Lab Chime","type":"chime"}]}
EOF
MOCHAD_HOST="$MOCHAD_LAB_HOST" MOCHAD_PORT="$MOCHAD_LAB_PORT" \
MQTT_HOST=127.0.0.1 MQTT_PORT="$MQTT_LAB_PORT" MQTT_BASE_TOPIC="$MQTT_BASE_TOPIC" \
MQTT_DISCOVERY_ENABLED=false BRIDGE_CONFIG_FILE="$config_file" DISCOVERY_REGISTRY_PATH="$tmpdir/discovery.json" \
python3 "$repo_root/mqtt_mochad_bridge.py" >"$bridge_log" 2>&1 &
bridge_pid=$!

for _ in $(seq 1 20); do grep -q 'Bridge Running' "$bridge_log" && break; sleep 1; done
grep -q 'Bridge Running' "$bridge_log" || { record --check "bridge startup" --status FAIL --note "bridge did not start"; exit 1; }
record --check "bridge startup" --status PASS --note "isolated bridge connected to lab broker"

mosquitto_pub -h 127.0.0.1 -p "$MQTT_LAB_PORT" -t "$MQTT_BASE_TOPIC/A2/command" -m ON
mosquitto_pub -h 127.0.0.1 -p "$MQTT_LAB_PORT" -t "$MQTT_BASE_TOPIC/A2/command" -m ON
for _ in $(seq 1 20); do [ "$(grep -c 'mochad tcp write line=rf A2 on' "$bridge_log" || true)" -ge 2 ] && break; sleep 1; done
[ "$(grep -c 'mochad tcp write line=rf A2 on' "$bridge_log" || true)" -ge 2 ] || { record --check "repeated SC546A ON" --status FAIL --note "two commands did not reach mochad"; exit 1; }
record --check "MQTT-to-mochad repeated SC546A ON" --status PASS --note "two distinct RF ON commands reached mochad"

if timeout 2 mosquitto_sub -h 127.0.0.1 -p "$MQTT_LAB_PORT" -C 1 -t "$MQTT_BASE_TOPIC/A2/state" >/dev/null 2>&1; then
    record --check "chime retained state" --status FAIL --note "action-only chime unexpectedly published state"
    exit 1
fi
record --check "chime retained state" --status PASS --note "no state was published for action-only chime"

if timeout 2 mosquitto_sub -h 127.0.0.1 -p "$MQTT_LAB_PORT" -C 1 -t 'homeassistant/#' >/dev/null 2>&1; then
    record --check "Home Assistant discovery" --status FAIL --note "discovery was published despite MQTT_DISCOVERY_ENABLED=false"
    exit 1
fi
record --check "Home Assistant discovery" --status PASS --note "discovery was disabled"
record --check "real mochad event ingestion" --status HARDWARE\ REQUIRED --note "Press a remote button and confirm a matching MQTT event under $MQTT_BASE_TOPIC."
record --check "SC546A audible result" --status HARDWARE\ REQUIRED --note "Confirm each chime activation manually; successful RF submission is not physical confirmation."

echo "Evidence: $EVIDENCE_FILE"
echo "Press a remote button, inspect $bridge_log, then press Enter to stop."
read -r _
