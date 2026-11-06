"""H32 regression from the real 2026-08 DANE 23-city annex."""
import csv
from pathlib import Path

import pytest

from icml.operations.excel_historical_sources import _records
from icml.operations.urban_annex import (
    _annual_columns,
    compare_historical_annex,
    extract_urban_historical_annex,
    extract_cundinamarca_department_anchors,
    extract_cundinamarca_area_breakdown,
)


def _inputs():
    root = Path(__file__).resolve().parents[2]
    return (
        root / 'datos/1_ingesta/geih_mercado_laboral/geih_mercado_laboral_2026-08.xlsx',
        root / 'datos/2_procesamiento/fuentes_preparadas/urbano/donantes_congelados_referencia.csv',
        root / 'datos/1_ingesta/geih_departamentos/geih_departamentos_2025.xlsx',
        root / 'datos/2_procesamiento/fuentes_preparadas/urbano/senales_historicas_23_y_donantes.csv',
    )


def test_rolling_quarter_year_ranges():
    assert (len(_annual_columns(2007)), _annual_columns(2007)[0]) == (10, 'B')
    assert (len(_annual_columns(2018)), len(_annual_columns(2025))) == (12, 12)
    assert len(_annual_columns(2026)) == 8
    with pytest.raises(ValueError):
        _annual_columns(2006)


def test_real_excel_rebuilds_660_legacy_signals_without_new_donors():
    annex, mapping, synthetic, frozen = _inputs()
    rows = extract_urban_historical_annex(annex, mapping, synthetic)
    comparison = compare_historical_annex(rows, _records(frozen))
    assert comparison['status'] == 'PASS'
    assert comparison['rows'] == 660
    assert comparison['max_geih_abs_thousands'] < 0.000051
    assert comparison['max_proxy_abs_persons'] < 0.051
    assert len(rows) == len({(r['dep_code'],r['year']) for r in rows})
    assert next(r for r in rows if r['dep_code']==25 and r['year']==2025)['employed'] is None
    assert next(r for r in rows if r['dep_code']==25 and r['year']==2023)['employed'] == 1667838.0


def test_mismatch_in_historic_mapping_is_blocked():
    annex, mapping, synthetic, frozen = _inputs()
    rows = extract_urban_historical_annex(annex, mapping, synthetic)
    original = _records(frozen)
    original[0]['dep_code_similar'] = '999'
    assert compare_historical_annex(rows, original)['status'] == 'BLOCKED'
    original = _records(frozen)
    original[0]['employed_geih'] = str(float(original[0]['employed_geih']) + 1)
    assert compare_historical_annex(rows, original)['status'] == 'BLOCKED'


def test_previous_spliced_columns_are_not_national_regressors():
    import tomllib
    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root/'configs/rc1/national.toml').read_text())
    regressors = config['national']['disaggregation']['indicators']
    names = [item for group in regressors.values() for item in group]
    assert set(names) <= {'real_value_unit_uvr', 'consumer_price_index',
                          'producer_price_index'}
    assert not any(name.endswith('_spliced') for name in names)


def test_departmental_excel_extracts_all_24_official_cundinamarca_anchors():
    import json
    _, _, annual_xlsx, _ = _inputs()
    rows=extract_cundinamarca_department_anchors(annual_xlsx)
    assert len(rows)==4 and all(len(row)==6 for row in rows.values())
    root=Path(__file__).resolve().parents[2]
    legacy=json.loads((root/'datos/2_procesamiento/fuentes_preparadas/urbano/cundinamarca_25_senales_sinteticas_2021_2024.json').read_text())
    for year,metrics in legacy['values'].items():
        assert rows[year]==metrics


def test_departmental_anchors_absent_or_wrong_workbook_are_rejected(tmp_path):
    with pytest.raises((FileNotFoundError,KeyError,ValueError)):
        extract_cundinamarca_department_anchors(tmp_path/'missing.xlsx')


def test_cundinamarca_area_decomposition_from_official_excel():
    _,_,xlsx,_=_inputs()
    result=extract_cundinamarca_area_breakdown(xlsx)
    assert set(result)=={'total','cabeceras','resto'}
    assert result['total']['2024']['employed']==1711836.0
    assert result['cabeceras']['2024']['employed']==1349239.0
    assert result['resto']['2024']['employed']==362597.0
    for year in result['total']:
        for field, total in result['total'][year].items():
            assert abs(total-result['cabeceras'][year][field]-result['resto'][year][field])<=2
