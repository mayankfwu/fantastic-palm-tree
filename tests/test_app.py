"""Verify the offline app, 3D playback, and the simulated impact."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.contracts import Conjunction
from src.orbits.demo import load_demo_scenario
from src.viz.encounter import close_up_html, orbit_html, orbit_window


def _scene_data(html):
    """Read the embedded scene data with positions in km and times in seconds."""
    return json.JSONDecoder().raw_decode(html.split("} = ", 1)[1])[0]


def test_offline_demo_switches_encounter_view_and_impact():
    """Verify the selected encounter, km separation, 3D close-up, and impact mode."""
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10).run()
    assert not app.exception
    assert app.radio[0].value == "3D orbit"
    assert app.metric[0].value == "581"
    assert "90 of 581 debris element sets" in app.warning[0].value
    assert any("SCD 2 2.3 days · Debris 2.6 days" in caption.value for caption in app.caption)
    assert list(app.dataframe[0].value["Debris NORAD ID"]) == [34387, 36048]
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

    html = close_up_html(primary, secondary, encounter, "SCD 2", simulate_impact=True)
    frames = _scene_data(html)["frames"]
    impact = frames[-1]
    assert impact["time"] == 0
    assert impact["impact"]
    assert impact["distance"] == pytest.approx(0)
    assert impact["positions"][0] == pytest.approx(impact["positions"][1])
    assert all(before != after for before, after in zip(frames[0]["positions"], impact["positions"]))


def test_live_mode_selects_named_satellites_and_samples_debris(monkeypatch):
    """Verify a live selection and a stable random debris count without network access."""
    from unittest.mock import Mock

    from src.orbits import catalog

    _, primary, debris = load_demo_scenario()
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
    assert [call.args[0] for call in load.call_args_list] == ["stations", "cosmos-2251-debris"]


def test_offline_catalog_supports_selection_with_network_disabled(monkeypatch):
    """Use bundled named objects with a fixed UTC start and no catalog requests."""
    from unittest.mock import Mock

    from src.orbits import catalog

    network = Mock(side_effect=AssertionError("offline catalog must not request live data"))
    monkeypatch.setattr(catalog.requests, "get", network)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10).run()
    app.sidebar.radio[0].set_value("Offline catalog").run()
    assert not app.exception
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

    from src.viz import encounter

    event = Conjunction(primary.satnum, debris[0].satnum, start + timedelta(seconds=31.25), 0.005, 10.0)
    monkeypatch.setattr(encounter, "find_conjunctions", lambda *args, **kwargs: [event])
    contact = orbit_window(satellites, objects, start, 0)
    assert [frame["time"] for frame in contact["frames"]] == [0, 31.25]
    assert contact["frames"][-1]["impact"]
    assert contact["frames"][-1]["impactObject"] == 0


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
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10).run()
    control = next(widget for widget in app.sidebar.number_input if widget.label == "Add simulated debris")
    assert control.max == 15
    control.set_value(15).run()
    assert not app.exception
    assert app.session_state.rolling_orbit_window[1]["simulatedCount"] == 15
    assert app.dataframe[0].value["Miss (km)"].iloc[0] == pytest.approx(0.662, abs=0.001)
