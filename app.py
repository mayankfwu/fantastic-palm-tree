"""Streamlit interface for the single-satellite offline screening demo."""

from datetime import datetime

import streamlit as st

from src.orbits import find_conjunctions
from src.orbits.demo import load_demo_scenario
from src.viz.encounter import close_up_html, orbit_html, separation_figure


def load_results():
    """Load the snapshot models and ranked encounters in UTC, km, and km/s."""
    scenario, primary, debris = load_demo_scenario()
    encounters = find_conjunctions(
        primary, debris, datetime.fromisoformat(scenario["start"]),
        scenario["hours"], scenario["step_s"], scenario["screen_km"],
    )
    return scenario, primary, {item.satnum: item for item in debris}, encounters


def main():
    """Render the offline demo with TEME plots, UTC times, km, and km/s."""
    st.set_page_config(page_title="Satellite Conjunction Explorer", layout="wide")
    st.title("Satellite Conjunction Explorer")
    if "demo_results" not in st.session_state:
        st.session_state.demo_results = load_results()
    scenario, primary, debris, encounters = st.session_state.demo_results
    satellite_name = scenario["primary_omm"]["OBJECT_NAME"]
    start = datetime.fromisoformat(scenario["start"])
    st.caption(
        f"{satellite_name} · NORAD {primary.satnum} · Frozen CelesTrak snapshot "
        f"starting {start:%Y-%m-%d %H:%M} UTC"
    )

    overview = st.columns(4)
    overview[0].metric("Debris screened", len(debris))
    overview[1].metric("Screening window", f"{scenario['hours']:g} h")
    overview[2].metric("Screening radius", f"{scenario['screen_km']:g} km")
    overview[3].metric("Predicted encounters", len(encounters))
    if not encounters:
        st.info("No encounters fall within the screening radius in this window.")
        return

    st.subheader("Ranked encounters")
    rows = [
        {
            "Debris NORAD ID": item.secondary_id,
            "Closest approach (UTC)": item.tca.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "Miss (km)": item.miss_km,
            "Relative speed (km/s)": item.rel_speed_kms,
        }
        for item in encounters
    ]
    st.dataframe(
        rows, hide_index=True, width="stretch",
        column_config={
            "Miss (km)": st.column_config.NumberColumn(format="%.3f"),
            "Relative speed (km/s)": st.column_config.NumberColumn(format="%.3f"),
        },
    )
    labels = [
        f"NORAD {item.secondary_id} · {item.miss_km:.3f} km · {item.tca:%b %d %H:%M:%S} UTC"
        for item in encounters
    ]
    selected = st.selectbox("Encounter to inspect", range(len(encounters)), format_func=labels.__getitem__)
    encounter = encounters[selected]
    secondary = debris[encounter.secondary_id]
    simulate_impact = st.toggle("Simulate an impact")
    if simulate_impact:
        st.info("Illustrative impact. The debris path is shifted to meet the satellite at closest approach.")
    view = st.radio("Encounter view", ["3D orbit", "3D close-up"], horizontal=True)
    if view == "3D close-up":
        html = close_up_html(
            primary, secondary, encounter, satellite_name, simulate_impact=simulate_impact,
        )
        # Replace the previous iframe, including its WebGL context, on a view change.
        with st.container(key=f"scene-{selected}-{view}-{simulate_impact}"):
            st.iframe(html, height=480, alt="Animated 3D close-up")
        st.caption("Drag to rotate while playing. The graph marker follows the playback time.")
    else:
        orbit_column, separation_column = st.columns([1, 1])
        with orbit_column:
            html = orbit_html(
                primary, secondary, encounter, satellite_name, simulate_impact=simulate_impact,
            )
            with st.container(key=f"scene-{selected}-{view}-{simulate_impact}"):
                st.iframe(html, height=480, alt="Animated 3D orbit")
            st.caption("Drag to rotate Earth and both orbits, including during playback.")
        with separation_column:
            st.subheader("Separation near closest approach")
            st.plotly_chart(
                separation_figure(
                    primary, secondary, encounter, scenario["screen_km"], simulate_impact=simulate_impact,
                ),
                width="stretch",
            )
    if simulate_impact:
        st.caption("Simulated impact at 0.000 km. Playback ends at contact.")
    else:
        st.caption(f"Predicted miss: {encounter.miss_km:.3f} km.")

    st.caption("Public GP orbital elements provide no covariance. This view shows predicted encounter geometry.")


if __name__ == "__main__":
    main()
