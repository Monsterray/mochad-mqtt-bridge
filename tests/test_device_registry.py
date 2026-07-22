import json
import os
import tempfile
import unittest
from unittest.mock import patch

from config import ConfigError, create_config_file_if_missing, load_config
from device_registry import (
    DeviceProfile,
    DeviceProfileRegistry,
    EvidenceConfidence,
    EvidenceSource,
    ProfileEvidence,
    ProfileLifecycle,
    ProfileRegistrationError,
    ProfileSelectionError,
    RESEARCH_PROFILE_IDS,
    VerificationState,
    apply_profile,
    configured_profile_diagnostics,
    get_profile,
    profile_ids,
    registered_profile_ids,
    select_profile,
)
from discovery import DiscoveryManager
from models import (
    Command,
    DeviceCapability,
    DeviceConfig,
    DeviceType,
    PublishCommandEventAction,
    PublishStateAction,
    SendDeviceCommandAction,
)
from state import StateManager


def _evidence(
    confidence: EvidenceConfidence = EvidenceConfidence.CONFIRMED,
) -> ProfileEvidence:
    return ProfileEvidence(
        confidence=confidence,
        sources=(
            EvidenceSource(
                reference="https://example.invalid/manual.pdf",
                source_type="manufacturer_manual",
                title="Test manual",
            ),
        ),
        fixture_verification=VerificationState.PASS,
        hardware_verification=VerificationState.NOT_APPLICABLE,
        last_reviewed="2026-07-21",
        reviewed_by="Test maintainer",
        notes="Synthetic registry test profile.",
    )


def _named_profile(
    lifecycle: ProfileLifecycle,
    evidence: ProfileEvidence | None = None,
) -> DeviceProfile:
    return DeviceProfile(
        profile_id=f"test_{lifecycle.value}",
        model="Test named device",
        description="Synthetic named profile for registry tests.",
        entity_type=DeviceType.SWITCH,
        capabilities=frozenset({DeviceCapability.ON_OFF}),
        supported_commands=frozenset({Command.ON, Command.OFF}),
        stateful=True,
        lifecycle=lifecycle,
        evidence=evidence,
    )


class DeviceProfileRegistrationTests(unittest.TestCase):
    def test_supported_profile_listing_excludes_experimental_and_research(self):
        self.assertEqual(
            profile_ids(),
            frozenset({"generic_switch", "generic_light"}),
        )
        self.assertEqual(
            registered_profile_ids(),
            frozenset(
                {"generic_switch", "generic_light", "sc546a_chime"}
            ),
        )
        self.assertTrue(RESEARCH_PROFILE_IDS.isdisjoint(registered_profile_ids()))

    def test_named_profile_requires_lifecycle_and_evidence(self):
        missing_metadata = DeviceProfile(
            profile_id="missing_metadata",
            model="Test device",
            description="Invalid named profile.",
            entity_type=DeviceType.SWITCH,
            capabilities=frozenset({DeviceCapability.ON_OFF}),
            supported_commands=frozenset({Command.ON, Command.OFF}),
            stateful=True,
        )

        with self.assertRaisesRegex(
            ProfileRegistrationError,
            "requires lifecycle and evidence metadata",
        ):
            DeviceProfileRegistry((missing_metadata,))

    def test_research_profile_is_never_selectable(self):
        registry = DeviceProfileRegistry(
            (
                _named_profile(
                    ProfileLifecycle.RESEARCH,
                    _evidence(EvidenceConfidence.UNVERIFIED),
                ),
            )
        )

        with self.assertRaisesRegex(ProfileSelectionError, "research-only"):
            registry.select(
                "test_research",
                allow_experimental=True,
            )

    def test_verified_profile_is_normally_selectable(self):
        profile = _named_profile(
            ProfileLifecycle.VERIFIED,
            _evidence(),
        )
        registry = DeviceProfileRegistry((profile,))

        self.assertIs(registry.select(profile.profile_id), profile)
        self.assertIn(profile.profile_id, registry.supported_ids())

    def test_deprecated_profile_load_is_explicit_and_not_offered(self):
        profile = _named_profile(
            ProfileLifecycle.DEPRECATED,
            _evidence(),
        )
        registry = DeviceProfileRegistry((profile,))

        self.assertNotIn(profile.profile_id, registry.supported_ids())
        with self.assertLogs("device_registry", level="WARNING") as logs:
            self.assertIs(registry.select(profile.profile_id), profile)
        self.assertIn("Deprecated device profile", logs.output[0])

        with self.assertRaisesRegex(ProfileSelectionError, "deprecated"):
            registry.select(profile.profile_id, allow_deprecated=False)


class GenericCapabilityRegressionTests(unittest.TestCase):
    def test_generic_switch_light_and_action_behavior_is_unchanged(self):
        direct_switch = DeviceConfig("A1", "Switch", DeviceType.SWITCH)
        direct_light = DeviceConfig("A2", "Light", DeviceType.LIGHT)
        direct_action = DeviceConfig("A3", "Action", DeviceType.CHIME)

        named_switch = apply_profile(
            DeviceConfig("A1", "Switch"),
            "generic_switch",
        )
        named_light = apply_profile(
            DeviceConfig("A2", "Light"),
            "generic_light",
        )

        self.assertEqual(
            named_switch.supported_commands,
            direct_switch.supported_commands,
        )
        self.assertEqual(named_switch.stateful, direct_switch.stateful)
        self.assertEqual(
            named_light.supported_commands,
            direct_light.supported_commands,
        )
        self.assertEqual(named_light.stateful, direct_light.stateful)
        self.assertEqual(
            direct_action.supported_commands,
            frozenset({Command.ON}),
        )
        self.assertFalse(direct_action.stateful)
        self.assertEqual(
            direct_action.repeatable_actions,
            frozenset({Command.ON}),
        )

    def test_generic_home_assistant_discovery_is_unchanged(self):
        discovery = DiscoveryManager(
            discovery_prefix="homeassistant",
            base_topic="x10",
        )
        switch = discovery.discovery_messages(
            DeviceConfig("A1", "Switch", DeviceType.SWITCH)
        )[0]
        light = discovery.discovery_messages(
            DeviceConfig("A2", "Light", DeviceType.LIGHT)
        )[0]

        self.assertEqual(
            switch.topic,
            "homeassistant/switch/x10_A1/config",
        )
        self.assertEqual(switch.payload["state_topic"], "x10/A1/state")
        self.assertEqual(switch.payload["command_topic"], "x10/A1/command")
        self.assertEqual(
            light.topic,
            "homeassistant/light/x10_A2/config",
        )
        self.assertEqual(light.payload["state_topic"], "x10/A2/state")
        self.assertEqual(light.payload["command_topic"], "x10/A2/command")


class DeviceProfileConfigTests(unittest.TestCase):
    def test_unknown_device_type_remains_an_unknown_type_error(self):
        with patch.dict(
            os.environ,
            {"X10_DEVICES": "A2:Unknown Device:not_a_profile"},
            clear=True,
        ):
            with self.assertRaisesRegex(ConfigError, "Unknown device type"):
                load_config()

    def test_experimental_profile_is_rejected_by_default(self):
        with patch.dict(
            os.environ,
            {"X10_DEVICES": "A2:Door Chime:sc546a_chime"},
            clear=True,
        ):
            with self.assertRaisesRegex(ConfigError, "experimental"):
                load_config()

    def test_experimental_profile_works_with_environment_opt_in(self):
        with patch.dict(
            os.environ,
            {
                "ALLOW_EXPERIMENTAL_PROFILES": "true",
                "X10_DEVICES": "A2:Door Chime:sc546a_chime",
            },
            clear=True,
        ):
            with self.assertLogs("device_registry", level="WARNING"):
                config = load_config()

        self.assertTrue(config.allow_experimental_profiles)
        self.assertEqual(config.devices["A2"].profile, "sc546a_chime")

    def test_experimental_profile_works_with_file_opt_in(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as config_file:
            json.dump(
                {
                    "profiles": {"allow_experimental": True},
                    "devices": [
                        {
                            "address": "A2",
                            "name": "Door Chime",
                            "type": "chime",
                            "profile": "sc546a_chime",
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
                with self.assertLogs("device_registry", level="WARNING"):
                    config = load_config()

        self.assertTrue(config.allow_experimental_profiles)
        self.assertEqual(config.devices["A2"].profile, "sc546a_chime")

    def test_research_profile_is_rejected_even_with_opt_in(self):
        with patch.dict(
            os.environ,
            {
                "ALLOW_EXPERIMENTAL_PROFILES": "true",
                "X10_DEVICES": "A1:Socket:lm15a_socket_rocket",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ConfigError, "research-only"):
                load_config()

    def test_generated_config_preserves_profile_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, "bridge.json")
            with patch.dict(
                os.environ,
                {
                    "ALLOW_EXPERIMENTAL_PROFILES": "true",
                    "BRIDGE_CONFIG_FILE": config_path,
                    "X10_DEVICES": "A2:Door Chime:sc546a_chime",
                },
                clear=True,
            ):
                config = load_config()

            self.assertTrue(create_config_file_if_missing(config))
            with open(config_path, encoding="utf-8") as handle:
                payload = json.load(handle)

        self.assertEqual(
            payload["profiles"],
            {"allow_experimental": True},
        )
        self.assertEqual(payload["devices"][0]["profile"], "sc546a_chime")


class Sc546aBehaviorTests(unittest.TestCase):
    def test_sc546a_remains_action_only_and_unconfirmed(self):
        device = apply_profile(
            DeviceConfig("A2", "Door Chime"),
            "sc546a_chime",
            allow_experimental=True,
        )
        state = StateManager([device])

        first = state.optimistic_update("A2", Command.ON)
        second = state.optimistic_update("A2", Command.ON)
        actions = first + second

        self.assertEqual(
            sum(isinstance(action, SendDeviceCommandAction) for action in actions),
            2,
        )
        self.assertFalse(
            any(isinstance(action, PublishStateAction) for action in actions)
        )
        events = [
            action
            for action in actions
            if isinstance(action, PublishCommandEventAction)
        ]
        self.assertEqual(len(events), 2)
        self.assertTrue(
            all(event.payload["confirmed"] is False for event in events)
        )

        discovery = DiscoveryManager(
            discovery_prefix="homeassistant",
            base_topic="x10",
        ).discovery_messages(device)[0]
        self.assertEqual(
            discovery.topic,
            "homeassistant/button/x10_A2/config",
        )
        self.assertNotIn("state_topic", discovery.payload)

    def test_profile_diagnostics_report_evidence_without_support_claim(self):
        device = apply_profile(
            DeviceConfig("A2", "Door Chime"),
            "sc546a_chime",
            allow_experimental=True,
        )

        self.assertEqual(
            configured_profile_diagnostics({"A2": device}),
            [
                {
                    "address": "A2",
                    "profile_id": "sc546a_chime",
                    "lifecycle": "experimental",
                    "confidence": "well_supported",
                    "fixture_verification": "pass",
                    "hardware_verification": "hardware_required",
                    "last_reviewed": "2026-07-21",
                }
            ],
        )
        profile = get_profile("sc546a_chime")
        self.assertIs(profile.lifecycle, ProfileLifecycle.EXPERIMENTAL)

    def test_direct_selection_requires_explicit_opt_in(self):
        with self.assertRaisesRegex(ProfileSelectionError, "experimental"):
            select_profile("sc546a_chime")


if __name__ == "__main__":
    unittest.main()
