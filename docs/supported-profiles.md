# Supported Device Profiles

Generated from the validated profile schema. Do not edit by hand.

## Generic Capability Profiles

| Profile | Category | Entity | Commands | State policy |
|---|---|---|---|---|
| `generic_light` | light | light | BRIGHT, DIM, OFF, ON | stateful |
| `generic_switch` | switch | switch | OFF, ON | stateful |

## Named Hardware Profiles

Experimental and candidate profiles require explicit opt-in.

| Profile | Lifecycle | Model | Entity | Evidence |
|---|---|---|---|---|
| `sc546a_chime` | experimental | SC546A Remote Chime | chime | fixture=true, hardware=false |
