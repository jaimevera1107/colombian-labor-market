import pandas as pd
import pytest

from icml.national.reference import ReferenceNationalError, reference_national
from icml.urban.synthetic import (
    SyntheticSignalBuilder,
    SyntheticSignalError,
    SyntheticSignalPolicy,
)

POLICY = SyntheticSignalPolicy(
    recipient_code=25,
    donor_code=11,
    recipient_name="Synthetic",
    donor_name="Donor",
    calibration_years=[2021, 2022, 2023, 2024],
    first_year=2007,
    last_year=2024,
    max_official_anchor_adjustment_persons=5.0,
)


def test_frozen_record_must_match_policy():
    frozen = {
        "recipient_code": 25,
        "donor_code": 5,
        "calibration_years": [2021, 2022, 2023, 2024],
        "ratio_by_variable": {},
    }
    with pytest.raises(SyntheticSignalError, match="does not match"):
        SyntheticSignalBuilder(POLICY, frozen, 1000.0)


def _national():
    periods = pd.period_range("1993-01", "2002-12", freq="M").astype(str)
    frame = pd.DataFrame({"period": periods})
    for column, value in (
        ("employed", 10.0),
        ("unemployed", 1.0),
        ("inactive", 6.0),
        ("labor_force", 11.0),
        ("working_age", 17.0),
        ("population", 30.0),
    ):
        frame[column] = value
    return frame


def test_reference_national_uses_reconciled_history():
    combined = _national()
    combined["provenance"] = ["anchored_reconstruction"] * 96 + [
        "observed"
    ] * 24
    reconciled = _national().iloc[:96].copy()
    reconciled["employed"] = 9.0
    result = reference_national(combined, reconciled, "2001-12")
    assert len(result) == 108
    assert (result.loc[result["period"] < "2001-01", "employed"] == 9).all()
    assert (result.loc[result["period"] >= "2001-01", "employed"] == 10).all()


def test_reference_national_rejects_interleaved_provenance():
    combined = _national()
    combined["provenance"] = ["observed", "anchored_reconstruction"] * 60
    with pytest.raises(ReferenceNationalError, match="precede"):
        reference_national(combined, _national(), "2002-12")
