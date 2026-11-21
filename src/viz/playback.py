"""Bridge the local orbit canvas to rolling propagation blocks."""

from pathlib import Path

import streamlit as st

from .encounter import orbit_window


@st.cache_resource
def _scene_component():
    """Register the offline-capable scene component with no physical units."""
    script = Path(__file__).with_name("playback.js").read_text()
    return st.components.v2.component("rolling_orbit_scene", js=script)


@st.fragment
def render_continuous_orbit(satellites, debris, start, key, *, show_timeline=True, simulated=()):
    """Serve succeeding blocks in TEME km from a fixed UTC playback start."""
    state_key = "rolling_orbit_window"
    player_key = f"{key}-orbit-player"
    if st.session_state.get(state_key, (None,))[0] != key:
        st.session_state[state_key] = key, orbit_window(
            satellites, debris, start, 0, show_timeline=show_timeline, simulated=simulated,
        )
    _, packet = st.session_state[state_key]

    def load_next():
        """Advance the requested unitless window sequence by one."""
        active_key, current = st.session_state[state_key]
        requested = st.session_state[player_key].get("advance")
        if active_key == key and requested == current["sequence"] + 1 and not current["frames"][-1]["impact"]:
            st.session_state[state_key] = key, orbit_window(
                satellites, debris, start, requested, show_timeline=show_timeline, simulated=simulated,
            )

    data = {
        "packet": packet,
        "template": Path(__file__).with_name("orbit_scene.html").read_text(),
    }
    _scene_component()(key=player_key, data=data, height=500, on_advance_change=load_next)
