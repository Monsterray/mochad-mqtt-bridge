# MQTT Mochad Bridge

![Status](https://img.shields.io/badge/status-integration%20testing-yellow)
![Version](https://img.shields.io/badge/version-0.1.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

MQTT Mochad Bridge connects a running `mochad` TCP service to MQTT so X10
devices can be used by Home Assistant through MQTT Discovery.

This repository is the bridge project only. It does not build `mochad` and
does not pin `mochad`; the bridge connects to an external `mochad` TCP service.

## Status

Integration testing is in progress.

Project version: `0.1.0`

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

## Configuration

Important environment variables:

```text
MOCHAD_HOST
MOCHAD_PORT
MQTT_HOST
MQTT_PORT
MQTT_USERNAME
MQTT_PASSWORD
MQTT_BASE_TOPIC
MQTT_DISCOVERY_PREFIX
X10_DEVICES
LOG_LEVEL
BRIDGE_DEBUG_WIRE
```

The variables above match the bridge runtime configuration in `config.py`.
`BRIDGE_HEALTH_MAX_AGE_SECONDS` is used by the Docker health check.

Example devices:

```text
X10_DEVICES=A1:Living Room Lamp:light,A2:Coffee Maker:switch
```

## MQTT Topics

Device topics are based on stable X10 addresses:

```text
x10/A1/command
x10/A1/state
x10/A1/event
x10/A1/attributes
x10/bridge/availability
x10/bridge/status
```

Home Assistant discovery topics:

```text
homeassistant/light/x10_A1/config
homeassistant/switch/x10_A2/config
```

Friendly names only affect Home Assistant display names. They never affect
MQTT topic identity or Home Assistant `unique_id`.

## Debugging

Set `BRIDGE_DEBUG_WIRE=true` to log mochad TCP reads and MQTT publishes.

The image includes manual mochad TCP helpers under `/app/tools`.

## License

MIT. See [LICENSE.md](LICENSE.md).
