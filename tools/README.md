# Bridge Image Test Tools

These tools are included inside the `mochad-mqtt-bridge` Docker image under
`/app/tools`. They are for manual network and mochad diagnostics only.

No MQTT usernames or passwords are stored in these files.

Device MQTT topics are always stable X10-address topics such as
`x10/A1/state`. Friendly names are display names only.

These tools use the main mochad TCP listener on port `1099`. Do not use the
legacy Flash XMLSocket-compatible listener on port `1100` for bridge testing;
that listener uses NUL-delimited event framing and is intended only for legacy
clients.

## Check TCP connectivity

```sh
docker compose exec mochad-mqtt-bridge python /app/tools/check_mochad_tcp.py --host mochad --port 1099
```

## Request status

```sh
docker compose exec mochad-mqtt-bridge python /app/tools/mochad_status.py --host mochad --port 1099
```

## Watch live remote traffic

```sh
docker compose exec mochad-mqtt-bridge python /app/tools/watch_mochad.py --host mochad --port 1099
```

## Back up and validate bridge configuration

The offline backup tool includes only `bridge.json` and the optional
`discovery_registry.json`. Restore defaults to a non-writing dry run and must
target an isolated root:

```sh
python /app/tools/config_backup_restore.py backup \
  --config-root /config \
  --output /tmp/mochad-bridge.tar.gz \
  --installation-method docker

python /app/tools/config_backup_restore.py restore \
  /tmp/mochad-bridge.tar.gz \
  --target-root /tmp/mochad-bridge-restore
```

See [backup and restore](../docs/backup-and-restore.md) for the apply and
overwrite workflow. The archive is unsanitized and must be kept private.

## Clean Home Assistant MQTT discovery

Dry-run first:

```sh
docker compose exec mochad-mqtt-bridge python /app/tools/ha_mqtt_discovery_cleanup.py --host mosquitto --prefix homeassistant --dry-run
```

Apply cleanup:

```sh
docker compose exec mochad-mqtt-bridge python /app/tools/ha_mqtt_discovery_cleanup.py --host mosquitto --username '<username>' --password 'PASSWORD' --prefix homeassistant --apply
```

Optional aggressive mode:

```sh
docker compose exec mochad-mqtt-bridge python /app/tools/ha_mqtt_discovery_cleanup.py --host mosquitto --username '<username>' --password 'PASSWORD' --apply --match-topic 'homeassistant/+/x10_+/config'
```

The cleanup helper reads retained discovery configs from `homeassistant/#` and
clears only configs that look owned by this bridge. It does not call the Home
Assistant API. With `--match-topic`, it can also clear retained discovery
configs matching an explicit topic pattern.
