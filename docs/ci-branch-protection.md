# CI And Branch Protection

GitHub branch protection is repository administration, not a setting that can
be enforced from this source checkout. After these workflows have completed at
least once, protect `master` and `develop` in the GitHub repository settings.

Require these checks before merging:

- `Bridge Python CI / Python 3.11`
- `Bridge Python CI / Python 3.12`
- `Bridge Python CI / Python 3.13`
- `Bridge MQTT Integration / integration`
- `Bridge Lifecycle CI / lifecycle`
- `Bridge Container CI / container`

`Bridge Multiarch CI / build` is build-only validation. Require it before
release tagging, or on release branches, rather than blocking every small fix.

All bridge validation workflows use `contents: read` permissions and do not
publish images, packages, tags, releases, or attestations.
