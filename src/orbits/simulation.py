"""Generate illustrative debris trajectories with staged orbital contacts."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random

import numpy as np

from .propagation import propagate

MAX_SIMULATED_DEBRIS = 15


@dataclass(frozen=True)
class SimulatedDebris:
    """A staged contact with a satellite at a UTC instant and rotation in radians."""

    satellite_index: int
    contact_time: datetime
    angle_rad: float


def place_simulated_debris(count: int, satellite_count: int, start: datetime, seed: int) -> tuple[SimulatedDebris, ...]:
    """Choose random orbital planes and UTC contacts 12–35 minutes from start."""
    if not 0 <= count <= MAX_SIMULATED_DEBRIS or (count and satellite_count < 1):
        raise ValueError("Choose up to 15 simulated debris objects and at least one satellite")
    random = Random(seed)
    return tuple(
        SimulatedDebris(
            random.randrange(satellite_count), start + timedelta(seconds=random.randint(720, 2100)),
            random.uniform(-np.pi / 3, np.pi / 3),
        )
        for _ in range(count)
    )


def simulated_positions(item: SimulatedDebris, satellite, times: list[datetime]) -> np.ndarray:
    """Return an illustrative retrograde path in TEME km through the UTC contact point."""
    # Match the satellite's position at contact and rotate the reversed path
    # around the radial line through that point. This preserves its altitude.
    reflected_times = [item.contact_time - (moment - item.contact_time) for moment in times]
    positions, _ = propagate(satellite, [item.contact_time, *reflected_times])
    contact, paths = positions[0], positions[1:]
    if not np.isfinite(contact).all():
        return np.full_like(paths, np.nan)
    axis = contact / np.linalg.norm(contact)
    cosine = np.cos(item.angle_rad)
    return (
        paths * cosine + np.cross(axis, paths) * np.sin(item.angle_rad)
        + np.outer(paths @ axis, axis) * (1 - cosine)
    )
