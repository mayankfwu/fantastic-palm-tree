"""Generate illustrative debris trajectories with staged orbital contacts."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random

import numpy as np

from .propagation import propagate

MAX_SIMULATED_DEBRIS = 15


@dataclass(frozen=True)
class SimulatedDebris:
    """A staged UTC contact, orbital-plane angle in radians, and speed multiplier."""

    satellite_index: int
    contact_time: datetime
    angle_rad: float
    speed_factor: float


def place_simulated_debris(count: int, satellite_count: int, start: datetime, seed: int) -> tuple[SimulatedDebris, ...]:
    """Choose random orbital planes and UTC contacts 12–35 minutes from start."""
    if not 0 <= count <= MAX_SIMULATED_DEBRIS or (count and satellite_count < 1):
        raise ValueError("Choose up to 15 simulated debris objects and at least one satellite")
    random = Random(seed)
    return tuple(
        SimulatedDebris(
            random.randrange(satellite_count), start + timedelta(seconds=random.randint(720, 2100)),
            random.uniform(-np.pi / 3, np.pi / 3), random.uniform(1.005, 1.045),
        )
        for _ in range(count)
    )


def simulated_positions(item: SimulatedDebris, satellite, times: list[datetime]) -> np.ndarray:
    """Sample an independent two-body orbit in TEME km through the UTC contact."""
    positions, velocities = propagate(satellite, [item.contact_time])
    contact, velocity = positions[0], velocities[0]
    if not np.isfinite(contact).all() or not np.isfinite(velocity).all():
        return np.full((len(times), 3), np.nan)
    radius = np.linalg.norm(contact)
    radial = contact / radius
    tangent = -(velocity - (velocity @ radial) * radial)
    tangent /= np.linalg.norm(tangent)
    tangent = tangent * np.cos(item.angle_rad) + np.cross(radial, tangent) * np.sin(item.angle_rad)

    # Give the debris its own speed at periapsis. The bound ellipse passes
    # through the staged contact and stays at or above its radius elsewhere.
    eccentricity = item.speed_factor ** 2 - 1
    axis_km = radius / (1 - eccentricity)
    elapsed = np.array([(moment - item.contact_time).total_seconds() for moment in times])
    mean_anomaly = elapsed * np.sqrt(satellite.mu / axis_km ** 3)
    eccentric_anomaly = mean_anomaly.copy()
    for _ in range(5):
        eccentric_anomaly -= (
            (eccentric_anomaly - eccentricity * np.sin(eccentric_anomaly) - mean_anomaly)
            / (1 - eccentricity * np.cos(eccentric_anomaly))
        )
    x = axis_km * (np.cos(eccentric_anomaly) - eccentricity)
    y = axis_km * np.sqrt(1 - eccentricity ** 2) * np.sin(eccentric_anomaly)
    return x[:, None] * radial + y[:, None] * tangent
