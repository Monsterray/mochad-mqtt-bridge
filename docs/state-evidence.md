# State Confidence and Provenance

Bridge state and command transport are separate. A successful TCP write,
Mochad transmit echo, USB completion, or controller acknowledgement does not
prove that a physical X10 module changed.

State attributes use:

- `unknown`: no usable state evidence;
- `assumed`: optimistic state from a validated MQTT command;
- `inferred`: status or profile rules imply the state;
- `reported`: an addressed receive event reported the state;
- `observed`: an independently verified return path reported the state.

`provenance` records the source, while `updated_at`, `observed_at`,
`expires_at`, and `stale` preserve timing. Staleness does not erase historical
confidence or provenance.

`physical_confirmation` remains separate and defaults to `unknown`. Runtime
transport never sets it to `observed` or `contradicted`; those values require
approved human or sensor evidence.

Legacy state payloads remain `ON`, `OFF`, and level values on the existing
state topic. Evidence is published through the existing retained attributes
topic and summarized by count in `x10/bridge/status`. No correlation is
inferred between nearby bridge commands and legacy Mochad events.
