# Hardware Lab Setup

The bridge hardware lab is deliberately separate from Home Assistant and
production MQTT. It uses a restricted SSH account and an isolated broker.

## Account and Lock

An administrator creates `codex-x10` with home and workspace
`/srv/x10-dev`, membership in `x10dev` and `x10`, and no `sudo` or `docker`
membership. The shared controller lock must be created once:

```sh
install -o root -g x10dev -m 0660 /dev/null /run/lock/x10-hardware.lock
```

The existing CM19A udev permission policy must expose `0bc7:0002` as
`root:x10`, mode `0660`.

## Run

Start a CM19A lab instance of mochad on `127.0.0.1:19099`, then run:

```sh
scripts/hardware/run-bridge-hardware-validation.sh
```

The script starts an isolated Mosquitto broker on `127.0.0.1:11883`, selects a
run-specific `x10-test/<sha>` prefix, and sets `MQTT_DISCOVERY_ENABLED=false`.
It verifies command delivery and the action-only chime state contract. RF
receive and audible SC546A effects remain `HARDWARE REQUIRED` until a person
records them.

## Future Self-Hosted Runner

After this manual process has been reviewed and proven, an optional runner may
use the labels `x10-hardware`, `cm19a`, and `sc546a`. Restrict it to manually
dispatched release workflows on trusted commits. Never register it for fork PRs
or automatic unreviewed branch runs.
