"""Approximate a finite along-track burn and a smooth orbital recovery."""

from datetime import datetime, timedelta

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import minimize_scalar

from .propagation import propagate

BURN_DURATION_S = 60
RECOVERY_DURATION_S = 1800


def after_along_track_burn(
    satellite, burn_time: datetime, end: datetime, dv_mps: float, *, recovery_time: datetime,
):
    """Sample TEME km after a finite signed Δv in m/s and a controlled UTC return."""
    seconds = (end - burn_time).total_seconds()
    recovery_start = (recovery_time - burn_time).total_seconds()
    if seconds <= 0 or not np.isfinite(dv_mps):
        raise ValueError("The burn must precede the end of propagation and have finite Δv")
    if recovery_start < BURN_DURATION_S:
        raise ValueError("Recovery must start after the avoidance burn")
    position, velocity = propagate(satellite, [burn_time])
    if not np.isfinite(position).all() or not np.isfinite(velocity).all():
        raise ValueError("The satellite has no valid state at the burn time")

    baseline = np.concatenate((position[0], velocity[0]))
    direction = velocity[0] / np.linalg.norm(velocity[0])
    peak_scale = (dv_mps / 1000) / BURN_DURATION_S

    def derivatives(elapsed, states):
        """Return km/s and km/s² for nominal and impulsed two-body states."""
        pairs = states.reshape(2, 6)
        positions = pairs[:, :3]
        radii = np.linalg.norm(positions, axis=1)
        accelerations = -satellite.mu * positions / radii[:, None] ** 3
        if 0 < elapsed < BURN_DURATION_S:
            # A raised cosine starts and ends at zero thrust and integrates to Δv.
            phase = 2 * np.pi * elapsed / BURN_DURATION_S
            accelerations[1] += peak_scale * (1 - np.cos(phase)) * direction
        return np.column_stack((pairs[:, 3:], accelerations)).ravel()

    solution = solve_ivp(
        derivatives, (0, min(seconds, recovery_start)), np.tile(baseline, 2),
        method="DOP853", rtol=1e-10, atol=1e-10, dense_output=True, max_step=30,
    )
    if not solution.success:
        raise ValueError("Could not propagate the finite avoidance burn")

    if recovery_start <= seconds:
        state = solution.y[:, -1].reshape(2, 6)
        acceleration = derivatives(recovery_start, state.ravel()).reshape(2, 6)[:, 3:]
        displacement = state[1, :3] - state[0, :3]
        relative_velocity = state[1, 3:] - state[0, 3:]
        relative_acceleration = acceleration[1] - acceleration[0]

    def sample(times: list[datetime]) -> np.ndarray:
        """Return nominal SGP4 plus the burn-induced position change in TEME km."""
        nominal, _ = propagate(satellite, times)
        elapsed = np.array([(moment - burn_time).total_seconds() for moment in times])
        if np.any(elapsed > seconds):
            raise ValueError("Cannot sample past the burn propagation window")
        coast = (elapsed >= 0) & (elapsed < recovery_start)
        if np.any(coast):
            states = solution.sol(elapsed[coast])
            nominal[coast] += (states[6:9] - states[:3]).T
        recovering = (elapsed >= recovery_start) & (elapsed < recovery_start + RECOVERY_DURATION_S)
        if np.any(recovering):
            # Match displacement, velocity, and acceleration at recovery start.
            # All three offsets reach zero at rejoin under this guidance profile.
            u = ((elapsed[recovering] - recovery_start) / RECOVERY_DURATION_S)[:, None]
            remaining = 1 - u
            nominal[recovering] += remaining ** 3 * (
                (1 + 3 * u + 6 * u ** 2) * displacement
                + RECOVERY_DURATION_S * (u + 3 * u ** 2) * relative_velocity
                + 0.5 * RECOVERY_DURATION_S ** 2 * u ** 2 * relative_acceleration
            )
        return nominal

    return sample


def preview_along_track_encounter(primary, debris, tca: datetime, dv_mps: float, *, earliest_burn=None, simulate_impact=False):
    """Compute TEME paths and refine the post-burn miss in km near the UTC TCA."""
    burn_time = tca - timedelta(minutes=20)
    if earliest_burn is not None:
        burn_time = max(burn_time, earliest_burn)
    if burn_time >= tca:
        raise ValueError("The encounter must occur after the simulation start")
    recovery_time = tca + timedelta(minutes=5)
    altered_positions = after_along_track_burn(
        primary, burn_time, tca + timedelta(minutes=50), dv_mps, recovery_time=recovery_time,
    )
    shift = np.zeros(3)
    if simulate_impact:
        shift = propagate(primary, [tca])[0][0] - propagate(debris, [tca])[0][0]

    def paths(offsets_s):
        """Return nominal, burned, and debris positions in TEME km."""
        times = [tca + timedelta(seconds=float(offset)) for offset in offsets_s]
        nominal, _ = propagate(primary, times)
        debris_path, _ = propagate(debris, times)
        return nominal, altered_positions(times), debris_path + shift

    offsets = np.linspace(-120, 120, 241)
    nominal, altered, debris_path = paths(offsets)
    if not all(np.isfinite(state).all() for state in (nominal, altered, debris_path)):
        raise ValueError("The orbital model returned an invalid state near closest approach")
    original = np.linalg.norm(nominal - debris_path, axis=1)
    changed = np.linalg.norm(altered - debris_path, axis=1)
    nearest = int(np.argmin(changed))
    new_offset, new_miss = offsets[nearest], changed[nearest]
    if 0 < nearest < len(offsets) - 1:
        def miss(offset):
            """Measure TEME separation in km at the given offset in seconds."""
            _, altered_path, debris_path = paths([offset])
            return float(np.linalg.norm(altered_path[0] - debris_path[0]))

        result = minimize_scalar(miss, method="bounded", bounds=(offsets[nearest - 1], offsets[nearest + 1]))
        if result.success and result.fun < new_miss:
            new_offset, new_miss = result.x, result.fun
    return paths, offsets, original, changed, float(new_offset), float(new_miss), burn_time, recovery_time
