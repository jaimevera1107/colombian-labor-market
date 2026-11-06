"""H12 sectoral priors: identity, chronology, non-observability and validation."""
import numpy as np
import pandas as pd
import pytest

from icml.sectoral_departmental_prior import (
    SECTORS, SCENARIOS, build_covariates, calculate_priors, national_composition,
)


def _make_composition(months=('2026-01', '2026-02')):
    return pd.DataFrame([dict(period=p,sector_code=s,sector_share=1/len(SECTORS),
                              source_status='SYNTHETIC',split_status='ESTIMATE')
                         for p in months for s in SECTORS])


def _make_cov(months=('2026-01', '2026-02')):
    return pd.DataFrame([dict(period=p,dep_code=d,rural_fraction_centered=r)
                         for p in months for d,r in [('05',-0.3),('08',0.3)]])


def test_zero_strength_gives_uniform_national_shares_for_every_department():
    out=calculate_priors(_make_composition(),_make_cov(),'NEUTRAL_NATIONAL')
    assert len(out)==2*2*15
    assert out.groupby(['period','dep_code']).sector_share.sum().sub(1).abs().max()<1e-14
    assert np.allclose(out.sector_share,1/15)
    assert not out.direct_department_sector_observation.any()


def test_rural_proxy_has_direction_and_preserves_row_simplex():
    data=calculate_priors(_make_composition(),_make_cov(),'RURAL_PROXY_MODERATE')
    a=data[(data.period=='2026-01') & (data.sector_code=='A')].set_index('dep_code').sector_share
    assert a['08']>a['05']
    assert (data.groupby(['period','dep_code']).sector_share.sum()-1).abs().max()<1e-12
    assert data.sector_share.ge(0).all()
    assert data.estimation_status.eq('H12_DEPARTMENTAL_SECTOR_PRIOR_UNVALIDATED').all()


def test_scenario_changes_are_not_training_claims():
    neutral=calculate_priors(_make_composition(),_make_cov(),'NEUTRAL_NATIONAL')
    weak=calculate_priors(_make_composition(),_make_cov(),'RURAL_PROXY_WEAK')
    strong=calculate_priors(_make_composition(),_make_cov(),'RURAL_PROXY_MODERATE')
    a=lambda df:df[(df.period=='2026-01') & (df.dep_code=='08') & (df.sector_code=='A')].sector_share.iloc[0]
    assert a(neutral)<a(weak)<a(strong)
    assert list(SCENARIOS)==['NEUTRAL_NATIONAL','RURAL_PROXY_WEAK','RURAL_PROXY_MODERATE']


def test_duplicate_covariate_or_missing_covariate_rejected():
    n=_make_composition()
    d=_make_cov()
    with pytest.raises(ValueError,match='Missing spatial covariate'):
        calculate_priors(n,d.iloc[:-1],'RURAL_PROXY_WEAK')
    with pytest.raises(ValueError,match='Unknown scenario'):
        calculate_priors(n,d,'OBSERVED_GOVERNMENT')


def _h11_synthetic():
    old=list(pd.period_range('1993-01','2001-06',freq='M').astype(str))
    mid=list(pd.period_range('2001-07','2014-12',freq='M').astype(str))
    val=1/len(SECTORS)
    historical=pd.DataFrame([dict(period=p,sector_code=s,sector_share=val,
         national_type='ICML_COMPLETO',method='ENH_SEP_PRINCIPAL')
         for p in old for s in SECTORS])
    backcast=pd.DataFrame([dict(period=p,sector_code=s,sector_share=val,
         national_type='ICML_COMPLETO',scenario='FULL_2015_BRIDGE')
         for p in (mid+['2015-03']) for s in SECTORS])
    recent=list(pd.period_range('2015-01','2026-08',freq='M').astype(str))
    official_codes=[s for s in SECTORS if s not in ('B','D_E','NO_INFO')]+['B_D_E_COMBINED']
    observations=pd.DataFrame([dict(period=p,sector_code=s,employed_persons=100.0)
                           for p in recent for s in official_codes])
    totals=pd.DataFrame([dict(period=p,occupied_official_persons=1300.,no_informa_persons=0.) for p in recent])
    return historical,backcast,observations,totals


def test_coverage_source_provenance_and_no_double_count_2015():
    source=_h11_synthetic()
    composition=national_composition(*source)
    assert len(composition)==404*15
    assert len(composition.period.unique())==404
    assert (composition.groupby('period').sector_share.sum()-1).abs().max()<1e-12
    assert composition[composition.period=='2015-01'].source_status.str.startswith('DANE_13').all()
    assert composition[(composition.period=='2015-01') & (composition.sector_code=='B')].split_status.item()=='ASSUMED_FIXED_H11_2015_03_B_D_E_RATIO'


def test_rounding_negative_no_info_is_not_negatively_imputed():
    h,b,obs,t=_h11_synthetic()
    t.loc[t.period=='2018-05','occupied_official_persons']=1298.
    out=national_composition(h,b,obs,t)
    row=out[(out.period=='2018-05')]
    assert row[row.sector_code=='NO_INFO'].sector_share.item()==0.0
    assert abs(row.sector_share.sum()-1)<1e-12
    assert (row.source_status=='DANE_13_PUBLISHED_PLUS_ROUNDING_NORMALIZATION').all()


def test_missing_month_throws_instead_of_interpolating():
    h,b,obs,t=_h11_synthetic()
    obs=obs[obs.period!='2018-05']
    with pytest.raises(ValueError,match='coverage mismatch'):
        national_composition(h,b,obs,t)


def test_input_observation_duplicate_is_rejected():
    h,b,obs,t=_h11_synthetic()
    obs=pd.concat([obs,obs.iloc[[0]]],ignore_index=True)
    with pytest.raises(ValueError,match='duplicated primary keys'):
        national_composition(h,b,obs,t)


def test_population_must_have_both_urban_and_rural_annual_projections():
    periods=list(pd.period_range('1993-01','2026-08',freq='M').astype(str))
    d=pd.DataFrame([dict(period=p,dep_code=f'{j:02}',employed=100,
          employed_represented=100,territory_name=str(j),source='SYNTHETIC')
          for p in periods for j in range(1,34)])
    # Insufficient years/territories: refuse rather than fill silently.
    pop=pd.DataFrame([dict(dep_code='01',year=1993,area_type='Total',population=1000)])
    with pytest.raises(ValueError,match='Annual rural/urban projections are incomplete'):
        build_covariates(d,pop)
