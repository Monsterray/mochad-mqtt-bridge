# CI And Branch Protection

GitHub branch protection is repository administration. Do not merge the
test-suite simplification branch or remove an old required check until each
replacement check below has passed at least once on the target branch.

## Required Pull-Request Checks

Protect `master` and `develop` with these exact current check names:

- `CI Fast / Python 3.10`
- `CI Fast / Python 3.11`
- `CI Fast / Python 3.12`
- `CI Fast / Python 3.13`
- `CI Fast / Python 3.14`
- `CI Integration / integration`
- `CI Container / container`

During the migration, retain the old required checks as well. After the new
checks are green on the target branch, update branch protection in GitHub
settings, then remove only the superseded requirements. The workflow files
cannot change branch protection by themselves.

## Release-Oriented Checks

`CI Multiarch / build` is manually dispatched build validation for
`linux/amd64` and `linux/arm64`; it is required before a release candidate or
tag, not every pull request. `CI Release` is tag/manual release validation and
must not be a normal pull-request requirement.

All bridge validation workflows use `contents: read` permissions and do not
publish images, packages, tags, releases, or attestations.
