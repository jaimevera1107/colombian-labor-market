"""Regression tests for original-informed, employment-preserving closure."""
import numpy as np
import pandas as pd
import pytest

from icml.informality.national_closure import (
    InfeasibleClosure,apply_to_panel,calibrate_month,original_independent_allocation,
)


def test_dual_closure_exact_and_identity():
    e=np.array([100.,200.,300.,400.]);f=np.array([1.,1.,.2,0.])
    r=np.array([.30,.50,.62,.75])
    t_icml=600.
    t_dane=(e*f).sum()*.55
    out=calibrate_month(r,e,f,t_icml,t_dane)
    assert np.sum(out['informal'])==pytest.approx(t_icml,abs=1e-7)
    assert out['informal']@f==pytest.approx(t_dane,abs=1e-7)
    np.testing.assert_allclose(out['informal']+out['formal'],e,rtol=0,atol=1e-9)
    assert np.all((out['calibrated_rate']>=0)&(out['calibrated_rate']<=1))


def test_historical_single_constraint():
    e=np.array([100.,200.,300.]);r=np.array([.2,.6,.7]);f=np.ones(3)
    out=calibrate_month(r,e,f,300.)
    assert out['constraint_mode']=='ICML_ONLY_HISTORICAL'
    assert out['informal'].sum()==pytest.approx(300,abs=1e-6)
    with pytest.raises(InfeasibleClosure,match='not an independent'):
        calibrate_month(r,e,f,300.,330.)


def test_legacy_scaling_can_break_local_identity():
    e=np.array([100.,200.,300.]);r=np.array([.2,.8,.5])
    i,fo=original_independent_allocation(r,e,400.,200.)
    assert i.sum()==pytest.approx(400.)
    assert fo.sum()==pytest.approx(200.)
    assert np.max(abs(i+fo-e))>1


def test_detect_dane_coverage_count_mismatch():
    dep=pd.DataFrame({'dep_code':range(1,34),'period':['2001-01']*33,
       'employed':[100.]*33,'factor_employed':[1.]*33})
    pred=dep[['dep_code','period']].copy();pred['rate']=[.5]*33
    nat=pd.DataFrame({'period':['2001-01']*2,
       'national_type':['ICML_COMPLETO','DANE_REFERENCIA'],
       'informal_estimated':[1650.,1550.],
       'employed_frozen':[3300.,3200.],
       'informality_rate_estimated':[.5,.5]})
    with pytest.raises(ValueError,match='DANE represented mismatch'):
        apply_to_panel(dep,pred,nat,rate_col='rate',label='test')
