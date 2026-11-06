"""Reader of the DANE monthly labor-market annex (GEIH).

The annex sheets contain stacked regional blocks::

    <region name>
    <subtitle>
    Concepto | <year>  ...
             | Ene  Feb ...
    <concept> | value value ...
    ...
    Fuerza de trabajo potencial | ...

Parsing is split in two layers: :func:`parse_labor_blocks` works on an
in-memory cell matrix (pure, testable without Excel), and
:class:`GeihAnnexReader` handles the workbook and the national extraction.
Published values are in thousands of persons; they are rounded to four
decimals and scaled to persons exactly as in RC1.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from icml.domain.periods import MonthlyPeriod
from icml.national.schema import PERIOD_COLUMN, QUANTITY_COLUMNS

# Number of rows between the region name and the block marker, and between
# the marker and the first data row, in the DANE layout.
_REGION_OFFSET_ROWS = 2
_DATA_OFFSET_ROWS = 2


class AnnexFormatError(ValueError):
    """Raised when an annex sheet does not follow the expected layout."""


@dataclass(frozen=True)
class GeihAnnexSpec:
    """Layout and extraction settings of the national monthly annex.

    Attributes
    ----------
    sheet_name : str
        Worksheet holding the monthly national blocks.
    region : str
        Block (region) to extract.
    start_period : str
        ``YYYY-MM`` of the first data column.
    block_marker : str
        Text in the first column that opens a block.
    block_end_marker : str
        Concept that closes a block (inclusive).
    value_decimals : int
        Rounding applied to published values before scaling.
    scale_factor : float
        Multiplier from published units to persons.
    concepts : Mapping[str, str]
        Published concept label to canonical quantity name.
    """

    sheet_name: str
    region: str
    start_period: str
    block_marker: str
    block_end_marker: str
    value_decimals: int
    scale_factor: float
    concepts: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the specification."""
        MonthlyPeriod.parse(self.start_period)
        if self.scale_factor <= 0:
            raise ValueError("scale_factor must be positive")
        if sorted(self.concepts.values()) != sorted(QUANTITY_COLUMNS):
            raise ValueError(
                "concepts must map exactly the six labor quantities"
            )


def _clean(value: object) -> str:
    return str(value).strip()


def parse_labor_blocks(
    cells: pd.DataFrame,
    *,
    start_period: str,
    block_marker: str,
    block_end_marker: str,
    value_decimals: int | None,
) -> pd.DataFrame:
    """Convert a sheet's cell matrix into a long table of block values.

    Parameters
    ----------
    cells : pandas.DataFrame
        Raw cells of the sheet (no header row), positional columns.
    start_period : str
        Period assigned to the first data column of every block.
    block_marker : str
        Case-insensitive text opening a block in the first column.
    block_end_marker : str
        Case-insensitive concept closing a block (included).
    value_decimals : int | None
        Decimals kept when converting values to numbers; ``None`` keeps the
        stored values unrounded.

    Returns
    -------
    pandas.DataFrame
        Columns ``region``, ``concept``, ``period`` and ``value``. Cells
        that are not numeric become NaN; nothing is imputed.

    Raises
    ------
    AnnexFormatError
        If no block is found.
    """
    first_column = cells.iloc[:, 0].map(_clean).str.lower()
    marker = block_marker.strip().lower()
    end_marker = block_end_marker.strip().lower()
    n_value_columns = cells.shape[1] - 1
    start = MonthlyPeriod.parse(start_period)
    periods = [str(start.shift(k)) for k in range(n_value_columns)]

    blocks: list[pd.DataFrame] = []
    row = 0
    n_rows = len(cells)
    while row < n_rows:
        if first_column.iloc[row] != marker or row < _REGION_OFFSET_ROWS:
            row += 1
            continue
        region = _clean(cells.iloc[row - _REGION_OFFSET_ROWS, 0])
        data_start = row + _DATA_OFFSET_ROWS
        data_end = data_start
        while data_end < n_rows:
            data_end += 1
            if first_column.iloc[data_end - 1] == end_marker:
                break
        block = cells.iloc[data_start:data_end]
        block = block[block.iloc[:, 0].notna()]
        values = block.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")
        if value_decimals is not None:
            values = values.round(value_decimals)
        values.columns = periods
        values.insert(0, "concept", block.iloc[:, 0].map(_clean))
        long = values.melt(
            id_vars="concept", var_name=PERIOD_COLUMN, value_name="value"
        )
        long.insert(0, "region", region)
        blocks.append(long)
        row = data_end

    if not blocks:
        raise AnnexFormatError(f"No block opened by {block_marker!r}")
    return pd.concat(blocks, ignore_index=True)


def extract_region_quantities(
    blocks: pd.DataFrame,
    *,
    region: str,
    concepts: Mapping[str, str],
    scale_factor: float,
) -> pd.DataFrame:
    """Pivot one region's labor concepts into a monthly wide table.

    Months where any of the six quantities is missing are dropped (they
    correspond to empty trailing columns of the sheet); the remaining
    periods must be contiguous.

    Raises
    ------
    AnnexFormatError
        If the region or a concept is missing, or months have gaps.
    """
    subset = blocks[blocks["region"] == region]
    if subset.empty:
        raise AnnexFormatError(f"Region not found in annex: {region!r}")
    subset = subset[subset["concept"].isin(list(concepts))]
    missing = sorted(set(concepts) - set(subset["concept"]))
    if missing:
        raise AnnexFormatError(f"Concepts not found for {region}: {missing}")
    duplicated = subset.duplicated(subset=["concept", PERIOD_COLUMN]).any()
    if duplicated:
        raise AnnexFormatError(f"Region {region!r} appears more than once")

    # ``pivot`` (not ``pivot_table``) never aggregates: duplicates were
    # rejected above, so every cell maps to exactly one published value.
    wide = subset.pivot(index=PERIOD_COLUMN, columns="concept", values="value")
    wide = wide.rename(columns=dict(concepts))[list(QUANTITY_COLUMNS)]
    wide = wide.dropna(how="any").sort_index()
    if wide.empty:
        raise AnnexFormatError(f"No complete month for {region!r}")
    expected = pd.period_range(wide.index[0], wide.index[-1], freq="M")
    if list(wide.index) != list(expected.astype(str)):
        raise AnnexFormatError(f"Non-contiguous months for {region!r}")
    scaled = wide * scale_factor
    if not np.isfinite(scaled.to_numpy(dtype=float)).all():
        raise AnnexFormatError("Non-finite values after scaling")
    return scaled.reset_index().rename_axis(columns=None)


class GeihAnnexReader:
    """Read national monthly quantities from a GEIH annex workbook."""

    def __init__(self, spec: GeihAnnexSpec) -> None:
        """Store the layout specification."""
        self._spec = spec

    def read_national_monthly(self, path: Path) -> pd.DataFrame:
        """Return the six national quantities, in persons, by month.

        Raises
        ------
        FileNotFoundError
            If the workbook does not exist.
        AnnexFormatError
            If the sheet layout is not the expected one.
        """
        if not path.is_file():
            raise FileNotFoundError(path)
        cells = pd.read_excel(
            path, sheet_name=self._spec.sheet_name, header=None
        )
        blocks = parse_labor_blocks(
            cells,
            start_period=self._spec.start_period,
            block_marker=self._spec.block_marker,
            block_end_marker=self._spec.block_end_marker,
            value_decimals=self._spec.value_decimals,
        )
        return extract_region_quantities(
            blocks,
            region=self._spec.region,
            concepts=self._spec.concepts,
            scale_factor=self._spec.scale_factor,
        )
