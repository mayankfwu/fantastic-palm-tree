"""Offline coverage of GP loading, TEME propagation, and encounter screening."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
import requests

from src.orbits import catalog, find_conjunctions, propagate


FIXTURES = Path(__file__).parent
EPOCH = datetime(2026, 11, 21, 12, 11, 7, 584288, tzinfo=UTC)


@pytest.fixture
def gp_response():
    """Return one valid SGP4 OMM record in standard OMM units."""
    return json.loads((FIXTURES / "sample_gp.json").read_text())


def test_cache_refresh_and_skip_invalid(monkeypatch, tmp_path, gp_response, caplog):
    """Parse offline UTC OMM records and refresh a cache after two hours."""
    reply = Mock(status_code=200)
    reply.json.return_value = gp_response + [{}]
    request = Mock(return_value=reply)
    monkeypatch.setattr(catalog.requests, "get", request)
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)
    group = "cosmos-2251-debris"
    for _ in range(2):
        assert [sat.satnum for sat in catalog.load_catalog(group)] == [22675]
    request.assert_called_once_with(
        catalog.GP_URL, params={"GROUP": group, "FORMAT": "JSON"},
        timeout=10, allow_redirects=False,
    )
    assert "Skipping GP record 2" in caplog.text
    stale = catalog.time.time() - 7201
    os.utime(tmp_path / f"{group}.json", (stale, stale))
    assert len(catalog.load_catalog(group)) == 1
    assert request.call_count == 2


@pytest.mark.parametrize("status_code", [403, 429])
def test_download_retries_only_transient_failures(monkeypatch, tmp_path, status_code):
    """Terminate after a unitless HTTP denial, even after a transient failure."""
    request = Mock(side_effect=[requests.Timeout, Mock(status_code=status_code)])
    monkeypatch.setattr(catalog.requests, "get", request)
    monkeypatch.setattr(catalog.time, "sleep", Mock())
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)
    with pytest.raises(requests.HTTPError, match=str(status_code)):
        catalog.load_catalog("cosmos-2251-debris")
    assert request.call_count == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("invalid_records", [[], [{}]])
def test_unusable_download_preserves_cache(monkeypatch, tmp_path, gp_response, invalid_records, caplog):
    """An HTTP 200 with unusable OMM records leaves the previous cache intact."""
    group = "cosmos-2251-debris"
    path = tmp_path / f"{group}.json"
    path.write_text(json.dumps(gp_response))
    stale = catalog.time.time() - 7201
    os.utime(path, (stale, stale))
    reply = Mock(status_code=200)
    reply.json.return_value = invalid_records
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(catalog.requests, "get", Mock(return_value=reply))
    assert [sat.satnum for sat in catalog.load_catalog(group)] == [22675]
    assert "Using stale CelesTrak cache" in caplog.text
    assert json.loads(path.read_text()) == gp_response
    assert path.stat().st_mtime == pytest.approx(stale)


def test_connection_failure_uses_stale_elements(monkeypatch, tmp_path, gp_response, caplog):
    """Use valid cached elements with a warning when the connection fails."""
    group = "cosmos-2251-debris"
    path = tmp_path / f"{group}.json"
    path.write_text(json.dumps(gp_response))
    stale = catalog.time.time() - 7201
    os.utime(path, (stale, stale))
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(catalog.time, "sleep", Mock())
    request = Mock(side_effect=requests.ConnectionError("offline"))
    monkeypatch.setattr(catalog.requests, "get", request)
    assert [sat.satnum for sat in catalog.load_catalog(group)] == [22675]
    assert request.call_count == 3
    assert "offline" in caplog.text and "Using stale CelesTrak cache" in caplog.text


def test_non_json_group_response_names_group(monkeypatch, tmp_path):
    """Explain a plain-text GP reply with the requested group name."""
    group = "unknown-group"
    reply = requests.Response()
    reply.status_code = 200
    reply._content = b"No GP data found"
    request = Mock(return_value=reply)
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(catalog.requests, "get", request)
    with pytest.raises(ValueError, match=f"non-JSON.*{group}"):
        catalog.load_catalog(group)
    request.assert_called_once()


def test_propagate_iss_like():
    """Check TEME array shapes, radius in km, and orbital speed in km/s."""
    from sgp4.api import Satrec, WGS72, jday

    jd, fraction = jday(2026, 11, 21, 12, 0, 0)
    satellite = Satrec()
    satellite.sgp4init(
        WGS72, "i", 25544, jd - 2433281.5 + fraction, 0, 0, 0,
        0.0005, 0, np.radians(51.6), 0, 15.5 * 2 * np.pi / 1440, 0,
    )
    positions, velocities = propagate(satellite, [EPOCH, EPOCH + timedelta(seconds=30)])
    assert positions.shape == velocities.shape == (2, 3)
    np.testing.assert_allclose(np.linalg.norm(positions, axis=1), 6780, atol=35)
    np.testing.assert_allclose(np.linalg.norm(velocities, axis=1), 7.7, atol=0.15)
    with pytest.warns(UserWarning, match="three days"):
        propagate(satellite, [EPOCH + timedelta(days=4)])
    with pytest.raises(ValueError, match="UTC"):
        propagate(satellite, [EPOCH.replace(tzinfo=None)])
    assert propagate(satellite, [])[0].shape == (0, 3)


def test_propagate_masks_errors():
    """Replace failed TEME km and km/s rows while preserving valid rows."""
    satellite = Mock(jdsatepoch=2461365.5, jdsatepochF=0.5)
    velocities = np.ones((3, 3))
    velocities[2, 0] = np.inf
    satellite.sgp4_array.return_value = np.array([0, 6, 0]), np.ones((3, 3)), velocities
    times = [EPOCH + timedelta(seconds=offset) for offset in range(3)]
    position, velocity = propagate(satellite, times)
    np.testing.assert_array_equal(position[0], [1, 1, 1])
    assert np.isnan(position[1:]).all() and np.isnan(velocity[1:]).all()


class LinearObject:
    """Synthetic local TEME state in km and km/s for deterministic screening."""

    a = 1.1
    ecco = 0
    radiusearthkm = 6378
    jdsatepoch = 2461365.5
    jdsatepochF = 0.5

    def __init__(self, satnum, speed, crossing_s, miss_km):
        """Set a constant speed in km/s, crossing in seconds, and miss in km."""
        self.satnum = satnum
        self.speed = speed
        self.crossing_s = crossing_s
        self.miss_km = miss_km

    def sgp4_array(self, jd, fraction):
        """Return synthetic TEME position and velocity over split Julian days."""
        seconds = ((jd - self.jdsatepoch) + (fraction - 0.5)) * 86400
        pos = np.column_stack((
            np.full_like(seconds, 7000 + self.miss_km),
            self.speed * (seconds - self.crossing_s),
            np.zeros_like(seconds),
        ))
        vel = np.tile([0.0, self.speed, 0.0], (len(seconds), 1))
        return np.zeros(len(seconds), dtype=int), pos, vel

    def sgp4(self, jd, fraction):
        """Return a single synthetic TEME state in km and km/s."""
        error, position, velocity = self.sgp4_array(np.array([jd]), np.array([fraction]))
        return error[0], position[0], velocity[0]


def test_screening_refines_between_samples_and_ranks():
    """Recover a sub-grid UTC TCA and rank by refined distance in km."""
    start = EPOCH.replace(minute=0, second=0, microsecond=0)
    primary = LinearObject(1, 0, 0, 0)
    crossing = LinearObject(2, 15, 29, 1)
    wider = LinearObject(3, 15, 83, 3)
    far = LinearObject(4, 15, 45, 9)
    high = LinearObject(5, 15, 29, 1)
    high.a = 1.5
    result = find_conjunctions(
        primary, [primary, wider, crossing, far, high], start, 1 / 30, 60, 5,
    )
    assert [item.secondary_id for item in result] == [2, 3]
    assert (result[0].tca - start).total_seconds() == pytest.approx(29, abs=0.001)
    assert result[0].miss_km == pytest.approx(1, abs=0.0001)
    assert result[0].rel_speed_kms == pytest.approx(15)


def test_screening_rejects_nonfinite_refinement_velocity(monkeypatch):
    """A failed scalar state cannot yield a conjunction with a NaN speed."""
    start = EPOCH.replace(minute=0, second=0, microsecond=0)
    primary = LinearObject(1, 0, 0, 0)
    secondary = LinearObject(2, 15, 29, 1)
    scalar_sgp4 = secondary.sgp4

    def invalid_velocity(jd, fraction):
        """Return a finite TEME position with an unusable velocity in km/s."""
        error, position, _ = scalar_sgp4(jd, fraction)
        return error, position, [np.nan, 0, 0]

    monkeypatch.setattr(secondary, "sgp4", invalid_velocity)
    assert find_conjunctions(primary, [secondary], start, 1 / 60, 60, 5) == []


def test_frozen_demo_matches_reference_and_local_minimum():
    """Check offline replay, UTC TCA, and smooth TEME separation near TCA."""
    from src.orbits.demo import SCENARIO_PATH, replay_demo
    from src.orbits.user_catalog import _satellite_from_omm

    scenario = json.loads(SCENARIO_PATH.read_text())
    with pytest.warns(UserWarning, match="three days"):
        result = replay_demo()
    assert [item.secondary_id for item in result] == [34387, 36048]
    for actual, expected in zip(result, scenario["conjunctions"], strict=True):
        expected_tca = datetime.fromisoformat(expected["tca"])
        assert (actual.tca - expected_tca).total_seconds() == pytest.approx(0, abs=0.005)
        assert actual.miss_km == pytest.approx(expected["miss_km"], abs=0.001)
        assert actual.rel_speed_kms == pytest.approx(expected["rel_speed_kms"], abs=0.001)

    closest = result[0]
    primary = _satellite_from_omm(scenario["primary_omm"])
    raw = json.loads(SCENARIO_PATH.with_name(scenario["debris_file"]).read_text())
    secondary = _satellite_from_omm(next(row for row in raw if row["NORAD_CAT_ID"] == 34387))
    times = [closest.tca + timedelta(milliseconds=100 * index) for index in range(-5, 6)]
    primary_position, _ = propagate(primary, times)
    secondary_position, _ = propagate(secondary, times)
    distances = np.linalg.norm(primary_position - secondary_position, axis=1)
    assert np.all(np.diff(distances[:6]) < 0)
    assert np.all(np.diff(distances[5:]) > 0)
    assert distances[5] == pytest.approx(closest.miss_km, abs=0.001)

    start = datetime.fromisoformat(scenario["start"])
    offset_s = (closest.tca - start).total_seconds()
    assert 0 < offset_s % scenario["step_s"] < scenario["step_s"]
    reference_tca = datetime(2026, 11, 23, 14, 2, 52, 908000, tzinfo=UTC)
    assert abs((closest.tca - reference_tca).total_seconds()) < 0.1
    assert abs(closest.miss_km - 0.625) < 0.1


def test_fake_conjunction_matches_contract():
    """Deserialize the synthetic encounter with UTC TCA, km, and km/s."""
    from src.contracts import Conjunction

    fixture = FIXTURES.parent / "data" / "fixtures" / "fake_conjunction.json"
    fields = json.loads(fixture.read_text())
    fields["tca"] = datetime.fromisoformat(fields["tca"])
    conjunction = Conjunction(**fields)
    assert conjunction.tca.utcoffset() == timedelta(0)
    assert conjunction.miss_km == 0.75


def test_socrates_same_input_epochs():
    """Reproduce the published UTC TCA, miss in km, and speed in km/s."""
    from csv import DictReader

    from src.orbits.user_catalog import _satellite_from_omm

    with (FIXTURES / "socrates_scd2_gp.csv").open(newline="") as elements:
        primary, secondary = map(_satellite_from_omm, DictReader(elements))
    start = datetime(2026, 11, 23, 14, tzinfo=UTC)
    with pytest.warns(UserWarning, match="three days"):
        (result,) = find_conjunctions(primary, [secondary], start, 0.1, 30, 5)
    assert result.tca.second + result.tca.microsecond / 1e6 == pytest.approx(52.908, abs=0.002)
    assert result.tca.minute == 2
    assert result.miss_km == pytest.approx(0.625, abs=0.001)
    assert result.rel_speed_kms == pytest.approx(10.327, abs=0.001)


def test_finite_burn_changes_velocity_gradually_and_rejoins_nominal():
    """Check TEME displacement in km and velocity offset in km/s at a UTC rejoin."""
    from src.orbits.demo import load_demo_scenario
    from src.orbits.impulse import RECOVERY_DURATION_S, after_along_track_burn

    _, satellite, _ = load_demo_scenario()
    burn = EPOCH
    recovery = burn + timedelta(minutes=15)
    rejoin = recovery + timedelta(seconds=RECOVERY_DURATION_S)
    times = [burn, burn + timedelta(seconds=0.1), burn + timedelta(seconds=60),
             recovery, rejoin - timedelta(seconds=0.1), rejoin, rejoin + timedelta(seconds=0.1)]
    sample = after_along_track_burn(satellite, burn, times[-1], 10.0, recovery_time=recovery)
    offsets = sample(times) - propagate(satellite, times)[0]
    np.testing.assert_array_equal(offsets[0], np.zeros(3))
    assert np.linalg.norm(offsets[1]) / 0.1 < 1e-5
    assert np.linalg.norm(offsets[2]) > 0.1
    assert np.linalg.norm(offsets[3]) > 1
    assert np.linalg.norm(offsets[5] - offsets[4]) / 0.1 < 1e-5
    np.testing.assert_array_equal(offsets[5:], np.zeros((2, 3)))


def test_staged_debris_has_independent_orbital_speed():
    """Check distinct debris velocities in km/s at the UTC staged contacts."""
    from src.orbits.demo import load_demo_scenario
    from src.orbits.simulation import place_simulated_debris, simulated_positions

    _, satellite, _ = load_demo_scenario()
    placements = place_simulated_debris(3, 1, EPOCH, 13)
    speed_factors = []
    for item in placements:
        contact = item.contact_time
        delta = timedelta(milliseconds=100)
        before, hit, after = simulated_positions(item, satellite, [contact - delta, contact, contact + delta])
        position, velocity = propagate(satellite, [contact])
        np.testing.assert_allclose(hit, position[0], atol=1e-8)
        debris_velocity = (after - before) / 0.2
        assert debris_velocity @ velocity[0] < 0
        circular_speed = np.sqrt(satellite.mu / np.linalg.norm(position[0]))
        speed_factors.append(np.linalg.norm(debris_velocity) / circular_speed)
    np.testing.assert_allclose(speed_factors, [item.speed_factor for item in placements], atol=1e-7)
    assert len(set(np.round(speed_factors, 6))) == len(placements)
