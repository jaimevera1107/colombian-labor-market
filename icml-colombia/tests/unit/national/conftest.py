import numpy as np
import pandas as pd
import pytest

QUANTITIES = (
    "population",
    "working_age",
    "labor_force",
    "employed",
    "unemployed",
    "inactive",
)


def consistent_levels(employed, unemployed, inactive, population):
    labor_force = employed + unemployed
    return {
        "employed": employed,
        "unemployed": unemployed,
        "inactive": inactive,
        "population": population,
        "labor_force": labor_force,
        "working_age": labor_force + inactive,
    }


@pytest.fixture
def monthly_levels():
    """Five years of positive, identity-consistent monthly levels."""
    rng = np.random.default_rng(20261101)
    periods = pd.period_range("1996-01", "2000-12", freq="M")
    n = len(periods)
    trend = np.linspace(1.0, 1.1, n)
    season = 1 + 0.02 * np.sin(2 * np.pi * np.arange(n) / 12)
    noise = 1 + 0.002 * rng.standard_normal(n)
    levels = consistent_levels(
        employed=10e6 * trend * season * noise,
        unemployed=1.5e6 * trend / season,
        inactive=6e6 * trend,
        population=33e6 * trend,
    )
    frame = pd.DataFrame(levels)
    frame.insert(0, "period", periods.astype(str))
    return frame
