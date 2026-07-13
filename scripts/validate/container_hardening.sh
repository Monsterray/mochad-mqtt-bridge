#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-x10-mochad-mqtt-bridge:hardening}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

log() {
    printf '[container-hardening] %s\n' "$*"
}

require_docker() {
    command -v docker >/dev/null 2>&1 || {
        printf 'docker is required for container hardening validation\n' >&2
        exit 127
    }
}

run_in_image() {
    docker run --rm \
        --read-only \
        --tmpfs /tmp \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        -e PUID=12345 \
        -e PGID=23456 \
        -e UMASK=022 \
        "$IMAGE" "$@"
}

require_docker

log "building $IMAGE"
docker build --pull --tag "$IMAGE" "$ROOT_DIR"

log "verifying runtime identity, writable paths and absent tools"
run_in_image sh -eu -c '
    test "$(id -u)" = "12345"
    test "$(id -g)" = "23456"
    ! touch /app/.write-test 2>/dev/null
    touch /config/.write-test
    touch /tmp/.write-test

    for tool in git curl wget bash gcc cc musl-gcc make apk; do
        ! command -v "$tool" >/dev/null 2>&1
    done
'

log "verifying /config ownership and umask"
container_id="$(
    docker run -d \
        --read-only \
        --tmpfs /tmp \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        -e PUID=12345 \
        -e PGID=23456 \
        -e UMASK=002 \
        "$IMAGE" \
        sh -eu -c 'touch /config/umask-test && sleep 300'
)"
trap 'docker rm -f "$container_id" >/dev/null 2>&1 || true' EXIT

docker exec "$container_id" sh -eu -c '
    test "$(stat -c %u /config/umask-test)" = "12345"
    test "$(stat -c %g /config/umask-test)" = "23456"
    test "$(stat -c %a /config/umask-test)" = "664"
'

docker rm -f "$container_id" >/dev/null
trap - EXIT

log "passed"
