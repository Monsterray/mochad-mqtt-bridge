# Test Strategy

## Ownership

`mochad-mqtt-bridge` tests MQTT transport, mochad text classification, state
transitions, device capabilities, Home Assistant discovery, persistence,
recovery, TLS, and bridge container behavior. USB access and X10 wire encoding
belong to `mochad-redux`; daemon image packaging belongs to `mochad-docker`.

## Test Levels

- Unit and component tests cover configuration, topics, protocol parsing,
  state, discovery, registries, profile evidence, backup, and support bundles.
- MQTT integration uses a test-controlled Mosquitto broker and fake mochad TCP
  server. It covers event translation, command delivery, reconnect behavior,
  interrupted status parsing, TLS, and repeated action-only commands.
- Lifecycle tests cover degraded startup, later recovery, bounded queues, and
  shutdown while connections are pending.
- Container tests cover image construction, labels, entrypoint behavior,
  runtime identity, writable paths, secrets, and prohibited tools.
- Multiarchitecture CI proves `linux/amd64` and `linux/arm64` builds. It is not
  hardware evidence.
- Physical CM19A and module behavior use the shared workspace hardware process,
  lock, house code `D`, explicit approval, and human observation rules.

## Pull Request Gates

The normal workflows are:

- `Bridge Python CI`
- `Bridge Python Compatibility`
- `Bridge MQTT Integration`
- `Bridge Lifecycle CI`
- `Bridge Container CI`
- `Bridge Multiarch CI`

Python source coverage runs across every supported interpreter. Broker,
lifecycle, and container behavior run in canonical Linux environments. Release
publication remains isolated in `release-image.yml`.

## Develop Maintenance Record: 2026-08-22

Baseline `28cea8fffcf2d449923aebdf315dc965069f375d` includes PRs #12 through
#15. The important fixes and decisions are:

- Support-bundle redaction handles quoted JSON-style credential values without
  matching its own replacement output.
- `MQTT_DISCOVERY_ENABLED` previously existed in the model and documentation
  but was not parsed by `load_config()`, passed through development Compose, or
  enforced by every discovery path. It now defaults to `true`, accepts the
  normal strict boolean parser, and blocks entity, diagnostic, state-requested,
  cleanup, reset, and rediscovery publication when false.
- Disabling discovery pauses registry writes instead of clearing the retained
  topic inventory. This preserves the data needed to prune stale entities after
  discovery is enabled again.
- The Heyu archaeology record is pinned research, not copied source or a device
  support claim. Its current-disposition section separates implemented profile,
  confidence, provenance, and reconciliation work from deferred RF research.

The old `test-simplification/mochad-mqtt-bridge` branch was retired. Its test
ownership inventory became this document; its workflow rename was not adopted.
Its hardware script was also rejected because it duplicated the shared lab
safety authority and transmitted on house code `A`. Hardware work must use the
current lock and approval process and development house code `D` only.

For the discovery fix, targeted local tests passed, exact-SHA restricted Ubuntu
validation reported six `PASS`, two `NOT RUN`, and one `NOT APPLICABLE`, and
the final `develop` Python, MQTT, lifecycle, container, and multiarchitecture
workflows all passed.

## Regression Boundaries

Keep deterministic coverage for status-parser isolation, validation before
state mutation, broker and mochad outage recovery, discovery-registry
quarantine, TLS verification, action-only repeated commands, and discovery
disable behavior. These checks protect previously identified release findings
and must not be removed without equivalent or stronger replacement coverage.

Do not add tests for the unimplemented JSON port, an official Home Assistant
integration, USB behavior, or physical module activation. Record unavailable
broker or container checks as `NOT RUN` and unobserved physical outcomes as
`HARDWARE REQUIRED`.
