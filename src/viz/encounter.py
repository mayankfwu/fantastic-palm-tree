"""Plot TEME trajectories and separation around a selected encounter."""

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import plotly.graph_objects as go

from src.contracts import Conjunction
from src.orbits import propagate

PRIMARY_COLOR = "#62daf4"
DEBRIS_COLOR = "#ffbb70"


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
    offsets_s = np.arange(-3000, 3001, 60)
    primary_path, debris_path = _sample_positions(primary, secondary, encounter, offsets_s, simulate_impact)
    return _scene_html(
        offsets_s, primary_path, debris_path, primary_name, encounter.secondary_id,
        simulate_impact, earth_radius_km=6378.137,
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
    along = relative_step / np.linalg.norm(relative_step)
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


def _scene_html(
    offsets_s, primary_path, debris_path, primary_name, debris_id, simulate_impact, *, earth_radius_km=0,
):
    """Embed synchronized trajectories in km and playback times in seconds."""
    if simulate_impact:
        center = len(offsets_s) // 2
        offsets_s = offsets_s[:center + 1]
        primary_path, debris_path = primary_path[:center + 1], debris_path[:center + 1]

    distances = np.linalg.norm(primary_path - debris_path, axis=1)
    data = {
        "labels": [primary_name, f"Debris {debris_id}"],
        "earthRadiusKm": earth_radius_km,
        "frames": [
            {
                "time": float(offset),
                "positions": [primary_position.tolist(), debris_position.tolist()],
                "distance": float(distance),
                "impact": simulate_impact and float(offset) == 0,
            }
            for offset, primary_position, debris_position, distance in zip(
                offsets_s, primary_path, debris_path, distances, strict=True,
            )
        ],
    }
    template = Path(__file__).with_name("orbit_scene.html").read_text()
    return template.replace("__ENCOUNTER_DATA__", json.dumps(data).replace("<", r"\u003c"))


