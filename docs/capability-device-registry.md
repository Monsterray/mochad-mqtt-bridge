# Capability-Driven X10 Device Registry

Status: initial design and bridge-side implementation.

The bridge should model user-facing X10 device behavior through explicit
capabilities instead of broad `light` and `switch` assumptions. mochad-redux
must remain protocol-oriented: it reports X10 activity and accepts X10
commands, but it should not learn product-model semantics such as SC546A,
LM15A, RR501, or PowerHorn behavior.

## Design Goals

- Keep immutable MQTT identity based on X10 address, such as `x10_A1`.
- Let friendly names affect display names only.
- Describe stateful devices, action-only devices, sensors, relays, alarms, and
  grouped X10 command behavior with profile data.
- Make deduplication state-aware so repeated intentional actions are not
  suppressed.
- Keep Home Assistant discovery derived from capabilities instead of hardcoded
  product names.
- Leave mochad-redux focused on standard X10, RF security, transport, and
  diagnostic events.

## Registry Fields

Each profile describes:

- `stateful`: whether the bridge may retain authoritative state.
- `supported_commands`: accepted commands for this device behavior.
- `repeatable_actions`: commands that may intentionally repeat without state
  changes.
- `all_lights_on_response`: whether `All Lights On` affects the device.
- `all_lights_off_response`: whether `All Lights Off` affects the device.
- `all_units_off_response`: whether `All Units Off` affects the device.
- `learned_addressing`: whether address identity is learned by command
  sequence instead of set by dials.
- `secondary_channels`: related address offsets such as dusk/dawn, sensor, or
  internal outlet channels.
- `exclusive_groups`: mutually exclusive hardware options, such as RR501 Unit
  1 versus Unit 9.
- `operation_mode`: continuous, momentary, action, sensor, or alarm sequence.
- `command_sequences`: intentional repeated or compound X10 patterns.
- `rf_identity`: standard RF identity versus security RF identity.

## Initial Profiles

| Profile | Key behavior |
| --- | --- |
| `generic_switch` | Stateful ON/OFF device. |
| `generic_light` | Stateful dimmable light responding to All Lights commands. |
| `lm15a_socket_rocket` | Learned-address ON/OFF lamp socket, no dim/bright, responds to All Lights On and All Units Off. |
| `um506_momentary` | Momentary contact closure; ON is action-only. |
| `um506_continuous` | Continuous contact closure; ON/OFF stateful, All Units Off aware. |
| `sc546a_chime` | Action-only chime; ON triggers sound, no retained state. |
| `ms13a_motion` | Standard RF motion channel plus base+1 dusk/dawn channel. |
| `ms14a_motion` | Standard RF motion channel plus base+1 dusk/dawn channel. |
| `ms16a_activeeye` | Standard RF motion channel plus optional base+1 dusk/dawn channel. |
| `pr511_motion_monitor` | Floodlight base address, sensor offsets +1..+4, dusk offsets +5..+8. |
| `powerflash_mode_1` | Compound alarm behavior using same-house lights and same-address reset. |
| `powerflash_mode_2` | Flashing alarm behavior where reset leaves lights on. |
| `powerflash_mode_3` | Same-address ON/OFF behavior. |
| `powerhorn` | Alarm sequence behavior triggered by repeated ON/OFF or All Lights/All Units patterns. |
| `rr501_unit_1` | RR501 internal outlet selected for Unit 1. |
| `rr501_unit_9` | RR501 internal outlet selected for Unit 9. |
| `grouped_address_function` | Protocol behavior where multiple addresses accumulate before one function. |

## Configuration

Profiles can be selected in compact `X10_DEVICES` configuration by using the
profile identifier where a device type normally appears:

```text
X10_DEVICES=A1:Porch Socket:lm15a_socket_rocket,A2:Door Chime:sc546a_chime
```

JSON configuration may use an explicit `profile` field:

```json
{
  "devices": [
    {
      "address": "A1",
      "name": "Porch Socket",
      "type": "light",
      "profile": "lm15a_socket_rocket"
    }
  ]
}
```

When the bridge creates `/config/bridge.json` from environment variables, it
preserves the selected profile so runtime config reloads keep the same device
behavior.

## Deduplication Rules

Stateful devices may suppress duplicate retained state transitions because the
state did not change. Action-only devices and alarm-sequence devices must not
use retained state as a deduplication key. Consecutive `ON` commands to an
SC546A chime, consecutive PowerHorn alarm steps, and repeated intentional
PowerFlash actions are valid user requests even when the command text repeats.

## Home Assistant Discovery

Discovery should be capability-driven:

- Stateful lights and switches publish stateful MQTT entities.
- Action-only devices publish MQTT buttons.
- `unique_id` remains address-based, such as `x10_A1`.
- Friendly names populate Home Assistant names only.
- Product profile metadata should not change MQTT topic identity.

## mochad-redux Boundary

mochad-redux should not contain this registry. Its future normalized event model
should instead preserve protocol facts accurately enough for clients to decide
what they mean:

- Multiple accumulated standard X10 addresses before one function.
- House/function events such as All Lights On and All Units Off.
- Standard RF identities kept separate from security RF identities.
- Direction, transport, raw text, and normalized command/function fields.

The bridge can then map those generic protocol events onto configured product
profiles without making the daemon Home Assistant-aware or product-specific.

## Manual Review Sources

Initial profiles were derived from the X10 instruction manual index and linked
manuals at TheX10Shop:

- https://thex10shop.com/pages/x10-instruction-manuals
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/lm15a-is.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/um506-is.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/sc546a-is.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/ms13a-is.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/ms14a-is.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/ms16a-is.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/pr511-om.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/pf284-is.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/sh10a-is.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/ph508-is.pdf
- https://cdn.shopify.com/s/files/1/0266/5772/8636/files/rr501-is.pdf
