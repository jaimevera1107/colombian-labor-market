import numpy as np
import pandas as pd
import pytest

from icml.national.geih_annex import (
    AnnexFormatError,
    GeihAnnexSpec,
    extract_region_quantities,
    parse_labor_blocks,
)

CONCEPTS = {
    "Población total": "population",
    "Población en edad de trabajar (PET)": "working_age",
    "Fuerza de trabajo": "labor_force",
    "Población ocupada": "employed",
    "Población desocupada": "unemployed",
    "Población fuera de la fuerza de trabajo": "inactive",
}
LAYOUT = dict(
    start_period="2001-01",
    block_marker="Concepto",
    block_end_marker="Fuerza de trabajo potencial",
    value_decimals=4,
)


def _block(region, values):
    rows = [
        [region, None, None, None],
        ["Serie", None, None, None],
        ["Concepto", 2001, None, None],
        [None, "Ene", "Feb", "Mar"],
        ["Tasa de Desocupación (TD)", 10.0, 11.0, 12.0],
    ]
    for concept, numbers in values.items():
        rows.append([concept, *numbers])
    rows.append(["Fuerza de trabajo potencial", 0, 0, 0])
    rows.append([None, None, None, None])
    return rows


def _cells(trailing_empty_month=True):
    values = {
        "Población total": [100.0, 101.0, None],
        "Población en edad de trabajar (PET)": [80.0, 81.0, None],
        "Fuerza de trabajo  ": [50.0, 51.0, None],
        "Población ocupada": [45.12346, 46.0, None],
        "Población desocupada": [4.87654, 5.0, None],
        "Población fuera de la fuerza de trabajo": [30.0, 30.0, None],
    }
    if not trailing_empty_month:
        values = {k: [v[0], v[1], v[1]] for k, v in values.items()}
    rows = [[None] * 4, [None] * 4]
    rows += _block("Total Nacional", values)
    rows += _block("Total Cabeceras", values)
    return pd.DataFrame(rows)


def test_blocks_are_parsed_per_region():
    blocks = parse_labor_blocks(_cells(), **LAYOUT)
    assert set(blocks["region"]) == {"Total Nacional", "Total Cabeceras"}
    assert blocks["period"].min() == "2001-01"
    assert "Fuerza de trabajo" in set(blocks["concept"])


def test_national_extraction_rounds_scales_and_drops_empty_months():
    blocks = parse_labor_blocks(_cells(), **LAYOUT)
    wide = extract_region_quantities(
        blocks, region="Total Nacional", concepts=CONCEPTS, scale_factor=1000.0
    )
    assert wide["period"].tolist() == ["2001-01", "2001-02"]
    assert wide.loc[0, "employed"] == pytest.approx(45123.5)
    assert np.isfinite(wide.drop(columns="period").to_numpy()).all()


def test_missing_region_and_concept_are_errors():
    blocks = parse_labor_blocks(_cells(), **LAYOUT)
    with pytest.raises(AnnexFormatError, match="Region"):
        extract_region_quantities(
            blocks, region="Nowhere", concepts=CONCEPTS, scale_factor=1.0
        )
    with pytest.raises(AnnexFormatError, match="Concepts"):
        extract_region_quantities(
            blocks,
            region="Total Nacional",
            concepts={**CONCEPTS, "Inexistente": "population"},
            scale_factor=1.0,
        )


def test_duplicated_region_is_rejected():
    cells = pd.concat([_cells(), _cells()], ignore_index=True)
    blocks = parse_labor_blocks(cells, **LAYOUT)
    with pytest.raises(AnnexFormatError, match="more than once"):
        extract_region_quantities(
            blocks,
            region="Total Nacional",
            concepts=CONCEPTS,
            scale_factor=1.0,
        )


def test_sheet_without_blocks_is_rejected():
    with pytest.raises(AnnexFormatError, match="No block"):
        parse_labor_blocks(pd.DataFrame([["x", 1], ["y", 2]]), **LAYOUT)


def test_spec_requires_all_six_quantities():
    with pytest.raises(ValueError, match="six"):
        GeihAnnexSpec(
            sheet_name="s",
            region="r",
            start_period="2001-01",
            block_marker="Concepto",
            block_end_marker="x",
            value_decimals=4,
            scale_factor=1000.0,
            concepts={"a": "employed"},
        )
