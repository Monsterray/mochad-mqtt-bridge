# Changelog

All notable changes to this project will be documented in this file.

This project follows semantic versioning once releases begin.

## [Unreleased]

### Added

- Initial MQTT bridge implementation for a running `mochad` TCP service.
- Home Assistant MQTT Discovery payload generation for light and switch entities.
- Address-based MQTT topics and stable Home Assistant `unique_id` values.
- Docker runtime, health check, and standalone compose file.
- Smoke-test helpers for checking mochad TCP connectivity.
- Basic GitHub Actions CI for Python 3.11-3.13, Compose validation, and Docker
  image builds.

### Known Gaps

- Discovery cleanup for removed configured devices is planned future work.

## [0.1.0] - Unreleased

- First release candidate baseline.
