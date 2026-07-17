# Hardware Lab Policy

Hardware validation is a manual, approval-gated activity. The bridge lab must
not touch production MQTT data or Home Assistant discovery.

- Use only the `codex-x10` SSH account. It owns `/srv/x10-dev`, belongs to
  `x10dev` and `x10`, and must not have `sudo` or `docker` membership.
- Begin from a clean, reviewed checkout and record its Git SHA.
- Use the reserved lab ports `19099` for mochad and `11883` for the isolated
  MQTT broker. Do not use production listeners.
- Set `MQTT_BASE_TOPIC=x10-test/<run-id>` and
  `MQTT_DISCOVERY_ENABLED=false`. The scripts reject `x10` as a base topic.
- Claim `/run/lock/x10-hardware.lock` with `flock`. The administrator creates
  it as `root:x10dev`, mode `0660`; scripts never elevate privileges.
- Use only `PASS`, `FAIL`, `NOT RUN`, `NOT APPLICABLE`, and
  `HARDWARE REQUIRED` in evidence. Audible or physical outcomes require human
  confirmation.
- Obtain project-lead approval before RF transmission, equipment changes, or
  any use outside the isolated lab.

A future runner with labels `x10-hardware`, `cm19a`, and `sc546a` must be
manual-dispatch-only and limited to trusted release commits. It is not enabled
for pull requests or forks.
