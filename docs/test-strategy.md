# Test Strategy

This is the read-only inventory before test-suite simplification. Runtime values
are CI estimates. Regression history is `not recorded` unless a test protects
a named audit finding or an action-only device contract.

## Cross-Repository Ownership

The bridge owns Python state, MQTT command validation, protocol classification,
Home Assistant discovery, registry handling, TLS configuration, and bridge
container behavior. `mochad-redux` owns daemon protocol and USB safety;
`mochad-docker` owns daemon image packaging. No test targets the future JSON
port or an official Home Assistant integration.

## Test Files

| Test file | Behavior / level | Runtime / requirements | Overlap / history | Action / replacement / removal risk |
| --- | --- | --- | --- | --- |
| `test_bridge_commands.py` | command intake/actions/queue; unit | <1s | topic/config overlap; command-safety finding | Keep; parameterize invalid input cases. |
| `test_config.py` | env/config/TLS; unit | <1s/temp files | reload parsing | Keep; parameterize invalid values. |
| `test_config_reload.py` | reload/generated config; component | <1s/temp files | distinct file reload | Keep. |
| `test_container_permissions.py` | static container assertions; unit | <1s | runtime harness stronger | Demote static runtime assertions. |
| `test_device_registry.py` | capability/action profiles; unit | <1s | discovery consumes profiles | Keep. |
| `test_discovery_buttons.py` | buttons/diagnostics; unit | <1s | discovery snapshots | Keep focused metadata. |
| `test_discovery_registry.py` | schema/quarantine/save; component | <1s/temp files | known-input fixtures | Keep; parameterize malformed files. |
| `test_healthcheck.py` | health-file freshness; unit | <1s | none | Keep. |
| `test_image_labels.py` | OCI/version source rules; unit | <1s | image inspection | Keep source contract. |
| `test_known_inputs.py` | fixture lines/topics/registry; component | <1s | parser/status/commands | Keep table-driven regressions. |
| `test_lifecycle.py` | outages/shutdown; integration | 2-10s/controlled transports | timing variants overlap | Keep canonical recovery only. |
| `test_mochad_client.py` | TCP framing/reconnect; unit | <1s | lifecycle complements it | Keep. |
| `test_mochad_diagnostics.py` | diagnostics/status merge; unit | <1s | discovery metadata | Keep. |
| `test_mqtt_client.py` | callbacks/availability; unit | <1s | broker integration | Keep. |
| `test_mqtt_tls.py` | TLS config/context; unit | <1s/temp certs | TLS integration complementary | Keep. |
| `test_status_parser_isolation.py` | interleaved status/RF; component | <1s | HIGH parser-isolation finding | Keep exact regression cases. |
| `test_topics.py` | topic generation; unit | <1s | command intake | Combine parameterized validation. |
| `integration/test_bridge_mqtt_integration.py` | events/commands/discovery/chime; integration | 5-20s/Mosquitto/fake mochad | canonical broker proof | Keep focused scenarios. |
| `integration/test_mqtt_tls_mosquitto.py` | trust/hostname/mTLS; integration | 10-30s/Mosquitto/OpenSSL | TLS unit config complementary | Keep integration-only. |
| `support/fake_mochad_server.py` | deterministic TCP fixture | n/a | shared support | Keep. |

## Scripts and CI Jobs

| Item | Behavior / level | Runtime / requirements | Action |
| --- | --- | --- | --- |
| `container_permissions.sh` | identity, filesystem, secrets, tools; container | 1-3m/Docker | Keep one built-image parameterized harness. |
| `image_labels.py` | actual OCI labels; container/release | <1s/image | Keep after image build. |
| `version-consistency.sh` | version/status/discovery/label contract; unit | <1s | Keep fast. |
| `Bridge Python CI` | unit on 3.11-3.13 | 1-3m each | Merge with compatibility matrix. |
| `Bridge Python Compatibility` | same unit suite on 3.10-3.14 | 1-3m each | Replace both with one all-supported matrix. |
| `Bridge MQTT Integration` | broker and TLS integration | 3-8m | Combine with lifecycle. |
| `Bridge Lifecycle` | outage/recovery | 2-5m | Combine with integration. |
| `Bridge Container` | build/Compose/labels/permissions | 3-8m | Keep canonical container job. |
| `Bridge Multiarch` | OCI build | 5-15m | Keep separate release-oriented gate. |
| `Release image` | publishing/SBOM/provenance | 10-25m | Keep tag-only. |

## Simplification Contract

Fast CI runs all unit/component tests on every supported Python version.
Integration CI runs Mosquitto, fake mochad, lifecycle, basic translation,
interrupted status parsing, valid and invalid MQTT commands, reconnect
discovery, and repeated SC546A actions on Python 3.12 only. Container CI builds
one image and reuses it. Multiarchitecture and publication remain separate.
