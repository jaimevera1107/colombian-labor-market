import pandas as pd
import pytest

from icml.domain.contracts import (
    IdentityPolicy,
    check_identities_by_provenance,
)
from icml.domain.provenance import ProvenanceCategory

POLICY = IdentityPolicy(
    observed_tolerance_persons=1.0, estimated_tolerance_persons=1e-6
)


def _frame(origin: str, labor_force: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "origin": origin,
                "population": 100.0,
                "working_age": 80.0,
                "labor_force": labor_force,
                "employed": 45.0,
                "unemployed": 5.0,
                "inactive": 80.0 - labor_force,
            }
        ]
    )


def test_rounding_is_tolerated_only_for_observed_rows():
    observed = _frame("geih_observado", 50.9)
    estimated = _frame("RECONSTRUCCION_CON_ANCLA_ANUAL", 50.9)
    reports = check_identities_by_provenance(
        pd.concat([observed, estimated]),
        provenance_column="origin",
        policy=POLICY,
    )
    assert reports[ProvenanceCategory.OBSERVED].passed
    assert not reports[ProvenanceCategory.ANCHORED_RECONSTRUCTION].passed


def test_unknown_labels_and_missing_column_rejected():
    with pytest.raises(KeyError):
        check_identities_by_provenance(
            _frame("UNKNOWN", 50.0), provenance_column="origin", policy=POLICY
        )
    with pytest.raises(KeyError):
        check_identities_by_provenance(
            _frame("geih_observado", 50.0),
            provenance_column="nope",
            policy=POLICY,
        )


def test_negative_policy_rejected():
    with pytest.raises(ValueError):
        IdentityPolicy(
            observed_tolerance_persons=-1.0, estimated_tolerance_persons=0.0
        )
