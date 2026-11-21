import pytest

from src.risk.probability import collision_probability


def test_probability_is_between_zero_and_one():
    pc = collision_probability(0.75, 1.0, 0.01)
    assert 0.0 <= pc <= 1.0


def test_probability_decreases_with_distance():
    near = collision_probability(0.1, 1.0, 0.1)
    far = collision_probability(5.0, 1.0, 0.1)
    assert near > far


def test_probability_increases_with_radius():
    small = collision_probability(1.0, 1.0, 0.01)
    large = collision_probability(1.0, 1.0, 0.5)
    assert large > small


def test_invalid_sigma():
    with pytest.raises(ValueError):
        collision_probability(1.0, 0.0, 0.1)


def test_negative_miss_distance():
    with pytest.raises(ValueError):
        collision_probability(-1.0, 1.0, 0.1)