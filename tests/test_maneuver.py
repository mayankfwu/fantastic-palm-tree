from datetime import datetime, timedelta, timezone

import pytest

from src.contracts import Conjunction
from src.maneuver.planner import plan_maneuver


@pytest.fixture
def conjunction():
    return Conjunction(
        primary_id=25544,
        secondary_id=99999,
        tca=datetime.now(timezone.utc) + timedelta(hours=1),
        miss_km=2.0,
        rel_speed_kms=10.0,
    )


def test_maneuver_increases_miss_distance(conjunction):
    result = plan_maneuver(None, conjunction)
    assert result.new_miss_km >= 5.0
    assert result.dv_mps > 0


def test_no_maneuver_when_already_safe(conjunction):
    conjunction.miss_km = 10.0
    result = plan_maneuver(None, conjunction)
    assert result.dv_mps == 0
    assert result.new_miss_km == 10.0


def test_invalid_threshold(conjunction):
    with pytest.raises(ValueError):
        plan_maneuver(None, conjunction, threshold_km=0)


def test_past_tca(conjunction):
    conjunction.tca = datetime.now(timezone.utc) - timedelta(hours=1)
    with pytest.raises(ValueError):
        plan_maneuver(None, conjunction)