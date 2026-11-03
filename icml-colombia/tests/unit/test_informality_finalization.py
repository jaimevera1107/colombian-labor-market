"""Regression guards for Hito 9 research completion (no official claims)."""
import numpy as np
import pandas as pd
import pytest

from icml.informality.finalize_block import MONTHS, _one_model_prior, _keys
from icml.informality.national_closure import calibrate_month


def test_404_months_and_2020_gap():
    assert len(MONTHS)==404
    assert MONTHS[0]=='1993-01' and MONTHS[-1]=='2026-08'
    assert sum(x.startswith('2020-') for x in MONTHS)==12


def test_single_model_2020_bridge_keeps_other_periods():
    base=pd.DataFrame({'period':['2019-12','2020-01','2021-01'],
                       'dep_code':[5,5,5],'prior_census':[.7,.4,.3],
                       'year':[2019,2020,2021]})
    # Input fixtures must represent a full 33 x 404 panel; enforce rejection.
    bridge=pd.DataFrame({'period':['2020-01'],'dep_code':[5],
                         'rate_prior':[.5],'candidate':['mlp_residual_92'],
                         'mode':['interpolated']})
    with pytest.raises(ValueError,match='Incomplete 2020 retrospective'):
        _one_model_prior(base,bridge,'interpolated')


def test_duplicate_keys_rejected():
    a=pd.DataFrame({'period':['1993-01','1993-01'],'dep_code':[1,1]})
    with pytest.raises(ValueError,match='duplicate keys'):
        _keys(a,['period','dep_code'],2,'test')


def test_full_margin_not_equal_to_second_margin_assumption():
    e=np.array([100.,150.,50.])
    f=np.array([1.,.6,0.])
    p=np.array([.2,.4,.8])
    target=.5*sum(e)
    out=calibrate_month(p,e,f,target,None)
    r=out['calibrated_rate']
    assert abs(float(np.dot(r,e))-target)<1e-6
    assert not np.isclose(np.average(r,weights=e*f),.5,atol=1e-5)
    assert np.allclose(out['informal']+out['formal'],e)


def test_zero_coverage_never_inverted():
    e=np.array([100.,200.,50.]);g=np.array([0.,100.,50.])
    p=np.array([.3,.5,.6])
    out=calibrate_month(p,e,g/e,150,None)
    rep=e*(g/e)*out['calibrated_rate']
    assert rep[0]==0
    assert np.all(rep>=0)
