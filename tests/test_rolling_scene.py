"""Regression tests for the rolling player and its closest-pass refinement."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from src.viz.rolling_scene import _closest_near
from src.orbits.demo import load_offline_catalogs
from src.orbits.simulation import SimulatedDebris
from src.viz import rolling_scene


def test_player_resumes_once_after_a_delayed_window():
    """Verify the JS playback clock using simulated seconds and wall-clock milliseconds."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to exercise the JavaScript player")
    subprocess.run([node, "--test", Path(__file__).with_name("orbit_playback.test.mjs")], check=True)


def test_closest_near_batches_samples_and_refines_through_missing_states():
    """Find a 3 km miss between samples 5 seconds apart despite an invalid TEME state."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    batch_sizes = []

    def primary(times):
        """Return the stationary origin in TEME km."""
        return np.zeros((len(times), 3))

    def debris(times):
        """Cross the primary at a 3 km offset with a 1 km/s relative speed."""
        batch_sizes.append(len(times))
        seconds = np.array([(time - start).total_seconds() for time in times])
        trajectory = np.column_stack((seconds - 7.25, np.full(len(times), 3), np.zeros(len(times))))
        trajectory[seconds == 0] = np.nan
        return trajectory

    moment, miss = _closest_near(start, primary, debris)
    assert batch_sizes[0] == 49
    assert abs(moment - (start + timedelta(seconds=7.25))) < timedelta(milliseconds=1)
    assert miss == pytest.approx(3.0)


def test_staged_burn_targets_all_passes_across_windows(monkeypatch):
    """Keep a single finite burn and at least 5 km separation across two playback blocks."""
    start, satellites, _ = load_offline_catalogs()
    staged = (
        SimulatedDebris(0, start + timedelta(minutes=12), 0.0, 1.02),
        SimulatedDebris(0, start + timedelta(minutes=24), 0.1, 1.02),
    )
    monkeypatch.setattr(rolling_scene, "WINDOW_S", 1200)
    first, second = [
        rolling_scene.orbit_window(satellites[:1], [], start, seq, simulated=staged, avoid_simulated=True)
        for seq in (0, 1)
    ]
    assert first["frames"][-1] == second["frames"][0]
    assert first["maneuverPhases"] == second["maneuverPhases"]
    for packet, debris_index in ((first, 1), (second, 2)):
        event, = packet["maneuverPasses"]
        assert event["dvMps"] == 20
        assert event["debris"] == debris_index
        assert event["missKm"] >= packet["safeMissKm"] == 5
        frame = next(frame for frame in packet["frames"] if frame["time"] == event["time"])
        primary, debris = frame["positions"][0], frame["positions"][debris_index]
        assert np.linalg.norm(np.subtract(primary, debris)) == pytest.approx(event["missKm"], abs=0.002)


def test_short_lead_can_miss_clearance_without_physical_contact():
    """Report a real sub-5 km shortfall even at the strongest allowed 20 m/s burn."""
    start, satellites, _ = load_offline_catalogs()
    staged = (SimulatedDebris(0, start + timedelta(minutes=3), 0.0, 1.02),)
    packet = rolling_scene.orbit_window(satellites[:1], [], start, 0, simulated=staged, avoid_simulated=True)
    event, = packet["maneuverPasses"]
    assert event["dvMps"] == 20
    assert 0.01 < event["missKm"] < 5
    assert not any(frame["impact"] for frame in packet["frames"])


def test_short_lead_physical_contact_still_stops_playback():
    """Stop on a miss of at most 10 m when the staged encounter is only 30 s away."""
    start, satellites, _ = load_offline_catalogs()
    staged = (SimulatedDebris(0, start + timedelta(seconds=30), 0.0, 1.02),)
    packet = rolling_scene.orbit_window(satellites[:1], [], start, 0, simulated=staged, avoid_simulated=True)
    assert not packet["maneuverPasses"]
    assert packet["frames"][-1]["impactKind"] == "simulated"
