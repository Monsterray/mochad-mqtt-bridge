# Heyu Archaeology Review

## Scope And Pin

This is a behavior and test-design review of the public
[`HeyuX10Automation/heyu`](https://github.com/HeyuX10Automation/heyu)
repository. No Heyu source was copied, translated, linked, or executed by this
project.

| Item | Value |
| --- | --- |
| Examined repository | `HeyuX10Automation/heyu` |
| Exact commit | `902a4ef46d857de7e7fc157ea7c3f2562f4f1624` |
| Commit date | 2021-03-24 |
| Commit subject | `Fix gcc 10+ build errors` |
| License observed | GPL-3.0-or-later: `COPYING` is GPLv3 and reviewed source headers state GPLv3-or-later. |
| Review branch | `research/heyu-archaeology` |

All rows below refer to that exact commit. `GPL-3.0-or-later header` means the
reviewed source file carries the GPLv3-or-later notice; historical copyright
notices remain relevant to any direct reuse. Direct reuse is prohibited by
this review's scope even where licenses might otherwise be compatible.

## Architecture Findings

Heyu is a CM11A-focused, multi-process system. `relay.c` owns the serial
reader and spool file; `poll.c` consumes serialized input; `x10state.c` is a
state engine with a persisted state table and script launcher; `x10aux.c`
decodes optional RF receiver input; `process.c` compiles timers/macros for the
CM11A EEPROM. Instance suffixes isolate files and locks for multiple CM11A
installations.

That split is a historical fit for a serial CM11A and shell-script integration,
not a design to import. `mochad-redux` remains the protocol/controller daemon;
`mochad-mqtt-bridge` owns device behavior, confidence, discovery mapping, and
Home Assistant-facing diagnostics.

## Candidate Record

| Candidate | Classification | Heyu source and behavior | License/header | Destination | Required independent rewrite | Tests and hardware |
| --- | --- | --- | --- | --- | --- | --- |
| Capability catalog | DATA | `modules.c`: `modules[]`, `module_attributes()`, `set_module_masks()` records command support, state response, dim range, group and exclusive behavior separately from model labels. | GPL-3.0-or-later header; Charles W. Sullivan, 2004-2008. | `mochad-mqtt-bridge` | Create a small declarative profile schema; retain only verified X10 behavior and cite manuals/observations, not Heyu entries. | Parameterized profile tests; CM19A plus representative modules. |
| Standard command matrix | TEST VECTOR | `modules.c` cflags distinguish All Units Off, All Lights On/Off, On/Off, Dim/Bright, preset, status request/ack, and address side effects. | GPL-3.0-or-later header. | Bridge tests/catalog | Encode expected capability acceptance and state effects as original fixtures. | Unit matrix for each command/profile; physical module confirmation. |
| Extended command matrix | TEST VECTOR | `cmd.c` command table and `x10state.c` extended update functions distinguish Type 0 shutters, Type 3 dimmers/switches, status, group execution, group removal, and group dim/bright. | GPL-3.0-or-later header. | `mochad-redux` protocol fixtures; bridge catalog | Define protocol-neutral extended event/command fixtures first; add encoder behavior only after hardware evidence. | Parser/encoder fixtures; LM14A/AM14A/SW10 hardware required. |
| Per-device state confidence | IDEA | `x10state.h` stores last command, addresses, state bitmaps, level, identifiers, flags, and per-unit timestamps. It does not expose an explicit confidence model. | GPL-3.0-or-later header; Charles W. Sullivan, 2004-2010. | Bridge `state.py`/models | Add explicit `observed`, `optimistic`, `transmitted_unconfirmed`, and `unknown` confidence rather than copying bitmaps. | State-transition tests for MQTT command, TX echo, RX event, timeout, reconnect. |
| Event provenance | DATA | `poll.c` uses source classes such as command-line, scheduled, power-line receive, RF auxiliary receive, timer, and trigger execution; launcher filtering uses the source. | GPL-3.0-or-later header; historical CM11A notices. | Bridge models/protocol events | Define a typed provenance enum independent of Heyu names: MQTT command, mochad TX report, PLC RX, RF RX, status reconciliation, synthetic. | One test per source and filtering/attributes tests; CM19A for TX semantics. |
| Capability-aware all-address reconciliation | ALGORITHM | `x10state_update_func()` and `modules.c` apply All Lights/All Units effects only to profile masks; flags cover modules that unaddress after global commands. | GPL-3.0-or-later headers. | Bridge state/catalog | Independently implement a pure profile-driven reducer; do not use Heyu masks or module table. | Table-driven All Lights On/Off and All Units Off tests; mixed lamp/appliance/exclusive profiles. |
| Exclusive groups and secondary channels | DATA | `modules.c` models exclusive groups of 4/8/16, group memberships, and model-specific command effects. `x10state.c` tracks group data. | GPL-3.0-or-later headers. | Bridge catalog | Model explicit `exclusive_group` and secondary-channel relationships only where documented. | Profile fixtures for RR501, PowerFlash, PR511/MSxx-style offsets; hardware required. |
| Heartbeat and inactivity | ALGORITHM | `x10state.c`: `update_activity_timeout()`, `sensor_elapsed_func()`, and timeout initialization use last-seen timestamps plus global/per-alias inactivity intervals. | GPL-3.0-or-later header. | Bridge state/models | Use monotonic/timestamped last-seen records and bounded scheduler checks; do not add a daemon or scripts. | Deterministic fake-clock tests for heartbeat, timeout, recovery, disabled monitoring. |
| Low battery | DATA | `x10state.h` has low-battery state; sensor decoders update it. `x10config.5` distinguishes binary indicators from percentage thresholds. | GPL-3.0-or-later headers/docs. | Bridge models/catalog | Represent `low_battery: bool | None` and source data separately; never infer a percentage from a binary flag. | Decoder fixtures and availability/attribute tests; relevant RF hardware. |
| Tamper and security mode | IDEA | `x10state.c`: `set_tamper_flag()`, `clear_tamper_flags()`; `x10config.5` documents strict/loose arm logic. | GPL-3.0-or-later header/docs. | Bridge security extension, later | Keep sensor tamper as event/attribute first. Do not adopt alarm arming policy or automation. | Security event fixtures; hardware-required for actual sensors. |
| Security RF identifiers | DATA | `x10aux.c`: `security_checksum()`; `x10config.5` documents 8/16-bit IDs, upper-byte parity, and DS90 alternating-parity quirk. | GPL-3.0-or-later header/docs. | `mochad-redux` decoder design; bridge mapping | Preserve raw identifier bytes and validation outcome; make compatibility exceptions opt-in and observable. | Valid, invalid, 8-bit, 16-bit, and alternating-parity fixture corpus; RFXCOM hardware required. |
| Security model quirks | TEST VECTOR | `x10config.5` documents DS90 auxiliary parity failure; KR10A/KR18/KR21 flag interpretation and dummy use; `SEC_IGNORE` behavior. | Documentation under repository GPL context. | Bridge catalog/mapping | Represent quirks as per-profile decoding/mapping configuration, never daemon-wide model semantics. | Fixture tests per quirk; security transmitter hardware required. |
| W800RF32A decoder boundary | ALGORITHM | `x10aux.c`: `aux_w800()` validates complement-style W800 words, classifies noise, and emits normal/raw virtual events. | GPL-3.0-or-later header. | Future standalone decoder library or `mochad-redux` optional input adapter | Write a bounded streaming decoder with explicit framing, validation result, and raw event output. | Byte-stream split/merge, valid frame, invalid complement, replay/noise tests; W800 hardware required. |
| MR26A decoder boundary | ALGORITHM | `x10aux.c`: `aux_mr26a()` performs receiver-specific framing and noise handling. | GPL-3.0-or-later header. | Future standalone decoder library | Independently specify framing and recovery; do not add it to core daemon without a maintained input interface. | Fragmentation/noise fixtures; MR26A hardware required. |
| RFXCOM decoder boundary | ALGORITHM | `x10aux.c`: `aux_rfxcomvl()`, receiver configuration, checksums, variable-length dispatch, and sensor serial follow-up. | GPL-3.0-or-later header. | Future standalone decoder library | Create a separately tested protocol adapter; keep X10 event normalization independent from receiver transport. | Version/config/packet fixtures; RFXCOM hardware required. |
| Raw RF and noise diagnostics | IDEA | `x10aux.c` distinguishes normal raw frames and judged noise; `x10config.5` exposes NONE/NOISE/ALL diagnostic modes. | GPL-3.0-or-later header/docs. | `mochad-redux` diagnostics, later | Add bounded, opt-in raw diagnostics with bytes, decoder, reason, and rate limiting. No normal MQTT topic flood. | Rate-limit and classification tests; receiver hardware required. |
| RF flood/jamming handling | DATA | `x10aux.c` has jamming/noise paths; `poll.c` includes RF-flood notifications. Older RFXCOM jamming signals are documented as noisy. | GPL-3.0-or-later headers/docs. | Future diagnostics policy | Surface a bounded health counter/event; do not treat it as an intrusion alarm by default. | Repeated-noise fixture; RFXCOM hardware required. |
| Structured command sequences | IDEA | `cmd.c`: `verify_scene()` and scene expansion accept semicolon-delimited, parameterized command groups with command-specific validation. | GPL-3.0-or-later header. | Bridge, future control feature | Define a closed typed sequence schema with maximum steps, delay bounds, allowed commands, and no shell execution. | Validation, cancellation, repeat/alarm sequence, and no-arbitrary-execution tests. |
| User synonyms | DO NOT ADOPT | `cmd.c` aliases user command labels and parses command-line scenes/usersyns. | GPL-3.0-or-later header. | None | Do not expose arbitrary text aliases or a command language through MQTT. | None. |
| Script launchers | DO NOT ADOPT | `x10state.c` launcher matching and `x10config.5` SCRIPT directives can execute arbitrary command lines. | GPL-3.0-or-later header/docs. | None | Explicitly out of scope for bridge and daemon. | Security regression: no configuration path executes a shell command. |
| Spool-file relay/state daemons | DO NOT ADOPT | `relay.c`/`poll.c` use TTY locks, spool files, and multiple cooperating processes. | GPL-3.0-or-later headers. | None | Existing mochad client/bridge transport model remains. | Architecture test: no spool-file IPC introduced. |
| CM11A collision avoidance | IDEA | `x10config.5` CHECK_RI_LINE and SEND_RETRIES; `relay.c`/`poll.c` handle polling, RI, and CM11A quirks. | GPL-3.0-or-later headers/docs. | `mochad-redux`, CM11A-only future | Retain as CM11A transport research only; no transplant to CM19A USB behavior. | CM11A serial hardware and collision test bench required. |
| CM11A EEPROM schedule/compiler | DO NOT ADOPT | `process.c`, `eeprom.c`, and schedule docs compile/upload 1024-byte timer/macro images. | GPL-3.0-or-later headers. | None | Explicitly excluded: no EEPROM scheduling in mochad-redux. | None. |
| Multiple-instance isolation | IDEA | `relay.c` and `x10config.5` use suffixes for lock, spool, and state-file isolation. | GPL-3.0-or-later headers/docs. | Deployment docs, later | Prefer unique container names, config paths, client IDs, and MQTT base topics over global suffix files. | Two isolated bridge instances with no topic/config collision. |
| Direct Heyu source reuse | DO NOT ADOPT | All reviewed implementation files. | GPL-3.0-or-later plus file-specific historic copyright notices. | None | Independently reimplement documented behavior or use original fixtures only where legally and technically appropriate. | Provenance review before any import. |

## Prioritized Recommendations

1. **Bridge capability catalog:** evolve `docs/capability-device-registry.md`
   into a declarative profile schema. Start with command support, statefulness,
   all-address responses, repeatability, exclusive groups, and known secondary
   channels. Each entry requires a manual/source citation and tests.
2. **State confidence and provenance:** add typed event provenance and state
   confidence to bridge models before expanding entity behavior. Mochad TX must
   remain `transmitted_unconfirmed`, never physically confirmed.
3. **All-address reconciliation:** implement a pure, profile-driven reducer in
   the bridge. Unknown/unprofiled devices must not be changed by broad commands.
4. **Sensor liveness:** design optional heartbeat/inactivity/low-battery state
   as bridge attributes and diagnostics, not Home Assistant automation rules.
5. **Bounded sequences:** if needed later, add typed sequences only after the
   catalog and command validation pipeline are stable. No free-form shell,
   no arbitrary text parser, and no unbounded queues.
6. **Fixture corpus:** capture independently authored standard/extended command
   fixtures and security/RF examples. Protocol decoding belongs in
   `mochad-redux`; device meaning belongs in the bridge.
7. **Raw diagnostics:** retain raw bytes and a classified reason only behind an
   opt-in, rate-limited diagnostic path.
8. **Security RF:** defer full support until a receiver-specific input adapter
   and hardware corpus exist. Preserve identifier width and validation status.

## Explicit Non-Adoption Boundary

This review does **not** recommend arbitrary script execution, Heyu's
spool-file/process architecture, usersyn command language, or CM11A EEPROM
scheduling. It also does not recommend putting product-model semantics into
the mochad-redux core daemon. The daemon may eventually decode normalized
protocol events; the bridge owns device profiles and Home Assistant mapping.

## Follow-Up Evidence Needed

- X10 module manuals and measured CM19A/CM15A behavior for every bridge
  profile.
- Captured, consented RF byte streams for W800RF32A, MR26A, and RFXCOM.
- Security transmitter captures for 8/16-bit identifier and parity cases.
- Separate CM11A hardware evidence before any CM11A-only transport work.
