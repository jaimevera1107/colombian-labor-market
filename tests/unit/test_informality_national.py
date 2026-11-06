"""Regression and source-domain contracts for Hito 5."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from icml.informality.national import (
    NEW, OLD_NAT, _exact_min_curvature, _monthly_latent,
    _rolling_comparison, check_source, load_informality_config,
)

ROOT = Path(__file__).resolve().parents[2]
POLICY = load_informality_config(ROOT / 'configs/rc1/informality.toml')
SOURCE = ROOT / 'data/sources/informality/informality_source_observations.csv'


def load():
    return pd.read_csv(SOURCE)


def test_official_snapshot_has_explicit_distinct_definitions():
    x = load()
    check_source(x, POLICY)
    assert set(x.definition) == {
        NEW, OLD_NAT, 'old_small_firm_size',
    }
    assert x.loc[(x.domain=='national') & (x.definition==NEW)].shape[0]==66
    assert x.loc[(x.domain=='national') & (x.definition==OLD_NAT)].shape[0]==169
    assert x.loc[x.value_status.eq('ZERO_SENTINEL_POSSIBLE_MISSING')].shape[0]==110


def test_source_count_and_boundaries_reject_modification():
    x=load()
    with pytest.raises(ValueError,match='Unexpected source'):
        check_source(x.iloc[:-1].copy(),POLICY)
    y=x.copy()
    y.loc[0,'period_end']='2035-12-01'
    with pytest.raises(ValueError,match='three-month'):
        check_source(y,POLICY)


def test_monthly_inverse_recovers_every_rolling_window():
    rng = np.random.default_rng(4)
    original=np.cumsum(rng.normal(0,0.2,68))+25
    a=np.array([original[i:i+3].mean() for i in range(66)])
    rec=_exact_min_curvature(a)
    np.testing.assert_allclose(np.array([rec[i:i+3].mean() for i in range(66)]),a,rtol=0,atol=1e-12)
    # Any null-space displacement increases or maintains the chosen curvature.
    curvature=lambda s:float(np.sum(np.diff(s,n=2)**2))
    pert=rec.copy()
    period=np.array([1,-1,0])
    pert+=np.tile(period,23)[:68]*0.3
    np.testing.assert_allclose([pert[i:i+3].mean() for i in range(66)],a,rtol=0,atol=1e-12)
    assert curvature(rec)<=curvature(pert)+1e-8


def test_latent_counts_preserve_employment_and_not_official():
    x=load()
    newer=x[(x.domain=='national')&(x.definition==NEW)]
    # Create a frozen employed series compatible with the official
    # employment rolling windows by the same linear inverse.
    occ=_exact_min_curvature(newer.sort_values('period_start').occupied_thousands.to_numpy()*1000)
    dates=pd.date_range('2021-01-01',periods=68,freq='MS')
    dane=pd.DataFrame({'employed':occ},index=dates)
    monthly,audit=_monthly_latent(newer,dane,POLICY)
    assert len(monthly)==68
    assert not monthly.is_official_monthly_observation.any()
    assert not monthly.eligible_for_icml_complete_without_bridge.any()
    np.testing.assert_allclose(monthly.informal_persons_latent+monthly.formal_persons_latent,monthly.employed_persons_fixed_dane,rtol=0,atol=1e-8)
    assert audit.informal_residual_persons.abs().max()<0.0001


def test_old_national_proxy_cannot_be_called_current_informality():
    x=load()
    a=x[(x.domain=='national')&(x.definition==OLD_NAT)]
    b=x[(x.domain=='national')&(x.definition==NEW)]
    both=a.merge(b,on='period_end',suffixes=('_old','_new'))
    assert len(both)==1
    assert (both.informality_rate_new.iloc[0]-both.informality_rate_old.iloc[0])*100==pytest.approx(-3.15512954,abs=1e-6)


def test_benchmark_requires_exact_same_months():
    x=load()
    a=x[(x.domain=='national')&(x.definition==NEW)].head(1)
    dates=pd.date_range('2021-01-01',periods=3,freq='MS')
    dane=pd.DataFrame({'employed':[2e7]*3},index=dates)
    y=_rolling_comparison(a,dane,dane)
    assert len(y)==1
    assert y.informality_is_comparable_with_new.iloc[0]
    with pytest.raises(ValueError,match='Missing national employment window'):
        _rolling_comparison(a,dane.iloc[:-1],dane)
