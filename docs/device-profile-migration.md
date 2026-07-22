# Device Profile Evidence and Migration

Generic capability profiles and named hardware profiles make different kinds
of promises.

Generic `switch`, `light`, and `chime` types mean that the user explicitly
declares the behavior needed by the bridge. They remain available without
evidence metadata and do not claim that a particular product model was tested.

Named profiles mean that the project describes a hardware model. Every named
profile therefore has a lifecycle and structured evidence record:

- `research`: documented for future review and never selectable;
- `experimental`: selectable only with explicit opt-in;
- `verified`: normally selectable after evidence review;
- `deprecated`: accepted from existing configuration with a warning but not
  shown as a supported choice for new configuration.

The default is:

```json
{
  "profiles": {
    "allow_experimental": false
  }
}
```

The equivalent environment setting is:

```text
ALLOW_EXPERIMENTAL_PROFILES=false
```

The SC546A profile remains experimental. Existing users who intentionally want
that named profile must set the opt-in to true. Its bridge behavior remains a
Home Assistant button, forwards every explicit ON, publishes no retained state,
and reports transmission as unconfirmed. This does not claim that the physical
chime acted.

All other prior named profiles are research-only. Replace a rejected profile
with a generic type only after reviewing whether that generic behavior is
correct for your configuration; the bridge will never make that replacement
automatically.

Configured named-profile lifecycle, confidence, fixture verification, and
hardware verification appear in the retained bridge status document. Evidence
metadata does not change MQTT topics, unique IDs, discovery entity behavior, or
state policy.
