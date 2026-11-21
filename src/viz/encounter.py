"""Plot TEME trajectories and separation around a selected encounter."""

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import plotly.graph_objects as go

from src.contracts import Conjunction
from src.orbits import propagate
from src.orbits.impulse import BURN_DURATION_S, RECOVERY_DURATION_S, preview_along_track_encounter

PRIMARY_COLOR = "#62daf4"
DEBRIS_COLOR = "#ffbb70"
EARTH_RADIUS_KM = 6378.137
CONTACT_KM = 0.01


def _sample_positions(primary, secondary, encounter, offsets_s, simulate_impact):
    """Return simultaneous TEME positions in km around the UTC encounter."""
    times = [encounter.tca + timedelta(seconds=float(offset)) for offset in offsets_s]
    primary_positions, _ = propagate(primary, times)
    secondary_positions, _ = propagate(secondary, times)
    if simulate_impact:
        center = len(times) // 2
        # Shift only the illustrative trajectory so both centers meet at TCA.
        secondary_positions -= secondary_positions[center] - primary_positions[center]
    return primary_positions, secondary_positions


def separation_figure(primary, secondary, encounter: Conjunction, screen_km: float, *, simulate_impact=False) -> go.Figure:
    """Plot separation in km against seconds near closest approach."""
    offsets_s = np.linspace(-2, 2, 161)
    primary_path, secondary_path = _sample_positions(primary, secondary, encounter, offsets_s, simulate_impact)
    distances = np.linalg.norm(primary_path - secondary_path, axis=1)
    center = len(offsets_s) // 2
    if simulate_impact:
        offsets_s = offsets_s[:center + 1]
        distances = distances[:center + 1]

    figure = go.Figure()
    figure.add_scatter(
        x=offsets_s.tolist(), y=distances.tolist(), mode="lines", name="Separation",
        line=dict(color=PRIMARY_COLOR, width=3),
        hovertemplate="%{x:+.2f} s · %{y:.3f} km<extra></extra>",
    )
    figure.add_hline(
        y=screen_km, line_dash="dot", line_color="#c8d6e4",
        annotation_text=f"{screen_km:g} km screen", annotation_position="top right",
    )
    figure.add_scatter(
        x=[0], y=[float(distances[center])],
        name="Simulated impact" if simulate_impact else "Closest approach", mode="markers",
        marker=dict(color="#ff5757" if simulate_impact else DEBRIS_COLOR, size=11),
        hovertemplate="At TCA · %{y:.3f} km<extra></extra>",
    )
    figure.update_layout(
        template="plotly_dark", height=475, margin=dict(l=48, r=20, b=58, t=30),
        xaxis_title="Time from closest approach (s)", yaxis_title="Separation (km)",
        showlegend=False,
    )
    figure.update_yaxes(rangemode="tozero")
    return figure


def orbit_html(primary, secondary, encounter: Conjunction, primary_name: str, *, simulate_impact=False) -> str:
    """Render the full Earth-centered orbits in TEME km around UTC TCA."""
    offsets_s = np.union1d(np.arange(-3000, 3001, 60), np.arange(-12, 13))
    primary_path, debris_path = _sample_positions(primary, secondary, encounter, offsets_s, simulate_impact)
    return _scene_html(
        offsets_s, primary_path, debris_path, primary_name, encounter.secondary_id,
        simulate_impact, earth_radius_km=EARTH_RADIUS_KM,
    )


def close_up_html(
    primary, secondary, encounter: Conjunction, primary_name: str,
    *, simulate_impact=False,
) -> str:
    """Render both paths and their separation in km around UTC TCA."""
    offsets_s = np.linspace(-1.5, 1.5, 61)
    primary_path, debris_path = _sample_positions(primary, secondary, encounter, offsets_s, simulate_impact)
    center = len(offsets_s) // 2
    # Choose a camera-friendly basis using the unmodified relative velocity.
    relative_step = (debris_path[center + 1] - primary_path[center + 1]) - (
        debris_path[center - 1] - primary_path[center - 1]
    )
    step_length = np.linalg.norm(relative_step)
    # Co-orbiting objects can have no relative motion to orient the camera.
    along = relative_step / step_length if step_length > 1e-12 else np.array([1.0, 0.0, 0.0])
    miss = debris_path[center] - primary_path[center]
    across = miss - (miss @ along) * along
    if np.linalg.norm(across) < 1e-9:
        across = np.cross(along, np.eye(3)[np.argmin(np.abs(along))])
    across /= np.linalg.norm(across)
    basis = np.column_stack((along, across, np.cross(along, across)))
    origin = (primary_path[center] + debris_path[center]) / 2
    primary_path = (primary_path - origin) @ basis
    debris_path = (debris_path - origin) @ basis
    return _scene_html(
        offsets_s, primary_path, debris_path, primary_name, encounter.secondary_id, simulate_impact,
    )


def avoidance_preview(
    primary, debris, encounter, primary_name, dv_mps, *, earliest_burn=None, simulate_impact=False, close_up=False,
):
    """Replay a signed m/s impulse and compare closest approaches in TEME km and UTC."""
    paths, search, original, changed, new_offset, new_miss, burn_time, recovery_time = preview_along_track_encounter(
        primary, debris, encounter.tca, dv_mps, earliest_burn=earliest_burn, simulate_impact=simulate_impact,
    )

    if close_up:
        offsets = np.linspace(new_offset - 2, new_offset + 2, 81)
    else:
        offsets = np.arange(-3000, 3001, 60)
    contact = new_offset if new_miss <= CONTACT_KM else None
    offsets = np.unique(np.append(offsets, new_offset))
    burn_offset_s = (burn_time - encounter.tca).total_seconds()
    recovery_offset_s = (recovery_time - encounter.tca).total_seconds()
    if not close_up:
        offsets = np.unique(np.concatenate((
            offsets, burn_offset_s + np.arange(0, BURN_DURATION_S + 1, 10),
            [recovery_offset_s, recovery_offset_s + RECOVERY_DURATION_S],
            new_offset + np.arange(-12, 13),
        )))
    if contact is not None:
        offsets = offsets[offsets <= contact]
    nominal, altered, debris_path = paths(offsets)
    if close_up:
        origin = (altered[len(offsets) // 2] + debris_path[len(offsets) // 2]) / 2
        nominal, altered, debris_path = nominal - origin, altered - origin, debris_path - origin
    html = _scene_html(
        offsets, altered, debris_path, primary_name, encounter.secondary_id, False,
        earth_radius_km=0 if close_up else EARTH_RADIUS_KM,
        nominal_path=nominal, burn_offset_s=burn_offset_s, contact_offset_s=contact,
        encounter_offset_s=new_offset,
        avoided_passes=(
            [{"time": new_offset, "primary": 0, "debris": 1, "missKm": new_miss}]
            if simulate_impact and contact is None and not close_up else ()
        ),
        maneuver_phases=[burn_offset_s, burn_offset_s + BURN_DURATION_S,
                         recovery_offset_s, recovery_offset_s + RECOVERY_DURATION_S],
    )
    graph = go.Figure()
    graph.add_scatter(x=search.tolist(), y=original.tolist(), name="Original", line=dict(dash="dot"))
    graph.add_scatter(x=search.tolist(), y=changed.tolist(), name="After burn")
    graph.add_scatter(x=[new_offset], y=[new_miss], name="New closest approach", mode="markers")
    graph.update_layout(
        template="plotly_dark", height=420, margin=dict(l=48, r=20, b=58, t=25),
        xaxis_title="Seconds from original closest approach", yaxis_title="Separation (km)",
    )
    return html, graph, float(new_miss), burn_time, encounter.tca + timedelta(seconds=float(new_offset))


def _scene_html(
    offsets_s, primary_path, debris_path, primary_name, debris_id, simulate_impact, *, earth_radius_km=0,
    nominal_path=None, burn_offset_s=None, contact_offset_s=None,
    maneuver_phases=None, encounter_offset_s=0.0, avoided_passes=(),
):
    """Embed synchronized trajectories in km and playback times in seconds."""
    if simulate_impact:
        center = len(offsets_s) // 2
        offsets_s = offsets_s[:center + 1]
        primary_path, debris_path = primary_path[:center + 1], debris_path[:center + 1]

    distances = np.linalg.norm(primary_path - debris_path, axis=1)
    data = {
        "labels": [primary_name, f"Debris {debris_id}"],
        "satelliteCount": 1,
        "earthRadiusKm": earth_radius_km,
        "clockStepS": 60 if earth_radius_km else 0.05,
        "encounterTimes": [encounter_offset_s],
        "avoidedPasses": avoided_passes,
        "nominalPath": nominal_path.tolist() if nominal_path is not None else [],
        "burnOffsetS": burn_offset_s,
        "maneuverPhases": {0: maneuver_phases} if maneuver_phases is not None else {},
        "frames": [
            {
                "time": float(offset),
                "positions": [primary_position.tolist(), debris_position.tolist()],
                "distance": float(distance),
                "impact": (simulate_impact and float(offset) == 0) or float(offset) == contact_offset_s,
            }
            for offset, primary_position, debris_position, distance in zip(
                offsets_s, primary_path, debris_path, distances, strict=True,
            )
        ],
    }
    return _embed_scene(data)


def _embed_scene(data: dict) -> str:
    """Embed the orbital scene with km positions and time offsets in seconds."""
    template = Path(__file__).with_name("orbit_scene.html").read_text()
    return template.replace("__ENCOUNTER_DATA__", json.dumps(data, allow_nan=False).replace("<", r"\u003c"))


