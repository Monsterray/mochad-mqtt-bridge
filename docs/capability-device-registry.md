# Capability-Driven X10 Device Registry

Status: generic capabilities are supported; named hardware profiles are
evidence-gated.

The bridge owns user-facing X10 device behavior. mochad-redux remains
protocol-oriented and does not learn product-model or Home Assistant semantics.

## Generic Capabilities

`switch`, `light`, and `chime` are explicit user declarations. They preserve
the existing stateful switch, dimmable light, and action-only button behavior
without making claims about a hardware model. Generic behavior needs no profile
lifecycle or evidence record.

## Named Profile Lifecycle

Named hardware profiles require structured evidence and exactly one lifecycle:

- `research`: recorded outside production registration and never selectable;
- `experimental`: selectable only with explicit configuration opt-in;
- `verified`: normally selectable;
- `deprecated`: loaded from existing configurations with a warning but omitted
  from supported-profile listings.

Evidence records contain confidence, source references, fixture-verification
state, hardware-verification state, last review information, and notes. The
confidence vocabulary is `confirmed`, `well_supported`,
`community_reported`, `inferred`, and `unverified`.

Named registration fails when lifecycle or required evidence metadata is
missing. Rejected profiles are never replaced silently with generic profiles.

## Experimental Opt-In

Experimental profiles are disabled by default:

```json
{
  "profiles": {
    "allow_experimental": false
  }
}
```

The environment equivalent is:

```text
ALLOW_EXPERIMENTAL_PROFILES=false
```

Selecting an experimental profile without opt-in fails startup with an
actionable configuration error. With opt-in, startup logs a warning and the
retained bridge status reports lifecycle, confidence, fixture verification,
and hardware verification.

## SC546A

`sc546a_chime` remains experimental. It preserves the existing limited bridge
behavior:

- Home Assistant MQTT button discovery;
- every explicit ON is sent;
- no retained state is created;
- transmission remains unconfirmed.

The profile is not verified hardware support. Its evidence record identifies
the reviewed manual and states that physical hardware confirmation is still
required.

## Research Records

Earlier LM15A, UM506, motion-sensor, PR511, PowerFlash, PowerHorn, RR501, and
grouped-command candidates are research-only. Their identifiers and candidate
questions are preserved in `research/device-profile-records.md`; no executable
capabilities are registered for them.

## Stable Integration Behavior

Profile evidence never changes MQTT identity. Unique IDs and topics remain
based on immutable X10 addresses. Friendly names remain display metadata only.
The lifecycle gate does not alter generic discovery, state, retention,
deduplication, or command behavior.

See [device profile migration](device-profile-migration.md) for existing
configuration guidance.
