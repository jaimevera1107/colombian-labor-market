"""Guardrails against treating 3-month DANE windows as observed calendar months."""

import numpy as np
import pandas as pd
import pytest

from icml.sectoral.monthly_backcast import (
    CATEGORIES, anchored_monthly_recent, build_rolling_matrix, inverse_rolling,
)


def test_true_monthly_rolling_identity_and_simplex():
    employed=np.full(165,15000000.0)
    a=build_rolling_matrix(employed)
    sectors=len(CATEGORIES)
    rng=np.random.default_rng(13)
    start=rng.dirichlet(np.ones(sectors)*3, size=165)
    start[-3:]=start[-3:].mean(axis=0)
    actual=a@start
    recovered=inverse_rolling(a,actual,start[-3:],0.03,iterations=1200)
    np.testing.assert_allclose(recovered.sum(axis=1),1.0,rtol=0,atol=1e-11)
    assert recovered.min()>=0
    assert (a@recovered-actual).__abs__().mean()<0.007
    np.testing.assert_allclose(recovered[-3:],start[-3:],atol=1e-12)


def test_mislabelled_rolling_counts_rejected():
    with pytest.raises(ValueError,match='H11_MONTHLY_EMPLOYED'):
        build_rolling_matrix(np.ones(164))


def test_incomplete_monthly_source_rejected():
    bad=pd.DataFrame({'period':['2015-01'],'sector_code':['A'],
            'employed_persons':[1.0], 'temporal_support':['calendar_month']})
    totals=pd.DataFrame({'period':['2015-01'], 'no_informa_persons':[0.]})
    with pytest.raises(ValueError,match='ANCHORS_MISSING'):
        anchored_monthly_recent(bad,totals,np.ones(len(CATEGORIES))/len(CATEGORIES))


def test_masked_windows_do_not_leak_into_fit():
    employed=np.full(165,1000.0);a=build_rolling_matrix(employed)
    y=np.tile(np.ones(len(CATEGORIES))/len(CATEGORIES),(163,1))
    anchors=y[-3:].copy()
    omission=np.zeros(163,bool);omission[54:60]=True
    modified=y.copy();modified[54:60,0]+=.03;modified[54:60,1]-=.03
    u=inverse_rolling(a,y,anchors,0.3,omitted=omission,iterations=400)
    v=inverse_rolling(a,modified,anchors,0.3,omitted=omission,iterations=400)
    np.testing.assert_allclose(u,v,rtol=0,atol=1e-11)
