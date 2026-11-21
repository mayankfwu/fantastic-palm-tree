"""Shared simulator data types."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Conjunction:
    """Encounter with a UTC TCA, miss in km, and relative speed in km/s."""

    primary_id: int
    secondary_id: int
    tca: datetime
    miss_km: float
    rel_speed_kms: float


@dataclass
class Maneuver:
    """UTC burn time, signed along-track delta-v in m/s, and new miss in km."""

    burn_time: datetime
    dv_mps: float
    new_miss_km: float
