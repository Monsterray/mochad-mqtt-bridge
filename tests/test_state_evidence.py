from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from bridge import Bridge
from config import MqttTlsConfig
from device_registry import apply_profile
from discovery import DiscoveryManager
from models import (
    Command,
    DeviceConfig,
    DeviceEvent,
    DeviceType,
    Direction,
    HouseEvent,
    MochadDiagnostics,
    PhysicalConfirmation,
    PublishAttributesAction,
    PublishStateAction,
    SendDeviceCommandAction,
    StateConfidence,
    StateProvenance,
    StatusSnapshot,
    Transport,
)
from state import StateManager


NOW = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


def _device_event(
    direction: Direction,
    command: Command = Command.ON,
) -> DeviceEvent:
    return DeviceEvent(
        timestamp=NOW,
        direction=direction,
        transport=Transport.RF,
        command=command,
        address="A1",
    )


def test_optimistic_state_is_assumed_and_keeps_legacy_state_api():
    manager = StateManager([DeviceConfig("A1", "Lamp")])

    with patch.object(StateManager, "_now", return_value=NOW):
        actions = manager.optimistic_update("A1", Command.ON)

    state = manager.snapshot()["A1"]
    attributes = next(
        action for action in actions if isinstance(action, PublishAttributesAction)
    )
    assert state.value is Command.ON
    assert state.current_state is Command.ON
    assert state.confidence is StateConfidence.ASSUMED
    assert state.provenance is StateProvenance.MQTT_COMMAND
    assert state.updated_at == NOW
    assert state.observed_at is None
    assert state.physical_confirmation is PhysicalConfirmation.UNKNOWN
    assert attributes.payload["last_command_sent"] == "ON"
    assert attributes.payload["confidence"] == "assumed"
    assert attributes.payload["provenance"] == "mqtt_command"
    assert attributes.payload["physical_confirmation"] == "unknown"


def test_received_duplicate_upgrades_assumed_state_to_reported():
    manager = StateManager([DeviceConfig("A1", "Lamp")])
    with patch.object(StateManager, "_now", return_value=NOW - timedelta(seconds=1)):
        manager.optimistic_update("A1", Command.ON)

    actions = manager.apply(_device_event(Direction.RX))
    state = manager.snapshot()["A1"]

    assert not any(isinstance(action, PublishStateAction) for action in actions)
    assert any(isinstance(action, PublishAttributesAction) for action in actions)
    assert state.confidence is StateConfidence.REPORTED
    assert state.provenance is StateProvenance.DEVICE_EVENT
    assert state.observed_at == NOW
    assert state.pending_command is None


def test_transmitted_event_never_raises_state_or_physical_confidence():
    manager = StateManager([DeviceConfig("A1", "Lamp")])

    manager.apply(_device_event(Direction.TX))
    state = manager.snapshot()["A1"]

    assert state.current_state is Command.ON
    assert state.confidence is StateConfidence.UNKNOWN
    assert state.provenance is StateProvenance.TRANSMITTED_EVENT
    assert state.observed_at is None
    assert state.physical_confirmation is PhysicalConfirmation.UNKNOWN


def test_transmitted_value_change_does_not_reuse_old_reported_confidence():
    manager = StateManager([DeviceConfig("A1", "Lamp")])
    manager.apply(_device_event(Direction.RX, Command.OFF))

    manager.apply(_device_event(Direction.TX, Command.ON))
    state = manager.snapshot()["A1"]

    assert state.current_state is Command.ON
    assert state.confidence is StateConfidence.UNKNOWN
    assert state.provenance is StateProvenance.TRANSMITTED_EVENT
    assert state.observed_at is None


def test_status_snapshot_is_profile_independent_inference():
    manager = StateManager([DeviceConfig("A1", "Lamp")])

    with patch.object(StateManager, "_now", return_value=NOW):
        manager.apply(StatusSnapshot(devices={"A1": Command.OFF}, completed=True))

    state = manager.snapshot()["A1"]
    assert state.confidence is StateConfidence.INFERRED
    assert state.provenance is StateProvenance.STATUS_SYNC
    assert state.observed_at is None


def test_received_house_command_uses_profile_derived_inference():
    manager = StateManager(
        [DeviceConfig("A1", "Lamp", entity_type=DeviceType.LIGHT)]
    )

    manager.apply(
        HouseEvent(
            timestamp=NOW,
            direction=Direction.RX,
            transport=Transport.RF,
            command=Command.ALL_LIGHTS_ON,
            house="A",
        )
    )

    state = manager.snapshot()["A1"]
    assert state.current_state is Command.ON
    assert state.confidence is StateConfidence.INFERRED
    assert state.provenance is StateProvenance.PROFILE_INFERENCE
    assert state.observed_at is None


def test_staleness_preserves_historical_evidence():
    manager = StateManager(
        [DeviceConfig("A1", "Lamp")],
        stale_after=timedelta(seconds=1),
    )
    with patch.object(StateManager, "_now", return_value=NOW):
        manager.optimistic_update("A1", Command.ON)
    with patch.object(
        StateManager,
        "_now",
        return_value=NOW + timedelta(seconds=2),
    ):
        state = manager.snapshot()["A1"]

    assert state.stale is True
    assert state.expires_at == NOW + timedelta(seconds=1)
    assert state.confidence is StateConfidence.ASSUMED
    assert state.provenance is StateProvenance.MQTT_COMMAND


def test_status_reports_bounded_state_evidence_counts():
    manager = StateManager([DeviceConfig("A1", "Lamp")])
    manager.apply(_device_event(Direction.RX))
    bridge = object.__new__(Bridge)
    bridge.config = SimpleNamespace(
        allow_experimental_profiles=False,
        mqtt_tls=MqttTlsConfig(),
    )
    bridge.state = manager
    bridge.clients = SimpleNamespace(
        mqtt=SimpleNamespace(connected=True),
        mochad=SimpleNamespace(connected=True),
    )
    bridge.devices = {"A1": DeviceConfig("A1", "Lamp")}
    bridge._mochad_diagnostics = MochadDiagnostics()

    evidence = bridge._bridge_status_payload()["state_evidence"]

    assert evidence["confidence"]["reported"] == 1
    assert evidence["confidence"]["observed"] == 0
    assert evidence["stale"] == 0
    assert evidence["physical_confirmation"]["unknown"] == 1


def test_discovery_adds_attributes_only_to_stateful_entities():
    manager = DiscoveryManager(
        discovery_prefix="homeassistant",
        base_topic="x10",
    )
    generic = manager.discovery_messages(DeviceConfig("A1", "Lamp"))[0]
    chime = apply_profile(
        DeviceConfig("A2", "Door Chime"),
        "sc546a_chime",
        allow_experimental=True,
    )
    button = manager.discovery_messages(chime)[0]

    assert generic.payload["json_attributes_topic"] == "x10/A1/attributes"
    assert generic.payload["state_topic"] == "x10/A1/state"
    assert "json_attributes_topic" not in button.payload
    assert "state_topic" not in button.payload


def test_sc546a_remains_action_only_without_retained_state_or_attributes():
    chime = apply_profile(
        DeviceConfig("A2", "Door Chime"),
        "sc546a_chime",
        allow_experimental=True,
    )
    manager = StateManager([chime])

    actions = (
        manager.optimistic_update("A2", Command.ON)
        + manager.optimistic_update("A2", Command.ON)
    )

    assert sum(
        isinstance(action, SendDeviceCommandAction) for action in actions
    ) == 2
    assert not any(isinstance(action, PublishStateAction) for action in actions)
    assert not any(
        isinstance(action, PublishAttributesAction) for action in actions
    )
