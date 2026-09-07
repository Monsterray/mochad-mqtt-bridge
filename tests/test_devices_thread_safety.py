"""
Bridge.devices is mutated from the paho MQTT callback thread
(_device_config's get-or-create insert, reached via any MQTT command for a
device address not yet configured) and iterated from the main thread
(_publish_current_discovery, _desired_discovery_topics, and the diagnostics
payload, all reached from run_forever's config-reload loop). A plain dict
offers no protection against a resize landing mid-iteration on another
thread -- CPython raises "RuntimeError: dictionary changed size during
iteration" for exactly this, which was previously uncaught on these paths.

This test hammers both sides concurrently: one thread continuously inserts
new device addresses via _device_config() while another continuously takes
snapshots via _devices_snapshot() and iterates them, for enough iterations
that the race reliably manifests on unlocked code. See test_race_is_real_
without_the_lock below for the control that proves this is not a theoretical
concern -- it demonstrates the crash on a deliberately unlocked stand-in
before asserting the real, locked Bridge method survives the same hammering.
"""

from __future__ import annotations

import sys
import threading
import unittest

from bridge import Bridge
from models import DeviceConfig

ADDRESSES_PER_WORKER = 5000
INSERT_THREADS = 4

# The race this guards against depends on a thread switch landing inside a
# dict resize -- rare at the default 5ms switch interval, reliable at this
# one. Restored in tearDown so it does not leak into unrelated tests.
_RACE_FRIENDLY_SWITCH_INTERVAL = 0.00001


def _bare_bridge() -> Bridge:
    bridge = object.__new__(Bridge)
    bridge.devices = {}
    bridge._devices_lock = threading.RLock()
    return bridge


def _hammer(bridge: Bridge, prefix: str, errors: list[Exception]) -> None:
    for i in range(ADDRESSES_PER_WORKER):
        try:
            bridge._device_config(f"{prefix}{i}")
        except Exception as exc:  # noqa: BLE001 -- captured for the assertion, not swallowed
            errors.append(exc)


def _snapshot_and_iterate(bridge: Bridge, iterations: int, errors: list[Exception]) -> None:
    for _ in range(iterations):
        try:
            for device in bridge._devices_snapshot().values():
                str(device.address)  # touch every entry, as real callers do
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)


class DevicesThreadSafetyTests(unittest.TestCase):
    def setUp(self):
        self._original_switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(_RACE_FRIENDLY_SWITCH_INTERVAL)
        self.addCleanup(sys.setswitchinterval, self._original_switch_interval)

    def test_device_config_and_snapshot_survive_concurrent_access(self):
        bridge = _bare_bridge()
        errors: list[Exception] = []

        inserters = [
            threading.Thread(
                target=_hammer, args=(bridge, f"W{worker}-", errors)
            )
            for worker in range(INSERT_THREADS)
        ]
        reader = threading.Thread(
            target=_snapshot_and_iterate,
            args=(bridge, ADDRESSES_PER_WORKER * INSERT_THREADS, errors),
        )

        reader.start()
        for t in inserters:
            t.start()
        for t in inserters:
            t.join()
        reader.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(bridge.devices), ADDRESSES_PER_WORKER * INSERT_THREADS)

    def test_concurrent_inserts_of_the_same_address_return_one_device(self):
        # _device_config's get-or-create was a check-then-act race even
        # before this fix: two threads could both see a KeyError for the same
        # new address and both construct+insert a DeviceConfig, wasting one.
        # Locking the whole method also closes that -- verify every thread
        # gets back the identical object for the same address.
        bridge = _bare_bridge()
        results: list[DeviceConfig] = []
        lock = threading.Lock()

        def resolve():
            device = bridge._device_config("A1")
            with lock:
                results.append(device)

        threads = [threading.Thread(target=resolve) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 16)
        self.assertTrue(all(d is results[0] for d in results))

    def test_race_is_real_without_the_lock(self):
        # Control case: the same hammering against a deliberately unlocked
        # stand-in reliably raises RuntimeError. If this stops failing, the
        # test above may be passing for the wrong reason (too little
        # contention to hit the race at all).
        class UnlockedStandIn:
            def __init__(self):
                self.devices: dict[str, DeviceConfig] = {}

            def _device_config(self, address):
                try:
                    return self.devices[address]
                except KeyError:
                    device = DeviceConfig(address=address, name=address)
                    self.devices[address] = device
                    return device

            def _devices_snapshot(self):
                return self.devices  # no lock, no copy -- the live dict itself

        stand_in = UnlockedStandIn()
        errors: list[Exception] = []

        inserters = [
            threading.Thread(target=_hammer, args=(stand_in, f"W{w}-", errors))
            for w in range(INSERT_THREADS)
        ]
        reader = threading.Thread(
            target=_snapshot_and_iterate,
            args=(stand_in, ADDRESSES_PER_WORKER * INSERT_THREADS, errors),
        )

        reader.start()
        for t in inserters:
            t.start()
        for t in inserters:
            t.join()
        reader.join()

        self.assertTrue(
            any(isinstance(e, RuntimeError) for e in errors),
            "expected the unlocked stand-in to raise RuntimeError from a "
            "dict resizing during iteration; if it did not, this run had "
            "too little contention to prove the control case",
        )


if __name__ == "__main__":
    unittest.main()
