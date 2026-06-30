# Bridge Image Test Tools

These tools are included inside the `mochad-mqtt-bridge` Docker image under
`/app/tools`. They are for manual network and mochad diagnostics only.

No MQTT usernames or passwords are stored in these files.

Device MQTT topics are always stable X10-address topics such as
`x10/A1/state`. Friendly names are display names only.

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
