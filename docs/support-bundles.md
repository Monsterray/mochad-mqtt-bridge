# Sanitized Support Bundles

The support-bundle tool creates a local diagnostic archive. It does not connect
to MQTT, Home Assistant, Mochad, Docker, or USB, and it never uploads the
result.

```sh
python tools/support_bundle.py \
  --output bridge-support.tar.gz \
  --config /config/bridge.json \
  --status /tmp/bridge-status.json \
  --log /tmp/bridge.log \
  --max-log-lines 200
```

Use `--dry-run` to display the collection categories without reading files.
When the checkout does not contain Git metadata, pass the exact 40-character
bridge SHA with `--repository-sha`.

The collector includes only bridge identity, an allowlisted configuration
summary, an explicitly supplied status document, and the tail of one explicitly
supplied log. Device addresses, IP addresses, and home-directory paths are
pseudonymized. Passwords, tokens, URL credentials, and private keys are
redacted.

Staged filenames and contents are scanned before packaging. The completed
archive is opened and scanned again. A failed scan deletes the distributable
archive. The output remains local with mode `0600`; review it before sharing.

Support bundles are not backups and cannot be restored. They exclude complete
configuration, discovery state, secret files, credentials, unrestricted logs,
broker ACLs, Home Assistant configuration, and raw security RF identities.
