"""Capability-driven X10 device profiles with evidence gating.

Generic profiles describe behavior explicitly chosen by the user. Named
hardware profiles make project claims about a product, so they require
lifecycle and evidence metadata before registration.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import logging
import re

from models import (
    Command,
    CommandSequence,
    DeviceCapability,
    DeviceConfig,
    DeviceType,
    OperationMode,
    RfIdentity,
    SecondaryChannel,
)


_LOG = logging.getLogger(__name__)
_REVIEW_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ProfileLifecycle(str, Enum):
    RESEARCH = "research"
    EXPERIMENTAL = "experimental"
    VERIFIED = "verified"
    DEPRECATED = "deprecated"


class EvidenceConfidence(str, Enum):
    CONFIRMED = "confirmed"
    WELL_SUPPORTED = "well_supported"
    COMMUNITY_REPORTED = "community_reported"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"


class VerificationState(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"
    NOT_APPLICABLE = "not_applicable"
    HARDWARE_REQUIRED = "hardware_required"


@dataclass(slots=True, frozen=True)
class EvidenceSource:
    """One reviewable source supporting a named profile."""

    reference: str
    source_type: str
    title: str
    sha256: str | None = None


@dataclass(slots=True, frozen=True)
class ProfileEvidence:
    """Evidence and verification state for a named hardware profile."""

    confidence: EvidenceConfidence
    sources: tuple[EvidenceSource, ...]
    fixture_verification: VerificationState
    hardware_verification: VerificationState
    last_reviewed: str
    reviewed_by: str
    notes: str

    def diagnostics(self) -> dict[str, object]:
        return {
            "confidence": self.confidence.value,
            "fixture_verification": self.fixture_verification.value,
            "hardware_verification": self.hardware_verification.value,
            "last_reviewed": self.last_reviewed,
        }


@dataclass(slots=True, frozen=True)
class DeviceProfile:
    """Stable capability description for an X10 behavior or product."""

    profile_id: str
    model: str
    description: str
    entity_type: DeviceType
    capabilities: frozenset[DeviceCapability]
    supported_commands: frozenset[Command]
    stateful: bool
    is_generic: bool = False
    lifecycle: ProfileLifecycle | None = None
    evidence: ProfileEvidence | None = None
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

    def diagnostics(self) -> dict[str, object] | None:
        if self.is_generic or self.lifecycle is None or self.evidence is None:
            return None

        return {
            "profile_id": self.profile_id,
            "lifecycle": self.lifecycle.value,
            **self.evidence.diagnostics(),
        }


class ProfileRegistrationError(ValueError):
    """Raised when a profile registration is structurally invalid."""


class ProfileSelectionError(ValueError):
    """Raised when configuration selects an unavailable profile."""


class DeviceProfileRegistry:
    """Validated registry and lifecycle-aware profile selection."""

    def __init__(self, profiles: tuple[DeviceProfile, ...] = ()) -> None:
        self._profiles: dict[str, DeviceProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: DeviceProfile) -> None:
        self._validate_registration(profile)
        profile_id = profile.profile_id.strip().lower()
        if profile_id in self._profiles:
            raise ProfileRegistrationError(
                f"Duplicate X10 device profile '{profile.profile_id}'."
            )
        self._profiles[profile_id] = profile

    def get(self, profile_id: str) -> DeviceProfile:
        normalized = profile_id.strip().lower()
        try:
            return self._profiles[normalized]
        except KeyError as exc:
            raise ProfileSelectionError(
                f"Unknown X10 device profile '{profile_id}'."
            ) from exc

    def select(
        self,
        profile_id: str,
        *,
        allow_experimental: bool = False,
        allow_deprecated: bool = True,
    ) -> DeviceProfile:
        profile = self.get(profile_id)

        if profile.is_generic:
            return profile

        lifecycle = profile.lifecycle
        if lifecycle is ProfileLifecycle.RESEARCH:
            raise ProfileSelectionError(
                f"Device profile '{profile.profile_id}' is research-only and "
                "cannot be selected. Use an explicit generic device type or "
                "wait for the profile to complete evidence review."
            )

        if lifecycle is ProfileLifecycle.EXPERIMENTAL:
            if not allow_experimental:
                raise ProfileSelectionError(
                    f"Device profile '{profile.profile_id}' is experimental. "
                    "Set profiles.allow_experimental=true in bridge.json or "
                    "ALLOW_EXPERIMENTAL_PROFILES=true to opt in explicitly."
                )
            _LOG.warning(
                "Experimental device profile selected profile=%s "
                "confidence=%s fixture_verification=%s "
                "hardware_verification=%s",
                profile.profile_id,
                profile.evidence.confidence.value,
                profile.evidence.fixture_verification.value,
                profile.evidence.hardware_verification.value,
            )
            return profile

        if lifecycle is ProfileLifecycle.DEPRECATED:
            if not allow_deprecated:
                raise ProfileSelectionError(
                    f"Device profile '{profile.profile_id}' is deprecated and "
                    "is not available for new configuration."
                )
            _LOG.warning(
                "Deprecated device profile loaded for compatibility profile=%s",
                profile.profile_id,
            )
            return profile

        return profile

    def registered_ids(self) -> frozenset[str]:
        return frozenset(self._profiles)

    def supported_ids(self) -> frozenset[str]:
        return frozenset(
            profile_id
            for profile_id, profile in self._profiles.items()
            if profile.is_generic
            or profile.lifecycle is ProfileLifecycle.VERIFIED
        )

    @staticmethod
    def _validate_registration(profile: DeviceProfile) -> None:
        if not profile.profile_id.strip():
            raise ProfileRegistrationError("Profile ID cannot be empty.")
        if not profile.model.strip():
            raise ProfileRegistrationError(
                f"Profile '{profile.profile_id}' must include a model."
            )

        if profile.is_generic:
            if profile.lifecycle is not None or profile.evidence is not None:
                raise ProfileRegistrationError(
                    f"Generic profile '{profile.profile_id}' must not include "
                    "named-profile lifecycle or evidence metadata."
                )
            return

        if profile.lifecycle is None or profile.evidence is None:
            raise ProfileRegistrationError(
                f"Named profile '{profile.profile_id}' requires lifecycle and "
                "evidence metadata."
            )

        evidence = profile.evidence
        if not evidence.sources:
            raise ProfileRegistrationError(
                f"Named profile '{profile.profile_id}' requires at least one "
                "evidence source."
            )
        if not _REVIEW_DATE_RE.fullmatch(evidence.last_reviewed):
            raise ProfileRegistrationError(
                f"Named profile '{profile.profile_id}' last_reviewed must use "
                "YYYY-MM-DD."
            )
        if not evidence.reviewed_by.strip() or not evidence.notes.strip():
            raise ProfileRegistrationError(
                f"Named profile '{profile.profile_id}' requires reviewed_by "
                "and notes."
            )
        for source in evidence.sources:
            if not (
                source.reference.strip()
                and source.source_type.strip()
                and source.title.strip()
            ):
                raise ProfileRegistrationError(
                    f"Named profile '{profile.profile_id}' has incomplete "
                    "evidence source metadata."
                )

        if profile.lifecycle is ProfileLifecycle.VERIFIED:
            if evidence.confidence not in {
                EvidenceConfidence.CONFIRMED,
                EvidenceConfidence.WELL_SUPPORTED,
            }:
                raise ProfileRegistrationError(
                    f"Verified profile '{profile.profile_id}' requires "
                    "confirmed or well-supported confidence."
                )
            if evidence.fixture_verification is not VerificationState.PASS:
                raise ProfileRegistrationError(
                    f"Verified profile '{profile.profile_id}' requires "
                    "passing deterministic fixtures."
                )
            if evidence.hardware_verification not in {
                VerificationState.PASS,
                VerificationState.NOT_APPLICABLE,
            }:
                raise ProfileRegistrationError(
                    f"Verified profile '{profile.profile_id}' requires "
                    "passing or not-applicable hardware verification."
                )


ON_OFF = frozenset({Command.ON, Command.OFF})
ON_ONLY = frozenset({Command.ON})
LIGHT_COMMANDS = frozenset({Command.ON, Command.OFF, Command.DIM, Command.BRIGHT})


GENERIC_SWITCH = DeviceProfile(
    profile_id="generic_switch",
    model="Generic X10 switch or appliance module",
    description="Stateful ON/OFF behavior explicitly declared by the user.",
    entity_type=DeviceType.SWITCH,
    capabilities=frozenset({DeviceCapability.ON_OFF}),
    supported_commands=ON_OFF,
    stateful=True,
    is_generic=True,
)

GENERIC_LIGHT = DeviceProfile(
    profile_id="generic_light",
    model="Generic X10 light module",
    description="Stateful dimmable light behavior explicitly declared by the user.",
    entity_type=DeviceType.LIGHT,
    capabilities=frozenset({DeviceCapability.ON_OFF, DeviceCapability.DIM}),
    supported_commands=LIGHT_COMMANDS,
    stateful=True,
    is_generic=True,
    all_lights_on_response=True,
    all_lights_off_response=True,
)

SC546A_CHIME = DeviceProfile(
    profile_id="sc546a_chime",
    model="SC546A Remote Chime",
    description=(
        "Experimental action-only chime mapping; ON triggers an unconfirmed "
        "transmission and no state is retained."
    ),
    entity_type=DeviceType.CHIME,
    capabilities=frozenset({DeviceCapability.ACTION}),
    supported_commands=ON_ONLY,
    stateful=False,
    lifecycle=ProfileLifecycle.EXPERIMENTAL,
    evidence=ProfileEvidence(
        confidence=EvidenceConfidence.WELL_SUPPORTED,
        sources=(
            EvidenceSource(
                reference=(
                    "https://cdn.shopify.com/s/files/1/2279/4329/"
                    "files/SC546A.pdf"
                ),
                source_type="manufacturer_manual",
                title="Remote Chime, Model SC546A (SC546A-6/13)",
                sha256=(
                    "84edf836c1ca3dc174c5703cb458f599f"
                    "b4ab8f20db3f458aeedde1af77d9645"
                ),
            ),
        ),
        fixture_verification=VerificationState.PASS,
        hardware_verification=VerificationState.HARDWARE_REQUIRED,
        last_reviewed="2026-07-21",
        reviewed_by="Mochad project maintainers",
        notes=(
            "Manual confirms SC546A chime identity and TM751 path. OFF and "
            "rapid repeated-ON physical behavior remain unverified."
        ),
    ),
    repeatable_actions=ON_ONLY,
    all_units_off_response=False,
    operation_mode=OperationMode.ACTION,
)


# These identifiers retain the prior research record names for clear errors.
# Their behavior remains in project research documentation and is not imported
# into the production registry.
RESEARCH_PROFILE_IDS = frozenset(
    {
        "grouped_address_function",
        "lm15a_socket_rocket",
        "ms13a_motion",
        "ms14a_motion",
        "ms16a_activeeye",
        "powerflash_mode_1",
        "powerflash_mode_2",
        "powerflash_mode_3",
        "powerhorn",
        "pr511_motion_monitor",
        "rr501_unit_1",
        "rr501_unit_9",
        "um506_continuous",
        "um506_momentary",
    }
)


PROFILE_REGISTRY = DeviceProfileRegistry(
    (GENERIC_SWITCH, GENERIC_LIGHT, SC546A_CHIME)
)


def profile_ids() -> frozenset[str]:
    """Return profiles that may be presented as normally supported choices."""

    return PROFILE_REGISTRY.supported_ids()


def registered_profile_ids() -> frozenset[str]:
    return PROFILE_REGISTRY.registered_ids()


def get_profile(profile_id: str) -> DeviceProfile:
    return PROFILE_REGISTRY.get(profile_id)


def select_profile(
    profile_id: str,
    *,
    allow_experimental: bool = False,
    allow_deprecated: bool = True,
) -> DeviceProfile:
    normalized = profile_id.strip().lower()
    if normalized in RESEARCH_PROFILE_IDS:
        raise ProfileSelectionError(
            f"Device profile '{normalized}' is research-only and cannot be "
            "selected. Use an explicit generic device type or wait for the "
            "profile to complete evidence review."
        )
    return PROFILE_REGISTRY.select(
        normalized,
        allow_experimental=allow_experimental,
        allow_deprecated=allow_deprecated,
    )


def apply_profile(
    device: DeviceConfig,
    profile_id: str,
    *,
    allow_experimental: bool = False,
    allow_deprecated: bool = True,
) -> DeviceConfig:
    profile = select_profile(
        profile_id,
        allow_experimental=allow_experimental,
        allow_deprecated=allow_deprecated,
    )

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


def configured_profile_diagnostics(
    devices: dict[str, DeviceConfig],
) -> list[dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    for device in sorted(devices.values(), key=lambda item: item.address):
        if device.profile is None:
            continue
        profile = get_profile(device.profile)
        profile_diagnostics = profile.diagnostics()
        if profile_diagnostics is None:
            continue
        diagnostics.append(
            {
                "address": device.address,
                **profile_diagnostics,
            }
        )
    return diagnostics
