"""Regression tests for the H27 gate against silent categorical/numeric drift."""
from pathlib import Path

import pandas as pd

from icml.operations.integral import compare_candidate, _all_products_equivalent


def _pair(tmp_path, original: pd.DataFrame, candidate: pd.DataFrame):
    old, new = tmp_path / 'old.csv', tmp_path / 'new.csv'
    original.to_csv(old, index=False)
    candidate.to_csv(new, index=False)
    return {'labor.nacionales': old}, {'labor.nacionales': new}


def _baseline():
    return pd.DataFrame({'period':['2026-07','2026-08'], 'national_type':['DANE_REFERENCIA']*2,
                         'employed':[1_000_000.0,1_200_000.0], 'unemployment_rate':[0.094,0.095],
                         'status':['OBSERVADO','ESTIMADO']})


def test_rounding_noise_within_tolerance_not_a_failure(tmp_path):
    original=_baseline(); changed=original.copy()
    changed.loc[0,'employed']+=0.00001
    old,new=_pair(tmp_path,original,changed)
    result=compare_candidate(old,new)['labor.nacionales']
    assert result['status']=='EQUIVALENT_WITHIN_TOLERANCES'
    assert not result['sha256_equal']


def test_categorical_drift_fails_gate(tmp_path):
    original=_baseline(); changed=original.copy()
    changed.loc[0,'status']='INVENTADO'
    old,new=_pair(tmp_path,original,changed)
    result=compare_candidate(old,new)['labor.nacionales']
    assert result['status']=='MISMATCH'
    assert result['categorical_mismatches_by_column']['status']==1


def test_large_numeric_or_rate_drift_fails_gate(tmp_path):
    original=_baseline(); changed=original.copy()
    changed.loc[0,'employed']+=0.01
    changed.loc[0,'unemployment_rate']+=0.00001
    old,new=_pair(tmp_path,original,changed)
    result=compare_candidate(old,new)['labor.nacionales']
    assert result['status']=='MISMATCH'
    assert set(result['numeric_tolerance_violations'])=={'employed','unemployment_rate'}
    assert not _all_products_equivalent({'labor.nacionales':result})


def test_missing_key_and_column_fail_gate(tmp_path):
    original=_baseline(); changed=original.drop(columns=['status']).iloc[:1]
    old,new=_pair(tmp_path,original,changed)
    result=compare_candidate(old,new)['labor.nacionales']
    assert result['status']=='MISMATCH'
    assert 'schema_columns_difference' in result['issues']
    assert 'key_coverage_difference' in result['issues']
