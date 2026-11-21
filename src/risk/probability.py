"""Collision probability calculations."""

from scipy.stats import ncx2


SIGMA_KM = 1.0


def collision_probability(
    miss_km: float,
    sigma_km: float,
    combined_radius_km: float
) -> float:
    """
    Estimate collision probability using a simplified 2D Gaussian model.

    Parameters:
        miss_km: Nominal miss distance in km.
        sigma_km: One-axis position uncertainty in km.
        combined_radius_km: Combined collision radius in km.

    Returns:
        Estimated collision probability between 0 and 1.
    """

    if miss_km < 0:
        raise ValueError("Miss distance cannot be negative.")

    if sigma_km <= 0:
        raise ValueError("Sigma must be positive.")

    if combined_radius_km <= 0:
        raise ValueError("Combined radius must be positive.")

    noncentrality = (miss_km / sigma_km) ** 2
    radius_term = (combined_radius_km / sigma_km) ** 2

    probability = ncx2.cdf(
        radius_term,
        df=2,
        nc=noncentrality
    )

    return float(probability)