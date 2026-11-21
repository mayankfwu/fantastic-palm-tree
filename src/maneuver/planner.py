"""Simplified along-track collision avoidance maneuver planner."""

from datetime import datetime
import math

from src.contracts import Conjunction, Maneuver


THRESHOLD_KM = 5.0


def plan_maneuver(
    primary,
    conjunction: Conjunction,
    threshold_km: float = THRESHOLD_KM
) -> Maneuver:
    """
    Estimate an avoidance maneuver using a simplified linear model.

    This is a demonstration approximation, not an operational
    orbital maneuver calculation.
    """

    if threshold_km <= 0:
        raise ValueError("Safety threshold must be positive.")

    miss_km = conjunction.miss_km

    if miss_km < 0:
        raise ValueError("Miss distance cannot be negative.")

    now = datetime.now(conjunction.tca.tzinfo)
    time_to_tca = (conjunction.tca - now).total_seconds()

    if time_to_tca <= 0:
        raise ValueError("TCA must be in the future.")

    if miss_km >= threshold_km:
        return Maneuver(
            burn_time=now,
            dv_mps=0.0,
            new_miss_km=miss_km
        )

    required_shift_km = math.sqrt(
        threshold_km**2 - miss_km**2
    )

    dv_mps = (required_shift_km / time_to_tca) * 1000

    return Maneuver(
        burn_time=now,
        dv_mps=dv_mps,
        new_miss_km=threshold_km
    )