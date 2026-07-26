# MQTT Topics and Bridge Controls

Topic identity always uses immutable X10 addresses. Friendly names affect Home
Assistant display names only.

## Device Topics

```text
x10/A1/command
x10/A1/state
x10/A1/event
x10/A1/attributes
```

`command` is write-only input, `state` is authoritative retained state for
stateful devices, and `event` is a non-retained event stream. Action-only
devices do not publish retained state.

## Bridge Topics

```text
x10/bridge/availability
x10/bridge/status
x10/bridge/command
x10/bridge/response
```

The retained status document summarizes bridge, MQTT, mochad, USB, controller,
version, TLS, and active profile evidence without exposing secrets or verbose
statistics.

## Discovery Topics

Examples:

```text
homeassistant/light/x10_A1/config
homeassistant/switch/x10_A2/config
homeassistant/button/x10_A3/config
homeassistant/sensor/mqtt_mochad_bridge_status/config
homeassistant/binary_sensor/mqtt_mochad_bridge_mochad_connected/config
homeassistant/binary_sensor/mqtt_mochad_bridge_usb_connected/config
homeassistant/sensor/mqtt_mochad_bridge_controller/config
homeassistant/sensor/mqtt_mochad_bridge_mochad_version/config
homeassistant/button/mqtt_mochad_bridge_sync/config
homeassistant/button/mqtt_mochad_bridge_rediscover/config
```

Discovery uses stable `unique_id` values and `default_entity_id` hints. It does
not use the deprecated `object_id` field.

## Bridge Commands

Publish one of these payloads to `x10/bridge/command`:

```text
PING
STATUS
SYNC
REDISCOVER
PRUNE_DISCOVERY
RESET_DISCOVERY
```

Results are published to `x10/bridge/response`. Home Assistant exposes `SYNC`
and `REDISCOVER` by default. `PRUNE_DISCOVERY` and `RESET_DISCOVERY` require
the maintenance opt-in.
