#!/bin/sh
set -eu

PUID="${PUID:-911}"
PGID="${PGID:-911}"
TZ="${TZ:-UTC}"
UMASK="${UMASK:-022}"

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

if ! is_number "$PUID" || ! is_number "$PGID"; then
    echo "[STARTUP] PUID and PGID must be numeric" >&2
    exit 64
fi

if [ "$PUID" = "0" ] || [ "$PGID" = "0" ]; then
    echo "[STARTUP] PUID and PGID must be non-root IDs" >&2
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

chown -R "$PUID:$PGID" /config

group_name="$(name_for_gid "$PGID" || true)"
if [ -n "$group_name" ]; then
    drop_identity="$PUID:$group_name"
else
    drop_identity="$PUID:$PGID"
fi

echo "[STARTUP] prepared /config owner=${PUID}:${PGID} umask=${UMASK} tz=${TZ}"
exec su-exec "$drop_identity" "$@"
