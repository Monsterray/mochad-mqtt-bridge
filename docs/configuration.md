# Configuration

Runtime configuration is environment-based, with supported device settings
also persisted in `/config/bridge.json`.

## Environment Variables

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
MQTT_DISCOVERY_ENABLED
BRIDGE_CONFIG_FILE
BRIDGE_CONFIG_RELOAD_INTERVAL_SECONDS
BRIDGE_HEALTH_MAX_AGE_SECONDS
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

These values correspond to the runtime parser in `config.py`; use
[`.env.example`](../.env.example) as the deployment template.

## Device Configuration

Compact device entries use:

```text
address:name:type:command_repeats:command_repeat_delay_ms
```

Example:

```text
X10_DEVICES=A1:Living Room Lamp:light:3:150,A2:Coffee Maker:switch:1:150
```

Repeat count defaults to `1`, delay defaults to `150` milliseconds, and only
`ON` and `OFF` repeat.

`BRIDGE_CONFIG_FILE` defaults to `/config/bridge.json`. When absent, it is
created from active environment-derived device settings. Existing files are
not overwritten. The bridge polls it at
`BRIDGE_CONFIG_RELOAD_INTERVAL_SECONDS`.

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
    }
  ]
}
```

The file may instead use the compact `x10_devices` string. Set
`X10_USE_FRIENDLY_NAMES=false` to display stable addresses as names.

`X10_HOUSECODES` restricts accepted house codes. Supported forms include `A`,
`ACF`, `A,C,F`, and `A-D`. Filtered events do not create state or discovery.

## Container Permissions

Defaults are `PUID=911`, `PGID=911`, `TZ=UTC`, and `UMASK=022`. The container
prepares `/config`, then permanently drops privileges. Application files stay
owned by `root:root`.

Compose `user:` bypasses this initialization. Pre-own volumes and provide
required groups in that externally managed mode.

## MQTT Authentication and TLS

The bridge supports direct and file-based broker passwords. Never configure
both `MQTT_PASSWORD` and `MQTT_PASSWORD_FILE`.

Enable TLS explicitly:

```text
MQTT_TLS_ENABLED=true
MQTT_PORT=8883
```

Without `MQTT_TLS_CA_FILE`, Python uses the system trust store. A private CA
can be mounted under `/run/secrets`:

```text
MQTT_TLS_CA_FILE=/run/secrets/mqtt_ca.crt
```

Mutual TLS requires both certificate and private key:

```text
MQTT_TLS_CERT_FILE=/run/secrets/mqtt_client.crt
MQTT_TLS_KEY_FILE=/run/secrets/mqtt_client.key
MQTT_TLS_KEY_PASSWORD_FILE=/run/secrets/mqtt_client_key_password
```

The bridge rejects insecure hostname verification and never falls back to
plaintext. TLS file settings while TLS is disabled are configuration errors.

`docker-compose.secrets.yml` demonstrates top-level Compose secrets mounted
under `/run/secrets`. Real files under `secrets/` are ignored by Git and are
never copied into `/config`.

## Discovery and Maintenance

`MQTT_DISCOVERY_ENABLED` controls whether Home Assistant discovery messages are
generated and published. It does not disable core MQTT event transport.

Discovery registry state defaults to
`/config/discovery_registry.json`. `DISCOVERY_CLEANUP=true` prunes stale
discovery topics during startup.

Safe Home Assistant buttons for `SYNC` and `REDISCOVER` are enabled by default.
Destructive maintenance controls require
`ENABLE_MAINTENANCE_BUTTONS=true`.

## Debugging

Set `BRIDGE_DEBUG_WIRE=true` to log mochad TCP reads and MQTT sends. Passwords,
private keys, and secret contents are never logged.
