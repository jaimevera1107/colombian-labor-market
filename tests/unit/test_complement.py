import numpy as np
import pandas as pd
import pytest

from icml.evaluation.complement import (
    ComplementError,
    build_department,
    observed_rest,
    ratios,
)

PERIODS = [f"2010-{m:02d}" for m in range(1, 13)]


def _levels(scale, unemployment=0.1):
    frame = pd.DataFrame(index=PERIODS)
    frame["population"] = 100.0 * scale
    frame["working_age"] = 80.0 * scale
    frame["labor_force"] = 50.0 * scale
    frame["unemployed"] = frame["labor_force"] * unemployment
    frame["employed"] = frame["labor_force"] - frame["unemployed"]
    frame["inactive"] = frame["working_age"] - frame["labor_force"]
    return frame


def test_build_department_adds_capital_and_rest_with_identities():
    capital = _levels(1.0)
    population = pd.Series(300.0, index=PERIODS)
    rest = ratios(_levels(2.0, unemployment=0.05))
    department = build_department(capital, population, rest)
    np.testing.assert_allclose(department["population"], 300.0)
    np.testing.assert_allclose(
        department["unemployed"], 5.0 + 200 * 0.8 * 0.625 * 0.05
    )
    np.testing.assert_allclose(
        department["working_age"],
        department["employed"]
        + department["unemployed"]
        + department["inactive"],
    )


def test_build_department_rejects_capital_larger_than_department():
    with pytest.raises(ComplementError):
        build_department(
            _levels(1.0), pd.Series(50.0, index=PERIODS), ratios(_levels(1.0))
        )


def _long(frame, code, key):
    out = frame.reset_index().rename(columns={"index": "period"})
    out.insert(0, key, code)
    return out


def test_observed_rest_uses_annual_means():
    departments = _long(_levels(3.0), 5, "dep_code")
    cities = _long(_levels(1.0), 5, "city_code")
    rest = observed_rest(departments, cities)
    assert rest.index.names == ["dep_code", "year"]
    assert rest.loc[(5, "2010"), "population"] == pytest.approx(200.0)


def test_observed_rest_rejects_non_positive_annual_rest():
    departments = _long(_levels(1.0), 5, "dep_code")
    cities = _long(_levels(1.0), 5, "city_code")
    with pytest.raises(ComplementError):
        observed_rest(departments, cities)


def test_proportional_rule_matches_the_national_and_shares_by_size():
    """The proportional allocation reproduces the national exactly."""
    import numpy as np

    from icml.reconciliation.representativeness import (
        RepresentativenessBuilder,
        RepresentativenessPolicy,
    )

    periods = [f"2021-{m:02d}" for m in range(1, 13)]
    represented = {
        5: pd.DataFrame(
            {
                "employed": 900.0,
                "unemployed": 100.0,
                "inactive": 500.0,
                "population": 2000.0,
            },
            index=periods,
        ),
        11: pd.DataFrame(
            {
                "employed": 90.0,
                "unemployed": 10.0,
                "inactive": 50.0,
                "population": 200.0,
            },
            index=periods,
        ),
    }
    national = pd.DataFrame(
        {
            "period": periods,
            "employed": 1100.0,
            "unemployed": 110.0,
            "inactive": 550.0,
            "population": 2200.0,
        }
    )
    policy = RepresentativenessPolicy(
        fully_urban_codes=[11],
        partial_codes=[],
        excluded_donor_codes=[],
        capitals_in_national_from="2014-01",
        population_strength=1.0,
        employed_strength=1.0,
        unemployed_strength=1.0,
        inactive_strength=1.0,
        joint_tolerance_persons=1e-3,
        reconcile_from="2001-01",
        population_from_projection_before="1900-01",
        residual_allocation="proportional",
    )
    builder = RepresentativenessBuilder(policy)
    adjusted, diagnostics = builder._allocate_proportionally(
        represented, national, periods
    )
    total = sum(frame["employed"] for frame in adjusted.values())
    np.testing.assert_allclose(total, 1100.0)
    # The residual (110) is shared by size: 10/11 to the larger unit.
    np.testing.assert_allclose(adjusted[5]["employed"], 1000.0)
    np.testing.assert_allclose(adjusted[11]["employed"], 100.0)
    assert diagnostics["residual_allocation"] == "proportional"
