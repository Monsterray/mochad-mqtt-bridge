# MQTT Mochad Bridge

![Status](https://img.shields.io/badge/status-release%20candidate-yellow)
![Version](https://img.shields.io/badge/version-0.4.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

MQTT Mochad Bridge connects a running `mochad` TCP service to MQTT so X10
devices can be used by Home Assistant through MQTT Discovery.

This repository is the bridge project only. It does not build `mochad` and
does not pin `mochad`; the bridge connects to an external `mochad` TCP service.

## Status

Version 0.4.0 is in release-candidate validation.

The project version is maintained in [VERSION](VERSION). Release image inputs
are tracked separately in [release/versions.env](release/versions.env).

## Versioning

Files use plain semantic versions such as `0.5.0`, `0.5.0-dev`, and `0.5.0-rc1`;
Git tags add a leading `v`. `scripts/release/prepare-release.sh` and
`scripts/release/prepare-next-dev.sh` prepare reviewable local changes only.
They never commit, tag, push, publish, or create a GitHub release. See
[compatibility](docs/compatibility.md) for the bridge release mapping.

Tested with:

- `mochad` 0.1.18
- Python 3.12 in Docker
- Eclipse Mosquitto
- Home Assistant MQTT Discovery

## Quick Start

1. Copy the example environment file:

```sh
cp .env.example .env
```

2. Edit `.env` for your MQTT broker, `mochad` host, and X10 devices. If
   `mochad` runs on the host or another server, set `MOCHAD_HOST` to that host
   name or IP address.

3. Make sure the Docker network used by your MQTT broker exists:

```sh
docker network create mqtt
```

If the network already exists, Docker will report that and you can continue.

4. Build and run:

```sh
docker compose up --build
```

The standalone compose file expects an external Docker network named `mqtt` by
default. Set `MQTT_DOCKER_NETWORK` if your broker is on a different network.

## Beta Testing

Version 0.4.0 is a cautious public beta. Use a tagged beta image or exact full
Git SHA, not develop or another moving branch. Pull-request CI separates fast
source checks from MQTT, lifecycle, container, and multiarchitecture checks;
consult the checks attached to the tested SHA for exact evidence. Physical
module delivery is not implied by a successful software transmission.

See [docs/beta-status.md](docs/beta-status.md) and file a Beta test report with
sanitized logs and a rollback result.

## Docker Image

The compose file builds the image locally for development and first-run testing.
Version tags publish multi-platform release images to:

```text
ghcr.io/monsterray/mochad-mqtt-bridge
```

To use a published image, replace the compose `build:` block with an `image:`
reference such as:

```yaml
image: ghcr.io/monsterray/mochad-mqtt-bridge:0.4.0
```

Pushing a matching `v*` tag publishes `linux/amd64` and `linux/arm64` images
with SBOM and provenance attestations, then creates the GitHub Release. Manual
workflow runs build without publishing.

Release image inputs are tracked in `release/versions.env`. Release Docker
builds use a digest-qualified Python base image and install dependencies from
`requirements.release.txt` with `pip --require-hashes`. OCI labels are populated
from Git metadata in CI so release images identify the exact source revision and
Git commit timestamp.

CI workflow and branch-protection setup is documented in
[`docs/ci-branch-protection.md`](docs/ci-branch-protection.md).

The container starts as root only long enough to prepare `/config`, then drops
to the configured `PUID:PGID` before starting the bridge. Application files
remain owned by `root:root`; only `/config` is made writable by the runtime
identity. The bridge health check uses the bundled Python runtime, so the image
does not need curl, wget, netcat, or other maintenance tools.

## Configuration

Important environment variables:

```text
MOCHAD_HOST
MOCHAD_PORT
PUID
PGID
TZ
UMASK
ALLOW_ROOT
MQTT_HOST
MQTT_PORT
MQTT_USERNAME
MQTT_PASSWORD
MQTT_PASSWORD_FILE
MQTT_TLS_ENABLED
MQTT_TLS_CA_FILE
MQTT_TLS_CERT_FILE
MQTT_TLS_KEY_FILE
MQTT_TLS_KEY_PASSWORD
MQTT_TLS_KEY_PASSWORD_FILE
MQTT_BASE_TOPIC
MQTT_DISCOVERY_PREFIX
BRIDGE_CONFIG_FILE
BRIDGE_CONFIG_RELOAD_INTERVAL_SECONDS
DISCOVERY_CLEANUP
DISCOVERY_REGISTRY_PATH
ENABLE_MAINTENANCE_BUTTONS
ALLOW_EXPERIMENTAL_PROFILES
X10_DEVICES
X10_USE_FRIENDLY_NAMES
X10_HOUSECODES
LOG_LEVEL
BRIDGE_DEBUG_WIRE
```

The variables above match the bridge runtime configuration in `config.py`.
`BRIDGE_HEALTH_MAX_AGE_SECONDS` is used by the Docker health check. The check
reports healthy while the bridge is starting or reconnecting; MQTT and mochad
availability remain visible in the retained bridge status document.

`PUID`, `PGID`, `TZ`, and `UMASK` control container runtime permissions. The
defaults are `PUID=911`, `PGID=911`, `TZ=UTC`, and `UMASK=022`. If Compose
`user:` is set, Docker bypasses this root initialization step; in that mode,
pre-own mounted volumes and provide any required `group_add` values yourself.
That mode is intended for externally managed deployments. The normal Compose
path is to leave `user:` unset and use `PUID`, `PGID`, and `UMASK`.

`MOCHAD_PORT` should point at the main mochad TCP listener. The default is
`1099`, and the bridge expects newline-delimited mochad events and diagnostic
responses on that listener. Do not point the bridge at port `1100`; that port
is the legacy Flash XMLSocket-compatible listener, which changes event framing
from newline-delimited to NUL-delimited and does not provide structured XML.
The bridge intentionally does not support the XMLSocket listener unless a
future legacy-compatibility requirement makes it necessary.

Example devices:

```text
X10_DEVICES=A1:Living Room Lamp:light,A2:Coffee Maker:switch,A3:Door Chime:chime
```

Optional command repeat settings can be appended per device:

```text
X10_DEVICES=A1:Living Room Lamp:light:3:150,A2:Coffee Maker:switch:1:150
```

The fourth field is the command repeat count and defaults to `1`. The fifth
field is the delay between repeats in milliseconds and defaults to `150`.
Repeats are bridge-side reliability tuning only; Home Assistant discovery is
unchanged. The bridge repeats only `ON` and `OFF` commands. `DIM` and `BRIGHT`
remain single-shot so brightness does not move farther than requested.

User-declared action-only devices can use the generic `chime` type without
making a named-model support claim:

```text
X10_DEVICES=A3:Door Chime:chime
```

Chimes are discovered in Home Assistant as buttons. Pressing the button
publishes `ON` to the normal per-address command topic, for example
`x10/A3/command`. Chimes are not stateful: the bridge does not publish retained
state for them, does not optimistically report them as `ON`, and emits only a
non-retained event noting that the physical transmission is unconfirmed.

Generic device types are user-declared capability profiles. They do not claim
that the project has verified a particular hardware model. The optional named
SC546A profile remains experimental and is rejected unless explicitly enabled:

```text
ALLOW_EXPERIMENTAL_PROFILES=true
X10_DEVICES=A3:Door Chime:sc546a_chime
```

Selecting an experimental profile logs a warning and reports its lifecycle and
evidence status in `x10/bridge/status`. Research-only profiles cannot be
selected and are never replaced silently with a generic type. See
[`docs/capability-device-registry.md`](docs/capability-device-registry.md).

Friendly names are enabled by default and are used only for Home Assistant
display names. Set `X10_USE_FRIENDLY_NAMES=false` to make discovered entity
names use stable X10 addresses such as `A1`.

Runtime-editable bridge files live under `/config`. By default
`BRIDGE_CONFIG_FILE` points to `/config/bridge.json`. If the file does not
exist on startup, the bridge creates it from the active environment-derived
device settings. Existing files are never overwritten. The bridge checks the
file every
`BRIDGE_CONFIG_RELOAD_INTERVAL_SECONDS` seconds and republishes Home Assistant
discovery when device names or configured devices change.

Example `bridge.json`:

```json
{
  "profiles": {
    "allow_experimental": false
  },
  "use_friendly_names": true,
  "devices": [
    {
      "address": "A1",
      "name": "Living Room Lamp",
      "type": "light",
      "command_repeats": 3,
      "command_repeat_delay_ms": 150
    },
    {
      "address": "A2",
      "name": "Coffee Maker",
      "type": "switch"
    },
    {
      "address": "A3",
      "name": "Door Chime",
      "type": "chime"
    }
  ]
}
```

The JSON file can also use the compact string form:

```json
{
  "use_friendly_names": false,
  "x10_devices": "A1:Living Room Lamp:light,A2:Coffee Maker:switch"
}
```

Set `X10_HOUSECODES` to restrict which X10 house codes the bridge accepts.
Unset means all house codes. Examples: `A`, `ACF`, `A,C,F`, or `A-D`.
Filtered house codes do not create device state or Home Assistant discovery.

## MQTT TLS

TLS is disabled by default. Enable it explicitly:

```text
MQTT_TLS_ENABLED=true
MQTT_PORT=8883
```

When TLS is enabled without `MQTT_TLS_CA_FILE`, Python's system trust store is
used. To trust a private Mosquitto CA, mount the CA file into the container and
set:

```text
MQTT_TLS_CA_FILE=/run/secrets/mqtt_ca.crt
```

For mutual TLS, configure both the client certificate and private key:

```text
MQTT_TLS_CERT_FILE=/run/secrets/mqtt_client.crt
MQTT_TLS_KEY_FILE=/run/secrets/mqtt_client.key
MQTT_TLS_KEY_PASSWORD_FILE=/run/secrets/mqtt_client_key_password
```

`MQTT_PASSWORD_FILE` and `MQTT_TLS_KEY_PASSWORD_FILE` support Docker-secret
style files. Do not set both `MQTT_PASSWORD` and `MQTT_PASSWORD_FILE`, or both
`MQTT_TLS_KEY_PASSWORD` and `MQTT_TLS_KEY_PASSWORD_FILE`.

An example Compose overlay is provided in `docker-compose.secrets.yml`. It
declares top-level Compose secrets, mounts them under `/run/secrets`, and wires
them into the existing `*_FILE` environment variables:

```sh
docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d
```

Real secret files should live under a local `secrets/` directory. That
directory is ignored by Git and secrets are never copied into `/config` by the
bridge.

The bridge does not support insecure hostname verification and does not
automatically fall back to plaintext. If any TLS file or private-key password
setting is provided while `MQTT_TLS_ENABLED=false`, startup fails so the broker
connection cannot silently downgrade.

## MQTT Topics

Device topics are based on stable X10 addresses:

```text
x10/A1/command
x10/A1/state
x10/A1/event
x10/A1/attributes
x10/bridge/availability
x10/bridge/status
x10/bridge/command
x10/bridge/response
```

Home Assistant discovery topics:

```text
homeassistant/light/x10_A1/config
homeassistant/switch/x10_A2/config
homeassistant/sensor/mqtt_mochad_bridge_status/config
homeassistant/binary_sensor/mqtt_mochad_bridge_mochad_connected/config
homeassistant/binary_sensor/mqtt_mochad_bridge_usb_connected/config
homeassistant/sensor/mqtt_mochad_bridge_controller/config
homeassistant/sensor/mqtt_mochad_bridge_mochad_version/config
homeassistant/button/mqtt_mochad_bridge_sync/config
homeassistant/button/mqtt_mochad_bridge_rediscover/config
```

Friendly names only affect Home Assistant display names. They never affect
MQTT topic identity or Home Assistant `unique_id`.

The bridge publishes one retained JSON status document to
`x10/bridge/status`. On mochad-redux connect or reconnect, the bridge queries
`hello`, `capabilities`, and `health` over the main newline-delimited mochad
listener, then folds the useful results into that status document. Home
Assistant diagnostics are discovered from that document: bridge status, mochad
connection, USB connection, controller type, and mochad version. mochad-redux
capability data is grouped under `mochad.features`, and runtime controller data
is grouped under `mochad.health`. MQTT TLS diagnostics are reported as safe
booleans under `mqtt.tls`; file paths and passwords are never published. The
retained registry at `DISCOVERY_REGISTRY_PATH` is updated on startup. Set
`DISCOVERY_CLEANUP=true` to also prune stale Home Assistant MQTT discovery
topics on startup.

Discovery payloads use stable `unique_id` values and `default_entity_id` hints.
They do not set Home Assistant's deprecated discovery payload `object_id`.

Bridge control commands are published to `x10/bridge/command` with one of
these payloads:

```text
PING
STATUS
SYNC
REDISCOVER
PRUNE_DISCOVERY
RESET_DISCOVERY
```

Command results are published to `x10/bridge/response`. Home Assistant buttons
for `SYNC` and `REDISCOVER` are discovered by default. Set
`ENABLE_MAINTENANCE_BUTTONS=true` to enable destructive maintenance commands
and Home Assistant buttons for `PRUNE_DISCOVERY` and `RESET_DISCOVERY`.

## Future Mochad JSON API

The bridge currently uses the main newline-delimited mochad TCP listener on
port `1099`. A future `mochad-redux` milestone may add an optional generic
JSON-RPC API on port `1102`. When that daemon API exists, the bridge can add a
protocol selector such as:

```text
MOCHAD_PROTOCOL=auto|json|legacy
```

Planned behavior:

- `auto`: try the JSON API, then fall back to the legacy main listener.
- `json`: require the JSON API and fail clearly if it is unavailable.
- `legacy`: keep the current newline-delimited listener behavior.

This is not implemented yet. The daemon JSON protocol must remain generic X10
infrastructure; MQTT topics and Home Assistant entity concepts stay in this
bridge and in Home Assistant integrations, not in `mochad-redux`.

## Debugging

Set `BRIDGE_DEBUG_WIRE=true` to log mochad TCP reads and MQTT publishes.

The image includes manual mochad TCP helpers under `/app/tools`.

## License

MIT. See [LICENSE.md](LICENSE.md).
