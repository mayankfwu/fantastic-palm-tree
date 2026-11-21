"""Stream rolling propagation blocks to the interactive orbit canvas."""

from datetime import timedelta
from functools import partial
from pathlib import Path

import numpy as np
import streamlit as st
from scipy.optimize import minimize_scalar

from src.orbits import find_conjunctions, propagate
from src.orbits.impulse import BURN_DURATION_S, RECOVERY_DURATION_S, after_along_track_burn
from src.orbits.simulation import simulated_positions

from .encounter import CONTACT_KM, EARTH_RADIUS_KM

WINDOW_S = 6000
CLOSE_PASS_KM = 5.0


def _closest_near(predicted_time, primary_path, secondary_path):
    """Return the refined UTC time and miss in km within two minutes of a candidate."""
    def separations(offsets):
        """Measure separations in TEME km at the requested offsets in seconds."""
        times = [predicted_time + timedelta(seconds=float(offset)) for offset in offsets]
        distances = np.linalg.norm(primary_path(times) - secondary_path(times), axis=1)
        return np.where(np.isfinite(distances), distances, np.inf)

    samples = np.arange(-120, 121, 5)
    distances = separations(samples)
    index = int(np.argmin(distances))
    offset, distance = samples[index], distances[index]
    if 0 < index < len(samples) - 1 and np.isfinite(distance):
        best = minimize_scalar(
            lambda value: separations([value])[0],
            bounds=(samples[index - 1], samples[index + 1]), method="bounded",
        )
        if best.success and best.fun < distance:
            offset, distance = best.x, best.fun
    return predicted_time + timedelta(seconds=float(offset)), distance


def orbit_window(satellites, debris, start, sequence, *, show_timeline=True, simulated=(), avoid_simulated=False) -> dict:
    """Build a 100-minute block of TEME km positions and check for contact."""
    first_s = sequence * WINDOW_S
    first_time = start + timedelta(seconds=first_s)
    end = first_time + timedelta(seconds=WINDOW_S)
    offsets_s = list(range(first_s, first_s + WINDOW_S + 1, 60))
    debris_models = [model for _, model in debris]
    catalog_encounters = [
        event
        for _, primary in satellites
        for event in find_conjunctions(primary, debris_models, first_time, WINDOW_S / 3600, screen_km=CLOSE_PASS_KM)
    ] if debris_models else []
    staged = [
        item for item in sorted(simulated, key=lambda item: item.contact_time)
        if np.isfinite(propagate(satellites[item.satellite_index][1], [item.contact_time])[0]).all()
    ]
    burned = {}
    burn_times = {}
    maneuver_phases = {}
    focus_offsets = set()
    if avoid_simulated:
        last_contacts = {item.satellite_index: item.contact_time for item in staged}
        for item in staged:
            index = item.satellite_index
            if index not in burned:
                burn_time = max(start, item.contact_time - timedelta(minutes=10))
                recovery_time = last_contacts[index] + timedelta(minutes=5)
                try:
                    burned[index] = after_along_track_burn(
                        satellites[index][1], burn_time, end + timedelta(minutes=2), 10.0,
                        recovery_time=recovery_time,
                    )
                except ValueError:
                    continue
                burn_times[index] = burn_time
                burn_s = (burn_time - start).total_seconds()
                recovery_s = (recovery_time - start).total_seconds()
                maneuver_phases[index] = [burn_s, burn_s + BURN_DURATION_S, recovery_s, recovery_s + RECOVERY_DURATION_S]
                focus_offsets.update(
                    burn_s + delta for delta in range(0, BURN_DURATION_S + 1, 10)
                    if first_s <= burn_s + delta <= first_s + WINDOW_S
                )
                focus_offsets.update(
                    offset for offset in (recovery_s, recovery_s + RECOVERY_DURATION_S)
                    if first_s <= offset <= first_s + WINDOW_S
                )
    indices = {model.satnum: index for index, (_, model) in enumerate(satellites)}
    debris_by_id = {model.satnum: model for model in debris_models}
    contacts = []
    encounter_times = set()
    avoided_passes = []
    for event in catalog_encounters:
        index = indices[event.primary_id]
        moment, miss = event.tca, event.miss_km
        if index in burned and moment >= burn_times[index]:
            moment, miss = _closest_near(
                moment, burned[index], lambda times: propagate(debris_by_id[event.secondary_id], times)[0],
            )
        if first_time <= moment <= end:
            if miss <= CLOSE_PASS_KM or event.miss_km <= CONTACT_KM:
                encounter_times.add((moment - start).total_seconds())
            if miss <= CONTACT_KM:
                contacts.append((moment, index, "predicted"))
    for item in staged:
        index = item.satellite_index
        if first_time <= item.contact_time <= end:
            moment, miss = item.contact_time, 0.0
            if index in burned:
                moment, miss = _closest_near(
                    moment, burned[index], partial(simulated_positions, item, satellites[index][1]),
                )
            if first_time <= moment <= end:
                offset = (moment - start).total_seconds()
                encounter_times.add(offset)
                if miss <= CONTACT_KM:
                    contacts.append((moment, index, "simulated"))
                elif index in burned and np.isfinite(miss):
                    avoided_passes.append({
                        "time": offset, "primary": index,
                        "debris": len(satellites) + len(debris) + simulated.index(item),
                        "missKm": miss,
                    })
    contact_time, primary_index, impact_kind = min(contacts, default=(None, None, None))
    focus_offsets.update(
        moment + delta for moment in encounter_times for delta in range(-12, 13)
        if first_s <= moment + delta <= first_s + WINDOW_S
    )
    offsets_s = sorted(set(offsets_s) | focus_offsets)
    if contact_time is not None:
        contact_s = (contact_time - start).total_seconds()
        offsets_s = [offset for offset in offsets_s if offset < contact_s] + [contact_s]
    times = [start + timedelta(seconds=offset) for offset in offsets_s]
    objects = [*satellites, *debris]
    nominal_paths = {index: propagate(satellites[index][1], times)[0] for index in burned}
    paths = [
        burned[index](times) if index in burned else propagate(model, times)[0]
        for index, (_, model) in enumerate(objects)
    ]
    paths.extend(simulated_positions(item, satellites[item.satellite_index][1], times) for item in simulated)
    return {
        "labels": [name for name, _ in objects] + [f"Simulated debris {i + 1}" for i in range(len(simulated))],
        "satelliteCount": len(satellites),
        "simulatedCount": len(simulated),
        "burnOffsetS": (min(burn_times.values()) - start).total_seconds() if burn_times else None,
        "maneuverPhases": maneuver_phases,
        "frameIntervalMs": 220 if simulated else 65,
        "clockStepS": 60,
        "encounterTimes": sorted(encounter_times),
        "avoidedPasses": avoided_passes,
        "earthRadiusKm": EARTH_RADIUS_KM,
        "live": True,
        "continuous": True,
        "showTimeline": show_timeline,
        "sequence": sequence,
        "frames": [
            {
                "time": offset,
                "positions": [
                    path[index].round(3).tolist() if np.isfinite(path[index]).all() else None
                    for path in paths
                ],
                "impact": contact_time is not None and index == len(offsets_s) - 1,
                "impactObject": primary_index,
                **({"nominalPositions": {
                    object_index: path[index].round(3).tolist()
                    for object_index, path in nominal_paths.items() if np.isfinite(path[index]).all()
                }} if nominal_paths else {}),
                **({"impactKind": impact_kind} if contact_time is not None and index == len(offsets_s) - 1 else {}),
            }
            for index, offset in enumerate(offsets_s)
        ],
    }


@st.cache_resource
def _scene_component():
    """Register the offline-capable scene component with no physical units."""
    script = Path(__file__).with_name("playback.js").read_text()
    return st.components.v2.component("orbitguard_rolling_scene", js=script)


@st.fragment
def render_continuous_orbit(satellites, debris, start, key, *, show_timeline=True, simulated=()):
    """Serve succeeding blocks in TEME km from a fixed UTC playback start."""
    state_key = "rolling_orbit_window"
    player_key = f"{key}-orbit-player"
    avoid_simulated = st.session_state.get("avoid_simulated_scene") == key
    if st.session_state.get(state_key, (None,))[0] != key:
        st.session_state[state_key] = key, orbit_window(
            satellites, debris, start, 0, show_timeline=show_timeline, simulated=simulated,
            avoid_simulated=avoid_simulated,
        )
    _, packet = st.session_state[state_key]

    def load_next():
        """Advance the requested unitless window sequence by one."""
        active_key, current = st.session_state[state_key]
        requested = st.session_state[player_key].get("advance")
        if active_key == key and requested == current["sequence"] + 1 and not current["frames"][-1]["impact"]:
            st.session_state[state_key] = key, orbit_window(
                satellites, debris, start, requested, show_timeline=show_timeline, simulated=simulated,
                avoid_simulated=avoid_simulated,
            )

    data = {
        "packet": packet,
        "template": Path(__file__).with_name("orbit_scene.html").read_text(),
    }
    _scene_component()(key=player_key, data=data, height=500, on_advance_change=load_next)
