"""Streamlit interface for frozen and live CelesTrak orbit scenarios."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from random import Random, SystemRandom
from time import monotonic

import requests
import streamlit as st
from sgp4.conveniences import sat_epoch_datetime

from src.orbits import find_conjunctions
from src.orbits.catalog import CACHE_SECONDS, load_named_catalog
from src.orbits.demo import load_demo_scenario, load_offline_catalogs
from src.orbits.simulation import MAX_SIMULATED_DEBRIS, place_simulated_debris
from src.viz.avoidance import render_avoidance, render_burn_replay
from src.viz.encounter import CONTACT_KM, SAFE_MISS_KM, close_up_html, orbit_html, separation_figure
from src.viz.rolling_scene import render_continuous_orbit

CATALOG_RETRY_SECONDS = 60
SATELLITE_GROUPS = {"Space stations": "stations", "Earth resources": "resource", "Active satellites": "active"}
DEBRIS_GROUPS = {
    "COSMOS 2251": "cosmos-2251-debris",
    "IRIDIUM 33": "iridium-33-debris",
    "FENGYUN 1C": "fengyun-1c-debris",
}


@st.cache_data(show_spinner=False)
def screen_snapshot():
    """Share ranked UTC encounters in km and km/s across app sessions."""
    scenario, primary, debris = load_demo_scenario()
    return find_conjunctions(
        primary, debris, datetime.fromisoformat(scenario["start"]),
        scenario["hours"], scenario["step_s"], scenario["screen_km"],
    )


def main():
    """Choose between frozen and live views with UTC times and TEME km."""
    st.set_page_config(page_title="ORBITGUARD · Satellite Conjunction Explorer", layout="wide")
    st.title("Satellite Conjunction Explorer")
    if st.sidebar.toggle("Demo mode", value=True, help="Turn off to select live CelesTrak objects."):
        demo_view = st.sidebar.radio("Offline view", ["Guided replay", "Offline catalog"])
        if demo_view == "Offline catalog":
            render_catalog_scene(offline=True)
        else:
            render_demo()
    else:
        render_catalog_scene(offline=False)


def session_catalog(group):
    """Reuse session-local CelesTrak names and SGP4 models with UTC epochs."""
    catalogs = st.session_state.setdefault("live_catalogs", {})
    failures = st.session_state.setdefault("catalog_failures", {})
    now = monotonic()
    if group in failures:
        retry_at, reason = failures[group]
        if now < retry_at:
            raise ValueError(reason)
        del failures[group]
    entry = catalogs.get(group)
    if entry is None or now - entry[0] >= CACHE_SECONDS:
        with st.spinner(f"Loading CelesTrak group {group}…"):
            try:
                models = load_named_catalog(group)
            except (requests.RequestException, ValueError, OSError) as exc:
                reason = f"{exc}. Retry this catalog after {CATALOG_RETRY_SECONDS} seconds"
                failures[group] = monotonic() + CATALOG_RETRY_SECONDS, reason
                raise ValueError(reason) from exc
        entry = monotonic(), {model.satnum: (name, model) for name, model in models}
        catalogs[group] = entry
    return entry[1]


def simulated_debris_controls(satellites, start):
    """Choose how many illustrative objects to place around Earth at a UTC start."""
    count = st.sidebar.number_input(
        "Add simulated debris", min_value=0, max_value=MAX_SIMULATED_DEBRIS, value=0,
        help="Adds illustrative orbital paths with staged contacts in the 3D orbit view.",
    )
    reshuffle = st.sidebar.button("Randomize simulated debris", disabled=count == 0)
    if "simulated_seed" not in st.session_state or reshuffle:
        st.session_state.simulated_seed = SystemRandom().getrandbits(64)
    return place_simulated_debris(count, len(satellites), start, st.session_state.simulated_seed)


def render_catalog_scene(*, offline: bool):
    """Render a selectable catalog in TEME km from a UTC playback start."""
    if offline:
        if "offline_catalogs" not in st.session_state:
            start, satellites, debris = load_offline_catalogs()
            st.session_state.offline_catalogs = (
                start, {model.satnum: (name, model) for name, model in satellites},
                {model.satnum: (name, model) for name, model in debris},
            )
        start, available, catalog = st.session_state.offline_catalogs
    else:
        satellite_group = st.sidebar.selectbox("Satellite catalog", tuple(SATELLITE_GROUPS))
        try:
            available = session_catalog(SATELLITE_GROUPS[satellite_group])
        except (requests.RequestException, ValueError, OSError) as exc:
            st.error(f"Could not load the satellite catalog: {exc}")
            return

    selected = st.sidebar.multiselect(
        "Add satellites", tuple(available),
        default=list(available)[:1] if offline else [],
        key="offline_satellites" if offline else "live_satellites",
        format_func=lambda catalog_id: f"{available[catalog_id][0]} · NORAD {catalog_id}",
        placeholder="Search by satellite name or NORAD ID",
    )
    if not selected:
        st.info("Search for and add satellites in the sidebar to start playback.")
        return

    if not offline:
        group = st.sidebar.selectbox("Debris group", tuple(DEBRIS_GROUPS))
        try:
            catalog = session_catalog(DEBRIS_GROUPS[group])
        except (requests.RequestException, ValueError, OSError) as exc:
            st.warning(f"Could not load the debris catalog: {exc}. Simulated debris is still available.")
            catalog = {}
        if "live_start" not in st.session_state:
            st.session_state.live_start = datetime.now(UTC).replace(second=0, microsecond=0)
        start = st.session_state.live_start

    eligible = [
        entry for catalog_id, entry in catalog.items()
        if catalog_id not in selected and "DEB" in entry[0].upper().split()
    ]
    count = st.sidebar.number_input(
        "Number of debris objects", min_value=0, max_value=len(eligible), value=min(10, len(eligible)),
    )
    resample = st.sidebar.button("Resample debris", disabled=count == 0)
    if "debris_seed" not in st.session_state or resample:
        st.session_state.debris_seed = SystemRandom().getrandbits(64)
    debris = Random(st.session_state.debris_seed).sample(eligible, count)
    satellites = [available[catalog_id] for catalog_id in selected]
    simulated = simulated_debris_controls(satellites, start)
    avoid_simulated = bool(simulated) and st.sidebar.toggle(
        "Avoid simulated debris", value=True,
        key="offline_avoid_simulated" if offline else "live_avoid_simulated",
        help="Apply an illustrative velocity change before a staged contact.",
    )
    source = "Bundled CelesTrak snapshot · COSMOS 2251" if offline else "Live CelesTrak elements"
    st.caption(
        f"{source} · {len(satellites)} satellites · {count} of {len(eligible)} debris sampled "
        f"· Playback starts {start:%Y-%m-%d %H:%M} UTC"
    )
    scene_key = sha256(repr((offline, start, simulated, avoid_simulated, [
        (model.satnum, sat_epoch_datetime(model)) for _, model in [*satellites, *debris]
    ])).encode()).hexdigest()
    scene_key = f"catalog-scene-{scene_key}"
    st.session_state.avoid_simulated_scene = scene_key if avoid_simulated else None
    render_continuous_orbit(satellites, debris, start, scene_key, show_timeline=offline, simulated=simulated)
    if avoid_simulated:
        st.caption(
            f"{len(simulated)} simulated debris added. Automatic burns target at least {SAFE_MISS_KM:g} km "
            "of clearance at each staged pass. Playback pauses on physical contact."
        )
    elif simulated:
        st.caption(f"{len(simulated)} simulated debris added. Playback stops at the first staged or predicted contact.")
    else:
        st.caption("Playback continues until a predicted contact within the assumed 10 m radius. Drag to rotate.")

    primary_id = st.sidebar.selectbox(
        "Satellite to screen", selected,
        format_func=lambda catalog_id: f"{available[catalog_id][0]} · NORAD {catalog_id}",
    )
    screen_km = st.sidebar.number_input("Screening radius (km)", min_value=1.0, value=50.0)
    primary = available[primary_id][1]
    objects = [model for _, model in debris]
    screen_key = (
        offline, primary_id, sat_epoch_datetime(primary),
        tuple((model.satnum, sat_epoch_datetime(model)) for model in objects), start, screen_km,
    )
    if st.button("Screen next 24 hours", disabled=not objects):
        with st.spinner("Screening sampled debris…"):
            encounters = find_conjunctions(primary, objects, start, 24, screen_km=screen_km)
        st.session_state.catalog_screen = screen_key, encounters
    if st.session_state.get("catalog_screen", (None,))[0] == screen_key:
        encounters = st.session_state.catalog_screen[1]
        render_encounter_table(encounters)
        if encounters:
            index = st.selectbox(
                "Encounter to inspect", range(len(encounters)),
                format_func=lambda item: f"NORAD {encounters[item].secondary_id} · "
                f"{encounters[item].miss_km:.3f} km · {encounters[item].tca:%b %d %H:%M:%S} UTC",
            )
            encounter = encounters[index]
            if st.toggle("Apply avoidance maneuver"):
                render_burn_replay(
                    primary, catalog[encounter.secondary_id][1], encounter, available[primary_id][0], earliest_burn=start,
                )
            render_avoidance(primary, encounter, start, CONTACT_KM)


def render_encounter_table(encounters):
    """Show ranked UTC approaches, miss distances in km, and speed in km/s."""
    if not encounters:
        st.info("No encounters fall within the screening radius in this window.")
        return
    st.subheader("Ranked encounters")
    st.dataframe(
        [
            {
                "Debris NORAD ID": item.secondary_id,
                "Closest approach (UTC)": (item.tca + timedelta(microseconds=500)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "Miss (km)": item.miss_km,
                "Relative speed (km/s)": item.rel_speed_kms,
            }
            for item in encounters
        ],
        hide_index=True, width="stretch",
        column_config={
            "Miss (km)": st.column_config.NumberColumn(format="%.3f"),
            "Relative speed (km/s)": st.column_config.NumberColumn(format="%.3f"),
        },
    )


def render_demo():
    """Render the offline demo with TEME plots, UTC times, km, and km/s."""
    if "demo_models" not in st.session_state:
        scenario, primary, objects = load_demo_scenario()
        st.session_state.demo_models = scenario, primary, {item.satnum: item for item in objects}
    scenario, primary, debris = st.session_state.demo_models
    with st.spinner("Screening the frozen catalog…"):
        encounters = screen_snapshot()
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
    debris_epochs = {catalog_id: sat_epoch_datetime(model) for catalog_id, model in debris.items()}
    older = sum((start - epoch).total_seconds() > 3 * 86400 for epoch in debris_epochs.values())
    if older:
        st.warning(
            f"{older} of {len(debris)} debris element sets were more than 3 days old "
            "at the window start. Older elements can reduce prediction accuracy."
        )
    render_encounter_table(encounters)
    if not encounters:
        return
    labels = [
        f"NORAD {item.secondary_id} · {item.miss_km:.3f} km · {item.tca:%b %d %H:%M:%S} UTC"
        for item in encounters
    ]
    selected = st.selectbox("Encounter to inspect", range(len(encounters)), format_func=labels.__getitem__)
    encounter = encounters[selected]
    secondary = debris[encounter.secondary_id]
    primary_age = (encounter.tca - sat_epoch_datetime(primary)).total_seconds() / 86400
    debris_age = (encounter.tca - debris_epochs[secondary.satnum]).total_seconds() / 86400
    st.caption(f"Element age at closest approach · {satellite_name} {primary_age:.1f} days · Debris {debris_age:.1f} days")
    if max(primary_age, debris_age) > 3:
        st.warning("This encounter uses elements more than 3 days old at closest approach.")
    simulate_impact = st.toggle("Simulate an impact")
    if simulate_impact:
        st.info("Illustrative impact. The debris path intersects the original satellite orbit.")
    apply_burn = st.toggle("Apply avoidance maneuver")
    view = st.radio("Encounter view", ["3D orbit", "3D close-up"], horizontal=True)
    if apply_burn:
        render_burn_replay(
            primary, secondary, encounter, satellite_name,
            earliest_burn=start, simulate_impact=simulate_impact, close_up=view == "3D close-up",
        )
    elif view == "3D close-up":
        html = close_up_html(
            primary, secondary, encounter, satellite_name, simulate_impact=simulate_impact,
        )
        # Reset playback when the encounter or impact mode changes.
        with st.container(key=f"scene-{selected}-{view}-{simulate_impact}"):
            st.iframe(html, height=480, alt="Animated 3D close-up")
        st.caption("The close-up replays the selected encounter. Drag to rotate while it plays.")
    else:
        orbit_column, separation_column = st.columns([1, 1])
        with orbit_column:
            if simulate_impact:
                html = orbit_html(primary, secondary, encounter, satellite_name, simulate_impact=True)
                st.iframe(html, height=480, alt="Animated 3D orbit")
            else:
                satellites = [(satellite_name, primary)]
                orbit_start = encounter.tca - timedelta(minutes=50)
                simulated = simulated_debris_controls(satellites, orbit_start)
                scene_key = f"demo-scene-{selected}-{len(simulated)}-{st.session_state.simulated_seed}"
                render_continuous_orbit(
                    satellites, [(f"Debris {secondary.satnum}", secondary)], orbit_start,
                    scene_key, simulated=simulated,
                )
                if simulated:
                    st.caption(f"{len(simulated)} simulated debris added with staged contacts.")
            st.caption("Drag to rotate Earth and both orbits, including during playback.")
        with separation_column:
            st.subheader("Separation near closest approach")
            st.plotly_chart(
                separation_figure(
                    primary, secondary, encounter, scenario["screen_km"], simulate_impact=simulate_impact,
                ),
                width="stretch",
            )
    if simulate_impact and not apply_burn:
        st.caption("Simulated impact at 0.000 km. Playback pauses on the contact snapshot.")
    elif not apply_burn:
        st.caption(f"Predicted miss: {encounter.miss_km:.3f} km.")

    st.caption("Public GP orbital elements provide no covariance. This view shows predicted encounter geometry.")
    render_avoidance(primary, encounter, start, CONTACT_KM)


if __name__ == "__main__":
    main()
