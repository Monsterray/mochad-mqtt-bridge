# Release Checklist

Use this checklist before publishing a GitHub release or Docker image.

## Version

- [ ] Update `version.py`.
- [ ] Update `release/versions.env` and the Docker `IMAGE_VERSION` default.
- [ ] Update README version badge.
- [ ] Replace the `CHANGELOG.md` version section's `Unreleased` marker with the
  actual release date in `YYYY-MM-DD` form.
- [ ] Tag the release with the same version.
- [ ] Create the tag from `master` after the `develop` release pull request is merged.

## Verification

- [ ] Run Python compile check.
- [ ] Run available unit tests.
- [ ] Run `docker compose config`.
- [ ] Run `docker compose -f docker-compose.yml -f docker-compose.secrets.yml config`.
- [ ] Build the Docker image.
- [ ] Validate release image labels with `scripts/validate/image_labels.py`.
- [ ] Confirm `release/versions.env` pins the expected digest-qualified base image.
- [ ] Archive runtime package evidence from `/usr/share/mochad-mqtt-bridge/apk-info.txt`.
- [ ] Confirm `/usr/share/licenses/mochad-mqtt-bridge/LICENSE.md` is present.
- [ ] Run `scripts/validate/container_permissions.sh` on a Docker host.
- [ ] Run README first-run smoke checks against a real MQTT broker and `mochad`.
- [ ] Confirm MQTT topics still use `/command`, not `/set`.
- [ ] Confirm Home Assistant discovery `unique_id` values remain address-based.

## Publishing

- [ ] Confirm Docker image labels are correct.
- [ ] Confirm no secrets or local paths are committed.
- [ ] Publish GitHub release notes from `CHANGELOG.md`.
- [ ] Publish Docker image with matching version tag.
- [ ] Confirm the tag workflow created the GitHub Release and published both
  `linux/amd64` and `linux/arm64` manifests to GHCR.
