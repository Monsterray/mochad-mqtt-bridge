#!/bin/sh
set -eu

PUID="${PUID:-911}"
PGID="${PGID:-911}"
TZ="${TZ:-UTC}"
UMASK="${UMASK:-022}"
ALLOW_ROOT="${ALLOW_ROOT:-false}"

is_number() {
    case "$1" in
        ''|*[!0-9]*)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}

name_for_gid() {
    awk -F: -v gid="$1" '$3 == gid { print $1; exit }' /etc/group
}

name_for_uid() {
    awk -F: -v uid="$1" '$3 == uid { print $1; exit }' /etc/passwd
}

if ! is_number "$PUID" || ! is_number "$PGID"; then
    echo "[STARTUP] PUID and PGID must be numeric" >&2
    exit 64
fi

if { [ "$PUID" = "0" ] || [ "$PGID" = "0" ]; } && [ "$ALLOW_ROOT" != "true" ]; then
    echo "[STARTUP] PUID and PGID must be non-root IDs unless ALLOW_ROOT=true" >&2
    exit 64
fi

if ! umask "$UMASK"; then
    echo "[STARTUP] UMASK must be a valid octal mask" >&2
    exit 64
fi

export TZ
mkdir -p /config

if [ "$(id -u)" != "0" ]; then
    echo "[STARTUP] running as preconfigured user uid=$(id -u) gid=$(id -g); skipping PUID/PGID initialization"
    exec "$@"
fi

group_name="$(name_for_gid "$PGID" || true)"
if [ -z "$group_name" ]; then
    group_name="appgroup"
    addgroup -g "$PGID" "$group_name"
fi

user_name="$(name_for_uid "$PUID" || true)"
if [ -z "$user_name" ]; then
    user_name="appuser"
    adduser -D -H -u "$PUID" -G "$group_name" "$user_name"
else
    addgroup "$user_name" "$group_name" >/dev/null 2>&1 || true
fi

chown -R "$PUID:$PGID" /config

echo "[STARTUP] prepared /config owner=${PUID}:${PGID} umask=${UMASK} tz=${TZ}"
exec su-exec "$user_name" "$@"
