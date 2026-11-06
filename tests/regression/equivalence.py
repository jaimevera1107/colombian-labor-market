"""Shared machinery to compare package outputs with RC1 golden tables."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd

from icml.regression.compare import ComparisonReport, Tolerance, compare_tables

# Ill-conditioned rows (see docs/migration/01_MIGRATION_PLAN.md, phase 4):
# one part per million of the value, plus the default absolute floor.
RELAXED_TOLERANCE = Tolerance(absolute=1e-6, relative=1e-6)
# Model outputs are float32: one unit in the last place is 2**-23 relative.
FLOAT32_EPSILON = 2.0**-23


@dataclass(frozen=True)
class RelaxedRows:
    """Rows compared with ``RELAXED_TOLERANCE`` instead of the default.

    Attributes
    ----------
    column : str
        RC1 column identifying the rows (e.g. ``city_code``).
    values : tuple[int, ...]
        Values of ``column`` whose rows are relaxed.
    columns : tuple[str, ...]
        RC1 columns relaxed on those rows; other columns stay strict.
    reason : str
        Why the rows cannot meet the default tolerance.
    derived : tuple[str, ...]
        Columns that are exact functions of relaxed columns and of exact
        published values (e.g. ``fitted - published``). Near zero, a
        relative tolerance is meaningless, so on relaxed rows they are
        verified through the columns they derive from.
    """

    column: str
    values: tuple[int, ...]
    columns: tuple[str, ...]
    reason: str
    derived: tuple[str, ...] = ()


@dataclass(frozen=True)
class Equivalence:
    """How one package output maps onto one RC1 golden table.

    Attributes
    ----------
    output : str
        Package output name.
    keys : tuple[str, ...]
        RC1 key columns.
    columns : dict[str, str]
        Package-to-RC1 column names; package columns not listed here are
        package-only diagnostics and are not compared.
    reference_filter : tuple[str, str] | None
        Optional ``(column, value)`` selecting the comparable RC1 rows.
    reference_only : tuple[str, ...]
        RC1 columns that belong to archived studies or redundant labels.
    relaxed : RelaxedRows | None
        Documented exception for ill-conditioned rows.
    tolerances : dict[str, Tolerance]
        Documented per-column tolerances (RC1 names) for every row.
    """

    output: str
    keys: tuple[str, ...]
    columns: dict[str, str] = field(default_factory=dict)
    reference_filter: tuple[str, str] | None = None
    reference_only: tuple[str, ...] = ()
    relaxed: RelaxedRows | None = None
    tolerances: dict[str, Tolerance] = field(default_factory=dict)


def compare_equivalence(
    golden_id: str,
    reference: pd.DataFrame,
    candidate: pd.DataFrame,
    equivalence: Equivalence,
    value_maps: Mapping[str, Mapping[str, str]] | None = None,
) -> list[ComparisonReport]:
    """Project both tables onto the shared schema and compare them.

    Returns one report, or two when ``relaxed`` rows are compared apart.
    """
    if equivalence.reference_filter is not None:
        column, value = equivalence.reference_filter
        reference = reference[reference[column] == value]
    reference = reference.drop(columns=list(equivalence.reference_only))
    candidate = candidate[
        [c for c in candidate.columns if c in equivalence.columns]
    ]
    candidate = candidate.rename(columns=equivalence.columns)
    for column, mapping in (value_maps or {}).items():
        candidate[column] = candidate[column].map(
            lambda value, m=mapping: m.get(value, value)
        )
    relaxed = equivalence.relaxed
    base = dict(equivalence.tolerances)
    if relaxed is None:
        return [
            compare_tables(
                reference,
                candidate,
                artifact_id=golden_id,
                keys=equivalence.keys,
                column_tolerances=base,
            )
        ]
    in_reference = reference[relaxed.column].isin(relaxed.values)
    in_candidate = candidate[relaxed.column].isin(relaxed.values)
    strict = compare_tables(
        reference[~in_reference],
        candidate[~in_candidate],
        artifact_id=golden_id,
        keys=equivalence.keys,
        column_tolerances=base,
    )
    loose = compare_tables(
        reference[in_reference].drop(columns=list(relaxed.derived)),
        candidate[in_candidate].drop(columns=list(relaxed.derived)),
        artifact_id=f"{golden_id}[relaxed]",
        keys=equivalence.keys,
        column_tolerances={
            **base,
            **{c: RELAXED_TOLERANCE for c in relaxed.columns},
        },
    )
    return [strict, loose]


def assert_reports(reports: list[ComparisonReport]) -> None:
    """Fail with the full report of the first failing comparison."""
    for report in reports:
        assert report.passed, report.to_dict()
