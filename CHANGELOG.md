# Changelog

All notable changes to this project will be documented in this file.

This project follows semantic versioning once releases begin.

## [Unreleased]

## [0.4.0] - Unreleased

### Fixed

- Docker builds now collect installed Alpine package evidence without attempting
  to read removed APK repository cache indexes.

### Added

- Initial MQTT bridge implementation for a running `mochad` TCP service.
- Home Assistant MQTT Discovery payload generation for light and switch entities.
- Address-based MQTT topics and stable Home Assistant `unique_id` values.
- Docker runtime, health check, and standalone compose file.
- Smoke-test helpers for checking mochad TCP connectivity.
- Basic GitHub Actions CI for Python 3.11-3.13, Compose validation, and Docker
  image builds.
- Docker image publishing readiness metadata, documentation, and non-root
  container runtime user.
- mochad-redux TCP diagnostics integration for retained bridge status and
  focused Home Assistant diagnostic entities.
- Home Assistant discovery metadata tuned for bridge device pages, including
  stable `default_entity_id` hints.
- Verified MQTT TLS support with system trust, custom CA files, optional mutual
  TLS, Docker-secret-compatible password files, and Mosquitto integration tests.
- Optional JSON bridge config file with reloadable device display names and
  `use_friendly_names` support.

### Known Gaps

- Discovery cleanup for removed configured devices is planned future work.
