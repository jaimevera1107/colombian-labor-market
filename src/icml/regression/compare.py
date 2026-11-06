"""Tolerance-based comparison of a migrated table against its RC1 golden.

The migration contract is numerical equivalence within an absolute
tolerance (default ``1e-6`` persons), not byte identity: re-ordering
floating-point operations may legitimately change the last bits.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_ABSOLUTE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Tolerance:
    """Numerical tolerance: ``|candidate - reference| <= abs + rel*|ref|``."""

    absolute: float = DEFAULT_ABSOLUTE_TOLERANCE
    relative: float = 0.0

    def __post_init__(self) -> None:
        """Reject negative tolerances."""
        if self.absolute < 0 or self.relative < 0:
            raise ValueError("Tolerances must be non-negative")


DEFAULT_TOLERANCE = Tolerance()


@dataclass(frozen=True)
class NumericColumnDiff:
    """Differences found in one numeric column."""

    column: str
    max_abs_diff: float
    n_out_of_tolerance: int
    n_missing_mismatch: int

    @property
    def passed(self) -> bool:
        """Return whether the column is within tolerance."""
        return self.n_out_of_tolerance == 0 and self.n_missing_mismatch == 0


@dataclass(frozen=True)
class ComparisonReport:
    """Full comparison result for one artifact."""

    artifact_id: str
    n_rows_reference: int
    n_rows_candidate: int
    missing_columns: tuple[str, ...]
    extra_columns: tuple[str, ...]
    n_missing_keys: int
    n_extra_keys: int
    numeric: tuple[NumericColumnDiff, ...]
    text_mismatches: Mapping[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Return whether the candidate reproduces the reference."""
        return (
            self.n_rows_reference == self.n_rows_candidate
            and not self.missing_columns
            and not self.extra_columns
            and self.n_missing_keys == 0
            and self.n_extra_keys == 0
            and all(diff.passed for diff in self.numeric)
            and not any(self.text_mismatches.values())
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        payload = asdict(self)
        payload["passed"] = self.passed
        payload["text_mismatches"] = dict(self.text_mismatches)
        return payload


def _align(
    reference: pd.DataFrame,
    candidate: pd.DataFrame,
    keys: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame, int, int]:
    """Align two tables on keys (or by position when no keys are given)."""
    if not keys:
        if len(reference) != len(candidate):
            return reference, candidate, 0, 0
        return (
            reference.reset_index(drop=True),
            candidate.reset_index(drop=True),
            0,
            0,
        )

    reference_keyed = reference.set_index(list(keys))
    candidate_keyed = candidate.set_index(list(keys))
    n_missing = int((~reference_keyed.index.isin(candidate_keyed.index)).sum())
    n_extra = int((~candidate_keyed.index.isin(reference_keyed.index)).sum())
    common = reference_keyed.index.intersection(candidate_keyed.index)
    return (
        reference_keyed.loc[common].reset_index(),
        candidate_keyed.loc[common].reset_index(),
        n_missing,
        n_extra,
    )


def _compare_numeric(
    reference: pd.Series, candidate: pd.Series, tolerance: Tolerance
) -> NumericColumnDiff:
    expected = np.array(reference, dtype=float)
    actual = np.array(pd.to_numeric(candidate, errors="coerce"), dtype=float)
    missing_expected, missing_actual = np.isnan(expected), np.isnan(actual)
    both_present = ~missing_expected & ~missing_actual
    difference = np.abs(actual - expected)
    allowed = tolerance.absolute + tolerance.relative * np.abs(expected)
    out_of_tolerance = both_present & (difference > allowed)
    max_diff = (
        float(difference[both_present].max()) if both_present.any() else 0.0
    )
    return NumericColumnDiff(
        column=str(reference.name),
        max_abs_diff=max_diff,
        n_out_of_tolerance=int(out_of_tolerance.sum()),
        n_missing_mismatch=int((missing_expected ^ missing_actual).sum()),
    )


def _count_text_mismatches(reference: pd.Series, candidate: pd.Series) -> int:
    expected = reference.astype("string").fillna("<NA>")
    actual = candidate.astype("string").fillna("<NA>")
    return int((expected.to_numpy() != actual.to_numpy()).sum())


def compare_tables(
    reference: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    artifact_id: str,
    keys: Sequence[str] = (),
    tolerance: Tolerance = DEFAULT_TOLERANCE,
    column_tolerances: Mapping[str, Tolerance] | None = None,
    column_map: Mapping[str, str] | None = None,
    ignore_columns: Sequence[str] = (),
) -> ComparisonReport:
    """Compare a candidate table against its RC1 reference.

    Parameters
    ----------
    reference : pandas.DataFrame
        Golden RC1 table.
    candidate : pandas.DataFrame
        Table produced by the migrated code.
    artifact_id : str
        Identifier reported in the result.
    keys : Sequence[str], optional
        Row-identifying columns (reference names). Empty means positional.
    tolerance : Tolerance, optional
        Default numerical tolerance.
    column_tolerances : Mapping[str, Tolerance], optional
        Per-column overrides, e.g. for rates expressed as fractions.
    column_map : Mapping[str, str], optional
        Candidate-to-reference column renaming, for migrated tables that
        already use canonical names.
    ignore_columns : Sequence[str], optional
        Reference columns excluded from the comparison (documented, never
        silent: they are listed by the caller).

    Returns
    -------
    ComparisonReport
        Structured differences; ``passed`` is the migration gate.
    """
    candidate = candidate.rename(columns=dict(column_map or {}))
    reference = reference.drop(columns=list(ignore_columns), errors="ignore")
    candidate = candidate.drop(columns=list(ignore_columns), errors="ignore")
    missing_columns = tuple(
        c for c in reference.columns if c not in candidate.columns
    )
    extra_columns = tuple(
        c for c in candidate.columns if c not in reference.columns
    )
    shared = [c for c in reference.columns if c in candidate.columns]
    usable_keys = [k for k in keys if k in shared]

    aligned_reference, aligned_candidate, n_missing, n_extra = _align(
        reference[shared], candidate[shared], usable_keys
    )
    overrides = dict(column_tolerances or {})
    numeric: list[NumericColumnDiff] = []
    text: dict[str, int] = {}
    if len(aligned_reference) == len(aligned_candidate):
        for column in shared:
            if column in usable_keys:
                continue
            expected = aligned_reference[column]
            if pd.api.types.is_bool_dtype(
                expected
            ) or not pd.api.types.is_numeric_dtype(expected):
                text[column] = _count_text_mismatches(
                    expected, aligned_candidate[column]
                )
            else:
                numeric.append(
                    _compare_numeric(
                        expected,
                        aligned_candidate[column],
                        overrides.get(column, tolerance),
                    )
                )

    return ComparisonReport(
        artifact_id=artifact_id,
        n_rows_reference=int(len(reference)),
        n_rows_candidate=int(len(candidate)),
        missing_columns=missing_columns,
        extra_columns=extra_columns,
        n_missing_keys=n_missing,
        n_extra_keys=n_extra,
        numeric=tuple(numeric),
        text_mismatches=text,
    )
