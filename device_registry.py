"""
Capability-driven X10 device profile registry.

The bridge owns product-level behavior because it translates generic X10
events into user-facing MQTT/Home Assistant entities. mochad-redux should stay
protocol-oriented and should not learn product model semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from models import (
    ChannelKind,
    Command,
    CommandSequence,
    DeviceCapability,
    DeviceConfig,
    DeviceType,
    OperationMode,
    RfIdentity,
    SecondaryChannel,
)


@dataclass(slots=True, frozen=True)
class DeviceProfile:
    """Stable capability description for an X10 product or behavior class."""

    profile_id: str
    model: str
    description: str
    entity_type: DeviceType
    capabilities: frozenset[DeviceCapability]
    supported_commands: frozenset[Command]
    stateful: bool
    repeatable_actions: frozenset[Command] = frozenset()
    all_lights_on_response: bool = False
    all_lights_off_response: bool = False
    all_units_off_response: bool = True
    learned_addressing: bool = False
    secondary_channels: tuple[SecondaryChannel, ...] = ()
    exclusive_groups: frozenset[str] = frozenset()
    operation_mode: OperationMode = OperationMode.CONTINUOUS
    command_sequences: tuple[CommandSequence, ...] = ()
    rf_identity: RfIdentity = RfIdentity.STANDARD


ON_OFF = frozenset({Command.ON, Command.OFF})
ON_ONLY = frozenset({Command.ON})
LIGHT_COMMANDS = frozenset({Command.ON, Command.OFF, Command.DIM, Command.BRIGHT})


DEVICE_PROFILES: dict[str, DeviceProfile] = {
    "generic_switch": DeviceProfile(
        profile_id="generic_switch",
        model="Generic X10 switch or appliance module",
        description="Stateful ON/OFF device with no All Lights response.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
    ),
    "generic_light": DeviceProfile(
        profile_id="generic_light",
        model="Generic X10 light module",
        description="Stateful dimmable light responding to All Lights commands.",
        entity_type=DeviceType.LIGHT,
        capabilities=frozenset({DeviceCapability.ON_OFF, DeviceCapability.DIM}),
        supported_commands=LIGHT_COMMANDS,
        stateful=True,
        all_lights_on_response=True,
        all_lights_off_response=True,
    ),
    "lm15a_socket_rocket": DeviceProfile(
        profile_id="lm15a_socket_rocket",
        model="LM15A Socket Rocket",
        description="Learned-address lamp socket; ON/OFF only, no dimming.",
        entity_type=DeviceType.LIGHT,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
        all_lights_on_response=True,
        all_lights_off_response=True,
        all_units_off_response=True,
        learned_addressing=True,
    ),
    "um506_momentary": DeviceProfile(
        profile_id="um506_momentary",
        model="UM506 Universal Module, momentary mode",
        description="Momentary contact closure; ON is an action, not state.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ACTION}),
        supported_commands=ON_ONLY,
        stateful=False,
        repeatable_actions=ON_ONLY,
        all_units_off_response=True,
        operation_mode=OperationMode.MOMENTARY,
    ),
    "um506_continuous": DeviceProfile(
        profile_id="um506_continuous",
        model="UM506 Universal Module, continuous mode",
        description="Continuous contact closure controlled by ON/OFF.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
        all_lights_on_response=False,
        all_units_off_response=True,
        operation_mode=OperationMode.CONTINUOUS,
    ),
    "sc546a_chime": DeviceProfile(
        profile_id="sc546a_chime",
        model="SC546A Remote Chime",
        description="Action-only chime; ON triggers sound and no state is retained.",
        entity_type=DeviceType.CHIME,
        capabilities=frozenset({DeviceCapability.ACTION}),
        supported_commands=ON_ONLY,
        stateful=False,
        repeatable_actions=ON_ONLY,
        all_units_off_response=False,
        operation_mode=OperationMode.ACTION,
    ),
    "ms13a_motion": DeviceProfile(
        profile_id="ms13a_motion",
        model="MS13A EagleEye Motion Sensor",
        description="Standard RF motion address plus base+1 dusk/dawn channel.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
        secondary_channels=(
            SecondaryChannel(ChannelKind.MOTION, 0, "motion on/off"),
            SecondaryChannel(ChannelKind.DUSK_DAWN, 1, "dusk/dawn on/off"),
        ),
        operation_mode=OperationMode.SENSOR,
    ),
    "ms14a_motion": DeviceProfile(
        profile_id="ms14a_motion",
        model="MS14A Motion Sensor",
        description="Standard RF motion address plus base+1 dusk/dawn channel.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
        secondary_channels=(
            SecondaryChannel(ChannelKind.MOTION, 0, "motion on/off"),
            SecondaryChannel(ChannelKind.DUSK_DAWN, 1, "dusk/dawn on/off"),
        ),
        operation_mode=OperationMode.SENSOR,
    ),
    "ms16a_activeeye": DeviceProfile(
        profile_id="ms16a_activeeye",
        model="MS16A ActiveEye Motion Sensor",
        description="Standard RF motion address with optional base+1 dusk/dawn channel.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
        secondary_channels=(
            SecondaryChannel(ChannelKind.MOTION, 0, "motion on/off"),
            SecondaryChannel(
                ChannelKind.DUSK_DAWN,
                1,
                "dusk/dawn on/off, controlled by sensor option",
                enabled_by_default=False,
            ),
        ),
        operation_mode=OperationMode.SENSOR,
    ),
    "pr511_motion_monitor": DeviceProfile(
        profile_id="pr511_motion_monitor",
        model="PR511 Motion Monitor",
        description="Floodlight with sensor channels at +1..+4 and dusk channels at +5..+8.",
        entity_type=DeviceType.LIGHT,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
        secondary_channels=(
            SecondaryChannel(ChannelKind.FLOODLIGHT, 0, "local floodlight"),
            SecondaryChannel(ChannelKind.SENSOR, 1, "sensor 1"),
            SecondaryChannel(ChannelKind.SENSOR, 2, "sensor 2"),
            SecondaryChannel(ChannelKind.SENSOR, 3, "sensor 3"),
            SecondaryChannel(ChannelKind.SENSOR, 4, "sensor 4"),
            SecondaryChannel(ChannelKind.DUSK_DAWN, 5, "dusk 1"),
            SecondaryChannel(ChannelKind.DUSK_DAWN, 6, "dusk 2"),
            SecondaryChannel(ChannelKind.DUSK_DAWN, 7, "dusk 3"),
            SecondaryChannel(ChannelKind.DUSK_DAWN, 8, "dusk 4"),
        ),
    ),
    "powerflash_mode_1": DeviceProfile(
        profile_id="powerflash_mode_1",
        model="PowerFlash PF284/PSC01 mode 1",
        description="Compound alarm mode using same-address and same-house responses.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF, DeviceCapability.ALL_LIGHTS}),
        supported_commands=ON_OFF,
        stateful=True,
        command_sequences=(
            CommandSequence("alarm_on", (Command.ALL_LIGHTS_ON, Command.ON)),
            CommandSequence("alarm_reset", (Command.OFF,)),
        ),
        operation_mode=OperationMode.ALARM_SEQUENCE,
    ),
    "powerflash_mode_2": DeviceProfile(
        profile_id="powerflash_mode_2",
        model="PowerFlash PF284/PSC01 mode 2",
        description="Compound flashing alarm mode; reset leaves lights on.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ALL_LIGHTS}),
        supported_commands=ON_OFF,
        stateful=False,
        repeatable_actions=ON_OFF,
        command_sequences=(
            CommandSequence(
                "flash_alarm",
                (Command.ALL_LIGHTS_ON, Command.ALL_LIGHTS_OFF),
            ),
        ),
        operation_mode=OperationMode.ALARM_SEQUENCE,
    ),
    "powerflash_mode_3": DeviceProfile(
        profile_id="powerflash_mode_3",
        model="PowerFlash PF284/PSC01 mode 3",
        description="Same-address ON/OFF mode.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
    ),
    "powerhorn": DeviceProfile(
        profile_id="powerhorn",
        model="PowerHorn SH10A/PH508",
        description="Siren triggered by repeated ON/OFF or All Lights/All Units sequences.",
        entity_type=DeviceType.CHIME,
        capabilities=frozenset({DeviceCapability.ACTION, DeviceCapability.ALL_LIGHTS}),
        supported_commands=frozenset(
            {
                Command.ON,
                Command.OFF,
                Command.DIM,
                Command.BRIGHT,
                Command.ALL_LIGHTS_ON,
                Command.ALL_UNITS_OFF,
            }
        ),
        stateful=False,
        repeatable_actions=frozenset({Command.ON, Command.OFF}),
        command_sequences=(
            CommandSequence("unit_alarm", (Command.ON, Command.OFF, Command.ON)),
            CommandSequence(
                "house_alarm",
                (Command.ALL_LIGHTS_ON, Command.ALL_UNITS_OFF),
            ),
            CommandSequence("ding_dong", (Command.DIM, Command.BRIGHT)),
        ),
        all_units_off_response=False,
        operation_mode=OperationMode.ALARM_SEQUENCE,
    ),
    "rr501_unit_1": DeviceProfile(
        profile_id="rr501_unit_1",
        model="RR501 Transceiver internal outlet, Unit 1",
        description="Selectable internal outlet responds to unit 1 ON/OFF.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
        secondary_channels=(
            SecondaryChannel(ChannelKind.INTERNAL_OUTLET, 0, "selected unit 1"),
        ),
        exclusive_groups=frozenset({"rr501_internal_outlet"}),
    ),
    "rr501_unit_9": DeviceProfile(
        profile_id="rr501_unit_9",
        model="RR501 Transceiver internal outlet, Unit 9",
        description="Selectable internal outlet responds to unit 9 ON/OFF.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
        secondary_channels=(
            SecondaryChannel(ChannelKind.INTERNAL_OUTLET, 8, "selected unit 9"),
        ),
        exclusive_groups=frozenset({"rr501_internal_outlet"}),
    ),
    "grouped_address_function": DeviceProfile(
        profile_id="grouped_address_function",
        model="Grouped X10 address/function sequence",
        description="Multiple accumulated addresses followed by one function.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=ON_OFF,
        stateful=True,
        secondary_channels=(
            SecondaryChannel(
                ChannelKind.GROUPED_ADDRESS,
                0,
                "function applies to accumulated address set",
            ),
        ),
    ),
}


def profile_ids() -> frozenset[str]:
    return frozenset(DEVICE_PROFILES)


def get_profile(profile_id: str) -> DeviceProfile:
    try:
        return DEVICE_PROFILES[profile_id.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"Unknown X10 device profile '{profile_id}'.") from exc


def apply_profile(device: DeviceConfig, profile_id: str) -> DeviceConfig:
    """Return a DeviceConfig with registry capabilities applied."""

    profile = get_profile(profile_id)

    return replace(
        device,
        profile=profile.profile_id,
        entity_type=profile.entity_type,
        capabilities=profile.capabilities,
        supported_commands=profile.supported_commands,
        stateful=profile.stateful,
        repeatable_actions=profile.repeatable_actions,
        all_lights_on_response=profile.all_lights_on_response,
        all_lights_off_response=profile.all_lights_off_response,
        all_units_off_response=profile.all_units_off_response,
        learned_addressing=profile.learned_addressing,
        secondary_channels=profile.secondary_channels,
        exclusive_groups=profile.exclusive_groups,
        operation_mode=profile.operation_mode,
        command_sequences=profile.command_sequences,
        rf_identity=profile.rf_identity,
    )
