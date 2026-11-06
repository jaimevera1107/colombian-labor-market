"""Source-ledger contracts for H31; never train estimators in these tests."""
from pathlib import Path
import pytest
from icml.operations.h31_sources import (
    _col,compare_numeric,extract_macro,extract_window_proxies,
)
from icml.operations.h31_prepare_all import run


def test_excel_column_boundaries():
    assert [_col(n) for n in (1,2,26,27,50,58)] == ['A','B','Z','AA','AX','BF']
    with pytest.raises(ValueError):_col(0)


def test_numeric_comparison_checks_all_columns_and_keys():
    reference=[{'id':'01','employed':'2.00'},{'id':'02','employed':'1.00'}]
    assert compare_numeric(reference,reference,('id',),('employed',),0)['equivalent']
    bad=[{'id':'01','employed':2.5},{'id':'03','employed':1.00}]
    result=compare_numeric(bad,reference,('id',),('employed',),1e-10)
    assert not result['equivalent']
    assert result['missing_keys']==result['extra_keys']==result['numeric_violations']==1
    with pytest.raises(ValueError):
        compare_numeric(reference+[reference[0]],reference,('id',),('employed',),0)


def test_h31_real_frozen_inputs_and_proxies(tmp_path):
    root=Path(__file__).resolve().parents[2]
    annex=root/'datos/1_ingesta/geih_mercado_laboral/geih_mercado_laboral_2026-08.xlsx'
    evidence=root/'datos/2_procesamiento/auditoria_historica_h30/Indicadores Económicos Externos Mensuales.xlsx'
    assert annex.is_file() and evidence.is_file()
    proxies=extract_window_proxies(annex)
    assert len(proxies)==192
    assert len({(r['dep_code'],r['year']) for r in proxies})==192
    assert len(extract_macro(evidence))==132


def test_atomic_staging_no_overwrite(tmp_path):
    root=Path(__file__).resolve().parents[2]
    output=tmp_path/'stage'
    result=run(root,output)
    assert result['status']=='PASS'
    assert result['verified_generators']==9
    assert (output/'h31/H31_AUDITORIA.json').is_file()
    assert (output/'h29/gdp_groups_2005_2024.csv').is_file()
    with pytest.raises(FileExistsError):run(root,output)
