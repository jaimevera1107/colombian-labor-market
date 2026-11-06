"""Guarantees on informational boundaries and notebook feature parity."""
from __future__ import annotations

import pandas as pd
import pytest
from icml.informality.feature_consolidation import _cluster_context, _shares, _validate_labor


def test_invalid_labor_keys_or_identities_are_rejected():
    frame=pd.DataFrame({'dep_code':[5]*2,'period':['2024-01']*2,'employed':[2.]*2,
        'unemployed':[1.]*2,'inactive':[1.]*2,'labor_force':[3.]*2,
        'working_age':[4.]*2,'population':[5.]*2})
    with pytest.raises(ValueError,match='duplicate'):
        _validate_labor(frame,'dep_code','unit')


def test_legacy_area_proportions_do_not_get_fabricated():
    source=pd.DataFrame({'dep_code':[5]*3,'year':[2010]*3,
        'area_type':['Total','Cabecera','Centros Poblados y Rural Disperso'],
        'population':[100.,65.,35.]})
    out=_shares(source)
    assert out.pop_urban_pct.iloc[0]==.65
    assert out.pop_rural_pct.iloc[0]==.35
    source.loc[2,'population']=50
    with pytest.raises(ValueError,match='area shares'):
        _shares(source)


def test_cluster_medians_never_depend_on_held_out_territory():
    a=pd.DataFrame({'dep_code':[5,8,11],'cluster_id':[0,0,0]})
    x=pd.DataFrame({'entity_type':['city']*3,'dep_code':[5,8,11],
      'period':['2021-01']*3,
      'participation_rate':[.5,.6,.9], 'employment_rate':[.4,.5,.7],
      'unemployment_rate':[.1,.2,.3],'inactivity_rate':[.5,.4,.1],
      'working_age':[100.]*3,'labor_force':[50.,60.,90.],
      'employed':[40.,50.,70.],'unemployed':[10.,10.,20.],
      'inactive':[50.,40.,10.],'population':[130.]*3})
    first=_cluster_context(x,a,[5,8],'ward_fold',2019)
    x.loc[2,'unemployed']=1000000
    other=_cluster_context(x,a,[5,8],'ward_fold',2019)
    assert first.loc[0,'unemployed_cluster_mean']==other.loc[0,'unemployed_cluster_mean']
    assert first.loc[2,'unemployed_cluster_mean']==10


def test_no_informal_label_in_model_feature_contract_at_source():
    from icml.informality import feature_consolidation as m
    code=open(m.__file__,encoding='utf8').read()
    assert "'urban_proxy_informality_rate','target_latent_informal_rate'" in code
    assert 'model_safe(city_full' in code
    assert 'TerritorialClustering' in code
