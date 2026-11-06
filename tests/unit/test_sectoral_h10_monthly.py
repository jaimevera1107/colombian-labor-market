"""Tests of genuine-month provenance and feasible simultaneous RAS margins."""
import numpy as np
import pytest
from icml.sectoral.monthly import ensure_direct_monthly, reconcile_sector_matrix,MONTHLY_GROUPS,REQUIRED_FINAL_14


def test_only_direct_months():
    ensure_direct_monthly('monthly_direct',1)
    for kind,w in [('moving_quarter',3),('annual',12),('monthly_direct',3)]:
        with pytest.raises(ValueError,match='BLOQUEADO'):
            ensure_direct_monthly(kind,w)


def test_source_groups_not_14_branches():
    assert len(MONTHLY_GROUPS)==13
    assert len(REQUIRED_FINAL_14)==14
    assert 'B_D_E_COMBINED' in MONTHLY_GROUPS
    assert 'B' not in MONTHLY_GROUPS and 'D_E' not in MONTHLY_GROUPS


def test_ras_both_margins_and_total():
    prior=np.array([[2,7,5],[3,4,2],[1,3,8]],float)
    r=np.array([120,240,140],float);c=np.array([110,160,230],float)
    x=reconcile_sector_matrix(prior,r,c)
    np.testing.assert_allclose(x.sum(axis=1),r,atol=1e-5)
    np.testing.assert_allclose(x.sum(axis=0),c,atol=1e-5)
    assert np.all(x>=0)


def test_incompatible_33_vs_1_wrong_margin_fails():
    with pytest.raises(ValueError, match='MARGENES_INCOMPATIBLES'):
        reconcile_sector_matrix(np.ones((33,14)),np.ones(33),np.ones(14)/14)


def test_structural_zero_fails():
    with pytest.raises(ValueError,match='STRUCTURAL_ZERO'):
        reconcile_sector_matrix(np.array([[1,0],[0,0]],float), np.array([1,1]), np.array([1,1]))


def test_all_zero():
    x=reconcile_sector_matrix(np.ones((2,3)),np.zeros(2),np.zeros(3))
    assert not x.any()


def test_snapshot_compatibility_rejects_rolling(tmp_path):
    import pandas as pd
    from icml.sectoral.monthly import read_normalized_monthly
    # A frozen snapshot must have all 140 genuine calendar months and 13 groups.
    obs = tmp_path/'obs.csv'; totals = tmp_path/'totals.csv'
    pd.DataFrame({'period':['2020-04'],'sector_code':['A'],'employed_persons':[1.0],
        'window_months':[3],'source_sha256':['a']}).to_csv(obs,index=False)
    pd.DataFrame({'period':['2020-04'],'window_months':[3],
        'source_sha256':['a']}).to_csv(totals,index=False)
    with pytest.raises(ValueError):
        read_normalized_monthly(obs, totals)
