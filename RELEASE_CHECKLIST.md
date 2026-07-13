# Release Checklist

Use this checklist before publishing a GitHub release or Docker image.

## Version

- [ ] Update `version.py`.
- [ ] Update Docker `IMAGE_VERSION`.
- [ ] Update README version badge.
- [ ] Update `CHANGELOG.md`.
- [ ] Tag the release with the same version.

## Verification

- [ ] Run Python compile check.
- [ ] Run available unit tests.
- [ ] Run `docker compose config`.
- [ ] Build the Docker image.
- [ ] Run `scripts/validate/container_hardening.sh` on a Docker host.
- [ ] Run README first-run smoke checks against a real MQTT broker and `mochad`.
- [ ] Confirm MQTT topics still use `/command`, not `/set`.
- [ ] Confirm Home Assistant discovery `unique_id` values remain address-based.

## Publishing

- [ ] Confirm Docker image labels are correct.
- [ ] Confirm no secrets or local paths are committed.
- [ ] Publish GitHub release notes from `CHANGELOG.md`.
- [ ] Publish Docker image with matching version tag.
