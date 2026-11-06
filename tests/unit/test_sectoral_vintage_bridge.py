"""H10 vintage bridge guards: source hashes, temporal support and both universes."""
import numpy as np
import pandas as pd
import pytest
from icml.sectoral_vintage_bridge import (
    BUCKET_DEFINITION, FINAL_14, HIST_CODES, RECENT_CODES, check_old,check_recent,
    make_candidates,overlap_and_crosswalk,
)


def example():
    months=pd.period_range('2015-01','2015-03',freq='M').strftime('%Y-%m')
    recent=pd.DataFrame([{'period':m,'sector_code':c,'employed_persons':3000.0,
        'window_months':1,'temporal_support':'calendar_month'} for m in months for c in RECENT_CODES if c!='NO_INFO'])
    totals=pd.DataFrame([{'period':m,'no_informa_persons':1.0,
        'occupied_official_persons':39001.0} for m in months])
    old=pd.DataFrame([{'period_end':'2015-03','legacy_sector_code':c,
        'employed_persons':200.0 if c=='NO_INFO' else 3200.0} for c in HIST_CODES])
    return old,recent,totals


def test_crosswalk_normalized_and_complete():
    old,r,t=example()
    overlap,mapping,ratios,split,*_=overlap_and_crosswalk(old,r,t)
    assert set(mapping.legacy_code)==set(HIST_CODES)
    assert len(overlap)==10
    assert np.isclose(sum(split['G_I'].values()),1)
    assert all(v>0 for v in ratios.values())
    assert set(mapping.modern_code)==set(FINAL_14)|{'NO_INFO'}
    assert mapping.not_independent_official_14_observation.all()


def test_exact_source_rolling_no_monthly_relabel():
    old,r,t=example();old['period_start']='2015-01';old['domain']='NACIONAL'
    old['window_months']=3;old['sector_system']='CIIU_Rev3'
    old['source_sha256']='a'*64
    old_no_jan=old.copy();old_no_jan.loc[0,'period_start']='2015-02'
    with pytest.raises(ValueError,match='HISTORICAL_WINDOWS_OR_CARDINALITY'):
        check_old(old)
    bad=r.copy();bad.loc[0,'window_months']=3
    with pytest.raises(ValueError,match='RECENT_MUST_BE_DIRECT_MONTHLY'):
        check_recent(bad,t)


def test_both_universes_and_all_sector_counts_preserve_rows():
    old,r,t=example()
    _,mapping,ratios,split,ov,nv=overlap_and_crosswalk(old,r,t)
    old['period_end']='2015-03'
    old['period_start']='2015-01'
    old['domain']='NACIONAL'
    old['window_months']=3
    old['source_sha256']='a'*64
    old['sector_system']='CIIU_Rev3'
    national=[]
    for m in pd.period_range('2014-12','2015-03',freq='M').strftime('%Y-%m'):
        national.extend([{'period':m,'national_type':'ICML_COMPLETO','employed':50000},
                          {'period':m,'national_type':'DANE_REFERENCIA','employed':40000}])
    test_old=pd.concat([old.assign(period_end=m,period_start=(pd.Period(m,freq='M')-2).strftime('%Y-%m'))
                        for m in ['2015-02','2015-03']],ignore_index=True)
    data=make_candidates(test_old,ratios,split,nv,pd.DataFrame(national))
    assert data.shape[0]==2*2*3*15
    assert not data.is_official_monthly_sector_observation.any()
    assert data.window_months.eq(3).all()
    sums=data.groupby(['period_end','scenario','national_type']).reconstructed_window_persons.sum()
    for (p,sc,u),v in sums.items():
        assert abs(v-(50000 if u=='ICML_COMPLETO' else 40000))<1e-7
    assert set(data.sector_code)==set(FINAL_14)|{'NO_INFO'}
