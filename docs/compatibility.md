# Compatibility

`mqtt-mochad-bridge` uses the root `VERSION` file as its project and image
version. The current bridge release is `0.4.0` and is tested with the
`mochad-redux`/`mochad-docker` 0.4.0 release line, whose upstream base is
`mochad 0.1.18`.

The bridge reports its version in retained `x10/bridge/status`, the startup
log, `python mqtt_mochad_bridge.py --version`, Home Assistant discovery
`sw_version`, and OCI image labels.

Use plain semantic versions in files (`0.5.0`, `0.5.0-dev`, `0.5.0-rc1`) and
Git tags with a leading `v`. The release preparation scripts only make local,
reviewable edits; they never commit, tag, push, publish, or create a release.
