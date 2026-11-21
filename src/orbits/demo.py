"""Replay the frozen SCD 2 conjunction screen without network access."""

import json
from datetime import datetime
from pathlib import Path

from sgp4.api import Satrec

from src.contracts import Conjunction

from .catalog import _parse_records
from .screening import find_conjunctions
from .user_catalog import _satellite_from_omm

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "demo_scd2.json"


def load_demo_scenario() -> tuple[dict, Satrec, list[Satrec]]:
    """Load the snapshot settings and SGP4 models with UTC epochs."""
    scenario = json.loads(SCENARIO_PATH.read_text())
    debris_records = json.loads(SCENARIO_PATH.with_name(scenario["debris_file"]).read_text())
    primary = _satellite_from_omm(scenario["primary_omm"])
    debris = [_satellite_from_omm(record) for record in debris_records]
    return scenario, primary, debris


def load_offline_catalogs() -> tuple[datetime, list[tuple[str, Satrec]], list[tuple[str, Satrec]]]:
    """Load bundled, named models in TEME with a fixed UTC playback start."""
    scenario = json.loads(SCENARIO_PATH.read_text())
    stations = json.loads(SCENARIO_PATH.with_name("offline_stations.json").read_text())
    debris = json.loads(SCENARIO_PATH.with_name(scenario["debris_file"]).read_text())
    return (
        datetime.fromisoformat(scenario["start"]),
        _parse_records([scenario["primary_omm"], *stations], "offline satellites"),
        _parse_records(debris, "offline COSMOS 2251"),
    )


def replay_demo() -> list[Conjunction]:
    """Return frozen-demo encounters with UTC TCA, km, and km/s."""
    scenario, primary, debris = load_demo_scenario()
    return find_conjunctions(
        primary, debris, datetime.fromisoformat(scenario["start"]),
        scenario["hours"], scenario["step_s"], scenario["screen_km"],
    )
