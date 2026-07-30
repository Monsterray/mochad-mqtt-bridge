# mochad-mqtt-bridge Agent Instructions

Workspace `AGENTS.md` defines safety, evidence, machine, and Git boundaries.
This file adds bridge-specific invariants.
In the shared workspace, conditional routing is under `../docs/agent/`.

## Invariants

- `state.py` is the state authority; the bridge executes typed actions.
- Protocol text handling stays in `protocol`; MQTT topic construction stays in
  `topics.py`; discovery payload construction stays in `discovery.py`.
- MQTT and mochad clients remain transport-focused.
- Device topics use immutable X10 addresses and the `command` suffix. Friendly
  names affect display names only.
- Home Assistant unique IDs remain stable and address-based.
- Generic capability profiles remain explicit user-declared behavior. Named
  profiles require lifecycle and evidence gating.
- Transport success never means physical activation. Preserve confidence,
  provenance, staleness, and physical confirmation as separate facts.
- Preserve existing generic switch, light, and action-only behavior unless the
  task explicitly changes that contract.

## Validation Entry Points

Use `.validation/capabilities.json` to select the profile. Start with ShellCheck,
`compileall`, and the smallest targeted unit test. Run the non-integration suite
before fake-mochad or Mosquitto integration.

Use the restricted Ubuntu virtual environment for exact-SHA source validation.
Run MQTT, lifecycle, container, and multiarchitecture checks only on the
isolated integration runner or GitHub Actions.

## Prohibited Actions

- Do not add USB access, controller lifecycle, or X10 wire encoding.
- Do not publish to production topics, use production credentials, or enable
  test discovery in production Home Assistant.
- Do not silently fall back from rejected named profiles to generic behavior.
- Do not change MQTT topics, retention, discovery entity type, deduplication,
  or optimistic state as incidental profile work.
- Do not promote research or experimental hardware without documented evidence
  and required physical validation.
