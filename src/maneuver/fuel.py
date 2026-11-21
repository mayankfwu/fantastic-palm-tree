"""Fuel consumption calculations using the rocket equation."""

import math


G0 = 9.80665


def fuel_used(dv_mps: float, mass_kg: float, isp_s: float) -> float:
    """
    Calculate propellant consumption using the Tsiolkovsky rocket equation.

    Parameters:
        dv_mps: Required velocity change in m/s.
        mass_kg: Initial spacecraft mass in kg.
        isp_s: Engine specific impulse in seconds.

    Returns:
        Propellant mass consumed in kg.
    """

    if dv_mps < 0:
        raise ValueError("Delta-v cannot be negative.")

    if mass_kg <= 0:
        raise ValueError("Spacecraft mass must be positive.")

    if isp_s <= 0:
        raise ValueError("Specific impulse must be positive.")

    propellant = mass_kg * (
        1 - math.exp(-dv_mps / (isp_s * G0))
    )

    return propellant

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