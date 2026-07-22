# Static Analysis Audit

The bridge owns a small set of release, container, and entrypoint shell
scripts. The initial review found no warning-level ShellCheck findings in those
maintained files.

ShellCheck remains a required CI gate because new entrypoint or release-script
defects could affect credentials, paths, or image provenance.

## Local Check

```sh
scripts/validate/shellcheck.sh
```

The gate checks tracked shell sources only. Python formatting and type-policy
changes are deliberately out of scope for this cross-repository cleanup.
