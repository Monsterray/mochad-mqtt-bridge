import os
import tempfile
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from config import create_config_file_if_missing, load_config
from device_registry import apply_profile, get_profile
from models import (
    BridgeAction,
    ChannelKind,
    Command,
    DeviceCapability,
    DeviceConfig,
    DeviceType,
    HouseEvent,
    OperationMode,
    RfIdentity,
    SendDeviceCommandAction,
)
from state import StateManager


class DeviceRegistryTests(unittest.TestCase):
    def test_lm15a_profile_uses_learned_addressing_without_dim(self):
        profile = get_profile("lm15a_socket_rocket")

        self.assertTrue(profile.learned_addressing)
        self.assertEqual(profile.entity_type, DeviceType.LIGHT)
        self.assertEqual(profile.supported_commands, frozenset({Command.ON, Command.OFF}))
        self.assertNotIn(Command.DIM, profile.supported_commands)
        self.assertTrue(profile.all_lights_on_response)
        self.assertTrue(profile.all_units_off_response)

    def test_um506_momentary_and_continuous_modes_are_distinct(self):
        momentary = get_profile("um506_momentary")
        continuous = get_profile("um506_continuous")

        self.assertFalse(momentary.stateful)
        self.assertEqual(momentary.operation_mode, OperationMode.MOMENTARY)
        self.assertEqual(momentary.repeatable_actions, frozenset({Command.ON}))
        self.assertTrue(momentary.all_units_off_response)

        self.assertTrue(continuous.stateful)
        self.assertEqual(continuous.operation_mode, OperationMode.CONTINUOUS)
        self.assertEqual(continuous.supported_commands, frozenset({Command.ON, Command.OFF}))
        self.assertFalse(continuous.all_lights_on_response)
        self.assertTrue(continuous.all_units_off_response)

    def test_sc546a_profile_is_action_only_on_command(self):
        profile = get_profile("sc546a_chime")

        self.assertEqual(profile.entity_type, DeviceType.CHIME)
        self.assertFalse(profile.stateful)
        self.assertEqual(profile.supported_commands, frozenset({Command.ON}))
        self.assertEqual(profile.repeatable_actions, frozenset({Command.ON}))
        self.assertNotIn(Command.OFF, profile.supported_commands)

    def test_motion_sensor_profiles_have_base_plus_one_dusk_channels(self):
        for profile_id in ("ms13a_motion", "ms14a_motion", "ms16a_activeeye"):
            profile = get_profile(profile_id)
            channels = {(channel.kind, channel.offset) for channel in profile.secondary_channels}

            self.assertIn((ChannelKind.MOTION, 0), channels)
            self.assertIn((ChannelKind.DUSK_DAWN, 1), channels)
            self.assertEqual(profile.rf_identity, RfIdentity.STANDARD)

        ms16a = get_profile("ms16a_activeeye")
        dusk = [
            channel
            for channel in ms16a.secondary_channels
            if channel.kind == ChannelKind.DUSK_DAWN
        ][0]
        self.assertFalse(dusk.enabled_by_default)

    def test_pr511_profile_models_sensor_and_dusk_offsets(self):
        profile = get_profile("pr511_motion_monitor")
        offsets = [(channel.kind, channel.offset) for channel in profile.secondary_channels]

        self.assertIn((ChannelKind.FLOODLIGHT, 0), offsets)
        for offset in range(1, 5):
            self.assertIn((ChannelKind.SENSOR, offset), offsets)
        for offset in range(5, 9):
            self.assertIn((ChannelKind.DUSK_DAWN, offset), offsets)

    def test_powerflash_profiles_model_compound_modes(self):
        mode_1 = get_profile("powerflash_mode_1")
        mode_2 = get_profile("powerflash_mode_2")
        mode_3 = get_profile("powerflash_mode_3")

        self.assertEqual(mode_1.operation_mode, OperationMode.ALARM_SEQUENCE)
        self.assertTrue(mode_1.command_sequences)
        self.assertFalse(mode_2.stateful)
        self.assertEqual(mode_2.operation_mode, OperationMode.ALARM_SEQUENCE)
        self.assertEqual(mode_3.supported_commands, frozenset({Command.ON, Command.OFF}))

    def test_powerhorn_repeated_alarm_sequences_are_explicit(self):
        profile = get_profile("powerhorn")
        sequences = {sequence.name: sequence.commands for sequence in profile.command_sequences}

        self.assertFalse(profile.stateful)
        self.assertEqual(profile.operation_mode, OperationMode.ALARM_SEQUENCE)
        self.assertEqual(sequences["unit_alarm"], (Command.ON, Command.OFF, Command.ON))
        self.assertEqual(
            sequences["house_alarm"],
            (Command.ALL_LIGHTS_ON, Command.ALL_UNITS_OFF),
        )
        self.assertIn(Command.ON, profile.repeatable_actions)

    def test_rr501_profiles_express_exclusive_unit_selection(self):
        unit_1 = get_profile("rr501_unit_1")
        unit_9 = get_profile("rr501_unit_9")

        self.assertEqual(unit_1.secondary_channels[0].offset, 0)
        self.assertEqual(unit_9.secondary_channels[0].offset, 8)
        self.assertEqual(unit_1.exclusive_groups, unit_9.exclusive_groups)
        self.assertIn("rr501_internal_outlet", unit_1.exclusive_groups)

    def test_grouped_address_profile_documents_accumulated_addresses(self):
        profile = get_profile("grouped_address_function")

        self.assertEqual(profile.secondary_channels[0].kind, ChannelKind.GROUPED_ADDRESS)
        self.assertIn(Command.ON, profile.supported_commands)

    def test_apply_profile_preserves_address_name_and_repeat_tuning(self):
        device = apply_profile(
            DeviceConfig(
                address="A1",
                name="Porch Socket",
                command_repeats=3,
                command_repeat_delay_ms=200,
            ),
            "lm15a_socket_rocket",
        )

        self.assertEqual(device.address, "A1")
        self.assertEqual(device.name, "Porch Socket")
        self.assertEqual(device.command_repeats, 3)
        self.assertEqual(device.command_repeat_delay_ms, 200)
        self.assertEqual(device.profile, "lm15a_socket_rocket")
        self.assertTrue(device.learned_addressing)


class DeviceProfileConfigTests(unittest.TestCase):
    def test_env_devices_can_use_profile_as_type_field(self):
        with patch.dict(
            os.environ,
            {"X10_DEVICES": "A2:Door Chime:sc546a_chime"},
            clear=True,
        ):
            config = load_config()

        device = config.devices["A2"]
        self.assertEqual(device.profile, "sc546a_chime")
        self.assertEqual(device.entity_type, DeviceType.CHIME)
        self.assertFalse(device.stateful)

    def test_json_devices_can_use_profile_field(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as config_file:
            json.dump(
                {
                    "devices": [
                        {
                            "address": "A1",
                            "name": "Porch Socket",
                            "type": "light",
                            "profile": "lm15a_socket_rocket",
                        }
                    ],
                },
                config_file,
            )
            config_file.flush()

            with patch.dict(
                os.environ,
                {"BRIDGE_CONFIG_FILE": config_file.name},
                clear=True,
            ):
                config = load_config()

        device = config.devices["A1"]
        self.assertEqual(device.profile, "lm15a_socket_rocket")
        self.assertTrue(device.learned_addressing)
        self.assertNotIn(Command.DIM, device.supported_commands)

    def test_generated_config_preserves_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, "bridge.json")

            with patch.dict(
                os.environ,
                {
                    "BRIDGE_CONFIG_FILE": config_path,
                    "X10_DEVICES": "A2:Door Chime:sc546a_chime",
                },
                clear=True,
            ):
                config = load_config()

            self.assertTrue(create_config_file_if_missing(config))

            with open(config_path, encoding="utf-8") as handle:
                payload = json.load(handle)

        self.assertEqual(payload["devices"][0]["profile"], "sc546a_chime")


class DeviceCapabilityStateTests(unittest.TestCase):
    def _action_types(self, actions: list[BridgeAction]) -> list[type[BridgeAction]]:
        return [type(action) for action in actions]

    def test_house_commands_respect_device_capability_flags(self):
        lamp = apply_profile(
            DeviceConfig(address="A1", name="Socket Rocket"),
            "lm15a_socket_rocket",
        )
        universal = apply_profile(
            DeviceConfig(address="A2", name="Relay"),
            "um506_continuous",
        )
        state = StateManager([lamp, universal])

        all_lights_actions = state.apply(
            HouseEvent(
                timestamp=datetime.now(timezone.utc),
                direction=None,  # type: ignore[arg-type]
                transport=None,  # type: ignore[arg-type]
                command=Command.ALL_LIGHTS_ON,
                house="A",
            )
        )
        self.assertEqual(
            [action.address for action in all_lights_actions if hasattr(action, "address")],
            ["A1"],
        )

        all_units_actions = state.apply(
            HouseEvent(
                timestamp=datetime.now(timezone.utc),
                direction=None,  # type: ignore[arg-type]
                transport=None,  # type: ignore[arg-type]
                command=Command.ALL_UNITS_OFF,
                house="A",
            )
        )
        self.assertEqual(
            [action.address for action in all_units_actions if hasattr(action, "address")],
            ["A1", "A2"],
        )

    def test_repeated_alarm_actions_are_not_deduped(self):
        horn = apply_profile(
            DeviceConfig(address="A4", name="PowerHorn"),
            "powerhorn",
        )
        state = StateManager([horn])

        commands = [Command.ON, Command.OFF, Command.ON]
        sent: list[Command] = []
        for command in commands:
            actions = state.optimistic_update("A4", command)
            send_actions = [
                action
                for action in actions
                if isinstance(action, SendDeviceCommandAction)
            ]
            self.assertEqual(len(send_actions), 1)
            sent.append(send_actions[0].command)

        self.assertEqual(sent, commands)

    def test_repeated_action_only_on_commands_are_not_deduped(self):
        chime = apply_profile(
            DeviceConfig(address="A3", name="Door Chime"),
            "sc546a_chime",
        )
        state = StateManager([chime])

        first = state.optimistic_update("A3", Command.ON)
        second = state.optimistic_update("A3", Command.ON)

        self.assertIn(SendDeviceCommandAction, self._action_types(first))
        self.assertIn(SendDeviceCommandAction, self._action_types(second))


if __name__ == "__main__":
    unittest.main()
