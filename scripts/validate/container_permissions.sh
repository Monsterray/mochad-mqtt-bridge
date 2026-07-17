#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-x10-mochad-mqtt-bridge:permissions}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_BUILT="${IMAGE_BUILT:-false}"

log() {
    printf '[container-permissions] %s\n' "$*"
}

require_docker() {
    command -v docker >/dev/null 2>&1 || {
        printf 'docker is required for container permission validation\n' >&2
        exit 127
    }
}

run_permission_probe() {
    umask_value="$1"
    expected_mode="$2"

    docker run --rm \
        -e PUID=12345 \
        -e PGID=23456 \
        -e UMASK="$umask_value" \
        "$IMAGE" \
        sh -eu -c "
            test \"\$(id -u)\" = '12345'
            test \"\$(id -g)\" = '23456'
            ! touch /app/.permission-test 2>/dev/null
            touch /config/permission-test
            test \"\$(stat -c %u /config/permission-test)\" = '12345'
            test \"\$(stat -c %g /config/permission-test)\" = '23456'
            test \"\$(stat -c %a /config/permission-test)\" = '$expected_mode'
        "
}

expect_failure() {
    description="$1"
    shift

    if docker run --rm "$@" "$IMAGE" sh -c 'true' >/dev/null 2>&1; then
        printf 'expected failure did not occur: %s\n' "$description" >&2
        exit 1
    fi
}

require_docker

if [ "$IMAGE_BUILT" != "true" ]; then
    log "building $IMAGE"
    docker build --pull --tag "$IMAGE" "$ROOT_DIR"
else
    log "using prebuilt $IMAGE"
fi

log "checking PUID/PGID and UMASK=022"
run_permission_probe 022 644

log "checking PUID/PGID and UMASK=002"
run_permission_probe 002 664

log "checking maintenance tools are absent"
docker run --rm --entrypoint sh "$IMAGE" -eu -c '
    for tool in git curl wget bash gcc cc make apk; do
        ! command -v "$tool" >/dev/null 2>&1
    done
'

log "checking configured secret files after privilege drop"
secret_dir="$(mktemp -d)"
trap 'rm -rf "$secret_dir"' EXIT
printf 'secret-value\n' > "$secret_dir/mqtt_password"
docker run --rm \
    -e PUID=12345 \
    -e PGID=23456 \
    -e UMASK=022 \
    -e MQTT_PASSWORD_FILE=/run/secrets/mqtt_password \
    -v "$secret_dir/mqtt_password:/run/secrets/mqtt_password:ro" \
    "$IMAGE" \
    sh -eu -c '
        test "$(id -u)" = "12345"
        test -r /run/secrets/mqtt_password
        ! test -e /config/mqtt_password
    '

log "checking invalid configuration fails fast"
expect_failure "invalid PUID" -e PUID=abc -e PGID=23456
expect_failure "invalid PGID" -e PUID=12345 -e PGID=abc
expect_failure "invalid UMASK" -e PUID=12345 -e PGID=23456 -e UMASK=invalid
expect_failure "root PUID without override" -e PUID=0 -e PGID=23456
expect_failure "root PGID without override" -e PUID=12345 -e PGID=0

log "checking explicit development root override"
docker run --rm \
    -e PUID=0 \
    -e PGID=0 \
    -e ALLOW_ROOT=true \
    "$IMAGE" \
    sh -eu -c 'test "$(id -u)" = "0" && test "$(id -g)" = "0"'

log "passed"
