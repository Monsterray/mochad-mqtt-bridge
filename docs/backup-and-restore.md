# Bridge Configuration Backup and Isolated Restore

The bridge backup tool preserves only bridge-owned operational configuration:

- `/config/bridge.json` is required.
- `/config/discovery_registry.json` is optional and rebuildable.

The archive is explicitly **unsanitized**. It excludes secret files, temporary
files, invalid-file quarantine copies, health files, and logs. Configuration
containing password, token, credential, private-key, or secret fields is
rejected. MQTT and TLS secrets must be backed up separately with an encrypted
system.

## Create a Backup

From a source checkout or the bridge container:

```sh
python tools/config_backup_restore.py backup \
  --config-root /config \
  --output /config-backups/mochad-bridge.tar.gz \
  --installation-method docker
```

The manifest records the exact bridge Git SHA and version, file hashes and
modes, original and archive paths, required state, restore order,
compatibility contracts, external-secret placeholders, prerequisites, and
rollback instructions.

The output path must not already exist. Keep the archive private.

## Inspect and Plan

Restore always targets an isolated root. The default is a dry run and writes
nothing:

```sh
python tools/config_backup_restore.py restore \
  /config-backups/mochad-bridge.tar.gz \
  --target-root /tmp/mochad-bridge-restore
```

Dry run performs `inspect -> validate -> plan`. It validates the manifest,
archive members, checksums, bridge configuration, discovery-registry schema,
paths, compatibility metadata, and overwrite requirements.

## Apply to an Isolated Root

After reviewing the plan:

```sh
python tools/config_backup_restore.py restore \
  /config-backups/mochad-bridge.tar.gz \
  --target-root /tmp/mochad-bridge-restore \
  --apply
```

Applying performs `inspect -> validate -> plan -> stage -> verify -> activate`.
Files are staged and verified before atomic replacement with `os.replace()`.
If activation fails, every file already replaced is rolled back.

A different existing file is never replaced without explicit approval:

```sh
python tools/config_backup_restore.py restore \
  /config-backups/mochad-bridge.tar.gz \
  --target-root /tmp/mochad-bridge-restore \
  --apply \
  --overwrite
```

An identical repeated restore is a no-op and does not require `--overwrite`.

The tool never starts the bridge and never contacts MQTT, Home Assistant, or
mochad. Validate the isolated restored configuration before copying it into a
production `/config` volume.
