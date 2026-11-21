"""Screen one satellite against a catalog of SGP4 objects."""

from datetime import datetime, timedelta
from math import isfinite

import numpy as np
from scipy.optimize import minimize_scalar

from src.contracts import Conjunction

from .propagation import _julian_parts, _propagate_julian


def _radial_range(sat) -> tuple[float, float]:
    """Estimate the orbit's radial bounds in km from the SGP4 mean elements."""
    axis_km = sat.a * sat.radiusearthkm
    # Mean elements omit short-period radial variations. Pad both bounds.
    padding_km = max(25.0, 0.01 * axis_km)
    return (
        axis_km * (1 - sat.ecco) - padding_km,
        axis_km * (1 + sat.ecco) + padding_km,
    )


def find_conjunctions(
    primary, catalog: list, start: datetime, hours: float,
    step_s: float = 60.0, screen_km: float = 50.0,
) -> list[Conjunction]:
    """Rank encounters by miss in km over a UTC window in hours, sampled in seconds."""
    if not all(isfinite(value) and value > 0 for value in (hours, step_s, screen_km)):
        raise ValueError("hours, step_s and screen_km must be finite and positive")
    start_jd, start_fraction = _julian_parts(start)
    end_s = hours * 3600
    offsets = np.append(np.arange(0, end_s, step_s), end_s)
    fractions = start_fraction + offsets / 86400
    whole_days = np.floor(fractions)
    dates = start_jd + whole_days
    fractions -= whole_days
    primary_positions, primary_velocities = _propagate_julian(primary, dates, fractions)
    primary_low, primary_high = _radial_range(primary)
    results = []
    seen = {primary.satnum}

    for secondary in catalog:
        if secondary.satnum in seen:
            continue
        seen.add(secondary.satnum)
        low, high = _radial_range(secondary)
        if low > primary_high + screen_km or primary_low > high + screen_km:
            continue

        positions, velocities = _propagate_julian(secondary, dates, fractions)
        distances = np.linalg.norm(positions - primary_positions, axis=1)
        valid = np.isfinite(distances)
        # Two independent TEME speeds give a conservative coarse allowance
        # for a fast encounter halfway between neighboring samples.
        speed_bound = np.linalg.norm(velocities, axis=1) + np.linalg.norm(primary_velocities, axis=1)
        coarse_limit = np.maximum(200.0, screen_km + speed_bound * step_s / 2)
        before = np.r_[np.inf, np.where(valid[:-1], distances[:-1], np.inf)]
        after = np.r_[np.where(valid[1:], distances[1:], np.inf), np.inf]
        minima = (distances < before) & (distances <= after)
        for index in np.flatnonzero(valid & minima & (distances <= coarse_limit)):
            left = offsets[index - 1] if index > 0 and valid[index - 1] else offsets[index]
            right = (
                offsets[index + 1] if index + 1 < len(offsets) and valid[index + 1]
                else offsets[index]
            )
            encounter = _refine(
                primary, secondary, start, start_jd, start_fraction,
                left, offsets[index], right, screen_km,
            )
            if encounter is not None:
                results.append(encounter)

    return sorted(results, key=lambda item: (item.miss_km, item.tca, item.secondary_id))


def _relative_state(primary, secondary, jd, fraction):
    """Return relative TEME position in km and velocity in km/s, or None."""
    error1, position1, velocity1 = primary.sgp4(jd, fraction)
    error2, position2, velocity2 = secondary.sgp4(jd, fraction)
    if error1 or error2:
        return None
    return np.subtract(position2, position1), np.subtract(velocity2, velocity1)


def _refine(primary, secondary, start, jd, fraction, left, sample, right, screen_km):
    """Refine a bracket in seconds and report UTC TCA, km and km/s."""
    def distance_squared(offset):
        """Return squared TEME separation in km² at offset seconds."""
        state = _relative_state(primary, secondary, jd, fraction + offset / 86400)
        if state is None:
            return np.inf
        return float(state[0] @ state[0])

    candidates = [left, sample, right]
    if right > left:
        optimum = minimize_scalar(
            distance_squared, bounds=(left, right), method="bounded", options={"xatol": 0.001},
        )
        if optimum.success:
            candidates.append(optimum.x)
    offset = min(candidates, key=distance_squared)
    miss_squared = distance_squared(offset)
    if not miss_squared < screen_km ** 2:
        return None
    _, relative_velocity = _relative_state(primary, secondary, jd, fraction + offset / 86400)
    return Conjunction(
        primary.satnum, secondary.satnum, start + timedelta(seconds=float(offset)),
        miss_squared ** 0.5, float(np.linalg.norm(relative_velocity)),
    )
