"""Regression tests for the rolling player and its closest-pass refinement."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from src.viz.rolling_scene import _closest_near


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
