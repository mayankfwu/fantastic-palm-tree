import pytest

from src.maneuver.fuel import fuel_used


def test_zero_delta_v_uses_zero_fuel():
    assert fuel_used(0, 500, 220) == 0


def test_fuel_consumption_is_positive():
    assert fuel_used(10, 500, 220) > 0


def test_fuel_increases_with_delta_v():
    low = fuel_used(5, 500, 220)
    high = fuel_used(20, 500, 220)
    assert high > low


def test_fuel_increases_with_spacecraft_mass():
    light = fuel_used(10, 300, 220)
    heavy = fuel_used(10, 500, 220)
    assert heavy > light


def test_invalid_mass():
    with pytest.raises(ValueError):
        fuel_used(10, 0, 220)


def test_invalid_isp():
    with pytest.raises(ValueError):
        fuel_used(10, 500, 0)


def test_negative_delta_v():
    with pytest.raises(ValueError):
        fuel_used(-10, 500, 220)