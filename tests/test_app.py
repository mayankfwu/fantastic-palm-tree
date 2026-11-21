"""Verify the offline app, 3D playback, and the simulated impact."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.contracts import Conjunction
from src.orbits.demo import load_demo_scenario
from src.viz.encounter import close_up_html, orbit_html
from src.viz.rolling_scene import orbit_window


def _scene_data(html):
    """Read the embedded scene data with positions in km and times in seconds."""
    return json.JSONDecoder().raw_decode(html.split("} = ", 1)[1])[0]


def _open_guided_replay():
    """Open the frozen UTC encounter replay through the offline view selector."""
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10).run()
    return app.sidebar.radio[0].set_value("Guided replay").run()


def test_offline_demo_switches_encounter_view_and_impact():
    """Verify the selected encounter, km separation, 3D close-up, and impact mode."""
    app = _open_guided_replay()
    assert not app.exception
    assert app.radio[0].value == "3D orbit"
    assert app.metric[0].value == "581"
    assert "90 of 581 debris element sets" in app.warning[0].value
    assert any("SCD 2 2.3 days · Debris 2.6 days" in caption.value for caption in app.caption)
    assert list(app.dataframe[0].value["Debris NORAD ID"]) == [34387, 36048]
    assert list(app.dataframe[0].value["Closest approach (UTC)"]) == [
        "2026-11-23 14:02:52.912", "2026-11-23 04:30:43.085",
    ]
    assert app.radio[0].options == ["3D orbit", "3D close-up"]
    orbit = app.session_state.rolling_orbit_window[1]
    assert orbit["continuous"]
    assert orbit["showTimeline"]
    assert orbit["earthRadiusKm"] == pytest.approx(6378.137)
    assert orbit["labels"] == ["SCD 2", "Debris 34387"]

    app.selectbox[0].set_value(1)
    app.radio[0].set_value("3D close-up").run()
    assert not app.exception
    assert app.get("iframe")[0].proto.alt == "Animated 3D close-up"
    assert "Debris 36048" in app.get("iframe")[0].proto.srcdoc
    app.radio[0].set_value("3D orbit").run()
    separation = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert separation["data"][1]["y"][0] == pytest.approx(3.517, abs=0.001)
    assert separation["data"][0]["x"][0] < 0 < separation["data"][0]["x"][-1]

    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert "Illustrative impact" in app.info[0].value
    separation = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert separation["data"][0]["x"][-1] == 0
    assert separation["data"][1]["y"][0] == pytest.approx(0)
    assert app.dataframe[0].value["Miss (km)"].iloc[1] == pytest.approx(3.517, abs=0.001)


def test_close_up_graph_tracks_the_3d_animation_through_impact():
    """Verify generated positions change in km and both markers meet at time zero."""
    scenario, primary, debris = load_demo_scenario()
    fields = scenario["conjunctions"][0]
    encounter = Conjunction(**dict(fields, tca=datetime.fromisoformat(fields["tca"])))
    secondary = next(satellite for satellite in debris if satellite.satnum == encounter.secondary_id)
    orbit = _scene_data(orbit_html(primary, secondary, encounter, "SCD 2"))
    assert orbit["earthRadiusKm"] > 0
    paths = [sample["positions"] for sample in orbit["frames"]]
    assert all(start != end for start, end in zip(paths[0], paths[-1]))

    html = close_up_html(primary, secondary, encounter, "SCD 2")
    data = _scene_data(html)
    assert data["earthRadiusKm"] == 0
    closest = next(frame for frame in data["frames"] if frame["time"] == 0)
    assert closest["distance"] == pytest.approx(encounter.miss_km, abs=0.001)
    assert 'id="separation"' in html
    assert 'id="timeline"' in html
    assert 'id="camera-mode"' in html
    assert 'id="speed" type="range" min="0.01" max="2"' in html
    assert 'id="slow-near" type="checkbox"' in html
    assert data["encounterTimes"] == [0.0]

    html = close_up_html(primary, secondary, encounter, "SCD 2", simulate_impact=True)
    frames = _scene_data(html)["frames"]
    impact = frames[-1]
    assert impact["time"] == 0
    assert impact["impact"]
    assert impact["distance"] == pytest.approx(0)
    assert impact["positions"][0] == pytest.approx(impact["positions"][1])
    assert all(before != after for before, after in zip(frames[0]["positions"], impact["positions"]))


def test_live_mode_selects_named_satellites_and_samples_debris(monkeypatch):
    """Verify live selection, stable sampling, and staged avoidance without the network."""
    from unittest.mock import Mock

    from src.orbits import catalog

    scenario, primary, debris = load_demo_scenario()
    load = Mock(side_effect=lambda group: (
        [("SCD 2", primary), ("Other satellite", debris[0])] if group == "stations" else
        [("COSMOS 2251", primary), *((f"COSMOS 2251 DEB {i}", model) for i, model in enumerate(debris[1:8]))]
    ))
    monkeypatch.setattr(catalog, "load_named_catalog", load)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10)
    app.run()
    assert load.call_count == 0
    app.sidebar.toggle[0].set_value(False).run()
    assert any("SCD 2 · NORAD 25504" in label for label in app.sidebar.multiselect[0].options)
    app.sidebar.multiselect[0].set_value([primary.satnum, debris[0].satnum]).run()
    app.session_state.debris_seed = 41
    app.sidebar.number_input[0].set_value(3).run()
    assert not app.exception
    data = app.session_state.rolling_orbit_window[1]
    assert not data["showTimeline"]
    assert data["satelliteCount"] == 2
    assert data["labels"][:2] == ["SCD 2", "Other satellite"]
    assert len(set(data["labels"][2:])) == 3
    assert all(" DEB " in name for name in data["labels"][2:])
    assert all(len(frame["positions"]) == 5 for frame in data["frames"])
    next(widget for widget in app.sidebar.number_input if widget.label == "Screening radius (km)").set_value(75.0).run()
    assert app.session_state.rolling_orbit_window[1]["labels"] == data["labels"]
    app.sidebar.button[0].click().run()
    assert app.session_state.debris_seed != 41
    assert len(app.session_state.rolling_orbit_window[1]["labels"]) == 5
    app.session_state.live_start = datetime.fromisoformat(scenario["start"])
    app.session_state.simulated_seed = 13
    app.sidebar.multiselect[0].set_value([primary.satnum]).run()
    next(widget for widget in app.sidebar.number_input if widget.label == "Number of debris objects").set_value(0).run()
    next(widget for widget in app.sidebar.number_input if widget.label == "Add simulated debris").set_value(3).run()
    assert not app.exception
    avoided = app.session_state.rolling_orbit_window[1]
    assert not avoided["showTimeline"]
    assert avoided["maneuverPhases"]
    assert not any(frame["impact"] for frame in avoided["frames"])
    next(widget for widget in app.sidebar.toggle if widget.label == "Avoid simulated debris").set_value(False).run()
    assert app.session_state.rolling_orbit_window[1]["frames"][-1]["impactKind"] == "simulated"
    assert [call.args[0] for call in load.call_args_list] == ["stations", "cosmos-2251-debris"]


def test_offline_catalog_opens_by_default_with_network_disabled(monkeypatch):
    """Start with bundled named objects at the fixed UTC epoch without catalog requests."""
    from unittest.mock import Mock

    from src.orbits import catalog

    network = Mock(side_effect=AssertionError("offline catalog must not request live data"))
    monkeypatch.setattr(catalog.requests, "get", network)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10).run()
    assert not app.exception
    assert app.sidebar.radio[0].value == "Offline catalog"
    assert app.sidebar.multiselect[0].value == [25504]
    options = app.sidebar.multiselect[0].options
    assert any("ISS (ZARYA)" in label for label in options)
    assert any("CSS (TIANHE)" in label for label in options)
    assert any("581 debris" in caption.value for caption in app.caption)
    app.sidebar.multiselect[0].set_value([25504, 25544]).run()
    app.sidebar.number_input[0].set_value(4).run()
    assert not app.exception
    data = app.session_state.rolling_orbit_window[1]
    assert data["labels"][:2] == ["SCD 2", "ISS (ZARYA)"]
    assert data["showTimeline"]
    assert data["satelliteCount"] == 2
    assert len(data["labels"]) == 6
    assert all(len(frame["positions"]) == 6 for frame in data["frames"])
    network.assert_not_called()


def test_rolling_windows_join_and_stop_at_contact(monkeypatch):
    """Continue at the same TEME state and end at the predicted contact in UTC."""
    scenario, primary, debris = load_demo_scenario()
    start = datetime.fromisoformat(scenario["start"])
    satellites = [("SCD 2", primary)]
    objects = [("Debris", debris[0])]
    first = orbit_window(satellites, objects, start, 0)
    second = orbit_window(satellites, objects, start, 1)
    assert first["frames"][-1] == second["frames"][0]
    assert not first["frames"][-1]["impact"]

    from src.viz import rolling_scene

    event = Conjunction(primary.satnum, debris[0].satnum, start + timedelta(seconds=31.25), 0.005, 10.0)
    monkeypatch.setattr(rolling_scene, "find_conjunctions", lambda *args, **kwargs: [event])
    contact = orbit_window(satellites, objects, start, 0)
    assert contact["frames"][0]["time"] == 0
    assert contact["frames"][-1]["time"] == 31.25
    assert contact["encounterTimes"] == [31.25]
    assert contact["frames"][-1]["impact"]
    assert contact["frames"][-1]["impactObject"] == 0

    event.miss_km = 3.0
    near_pass = orbit_window(satellites, objects, start, 0)
    assert near_pass["encounterTimes"] == [31.25]
    assert not any(frame["impact"] for frame in near_pass["frames"])


def test_simulated_debris_can_stop_playback_at_a_staged_contact():
    """Add up to fifteen synthetic paths in TEME km and meet at a staged UTC contact."""
    from src.orbits.simulation import place_simulated_debris

    scenario, primary, _ = load_demo_scenario()
    start = datetime.fromisoformat(scenario["start"])
    with pytest.raises(ValueError, match="up to 15"):
        place_simulated_debris(16, 1, start, 13)
    placements = place_simulated_debris(15, 1, start, 13)
    assert placements == place_simulated_debris(15, 1, start, 13)
    assert len({item.angle_rad for item in placements}) == 15
    first = min(range(len(placements)), key=lambda i: placements[i].contact_time)
    packet = orbit_window([("SCD 2", primary)], [], start, 0, simulated=placements)
    impact = packet["frames"][-1]
    assert packet["simulatedCount"] == 15
    assert len(packet["labels"]) == 16
    assert impact["impactKind"] == "simulated"
    assert impact["time"] == (placements[first].contact_time - start).total_seconds()
    assert impact["positions"][0] == impact["positions"][first + 1]
    assert packet["frames"][0]["positions"][1] != packet["frames"][0]["positions"][2]


def test_guided_replay_has_a_capped_simulated_debris_control():
    """Select fifteen illustrative objects and preserve predicted encounter distances in km."""
    app = _open_guided_replay()
    control = next(widget for widget in app.sidebar.number_input if widget.label == "Add simulated debris")
    assert control.max == 15
    control.set_value(15).run()
    assert not app.exception
    assert app.session_state.rolling_orbit_window[1]["simulatedCount"] == 15
    assert app.dataframe[0].value["Miss (km)"].iloc[0] == pytest.approx(0.662, abs=0.001)


def test_avoidance_panel_uses_the_frozen_scenario_clock():
    """Run Owner B's models for an archived UTC encounter with an hour of lead time."""
    pytest.importorskip("src.maneuver.planner")
    pytest.importorskip("src.risk.probability")
    app = AppTest.from_string(
        """
from datetime import UTC, datetime, timedelta
from src.contracts import Conjunction
from src.viz.avoidance import render_avoidance

start = datetime(2000, 1, 1, tzinfo=UTC)
encounter = Conjunction(25544, 34387, start + timedelta(hours=1), 2.0, 10.0)
render_avoidance(None, encounter, start, 0.01)
"""
    ).run()
    assert not app.exception
    metrics = {metric.label: metric.value for metric in app.metric}
    assert float(metrics["Estimated collision probability"].rstrip("%")) > 0
    assert float(metrics["Burn now Δv"].split()[0]) == pytest.approx(1.273, abs=0.001)
    assert metrics["Estimated post-burn miss"] == "5.000 km"
    assert metrics["Recommended burn time (UTC)"] == "2000-01-01 00:00:00"
    comparison = json.loads(app.get("plotly_chart")[0].proto.spec)
    fuel_now, fuel_later = comparison["data"][0]["y"]
    assert 0 < fuel_now < fuel_later


def test_applied_avoidance_replays_a_burn_and_recomputes_contact():
    """Replay both trajectories in TEME km and stop only at an unavoided contact."""
    app = _open_guided_replay()
    next(widget for widget in app.toggle if widget.label == "Simulate an impact").set_value(True)
    next(widget for widget in app.toggle if widget.label == "Apply avoidance maneuver").set_value(True).run()
    assert not app.exception
    scene = _scene_data(app.get("iframe")[0].proto.srcdoc)
    burn_sample = next(i for i, frame in enumerate(scene["frames"]) if frame["time"] == -1200)
    assert scene["frames"][burn_sample]["positions"][0] == scene["nominalPath"][burn_sample]
    assert scene["frames"][0]["positions"][0] == scene["nominalPath"][0]
    closest = next(i for i, frame in enumerate(scene["frames"]) if frame["time"] == 0)
    assert scene["frames"][closest]["positions"][0] != scene["nominalPath"][closest]
    assert scene["frames"][-1]["positions"][0] == scene["nominalPath"][-1]
    assert scene["maneuverPhases"]["0"] == [-1200, -1140, 300, 2100]
    assert not any(frame["impact"] for frame in scene["frames"])
    assert scene["maneuverPasses"][0]["missKm"] >= scene["safeMissKm"] == 5
    assert any("Successful avoidance" in notice.value for notice in app.success)
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Original miss"] == "0.000 km"
    assert float(metrics["Recomputed miss after burn"].split()[0]) > 5

    next(widget for widget in app.number_input if widget.label == "Along-track Δv (m/s)").set_value(1.0).run()
    assert not app.exception
    scene = _scene_data(app.get("iframe")[0].proto.srcdoc)
    assert 0.01 < scene["maneuverPasses"][0]["missKm"] < scene["safeMissKm"]
    assert not any(frame["impact"] for frame in scene["frames"])
    assert any("Unsafe close pass" in notice.value for notice in app.warning)
    assert not app.success

    next(widget for widget in app.number_input if widget.label == "Along-track Δv (m/s)").set_value(0.0).run()
    assert not app.exception
    scene = _scene_data(app.get("iframe")[0].proto.srcdoc)
    assert scene["frames"][-1]["impact"]
    assert scene["frames"][-1]["distance"] == pytest.approx(0)
    assert any("Collision at closest approach" in notice.value for notice in app.error)
    assert not app.success


@pytest.mark.parametrize(("miss_km", "notice", "display"), [
    (0.01, "error", "0.010 km"),
    (0.010001, "warning", "> 0.01 km"),
    (4.999999, "warning", "< 5 km"),
    (5.0, "success", "5.000 km"),
])
def test_burn_result_uses_unrounded_clearance(monkeypatch, miss_km, notice, display):
    """Classify the refined minimum in km on both sides of the contact and safety limits."""
    from src.viz import avoidance

    moment = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(avoidance, "avoidance_preview", lambda *a, **kw: ("", None, miss_km, moment, moment))
    app = AppTest.from_string(
        """
from types import SimpleNamespace
from src.viz.avoidance import render_burn_replay
render_burn_replay(None, None, SimpleNamespace(miss_km=0), "Test", close_up=True)
"""
    ).run()
    assert not app.exception
    assert app.metric[1].value == display
    assert len(getattr(app, notice)) == 1


def test_part_b_panel_updates_for_each_guided_encounter():
    """Update the selected miss in km, probability in percent, and fuel in kg."""
    probability = pytest.importorskip("src.risk.probability")
    fuel = pytest.importorskip("src.maneuver.fuel")
    pytest.importorskip("src.maneuver.planner")
    app = _open_guided_replay()
    for index in (0, 1):
        app.selectbox[0].set_value(index).run()
        assert not app.exception
        assert any(item.value == "Risk Assessment & Avoidance Planning" for item in app.subheader)
        assert any("Avoidance maneuver recommended" in item.value for item in app.markdown)
        metrics = {metric.label: metric.value for metric in app.metric}
        miss_km = app.dataframe[0].value["Miss (km)"].iloc[index]
        assert metrics["Current miss distance"] == f"{miss_km:.3f} km"
        expected_percent = probability.collision_probability(miss_km, 1.0, 0.01) * 100
        assert metrics["Estimated collision probability"] == f"{expected_percent:.3g}%"
        dv_mps = float(metrics["Burn now Δv"].split()[0])
        propellant = float(metrics["Estimated propellant consumption"].split()[0])
        assert propellant == pytest.approx(fuel.fuel_used(dv_mps, 500, 220), rel=0.002)

    mass = next(widget for widget in app.sidebar.number_input if widget.label == "Spacecraft mass (kg)")
    mass.set_value(1000.0).run()
    adjusted = next(metric for metric in app.metric if metric.label == "Estimated propellant consumption")
    assert float(adjusted.value.split()[0]) == pytest.approx(propellant * 2, rel=0.002)


def test_part_b_panel_shows_no_burn_for_safe_encounter(monkeypatch):
    """A safe miss in km shows 0 kg without invoking the fuel model."""
    fuel = pytest.importorskip("src.maneuver.fuel")
    pytest.importorskip("src.maneuver.planner")

    def unexpected_fuel_call(*args):
        """Reject a fuel calculation in kg when the planner returns zero Δv."""
        pytest.fail("Fuel model must not be called for a zero-Δv maneuver")

    monkeypatch.setattr(fuel, "fuel_used", unexpected_fuel_call)
    app = AppTest.from_string(
        """
from datetime import UTC, datetime, timedelta
from src.contracts import Conjunction
from src.viz.avoidance import render_avoidance
start = datetime(2000, 1, 1, tzinfo=UTC)
render_avoidance(None, Conjunction(25544, 34387, start + timedelta(hours=1), 5.0, 10.0), start, 0.01)
"""
    ).run()
    assert not app.exception
    assert any("No maneuver required" in item.value for item in app.markdown)
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Recommended burn time (UTC)"] == "—"
    assert metrics["Estimated propellant consumption"] == "0 kg"


def test_part_b_panel_keeps_risk_visible_when_planner_rejects_input(monkeypatch):
    """Report a planner ValueError and retain the probability in percent."""
    planner = pytest.importorskip("src.maneuver.planner")
    pytest.importorskip("src.risk.probability")

    def reject_plan(*args, **kwargs):
        """Simulate an invalid UTC maneuver input from the existing planner."""
        raise ValueError("Synthetic invalid planner input")

    monkeypatch.setattr(planner, "plan_maneuver", reject_plan)
    app = _open_guided_replay()
    assert not app.exception
    assert any("Planner unavailable" in item.value and "Synthetic invalid" in item.value for item in app.warning)
    assert any(metric.label == "Estimated collision probability" for metric in app.metric)
    assert all(metric.label != "Estimated propellant consumption" for metric in app.metric)


def test_offline_catalog_avoids_staged_debris_by_default():
    """Apply a simulated UTC burn in offline playback and preserve the collision example."""
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10).run()
    default_counts = {widget.label: widget.value for widget in app.sidebar.number_input}
    assert default_counts["Number of debris objects"] == 10
    assert default_counts["Add simulated debris"] == 0
    app.session_state.simulated_seed = 13
    next(widget for widget in app.sidebar.number_input if widget.label == "Number of debris objects").set_value(0).run()
    next(widget for widget in app.sidebar.number_input if widget.label == "Add simulated debris").set_value(3).run()
    assert not app.exception
    _, avoided = app.session_state.rolling_orbit_window
    assert avoided["burnOffsetS"] is not None
    assert avoided["frames"][-1]["time"] == 6000
    assert not any(frame["impact"] for frame in avoided["frames"])
    assert len(avoided["maneuverPasses"]) == 3
    assert all(
        event["time"] in avoided["encounterTimes"] and event["missKm"] >= avoided["safeMissKm"] == 5
        for event in avoided["maneuverPasses"]
    )
    assert any(
        following["time"] - current["time"] == 1
        for current, following in zip(avoided["frames"], avoided["frames"][1:])
    )
    assert any(
        frame["positions"][0] != frame["nominalPositions"][0]
        for frame in avoided["frames"]
    )
    assert avoided["frames"][-1]["positions"][0] == avoided["frames"][-1]["nominalPositions"][0]

    switch = next(widget for widget in app.sidebar.toggle if widget.label == "Avoid simulated debris")
    switch.set_value(False).run()
    assert not app.exception
    _, original = app.session_state.rolling_orbit_window
    assert original["frames"][-1]["impactKind"] == "simulated"
    assert avoided["frames"][0]["positions"][0] == original["frames"][0]["positions"][0]
    avoided_positions = {frame["time"]: frame["positions"][0] for frame in avoided["frames"]}
    assert any(
        frame["time"] in avoided_positions and avoided_positions[frame["time"]] != frame["positions"][0]
        for frame in original["frames"]
    )


def test_failed_live_debris_request_waits_before_retrying(monkeypatch):
    """Keep the simulation usable during a catalog outage and recover after the cooldown in seconds."""
    import time
    from unittest.mock import Mock

    import requests
    from src.orbits import catalog

    _, primary, debris = load_demo_scenario()
    load = Mock(side_effect=[
        [("SCD 2", primary)], requests.ConnectionError("Debris catalog offline"),
        [("COSMOS 2251 DEB", debris[0])],
    ])
    monkeypatch.setattr(catalog, "load_named_catalog", load)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10).run()
    app.sidebar.toggle[0].set_value(False).run()
    app.sidebar.multiselect[0].set_value([primary.satnum]).run()
    assert any("Debris catalog offline" in warning.value for warning in app.warning)
    assert app.session_state.rolling_orbit_window[1]["labels"] == ["SCD 2"]

    next(w for w in app.sidebar.number_input if w.label == "Add simulated debris").set_value(1).run()
    assert not app.exception
    assert load.call_count == 2
    assert app.session_state.rolling_orbit_window[1]["labels"] == ["SCD 2", "Simulated debris 1"]

    real_clock = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real_clock() + 61)
    app.run()
    assert not app.exception
    assert load.call_count == 3
    assert "COSMOS 2251 DEB" in app.session_state.rolling_orbit_window[1]["labels"]


def test_close_up_of_two_objects_with_identical_orbits():
    """Keep a finite 3D view in km when relative velocity and miss are both zero."""
    scenario, primary, _ = load_demo_scenario()
    encounter = Conjunction(primary.satnum, 99999, datetime.fromisoformat(scenario["start"]), 0, 0)
    frames = _scene_data(close_up_html(primary, primary, encounter, "Co-orbital primary"))["frames"]
    assert all(frame["distance"] == 0 for frame in frames)
    assert frames[0]["positions"][0] != frames[-1]["positions"][0]
