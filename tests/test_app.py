"""Verify the offline app, 3D playback, and the simulated impact."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.contracts import Conjunction
from src.orbits.demo import load_demo_scenario
from src.viz.encounter import close_up_html, orbit_html


def _scene_data(html):
    """Read the embedded scene data with positions in km and times in seconds."""
    return json.JSONDecoder().raw_decode(html.split("const {frames, labels, earthRadiusKm} = ", 1)[1])[0]


def test_offline_demo_switches_encounter_view_and_impact():
    """Verify the selected encounter, km separation, 3D close-up, and impact mode."""
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=10).run()
    assert not app.exception
    assert app.radio[0].value == "3D orbit"
    assert app.metric[0].value == "581"
    assert list(app.dataframe[0].value["Debris NORAD ID"]) == [34387, 36048]
    assert app.radio[0].options == ["3D orbit", "3D close-up"]
    orbit = _scene_data(app.get("iframe")[0].proto.srcdoc)
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
