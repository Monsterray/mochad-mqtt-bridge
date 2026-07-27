# Release Engineering

`VERSION` is the bridge project and image version source. Files use semantic
versions without a leading `v`; Git tags add it.

Prepare reviewable release changes with:

```sh
scripts/release/prepare-release.sh 0.5.0
scripts/release/prepare-next-dev.sh 0.6.0
```

These scripts require a clean tree and never commit, tag, push, publish, or
create a GitHub release.

## Release Image Inputs

Immutable base-image and package inputs are recorded in
`release/versions.env`. Release Docker builds use a digest-qualified Python
base and install hash-checked dependencies from `requirements.release.txt`.

OCI labels are populated from Git metadata so an image identifies its exact
source revision and commit timestamp.

## Publishing Contract

Matching version tags are configured to publish:

```text
ghcr.io/monsterray/mochad-mqtt-bridge
```

Release images target `linux/amd64` and `linux/arm64` and include BuildKit SBOM
and provenance attestations. Manual workflow runs and pull requests validate
without publishing.

Confirm a tag exists in GHCR before using it. A README image reference is not
publication evidence.

## Runtime Image

The container prepares `/config` as root, creates the configured runtime
identity, then permanently drops privileges. Application files remain
`root:root`; only `/config` is writable persistent state. The Python health
check avoids adding curl, wget, netcat, or build tools to the runtime image.

Workflow names and branch-protection requirements are documented in
[CI and branch protection](ci-branch-protection.md).
