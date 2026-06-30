# Contributing

Thanks for helping improve MQTT Mochad Bridge.

## Development Rules

- Keep the bridge focused on connecting an external `mochad` TCP service to MQTT.
- Do not move protocol parsing into MQTT transport code.
- Do not move MQTT publishing or Home Assistant discovery into state management.
- Keep MQTT topics centralized in `topics.py`.
- Keep Home Assistant `unique_id` values based on immutable X10 addresses.
- Never commit credentials or local machine paths.

## Local Checks

Run:

```sh
python3 -m compileall -q .
```

If you are working from a checkout that includes tests, run that checkout's
unit test command before opening a pull request.

## Pull Requests

- Keep changes focused.
- Update README, CHANGELOG, and tests when behavior changes.
- For Docker changes, verify `docker compose config` and a local image build
  when Docker is available.
