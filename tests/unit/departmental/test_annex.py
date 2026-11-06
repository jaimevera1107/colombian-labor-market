from pathlib import Path

import pytest

from icml.config import build_dataclass, load_toml, section
from icml.departmental.annex import (
    DepartmentAnnexError,
    DepartmentAnnexParser,
    DepartmentAnnexSpec,
    normalize_label,
    parse_number,
    parse_year,
)

CONFIG = Path(__file__).resolve().parents[3] / "configs/rc1/departmental.toml"
LABELS = {
    "population": "Población total",
    "working_age": "Población en edad de trabajar (PET)",
    "labor_force": "Fuerza de trabajo",
    "employed": "Población ocupada",
    "unemployed": "Población desocupada",
    "inactive": "Población fuera de la fuerza de trabajo",
}


@pytest.fixture
def spec():
    values = dict(section(load_toml(CONFIG), "departmental.annex"))
    return build_dataclass(DepartmentAnnexSpec, values, context="test")


def _block(title, years_on_next_row=False, missing=None):
    rows = [[title, None, None]]
    if years_on_next_row:
        rows += [["Concepto", None, None], [None, 2024, 2025]]
    else:
        rows += [["Concepto", 2024, 2025]]
    values = {
        "population": 100,
        "working_age": 80,
        "labor_force": 50,
        "employed": 45,
        "unemployed": 5,
        "inactive": 30,
    }
    for name, label in LABELS.items():
        if name == missing:
            continue
        rows.append([label, values[name], values[name] + 1])
    rows.append(["Tasa de desocupación (TD)", 10.0, 9.0])
    return rows


def test_blocks_in_both_layouts_are_parsed(spec):
    rows = _block("Antioquia") + _block(
        "Departamento del Cesar", years_on_next_row=True
    )
    records = DepartmentAnnexParser(spec).parse(rows)
    assert set(records["dane_code"]) == {5, 20}
    assert set(records["year"]) == {2024, 2025}
    assert len(records) == 2 * 2 * 7


def test_bogota_alias_and_accents(spec):
    records = DepartmentAnnexParser(spec).parse(_block("BOGOTÁ"))
    assert set(records["dane_code"]) == {11}


def test_unknown_title_and_missing_concept_fail(spec):
    with pytest.raises(DepartmentAnnexError, match="Unidentified"):
        DepartmentAnnexParser(spec).parse(_block("Atlantis"))
    with pytest.raises(DepartmentAnnexError, match="Missing concepts"):
        DepartmentAnnexParser(spec).parse(_block("Huila", missing="employed"))


def test_rates_out_of_range_fail(spec):
    rows = _block("Huila")
    rows[-1] = ["Tasa de desocupación (TD)", 150.0, 9.0]
    with pytest.raises(DepartmentAnnexError, match="Rate"):
        DepartmentAnnexParser(spec).parse(rows)


def test_cell_parsers():
    assert parse_year("Año 2019") == 2019
    assert parse_year(2019.0) == 2019
    assert parse_year(19.5) is None
    assert parse_number("1,5", ["-"]) == 1.5
    assert parse_number("-", ["-"]) is None
    assert parse_number("1.234,5", ["-"]) is None
    assert normalize_label("  Población   Total ") == "poblacion total"
