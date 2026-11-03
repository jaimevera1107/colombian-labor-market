"""Experimental national informality history, with separate evidence regimes.

Never overwrites the frozen national labor bases or the Hito 5 recent candidate.
ILOSTAT annual levels are independent anchors with definition-break metadata;
old social-security non-affiliation is a SHAPE indicator, not a current GEIH
informality observation. Pre-2007 is an explicit assumption-based scenario.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from icml.domain.cutoff import (
    FIRST_MONTH,
    ACTIVE_CUTOFF,
    LAST_YEAR,
    RECENT_MONTHS,
    INFORMALITY_NEW_FIRST_MONTH,
    ROWS_NATIONAL,
    month_starts,
)
from scipy.optimize import lsq_linear
from scipy.special import expit, logit

from icml.informality.national import NEW, OLD_NAT

LABOR_FIELDS = ('population', 'working_age', 'labor_force', 'employed', 'unemployed', 'inactive')


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _baseline(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if set(df.national_type) != {'DANE_REFERENCIA', 'ICML_COMPLETO'}:
        raise ValueError('Expected both and only both national labor series')
    if df.duplicated(['national_type', 'period']).any():
        raise ValueError('National calendar not unique')
    if df[list(LABOR_FIELDS)].isna().any().any():
        raise ValueError('Frozen national levels must have no missing values')
    d = df.copy()
    d['period'] = pd.to_datetime(d.period)
    a = d[d.national_type.eq('DANE_REFERENCIA')].set_index('period').sort_index()
    b = d[d.national_type.eq('ICML_COMPLETO')].set_index('period').sort_index()
    expected = month_starts()
    if not (a.index.equals(expected) and b.index.equals(expected)):
        raise ValueError(f'Frozen national series lack {FIRST_MONTH}..{ACTIVE_CUTOFF} coverage')
    if (a.employed <= 0).any() or (b.employed <= 0).any():
        raise ValueError('Non-positive employed levels')
    return a, b


def fit_historical_proxy(source: pd.DataFrame, labor: pd.DataFrame,
                         smoothness: float = 0.075) -> tuple[pd.Series, pd.DataFrame]:
    """Fit bounded monthly proxy rates to usable moving windows.

    Rates of 3-month windows are ratios of occupation counts. We approximate
    each ratio using monthly occupation-weighted rates. The approximation and
    all residuals are explicitly audited; zero-sentinel windows are excluded.
    """
    old = source[(source.definition == OLD_NAT) & (source.domain == 'national')].copy()
    old = old.sort_values('period_end')
    good = old[(old.occupied_thousands > 0) & (old.informal_thousands > 0)]
    months = pd.date_range('2007-01-01', '2021-03-01', freq='MS')
    if len(old) != 169 or len(months) != 171 or len(good) < 145:
        raise ValueError('Old national source coverage changed')
    A = np.zeros((len(good), len(months)))
    for i, r in enumerate(good.itertuples(index=False)):
        dates = pd.date_range(r.period_start, r.period_end, freq='MS')
        pos = months.get_indexer(dates)
        if (pos < 0).any() or len(pos) != 3:
            raise ValueError('Invalid historical rolling window')
        levels = labor.loc[dates, 'employed'].to_numpy(float)
        A[i, pos] = levels / levels.sum()
    obs = good.informality_rate.to_numpy(float)
    D = np.diff(np.eye(len(months)), n=2, axis=0)
    W = np.vstack([A, smoothness**0.5 * D])
    y = np.r_[obs, np.zeros(len(D))]
    sol = lsq_linear(W, y, bounds=(0.001, 0.999), method='bvls', tol=1e-11, max_iter=800)
    if not sol.success or not np.isfinite(sol.x).all():
        raise ValueError('Constrained historical proxy reconstruction failed')
    audit = good[['period_start', 'period_end', 'informality_rate']].copy()
    audit['proxy_rate_reconstructed_weighted'] = A @ sol.x
    audit['residual_pp'] = (audit.proxy_rate_reconstructed_weighted - audit.informality_rate) * 100
    audit['valid_window'] = True
    return pd.Series(sol.x, index=months, name='old_proxy_monthly_rate'), audit


def _find_offset(month_rates: np.ndarray, occupied: np.ndarray, target_mean_informal: float) -> float:
    if not (0 < target_mean_informal < occupied.mean()):
        raise ValueError('External informal annual anchor outside employment')
    z = logit(np.clip(month_rates, 1e-7, 1 - 1e-7))
    lo, hi = -15., 15.
    for _ in range(90):
        mid = (lo + hi) / 2
        mean = np.mean(occupied * expit(z + mid))
        if mean < target_mean_informal:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _ilo_annual(ilo: pd.DataFrame) -> pd.DataFrame:
    req = {'year', 'informal_persons_ilo', 'reference_status', 'original_file_sha256'}
    if not req.issubset(ilo.columns):
        raise ValueError('ILOSTAT source contract changed')
    a = ilo.copy().sort_values('year')
    if a.year.duplicated().any() or not set(range(2007, 2020)).issubset(set(a.year)):
        raise ValueError('ILOSTAT annual history incomplete or duplicate year')
    if not (a.informal_persons_ilo > 0).all():
        raise ValueError('Invalid ILOSTAT annual informality count')
    if a.original_file_sha256.nunique() != 1:
        raise ValueError('ILOSTAT has ambiguous source hashes')
    return a.set_index('year')


def _pre2007_sensitivity(ilo: pd.DataFrame, labor: pd.DataFrame,
                         base2007: float, anchor_date: pd.Timestamp) -> tuple[pd.Series, dict]:
    """Compare zero-slope against unemployment-linked scenario (not evidence)."""
    years = list(range(2007, 2020))
    rows = []
    for year in years:
        months = labor.loc[str(year)]
        unemp = (months.unemployed / (months.unemployed + months.employed)).mean()
        annual_rate = float(ilo.loc[year, 'informal_persons_ilo'] / months.employed.mean())
        rows.append((year, unemp, annual_rate))
    arr = np.array(rows, float)
    x = arr[:, 1]
    y = logit(np.clip(arr[:, 2], .01, .99))
    # Tiny sample: simple one-variable ridge, with slope fitted in each held-out fold.
    def slope_fit(idx: np.ndarray) -> float:
        xc = x[idx] - x[idx].mean()
        yc = y[idx] - y[idx].mean()
        return float(np.clip(np.dot(xc, yc) / (np.dot(xc, xc) + .01), -3, 3))
    e_flat, e_model = [], []
    for t in range(len(y)):
        train = np.arange(len(y)) != t
        beta = slope_fit(train)
        y_center = y[train].mean()
        e_flat.append(abs(expit(y_center)-expit(y[t])))
        e_model.append(abs(expit(y_center + beta * (x[t]-x[train].mean()))-expit(y[t])))
    chosen_beta = slope_fit(np.ones(len(y), dtype=bool)) if np.mean(e_model) < np.mean(e_flat) else 0.0
    dates = pd.date_range(labor.index[0], anchor_date-pd.offsets.MonthBegin(1), freq='MS')
    unemp_series = labor.unemployed / (labor.unemployed + labor.employed)
    anchor_u = float(unemp_series.loc[anchor_date])
    pre = expit(logit(base2007) + chosen_beta * (unemp_series.loc[dates].to_numpy() - anchor_u))
    # Extrapolation guard is a scenario boundary, never a statistical interval.
    pre = np.clip(pre, max(0.01, base2007-.10), min(.99,base2007+.10))
    return pd.Series(pre,index=dates), {
        'chosen_unemployment_logit_coefficient':chosen_beta,
        'loo_mae_pp_zero_slope':float(np.mean(e_flat)*100),
        'loo_mae_pp_unemployment_slope':float(np.mean(e_model)*100),
        'pre2007_max_rate_distance_pp':float(np.max(abs(pre-base2007))*100),
        'method':'scenario_extrapolation_from_2007_first_month_and_national_unemployment; NOT independently validated'
    }


def reconstruct_history(source: pd.DataFrame, nations: pd.DataFrame,
                        recent: pd.DataFrame, ilo_data: pd.DataFrame) -> tuple[pd.DataFrame, dict[str,pd.DataFrame], dict]:
    dane, icml = _baseline(nations)
    ilo = _ilo_annual(ilo_data)
    proxy, audit_proxy = fit_historical_proxy(source, dane)
    recent = recent.copy()
    recent['period'] = pd.to_datetime(recent.period)
    recent = recent.set_index('period').sort_index()
    new_dates = month_starts(INFORMALITY_NEW_FIRST_MONTH)
    if not recent.index.equals(new_dates):
        raise ValueError(f'Recent {RECENT_MONTHS}-month candidate calendar changed')
    if not np.allclose(recent.employed_persons_fixed_dane,dane.loc[new_dates,'employed'],atol=1e-6,rtol=0):
        raise ValueError('Recent candidate employment differs from frozen DANE base')
    recent_rate = recent.informality_rate_latent.to_numpy(dtype=float)
    if not np.isfinite(recent_rate).all() or ((recent_rate<0)|(recent_rate>1)).any():
        raise ValueError('Recent candidate invalid')
    historic = pd.Series(np.nan,index=dane.index,dtype=float)
    offsets = {}
    annual_fit = []
    for year in range(2007,2020):
        ds=pd.date_range(f'{year}-01-01',periods=12,freq='MS')
        o = dane.loc[ds,'employed'].to_numpy(float)
        off = _find_offset(proxy.loc[ds].to_numpy(float),o,float(ilo.loc[year,'informal_persons_ilo']))
        offsets[year]=off
        historic.loc[ds]=expit(logit(proxy.loc[ds].to_numpy(float))+off)
        recovered=float((historic.loc[ds].to_numpy()*o).mean())
        annual_fit.append({'year':year,'source_ilo_informal_persons':float(ilo.loc[year,'informal_persons_ilo']),
                           'recovered_informal_persons':recovered,'error_persons':recovered-float(ilo.loc[year,'informal_persons_ilo']),
                           'logit_offset':off,'source_status':ilo.loc[year,'reference_status']})
    # End-point bridge inferred from the sole 2021Q1 definitional overlap.
    ds=pd.date_range('2021-01-01',periods=3,freq='MS')
    r_proxy=proxy.loc[ds].to_numpy(float)
    o=dane.loc[ds,'employed'].to_numpy(float)
    new_q1_count=float((recent.loc[ds,'informality_rate_latent'].to_numpy()*o).mean())
    off_2021=_find_offset(r_proxy,o,new_q1_count)
    months2020=pd.date_range('2020-01-01',periods=12,freq='MS')
    # Interpolate offsets between 2019-12 and 2021-01; only 2020 is inferred.
    off2020=offsets[2019]+(off_2021-offsets[2019])*np.arange(1,13)/13
    historic.loc[months2020]=expit(logit(proxy.loc[months2020].to_numpy())+off2020)
    historic.loc[new_dates]=recent_rate
    pre, diagnostic_pre=_pre2007_sensitivity(ilo,dane,float(historic.loc['2007-01-01']),pd.Timestamp('2007-01-01'))
    historic.loc[pre.index]=pre
    if historic.isna().any() or not historic.between(0,1).all():
        raise ValueError('Historic scenario has missing/invalid rates')
    rows=[]
    for label, lab in [('DANE_REFERENCIA',dane),('ICML_COMPLETO',icml)]:
        for dt, r in historic.items():
            employment=float(lab.loc[dt,'employed'])
            if dt.year < 2007:
                provenance='PRE2007_UNEMPLOYMENT_SENSITIVITY_SCENARIO_NO_ANCHORS'
                tier='VERY_HIGH'
            elif dt.year <= 2019:
                provenance='ILOSTAT_ANNUAL_ANCHORED_OLD_NONPENSION_MONTHLY_SHAPE'
                tier='HIGH'
            elif dt.year == 2020:
                provenance='OLD_NONPENSION_PROXY_WITH_2019_TO_2021_BRIDGE'
                tier='VERY_HIGH'
            else:
                provenance='GEIH_NEW_3MONTH_ROLLING_LATENT_MIN_CURVATURE'
                tier='MODERATE_MONTHLY_IDENTIFICATION'
            if label=='ICML_COMPLETO':
                provenance+='__RATE_TRANSFERRED_TO_COMPLETE_UNIVERSE_ASSUMPTION'
                tier='VERY_HIGH' if tier=='VERY_HIGH' else 'HIGH'
            informal=employment*float(r)
            rows.append({'period':dt.strftime('%Y-%m'), 'dep_code':'00',
                'national_type':label,'employed_frozen':employment,
                'informal_estimated':informal, 'formal_estimated':employment-informal,
                'informality_rate_estimated':float(r), 'provenance':provenance,
                'uncertainty_class':tier,'is_official_informality_monthly':False,
                'publication_status':'EXPERIMENTAL_NOT_CANONICAL',
                'universe_transfer_assumed':label=='ICML_COMPLETO'})
    result=pd.DataFrame(rows).sort_values(['period','national_type']).reset_index(drop=True)
    closed=(result.informal_estimated+result.formal_estimated-result.employed_frozen).abs().max()
    if closed>1e-6 or len(result)!=ROWS_NATIONAL or result[['informal_estimated','formal_estimated']].isna().any().any():
        raise ValueError('Historic candidate failed coverage or accounting gate')
    annual=pd.DataFrame(annual_fit)
    # Leave-one-year-out: the held-out ILOSTAT year is NEVER used in its offset.
    # This evaluates between-year calibration skill, unlike the tautological
    # in-sample zero residual of the exact annual anchors.
    cv=[]
    for year in range(2007,2020):
        available=[j for j in offsets if j!=year]
        left=max((j for j in available if j<year),default=None)
        right=min((j for j in available if j>year),default=None)
        if left is not None and right is not None:
            off=offsets[left]+(offsets[right]-offsets[left])*(year-left)/(right-left)
        elif left is not None:
            off=offsets[left]
        else:
            off=offsets[right]
        ds=pd.date_range(f'{year}-01-01',periods=12,freq='MS')
        emp=dane.loc[ds,'employed'].to_numpy(float)
        guess=expit(logit(proxy.loc[ds].to_numpy(float))+off)
        estimate=float(np.mean(emp*guess))
        actual=float(ilo.loc[year,'informal_persons_ilo'])
        cv.append({'year':year,'actual_ilo':actual,'predicted_ilo_leave_year_out':estimate,
                   'error_pct':(estimate/actual-1)*100,
                   'year_had_break_note':str(ilo.loc[year,'reference_status'])=='Break in series'})
    cv_table=pd.DataFrame(cv)
    # Structural proxy sensitivity: regularization is a MODEL choice.
    # This is diagnostics only; the base candidate remains 0.075.
    sensitivity=[]
    for value in (0.02,0.075,0.25):
        p_alt,a_alt=fit_historical_proxy(source,dane,smoothness=value)
        sensitivity.append({'smoothness':value,
            'mae_old_rolling_rate_pp':float(a_alt.residual_pp.abs().mean()),
            'max_difference_in_monthly_proxy_pp_vs_base':float(abs(p_alt-proxy).max()*100)})
    sensitivity_table=pd.DataFrame(sensitivity)
    # Comparison only. 2021 has a documented change of frame and a large discrepancy.
    check=[]
    for year in sorted(set(ilo.index)&set(range(2021,LAST_YEAR+1))):
        if year>2025:continue
        ds=pd.date_range(f'{year}-01-01',periods=12,freq='MS')
        v=float((historic.loc[ds].to_numpy()*dane.loc[ds,'employed'].to_numpy()).mean())
        ref=float(ilo.loc[year,'informal_persons_ilo'])
        check.append({'year':year,'ilo_informal':ref,'geih_latent_informal':v,
                      'difference_pct':(v/ref-1)*100,'ilo_status':ilo.loc[year,'reference_status'],
                      'used_for_calibration':False})
    external=pd.DataFrame(check)
    gaps=result[result.national_type.eq('DANE_REFERENCIA')].copy()
    gaps['delta_rate_pp']=gaps.informality_rate_estimated.diff()*100
    gaps['delta_informal_yoy_pct']=gaps.informal_estimated.pct_change(12)*100
    gaps['absolute_jump_rate_pp']=gaps.delta_rate_pp.abs()
    big=gaps[(gaps.absolute_jump_rate_pp>3)|(gaps.delta_informal_yoy_pct.abs()>100)]
    stats={'months':len(dane),'national_series':2,'historical_years_ilo_anchored':13,
           'old_national_windows_total':169,'old_windows_used':len(audit_proxy),
           'old_windows_excluded_zero':169-len(audit_proxy),
           'proxy_window_mae_pp':float(audit_proxy.residual_pp.abs().mean()),
           'ilo_leave_year_out_mae_pct':float(cv_table.error_pct.abs().mean()),
           'ilo_leave_year_out_max_abs_pct':float(cv_table.error_pct.abs().max()),
           'proxy_regularization_sensitivity':sensitivity_table.to_dict(orient='records'),
           'proxy_window_max_abs_pp':float(audit_proxy.residual_pp.abs().max()),
           'annual_ilo_anchor_max_abs_persons':float(annual.error_persons.abs().max()),
           'max_absolute_identity_error_persons':float(closed),
           'definitional_bridge_offset_2019':float(offsets[2019]),
           'definitional_bridge_offset_2021_q1':float(off_2021),
           'annual_external_comparisons':external.where(pd.notna(external),None).to_dict(orient='records'),
           'flagged_rate_or_yoy_jumps':len(big),'pre2007_sensitivity':diagnostic_pre,
           'status':'SCENARIO_1993_2026_NOT_COMPARABLE_OFFICIAL_HISTORY_NOT_CANONICAL',
           'frozen_labor_modified':False}
    audits={'old_proxy_windows':audit_proxy,'ilo_annual_anchor':annual,'ilo_leave_year_out':cv_table,
            'proxy_sensitivity':sensitivity_table,'ilo_external_comparison':external,
            'rate_jump_flags':big[['period','provenance','delta_rate_pp','delta_informal_yoy_pct']].reset_index(drop=True),
            'monthly_proxy_2007_2021':pd.DataFrame({'period':proxy.index.strftime('%Y-%m'),
                                                   'non_pension_proxy_rate_latent':proxy.to_numpy()})}
    return result,audits,stats


def run(sources: Path, nationals: Path, recent: Path, ilo: Path, out: Path) -> dict:
    out=Path(out)
    if out.exists():
        raise FileExistsError(f'Historical run already exists: {out}')
    s=pd.read_csv(sources)
    n=pd.read_csv(nationals,dtype={'dep_code':str})
    r=pd.read_csv(recent)
    i=pd.read_csv(ilo)
    products,audits,metrics=reconstruct_history(s,n,r,i)
    (out/'candidates').mkdir(parents=True)
    (out/'audit').mkdir()
    generated={}
    target=out/'candidates/national_informality_1993_2026_experimental.csv'
    products.to_csv(target,index=False)
    generated[str(target.relative_to(out))]=_sha256(target)
    for key,df in audits.items():
        p=out/f'audit/{key}.csv';df.to_csv(p,index=False)
        generated[str(p.relative_to(out))]=_sha256(p)
    hashes={key:_sha256(path) for key,path in [
        ('source_observations_csv',sources),('nacionales_frozen_csv',nationals),
        ('recent_monthly_candidate_csv',recent),('ilo_colombia_annual_csv',ilo)]}
    (out/'audit/summary.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    generated['audit/summary.json']=_sha256(out/'audit/summary.json')
    (out/'manifest.json').write_text(json.dumps({'inputs_sha256':hashes,'outputs_sha256':generated,
        'method':'annual_ilo_anchor + old_nonpension_rolling_signal + 2020_bridge + pre2007_sensitivity',
        'publication_status':'EXPERIMENTAL_NOT_CANONICAL'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return metrics
