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
