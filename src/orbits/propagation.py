"""Vectorized propagation of SGP4 elements."""

import warnings
from datetime import datetime, timedelta

import numpy as np
from sgp4.api import jday


def propagate(sat, times: list[datetime]):
    """Return TEME positions in km and velocities in km/s for UTC datetimes."""
    if not times:
        return np.empty((0, 3)), np.empty((0, 3))
    dates, fractions = np.array([_julian_parts(moment) for moment in times]).T.copy()
    return _propagate_julian(sat, dates, fractions)


def _propagate_julian(sat, dates, fractions):
    """Propagate split Julian days to TEME km and km/s."""
    epoch_age = (dates - sat.jdsatepoch) + (fractions - sat.jdsatepochF)
    if np.any(np.abs(epoch_age) > 3):
        warnings.warn("Requested propagation is over three days from the SGP4 epoch", stacklevel=2)
    errors, positions, velocities = sat.sgp4_array(dates, fractions)
    invalid = (errors != 0) | ~np.isfinite(positions).all(axis=1) | ~np.isfinite(velocities).all(axis=1)
    positions[invalid] = np.nan
    velocities[invalid] = np.nan
    return positions, velocities


def _julian_parts(moment: datetime) -> tuple[float, float]:
    """Convert a timezone-aware UTC datetime to split Julian days."""
    if moment.utcoffset() != timedelta(0):
        raise ValueError("Propagation times must be timezone-aware UTC datetimes")
    return jday(
        moment.year, moment.month, moment.day, moment.hour, moment.minute,
        moment.second + moment.microsecond / 1_000_000,
    )
