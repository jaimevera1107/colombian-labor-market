"""National DANE definition bridge/2020 sensitivity, all noncanonical."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from icml.informality.national_bridge_stress import (
    calibrate_scenarios, fill_gap_2020, retrospective_pseudogaps,
)


def _synthetic_candidates():
    rows=[]
    urban=[]
    for code in range(1,34):
        for year in (2018,2019,2021):
            for month in range(1,13) if year!=2021 else (1,):
                period=f'{year}-{month:02d}'
                rate=.3+.001*code+.0001*month
                rows.append({'dep_code':code,'period':period,'rate_prior':rate})
        for month in range(1,13):
            period=f'2020-{month:02d}'
            urban.append({'dep_code':code,'period':period,'rate_prior':.5+.001*code})
        urban.extend([{'dep_code':code,'period':'2019-12','rate_prior':.5+.001*code},
                      {'dep_code':code,'period':'2021-01','rate_prior':.51+.001*code}])
    return pd.DataFrame(rows),pd.DataFrame(urban)


@pytest.mark.parametrize('mode', ['seasonal_2019', 'interpolated', 'urban_shock'])
def test_gap_exact_33_times_12_and_does_not_overwrite(mode):
    prior,urban=_synthetic_candidates()
    original=prior.copy(deep=True)
    gap=fill_gap_2020(prior,urban,mode)
    assert len(gap)==396
    assert gap[['dep_code','period']].duplicated().sum()==0
    assert set(gap.period.str[:4])=={'2020'}
    assert gap.rate_prior.between(0,1).all()
    pd.testing.assert_frame_equal(prior,original)


def test_gap_fails_if_preexisting_data_are_present():
    p,u=_synthetic_candidates()
    p=pd.concat([p,pd.DataFrame([{'dep_code':1,'period':'2020-01','rate_prior':.4}])],ignore_index=True)
    with pytest.raises(ValueError,match='refusing overwrite'):
        fill_gap_2020(p,u,'interpolated')


def test_gap_invalid_policy_fails():
    p,u=_synthetic_candidates()
    with pytest.raises(ValueError):fill_gap_2020(p,u,'magic')


def test_two_targets_and_pre2001_single_margin():
    dep=[];national=[];priors=[]
    for month in ('1999-01','2002-01'):
        e=np.linspace(100.,220.,33); f=np.linspace(0.,1.,33) if month>'2000' else np.ones(33)
        ref=np.linspace(.4,.6,33)
        for i in range(33):
            dep.append({'dep_code':i+1,'period':month,'employed':e[i],'factor_employed':f[i]})
            priors.append({'candidate':'mlp_residual_92','dep_code':i+1,'period':month,'rate_prior':.6})
        national += [{'scenario':'proxy_strength_0.5','period':month,'national_type':'ICML_COMPLETO',
                      'informal_estimated':float(e@ref),'employed_frozen':float(e.sum())},
                     {'scenario':'proxy_strength_0.5','period':month,'national_type':'DANE_REFERENCIA',
                      'informal_estimated':float((e*f)@ref),'employed_frozen':float(e@f)}]
    result,audit=calibrate_scenarios(pd.DataFrame(national),pd.DataFrame(dep),pd.DataFrame(priors))
    assert len(result)==66
    assert abs(audit.residual_icml_people).max()<1e-6
    assert abs(audit.residual_dane_people.dropna()).max()<1e-6
    assert ((result.informal+result.formal-result.employed).abs()<1e-9).all()


def test_pseudogaps_are_not_called_observed():
    p,u=_synthetic_candidates()
    p['candidate']='mlp_residual_92'
    u['candidate']='urban_direct'
    result=retrospective_pseudogaps(pd.concat([p,u]),u,years=(2019,))
    assert result.empty  # 2020 is absent: right endpoint missing
