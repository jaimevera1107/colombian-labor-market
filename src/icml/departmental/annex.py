"""Extraction of official annual anchors from the DANE departmental annex.

The annex sheet stacks one block per department: a title row naming the
department, a ``Concepto`` row followed (possibly on the next row) by the
calendar years, and one row per concept. Parsing is fail-closed: unknown
titles, repeated years, missing concepts, non-numeric cells and impossible
values are errors. Nothing is imputed.

Workbook reading prefers ``.xlsx`` via openpyxl; legacy binary ``.xls``
remains supported via xlrd. Both are parsed by the same strict validator.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from icml.domain.quantities import LaborQuantity
from icml.domain.territories import load_territories

RATE_SUFFIX = "_rate"
MAX_RATE_PERCENT = 100.0
_YEAR_PATTERN = re.compile(r"(?:ano|año)?\s*(19\d{2}|20\d{2})")
_MIN_YEAR, _MAX_YEAR = 1990, 2100


class DepartmentAnnexError(ValueError):
    """Raised when the departmental annex violates its expected layout."""


@dataclass(frozen=True)
class DepartmentAnnexSpec:
    """Layout and extraction settings of the departmental annex."""

    sheet_name: str
    block_marker: str
    marker_search_columns: int
    title_search_rows: int
    year_search_rows: int
    published_unit_persons: float
    first_year: int
    last_year: int
    anchored_codes: Sequence[int]
    missing_markers: Sequence[str]
    title_prefix_pattern: str
    aliases: Mapping[str, int] = field(default_factory=dict)
    concepts: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Require patterns for the six labor quantities."""
        missing = {str(q) for q in LaborQuantity} - set(self.concepts)
        if missing:
            raise ValueError(f"Concept patterns missing: {sorted(missing)}")


def normalize_label(value: object) -> str:
    """Lower-case, accent-free, single-spaced text."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"\s+", " ", text.strip())


def _territory_key(label: str) -> str:
    return normalize_label(label).replace(".", "").strip(" :")


def parse_year(value: object) -> int | None:
    """Return a calendar year from a header cell, or None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        number = float(value)
        if number.is_integer() and _MIN_YEAR <= int(number) <= _MAX_YEAR:
            return int(number)
        return None
    match = _YEAR_PATTERN.fullmatch(normalize_label(value))
    return int(match.group(1)) if match else None


def parse_number(
    value: object, missing_markers: Sequence[str]
) -> float | None:
    """Return a finite number from a data cell, or None.

    A comma is accepted as decimal separator only when no dot is present;
    thousands separators are never guessed.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str):
        text = value.strip().replace("\u00a0", "")
        if text in set(missing_markers):
            return None
        if re.fullmatch(r"-?\d+(?:,\d+)?", text):
            return float(text.replace(",", "."))
        if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
            return float(text)
    return None


@dataclass(frozen=True)
class _Block:
    header_row: int
    concept_column: int
    dane_code: int
    years: Mapping[int, int]


class DepartmentAnnexParser:
    """Parse department blocks from an in-memory cell matrix."""

    def __init__(self, spec: DepartmentAnnexSpec) -> None:
        """Build the title lookup from the territorial catalog."""
        self._spec = spec
        lookup = {
            _territory_key(t.name): t.dane_code for t in load_territories()
        }
        lookup.update({_territory_key(k): v for k, v in spec.aliases.items()})
        self._territories = lookup
        self._names = {t.dane_code: t.name for t in load_territories()}
        self._concepts = {k: re.compile(p) for k, p in spec.concepts.items()}
        self._prefix = re.compile(spec.title_prefix_pattern)

    def _territory(self, value: object) -> int | None:
        key = self._prefix.sub("", normalize_label(value).strip(":"))
        return self._territories.get(_territory_key(key))

    def _concept(self, value: object) -> str | None:
        label = normalize_label(value)
        for name, pattern in self._concepts.items():
            if pattern.fullmatch(label):
                return name
        return None

    @staticmethod
    def _years(row: Sequence[Any], start: int, line: int) -> dict[int, int]:
        years: dict[int, int] = {}
        for column in range(start, len(row)):
            year = parse_year(row[column])
            if year is None:
                continue
            if year in years.values():
                raise DepartmentAnnexError(
                    f"Duplicated year in row {line + 1}: {year}"
                )
            years[column] = year
        return years

    def _blocks(self, rows: Sequence[Sequence[Any]]) -> list[_Block]:
        spec = self._spec
        marker = spec.block_marker.casefold()
        blocks: list[_Block] = []
        for line, row in enumerate(rows):
            for column, value in enumerate(row[: spec.marker_search_columns]):
                if normalize_label(value) != marker:
                    continue
                years = self._years(row, column + 1, line)
                if not years:
                    for nearby in range(
                        line + 1,
                        min(line + 1 + spec.year_search_rows, len(rows)),
                    ):
                        years = self._years(rows[nearby], column + 1, nearby)
                        if years:
                            break
                if not years:
                    continue
                titles = [
                    code
                    for previous in range(
                        max(0, line - spec.title_search_rows), line
                    )
                    for cell in rows[previous][: spec.marker_search_columns]
                    if (code := self._territory(cell)) is not None
                ]
                if not titles:
                    raise DepartmentAnnexError(
                        f"Unidentified department above row {line + 1}"
                    )
                blocks.append(_Block(line, column, titles[-1], years))
                break
        return blocks

    def parse(self, rows: Sequence[Sequence[Any]]) -> pd.DataFrame:
        """Return one record per department, year and concept.

        Columns: ``dane_code``, ``department``, ``year``, ``concept``,
        ``label``, ``value``, ``unit``, ``source_row``, ``source_column``.

        Raises
        ------
        DepartmentAnnexError
            On any layout or value violation.
        """
        if not rows:
            raise DepartmentAnnexError("Empty sheet")
        blocks = self._blocks(rows)
        records: list[dict[str, Any]] = []
        required = {str(q) for q in LaborQuantity}
        for position, block in enumerate(blocks):
            end = (
                blocks[position + 1].header_row
                if position + 1 < len(blocks)
                else len(rows)
            )
            seen: set[str] = set()
            name = self._names[block.dane_code]
            for line in range(block.header_row + 1, end):
                row = rows[line]
                label = (
                    row[block.concept_column]
                    if len(row) > block.concept_column
                    else None
                )
                concept = self._concept(label)
                if concept is None:
                    continue
                if concept in seen:
                    raise DepartmentAnnexError(
                        f"Repeated concept {concept} for {name}"
                    )
                seen.add(concept)
                for column, year in block.years.items():
                    value = parse_number(
                        row[column] if len(row) > column else None,
                        self._spec.missing_markers,
                    )
                    if value is None:
                        raise DepartmentAnnexError(
                            f"Missing value: {name} {year} {concept}"
                        )
                    is_rate = concept.endswith(RATE_SUFFIX)
                    if is_rate and not 0 <= value <= MAX_RATE_PERCENT:
                        raise DepartmentAnnexError(
                            f"Rate outside [0, 100]: {name} {year}"
                        )
                    if not is_rate and value < 0:
                        raise DepartmentAnnexError(
                            f"Negative quantity: {name} {year} {concept}"
                        )
                    records.append(
                        {
                            "dane_code": block.dane_code,
                            "department": name,
                            "year": year,
                            "concept": concept,
                            "label": str(label),
                            "value": value,
                            "unit": "percent" if is_rate else "published_unit",
                            "source_row": line + 1,
                            "source_column": column + 1,
                        }
                    )
            missing = required - seen
            if missing:
                raise DepartmentAnnexError(
                    f"Missing concepts for {name}: {sorted(missing)}"
                )
        table = pd.DataFrame(records)
        if table.duplicated(subset=["dane_code", "year", "concept"]).any():
            raise DepartmentAnnexError("Duplicated department blocks")
        return table


def read_sheet_rows(path: Path, sheet_name: str) -> list[list[Any]]:
    """Read DANE department annexes in XLSX or the legacy XLS format.

    XLSX is the preferred production input, with stored numeric values and
    no spreadsheet formula evaluation or implicit conversion of labels.
    """
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook

        book = load_workbook(path, read_only=True, data_only=True)
        try:
            if sheet_name not in book.sheetnames:
                raise DepartmentAnnexError(f"Unknown sheet: {sheet_name}")
            return [list(row) for row in book[sheet_name].iter_rows(values_only=True)]
        finally:
            book.close()
    if path.suffix.lower() == ".xls":
        try:
            import xlrd
        except ImportError as exc:
            raise DepartmentAnnexError(
                "Legacy XLS requires xlrd; provide an equivalent XLSX instead"
            ) from exc
        book = xlrd.open_workbook(str(path), on_demand=True)
        try:
            if sheet_name not in book.sheet_names():
                raise DepartmentAnnexError(f"Unknown sheet: {sheet_name}")
            sheet = book.sheet_by_name(sheet_name)
            return [sheet.row_values(i) for i in range(sheet.nrows)]
        finally:
            book.release_resources()
    raise DepartmentAnnexError("Expected a DANE Excel workbook (.xlsx or .xls)")


class DepartmentAnnexReader:
    """Read official annual departmental anchors in persons."""

    def __init__(self, spec: DepartmentAnnexSpec) -> None:
        """Compose the parser."""
        self._spec = spec
        self._parser = DepartmentAnnexParser(spec)

    def annual_anchors(self, rows: Sequence[Sequence[Any]]) -> pd.DataFrame:
        """Return the six quantities per department and year, in persons.

        Raises
        ------
        DepartmentAnnexError
            If the territories or years differ from the specification.
        """
        spec = self._spec
        records = self._parser.parse(rows)
        quantities = [str(q) for q in LaborQuantity]
        records = records[records["concept"].isin(quantities)]
        if set(records["dane_code"]) != set(spec.anchored_codes):
            raise DepartmentAnnexError("Annex territories differ from spec")
        expected_years = set(range(spec.first_year, spec.last_year + 1))
        if set(records["year"]) != expected_years:
            raise DepartmentAnnexError("Annex years differ from spec")
        expected_rows = (
            len(spec.anchored_codes) * len(expected_years) * len(quantities)
        )
        if len(records) != expected_rows:
            raise DepartmentAnnexError("Incomplete official anchors")
        records = records.assign(
            value=records["value"].astype(float) * spec.published_unit_persons
        )
        annual = records.pivot_table(
            index=["dane_code", "department", "year"],
            columns="concept",
            values="value",
            aggfunc="first",
        ).reset_index()
        annual.columns.name = None
        annual = annual.rename(columns={"dane_code": "dep_code"})
        return annual.sort_values(["dep_code", "year"]).reset_index(drop=True)

    def read(self, path: Path) -> pd.DataFrame:
        """Read the workbook and return the annual anchors."""
        return self.annual_anchors(
            read_sheet_rows(path, self._spec.sheet_name)
        )
