"""Connect encounter results to Owner B's risk and fuel models."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import isfinite
from numbers import Real

import plotly.graph_objects as go
import streamlit as st

from src.contracts import Conjunction
from src.viz.encounter import CONTACT_KM, SAFE_MISS_KM, avoidance_preview

SIGMA_KM = 1.0
ELEVATED_RISK_PERCENT = 0.001
HIGH_RISK_PERCENT = 0.01
_OPTIONAL_MODULES = {
    "src.maneuver", "src.maneuver.fuel", "src.maneuver.planner",
    "src.risk", "src.risk.probability",
}


def render_burn_replay(
    primary, secondary, encounter, primary_name, *, earliest_burn=None, simulate_impact=False, close_up=False,
):
    """Replay a UTC along-track burn and report the recomputed miss in km."""
    dv_mps = st.number_input(
        "Along-track Δv (m/s)", min_value=-20.0, max_value=20.0, value=10.0, step=0.5,
        help="Positive speeds the satellite up. Negative slows it down.",
    )
    try:
        html, graph, miss_km, burn_time, new_tca = avoidance_preview(
            primary, secondary, encounter, primary_name, dv_mps,
            earliest_burn=earliest_burn, simulate_impact=simulate_impact, close_up=close_up,
        )
    except ValueError as error:
        st.error(f"Could not simulate this burn: {error}")
        return
    original_miss = 0 if simulate_impact else encounter.miss_km
    metrics = st.columns(2)
    metrics[0].metric("Original miss", f"{original_miss:.3f} km")
    displayed_miss = f"{miss_km:.3f} km"
    if miss_km < SAFE_MISS_KM and round(miss_km, 3) == SAFE_MISS_KM:
        displayed_miss = f"< {SAFE_MISS_KM:g} km"
    elif miss_km > CONTACT_KM and round(miss_km, 3) == CONTACT_KM:
        displayed_miss = f"> {CONTACT_KM:g} km"
    metrics[1].metric("Recomputed miss after burn", displayed_miss)
    if miss_km <= CONTACT_KM:
        st.error(f"Collision at closest approach. The objects came within the {CONTACT_KM * 1000:g} m contact distance.")
    elif miss_km < SAFE_MISS_KM:
        st.warning(f"Unsafe close pass. Successful avoidance requires at least {SAFE_MISS_KM:g} km at closest approach.")
    else:
        st.success(f"Successful avoidance. The trajectory meets the {SAFE_MISS_KM:g} km safety clearance for this encounter.")
    st.caption(
        f"Burn at {burn_time:%Y-%m-%d %H:%M:%S} UTC. "
        f"New closest approach at {new_tca:%H:%M:%S} UTC. "
        "The preview applies thrust over 60 s, then guides the satellite back to its original orbit over 30 minutes after the pass."
    )
    if close_up:
        st.iframe(html, height=480, alt="Close-up after avoidance burn")
    else:
        scene, separation = st.columns(2)
        with scene:
            st.iframe(html, height=480, alt="Orbit after avoidance burn")
        with separation:
            st.plotly_chart(graph, width="stretch")


def _plan_for_reference(planner, primary, encounter, reference):
    """Call the wall-clock planner with the scenario lead time and map its burn to UTC."""
    lead = encounter.tca - reference
    if lead <= timedelta(0):
        raise ValueError("Closest approach must occur after the planning start.")
    wall_start = datetime.now(UTC)
    result = planner(primary, replace(encounter, tca=wall_start + lead), threshold_km=SAFE_MISS_KM)
    if not isfinite(result.dv_mps) or not isfinite(result.new_miss_km) or result.new_miss_km < 0:
        raise ValueError("The planner returned an invalid burn or miss distance.")
    if result.dv_mps == 0:
        return result
    if not isinstance(result.burn_time, datetime) or result.burn_time.utcoffset() is None:
        raise ValueError("The planner returned an invalid burn time.")
    return replace(result, burn_time=reference + (result.burn_time - wall_start))


def render_avoidance(primary, encounter: Conjunction, reference: datetime, combined_radius_km: float):
    """Show selected-encounter risk, UTC burn recommendation, and fuel in kg."""
    st.subheader("Risk Assessment & Avoidance Planning")
    st.markdown("#### Collision Risk")
    valid_miss = isinstance(encounter.miss_km, Real) and isfinite(encounter.miss_km) and encounter.miss_km >= 0
    valid_radius = isinstance(combined_radius_km, Real) and isfinite(combined_radius_km) and combined_radius_km > 0
    radius_label = f"{combined_radius_km:g} km" if valid_radius else "Unavailable"
    st.metric("Current miss distance", f"{encounter.miss_km:.3f} km" if valid_miss else "Unavailable")
    st.caption(
        f"Model assumptions · Isotropic position uncertainty {SIGMA_KM:g} km · "
        f"Combined collision radius {radius_label}."
    )
    try:
        from src.risk.probability import collision_probability
    except ModuleNotFoundError as error:
        if error.name not in _OPTIONAL_MODULES:
            raise
        st.info("Collision probability is unavailable until the Part B risk module is present.")
    else:
        try:
            if not valid_miss or not valid_radius:
                raise ValueError("Use a finite, nonnegative miss distance and a positive combined radius.")
            probability = collision_probability(encounter.miss_km, SIGMA_KM, combined_radius_km)
            if not 0 <= probability <= 1:
                raise ValueError("The probability model returned an invalid result.")
        except ValueError as error:
            st.warning(f"Collision probability unavailable · {error}")
        else:
            percent = probability * 100
            risk = "High" if percent >= HIGH_RISK_PERCENT else "Elevated" if percent >= ELEVATED_RISK_PERCENT else "Low"
            risk_columns = st.columns(2)
            risk_columns[0].metric("Estimated collision probability", f"{percent:.3g}%")
            risk_columns[1].metric("Demo risk classification", risk)
            st.caption(
                f"Demo risk bands · Low below {ELEVATED_RISK_PERCENT:g}% · Elevated from "
                f"{ELEVATED_RISK_PERCENT:g}% to below {HIGH_RISK_PERCENT:g}% · High at or above {HIGH_RISK_PERCENT:g}%."
            )

    st.markdown("#### Avoidance Maneuver Recommendation")
    st.caption(
        f"Safety threshold {SAFE_MISS_KM:g} km. The linear planner's estimates are for demonstration only. "
        "It accepts the primary satellite and conjunction. The separate orbit replay propagates an illustrative burn."
    )
    try:
        from src.maneuver.planner import plan_maneuver
    except ModuleNotFoundError as error:
        if error.name not in _OPTIONAL_MODULES:
            raise
        st.info("Planner unavailable · The Part B maneuver module is needed.")
        return
    try:
        if not valid_miss:
            raise ValueError("The miss distance must be finite and nonnegative.")
        if not all(isinstance(moment, datetime) and moment.utcoffset() == timedelta(0)
                   for moment in (encounter.tca, reference)):
            raise ValueError("Closest approach and planning start must use timezone-aware UTC.")
        immediate = _plan_for_reference(plan_maneuver, primary, encounter, reference)
    except ValueError as error:
        st.warning(f"Planner unavailable · {error}")
        return

    recommended = immediate.dv_mps != 0
    st.write("**Avoidance maneuver recommended**" if recommended else "**No maneuver required**")
    metrics = st.columns(4)
    metrics[0].metric(
        "Recommended burn time (UTC)",
        immediate.burn_time.strftime("%Y-%m-%d %H:%M:%S") if recommended else "—",
    )
    metrics[1].metric("Burn now Δv", f"{immediate.dv_mps:.4g} m/s")
    metrics[2].metric("Pre-burn miss", f"{encounter.miss_km:.3f} km")
    metrics[3].metric("Estimated post-burn miss", f"{immediate.new_miss_km:.3f} km")
    if recommended:
        st.caption(f"Planning clock · {reference:%Y-%m-%d %H:%M:%S} UTC")

    st.markdown("#### Fuel Estimation")
    mass = st.sidebar.number_input("Spacecraft mass (kg)", min_value=1.0, value=500.0)
    isp = st.sidebar.number_input("Specific impulse (s)", min_value=1.0, value=220.0)
    dv_magnitude = abs(immediate.dv_mps)
    st.caption(f"Spacecraft mass {mass:g} kg · Specific impulse {isp:g} s · Δv magnitude {dv_magnitude:.4g} m/s")
    if not recommended:
        st.metric("Estimated propellant consumption", "0 kg")
        return
    try:
        from src.maneuver.fuel import fuel_used
    except ModuleNotFoundError as error:
        if error.name not in _OPTIONAL_MODULES:
            raise
        st.info("Fuel estimation is unavailable until the Part B fuel module is present.")
        return
    try:
        fuel_now = fuel_used(dv_magnitude, mass, isp)
    except ValueError as error:
        st.warning(f"Fuel estimation unavailable · {error}")
        return
    st.metric("Estimated propellant consumption", f"{fuel_now:.4g} kg")

    halfway = reference + (encounter.tca - reference) / 2
    try:
        later = _plan_for_reference(plan_maneuver, primary, encounter, halfway)
        fuel_later = fuel_used(abs(later.dv_mps), mass, isp) if later.dv_mps else 0.0
    except ValueError as error:
        st.info(f"Later-burn comparison unavailable · {error}")
        return
    comparison = go.Figure(go.Bar(
        x=["At scenario start", "Halfway to TCA"], y=[fuel_now, fuel_later],
    ))
    comparison.update_layout(
        yaxis_title="Fuel (kg)", height=300, margin=dict(l=40, r=10, t=10, b=40),
    )
    with st.expander("Compare burn timing"):
        st.plotly_chart(comparison, width="stretch")
