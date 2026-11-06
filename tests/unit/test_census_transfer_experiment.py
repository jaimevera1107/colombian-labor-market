"""Regression tests for the CNPV 2018 two-universe *single-model* experiment."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# The experiment module imports the MLP at import time (optional ``ml`` extra).
pytest.importorskip("torch", reason="requires the optional 'ml' extra")

from icml.informality.census_transfer_experiment import (  # noqa: E402
    NINE,
    _rates_by_method,
)


def _fixture(period: str = '2021-06'):
    codes=[5,8,11,13,15,17,18,19,20,23,25,27,41,44,47,50,52,54,63,66,68,70,73,76,
           81,85,86,88,91,94,95,97,99]
    assert len(codes)==33
    x=pd.DataFrame({'dep_code':codes,'period':period,
        'employed':np.linspace(500,1500,33),
        'geih_employed':np.linspace(500,1500,33),
        'prior_original':np.linspace(.22,.81,33),
        'prior_census':np.linspace(.22,.81,33)})
    x.loc[x.dep_code.isin(NINE),'geih_employed']*=.42
    x['factor_geih_employed']=x.geih_employed/x.employed
    x['geih_domain_status']='TEST'
    n=pd.DataFrame({'period':[period],'national_type':['ICML_COMPLETO'],
       'informality_rate_estimated':[.57]})
    return x,n


def test_full_first_identity_and_domain_conversion():
    x,n=_fixture()
    out,m=_rates_by_method(x,n)
    full=out[(out.method=='FULL_FIRST') & (out.scenario=='CNPV_2018_SIGNAL')]
    assert len(full)==33
    assert np.isclose(full.informal_full.sum(),.57*x.employed.sum(),atol=1e-7)
    assert np.allclose(full.informal_full+full.formal_full,full.employed,atol=1e-9)
    assert np.allclose(full.informal_geih+full.formal_geih,full.geih_employed,atol=1e-9)
    assert np.allclose(full.informal_full,full.informal_geih+full.outside_informal,atol=1e-9)
    assert m[m.method=='FULL_FIRST'].national_full_gap_pp.abs().max()<1e-8


def test_geih_first_and_dual_each_have_explicit_role():
    x,n=_fixture()
    out,m=_rates_by_method(x,n)
    assert set(out.method)=={'FULL_FIRST','GEIH_FIRST','DUAL_IDENTICAL_RATE_ASSUMPTION'}
    assert abs(m[m.method=='GEIH_FIRST'].national_geih_gap_pp.iloc[0]) < 1e-8
    dual=m[m.method=='DUAL_IDENTICAL_RATE_ASSUMPTION']
    assert dual.national_full_gap_pp.abs().max()<1e-8
    assert dual.national_geih_gap_pp.abs().max()<1e-8


def test_2020_remains_unidentified():
    x,n=_fixture('2020-06')
    out,m=_rates_by_method(x,n)
    assert out.empty
    assert m.iloc[0]['mode']=='BLOCKED_2020_UNIDENTIFIED'
