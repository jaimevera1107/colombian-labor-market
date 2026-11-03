"""Hito 5 history: no observed data invented, frozen labor preserved."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from icml.informality.historical import (
    _baseline, _find_offset, _ilo_annual, fit_historical_proxy,
    reconstruct_history,
)
from icml.informality.national import OLD_NAT

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT.parent
SOURCE = ROOT / 'data/sources/informality/informality_source_observations.csv'
ILO = ROOT / 'data/sources/informality/ilo_colombia_annual.csv'

# The frozen labor panel is intentionally NOT checked into the source package.
# Integration tests are skip-aware; standalone unit tests still always run.
NATIONALS = PKG / 'datos/2_procesamiento/productos_congelados/laboral/nacionales.csv'
RECENT = PKG / 'datos/2_procesamiento/fuentes_preparadas/informalidad/national_informality_monthly_2021_2026.csv'


@pytest.fixture(scope='module')
def source():
    return pd.read_csv(SOURCE)


@pytest.fixture(scope='module')
def ilo():
    return pd.read_csv(ILO)


@pytest.fixture(scope='module')
def labor():
    if not NATIONALS.exists():
        pytest.skip('Frozen labor bases provided in distribution ZIP, not source checkout')
    return pd.read_csv(NATIONALS)


@pytest.fixture(scope='module')
def history(source, labor, ilo):
    if not RECENT.exists():
        pytest.skip('Hito 5 recent candidate available in complete release ZIP')
    return reconstruct_history(source, labor, pd.read_csv(RECENT), ilo)


def test_ilo_no_pre2007_fake_observations(ilo):
    a = _ilo_annual(ilo)
    assert a.index.min() == 2007
    assert 2020 not in a.index
    assert int(a.index.max()) == 2024
    assert str(a.loc[2010, 'reference_status']) == 'Break in series'


def test_source_is_not_new_informality(source):
    old = source[(source.definition == OLD_NAT) & source.domain.eq('national')]
    assert len(old) == 169
    assert (old.occupied_thousands == 0).sum() == 4
    assert old[old.occupied_thousands == 0].period_end.tolist() == [
        '2020-03-01', '2020-04-01', '2020-05-01', '2020-06-01'
    ]


def test_ilo_duplicate_year_rejected(ilo):
    extra = pd.concat([ilo, ilo.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match='annual history incomplete|duplicate|incomplete'):
        _ilo_annual(extra)


def test_annual_offset_exact_accounting():
    rates = np.array([.53, .58, .59, .63])
    emp = np.array([100, 120, 140, 160.])
    off = _find_offset(rates, emp, 65.)
    from scipy.special import expit, logit
    assert abs(np.mean(expit(logit(rates)+off)*emp)-65)<1e-9
    with pytest.raises(ValueError):
        _find_offset(rates, emp, 999.)


def test_full_national_coverage(history):
    result, audits, stats = history
    assert len(result)==808 and stats['months']==404
    assert set(result.national_type)=={'DANE_REFERENCIA','ICML_COMPLETO'}
    assert not result.duplicated(['national_type','period']).any()
    assert result.period.min()=='1993-01'
    assert result.period.max()=='2026-08'
    assert result[['informal_estimated','formal_estimated','informality_rate_estimated']].notna().all().all()
    assert result.informality_rate_estimated.between(0,1).all()
    assert (result[['informal_estimated','formal_estimated']]>=0).all().all()


def test_fixed_employment_and_accounting(history, labor):
    result, _, stats=history
    ref=labor[['national_type','period','employed']].merge(result,on=['national_type','period'],validate='1:1')
    assert np.allclose(ref.employed,ref.employed_frozen,rtol=0,atol=1e-8)
    assert np.allclose(ref.informal_estimated+ref.formal_estimated,ref.employed_frozen,rtol=0,atol=1e-6)
    assert stats['frozen_labor_modified'] is False


def test_evidence_regimes_are_explicit(history):
    result,_,_=history
    dane=result[result.national_type=='DANE_REFERENCIA'].copy()
    assert dane[dane.period<'2007-01'].provenance.str.startswith('PRE2007').all()
    assert dane[dane.period.between('2007-01','2019-12')].provenance.str.startswith('ILOSTAT_ANNUAL').all()
    assert dane[dane.period.between('2020-01','2020-12')].provenance.str.startswith('OLD_NONPENSION').all()
    assert dane[dane.period>='2021-01'].provenance.str.startswith('GEIH_NEW').all()
    assert result.publication_status.eq('EXPERIMENTAL_NOT_CANONICAL').all()
    assert result.is_official_informality_monthly.eq(False).all()
    assert result[result.national_type=='ICML_COMPLETO'].universe_transfer_assumed.eq(True).all()


def test_annual_ilo_and_post2021_external_held_out(history):
    _, audits, stats = history
    annual=audits['ilo_annual_anchor']
    assert len(annual)==13
    assert annual.error_persons.abs().max()<1e-5
    cv=audits['ilo_leave_year_out']
    assert len(cv)==13 and cv.error_pct.abs().mean()<2.0
    post=audits['ilo_external_comparison']
    assert not post.used_for_calibration.any()
    assert set(post.year)=={2021,2022,2023,2024}
    assert abs(float(post[post.year.eq(2021)].difference_pct.iloc[0]))>5
    assert stats['old_windows_excluded_zero']==4


def test_proxy_fit_excludes_bad_windows(source, labor):
    dane,_ = _baseline(labor)
    proxy, audit = fit_historical_proxy(source,dane)
    assert len(proxy)==171 and len(audit)==165
    assert (proxy>0).all() and (proxy<1).all()
    assert (audit.residual_pp.abs() < 2).all()


def test_missing_labor_blocked(labor):
    changed=labor.copy()
    changed.loc[0,'employed']=np.nan
    with pytest.raises(ValueError,match='missing'):
        _baseline(changed)
