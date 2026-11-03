"""H11: nonnegative source-aware inverse of 3-month *moving* sector estimates.

A DANE three-month rolling observation is a linear constraint on monthly levels,
not a directly observed calendar month. Its 2-dimensional nullspace means that
exact reproduction need not give credible monthly values. This module explicitly
trades fidelity against identification under the observed monthly occupied levels,
using blocked window holdouts and preserving direct monthly 2015 DANE sources.

No independent sectoral microdata, no artificial monthly source values, and no
rewriting of frozen ICML labor/urban/informality input series.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from icml.sectoral_vintage_bridge import FINAL_14

CATEGORIES = (*FINAL_14, 'NO_INFO')
MONTHS = pd.period_range('2001-07', '2015-03', freq='M').strftime('%Y-%m').tolist()
WINDOWS = MONTHS[2:]
CV_STARTS = (22,45,68,91,114,135)  # fixed date-scoped contiguous 6-window holdouts
REGULARIZATIONS = (0.03, 0.1, 0.3, 1.0)


def _simplex(rows: np.ndarray) -> np.ndarray:
    """Euclidean projection on the nonnegative unit simplex, for each month."""
    rank = np.sort(rows, axis=1)[:, ::-1]
    cumul = np.cumsum(rank, axis=1) - 1.0
    denom = np.arange(1, rows.shape[1]+1)
    valid = rank > cumul/denom
    cardinality = valid.sum(axis=1)
    threshold = cumul[np.arange(len(rows)), cardinality-1]/cardinality
    return np.maximum(rows - threshold[:, None], 0.0)


def build_rolling_matrix(employed: np.ndarray) -> np.ndarray:
    """One row per overlapping 3m window, weights use monthly ICML employed."""
    e = np.asarray(employed, dtype=float)
    if e.shape != (165,) or not np.isfinite(e).all() or (e<=0).any():
        raise ValueError('H11_MONTHLY_EMPLOYED_WRONG_DOMAIN_OR_COVERAGE')
    a = np.zeros((163, 165))
    for i in range(163):
        a[i,i:i+3] = e[i:i+3] / e[i:i+3].sum()
    return a


def anchored_monthly_recent(recent: pd.DataFrame, totals: pd.DataFrame,
                            final_2015_share: np.ndarray) -> tuple[np.ndarray, float]:
    """Exact published 2015 Jan-Mar 13-group monthly rates; B/D_E split is assumed."""
    anchor_periods = MONTHS[-3:]
    rr=recent.loc[recent.period.isin(anchor_periods)].copy()
    if (rr.duplicated(['period','sector_code']).any() or
        rr.groupby('period').sector_code.nunique().ne(13).any() or
        set(rr.period)!=set(anchor_periods)):
        raise ValueError('H11_2015_DIRECT_MONTHLY_ANCHORS_MISSING')
    if not rr.temporal_support.eq('calendar_month').all():
        raise ValueError('H11_2015_ANCHOR_MUST_BE_DIRECT_MONTHLY')
    p=rr.pivot(index='period', columns='sector_code', values='employed_persons').reindex(anchor_periods)
    total=totals.set_index('period').reindex(anchor_periods)
    p['NO_INFO']=total.no_informa_persons
    if not {'B_D_E_COMBINED','NO_INFO'} <= set(p):
        raise ValueError('H11_RECENT_MISSING_GROUPS')
    ratio = float(final_2015_share[CATEGORIES.index('B')]/
                  (final_2015_share[CATEGORIES.index('B')] + final_2015_share[CATEGORIES.index('D_E')]))
    p['B'] = p.B_D_E_COMBINED*ratio
    p['D_E'] = p.B_D_E_COMBINED*(1.0-ratio)
    values=p[list(CATEGORIES)].to_numpy(float)
    if not np.isfinite(values).all() or (values<0).any():
        raise ValueError('H11_RECENT_INVALID_MONTHLY_LEVELS')
    values=values/values.sum(axis=1,keepdims=True)
    return values,ratio


def inverse_rolling(a: np.ndarray, targets: np.ndarray, recent_anchor: np.ndarray,
                    strength: float, *, omitted: np.ndarray | None = None,
                    iterations: int=1800) -> np.ndarray:
    """Convex quadratic fit with fixed direct-monthly boundary and simplex rows.

    The squared first difference only identifies the unobserved 2-dimensional
    component and inconsistencies of overlapping publication windows. It is *not*
    smoothing of DANE monthly observations (which are fixed and never altered).
    """
    if targets.shape != (163,len(CATEGORIES)) or recent_anchor.shape!=(3,len(CATEGORIES)):
        raise ValueError('H11_DIMENSION_INCONSISTENCY')
    if (targets<0).any() or not np.isfinite(targets).all():
        raise ValueError('H11_INVALID_ROLLING_SHARES')
    if not np.allclose(targets.sum(axis=1),1,atol=1e-8):
        raise ValueError('H11_MOVING_WINDOWS_NOT_CLOSING')
    mask=np.ones(len(a),dtype=bool) if omitted is None else ~omitted
    aa=a[mask]
    t=targets[mask]
    d=np.diff(np.eye(a.shape[1]),axis=0)
    af,ac=aa[:,:-3],aa[:,-3:]
    df,dc=d[:,:-3],d[:,-3:]
    H=af.T@af + strength*(df.T@df)
    rhs=af.T@(t-ac@recent_anchor) - strength*df.T@dc@recent_anchor
    # L=norm(H) is the Lipschitz constant of the gradient.
    lip=float(np.linalg.eigvalsh(H)[-1])
    init=np.tile(t.mean(axis=0),(af.shape[1],1))
    x=_simplex(init)
    z=x.copy(); beta=1.0
    for it in range(iterations):
        xn=_simplex(z-(H@z-rhs)/lip)
        next_beta=(1+np.sqrt(1+4*beta*beta))/2
        z=xn+(beta-1)/next_beta*(xn-x)
        x=xn;beta=next_beta
    out=np.vstack((x,recent_anchor))
    if not np.isfinite(out).all() or (out < -1e-11).any() or np.abs(out.sum(axis=1)-1).max()>1e-10:
        raise ValueError('H11_SIMPLEX_OR_NUMERIC_FAILURE')
    return out


def _sha256(path: Path) -> str:
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def run(*, rolling_csv: str|Path, recent_csv: str|Path, totals_csv: str|Path,
        nationals_csv: str|Path, output: str|Path) -> dict:
    """Produce H11 candidate monthly 2001–2014, with CV and method tradeoffs."""
    rolling_csv=Path(rolling_csv);recent_csv=Path(recent_csv)
    totals_csv=Path(totals_csv);nationals_csv=Path(nationals_csv)
    dest=Path(output);dest.mkdir(parents=True,exist_ok=True)
    hist=pd.read_csv(rolling_csv)
    recent=pd.read_csv(recent_csv)
    totals=pd.read_csv(totals_csv)
    nationals=pd.read_csv(nationals_csv)
    req={'period_end','national_type','scenario','sector_code','sector_share','window_months','is_official_monthly_sector_observation'}
    if not req.issubset(hist):raise ValueError('H11_OLD_VINTAGE_COLUMNS_MISSING')
    if hist.window_months.ne(3).any() or hist.is_official_monthly_sector_observation.astype(str).str.lower().eq('true').any():
        raise ValueError('H11_OLD_ROLLING_MISREPRESENTED_AS_MONTHLY')
    scenarios=['RAW_HIST_VINTAGE','HALF_2015_BRIDGE','FULL_2015_BRIDGE']
    national_types=['ICML_COMPLETO','DANE_REFERENCIA']
    expect=pd.MultiIndex.from_product([WINDOWS,CATEGORIES],names=['period_end','sector_code'])
    ymap={}
    for sc in scenarios:
        for universe in national_types:
            dd=hist[(hist.scenario==sc)&(hist.national_type==universe)]
            if dd.duplicated(['period_end','sector_code']).any() or len(dd)!=len(expect):
                raise ValueError('H11_HISTORIC_DUPLICATE_OR_MISSING_WINDOW')
            y=dd.set_index(['period_end','sector_code']).sector_share.reindex(expect)
            if y.isna().any():raise ValueError('H11_HISTORIC_WINDOW_CATEGORIES_MISSING')
            ymap[(sc,universe)]=y.to_numpy(float).reshape(len(WINDOWS),len(CATEGORIES))
    for universe in national_types:
        n=nationals[nationals.national_type.eq(universe)].set_index('period').reindex(MONTHS)
        if n.employed.isna().any():raise ValueError('H11_MISSING_MONTHLY_OCCUPIED')
    complete=nationals[nationals.national_type.eq('ICML_COMPLETO')].set_index('period').reindex(MONTHS)
    E=complete.employed.to_numpy(float)
    a=build_rolling_matrix(E)
    anchor,ratio=anchored_monthly_recent(recent,totals,ymap[('FULL_2015_BRIDGE','ICML_COMPLETO')][-1])
    result=[];cv=[];summary=[];audit=[];audit_sector=[]
    target=ymap[('FULL_2015_BRIDGE','ICML_COMPLETO')]
    for lam in REGULARIZATIONS:
        for begin in CV_STARTS:
            omitted=np.zeros(len(WINDOWS),dtype=bool)
            omitted[begin:begin+6]=True
            q=inverse_rolling(a,target,anchor,lam,omitted=omitted)
            residual=(a@q-target)*100
            known=np.where(~omitted)[0]+2
            naive=np.column_stack([np.interp(np.arange(165),known,target[~omitted,j])
                     for j in range(len(CATEGORIES))])
            naive[-3:]=anchor
            naive=_simplex(naive)
            baseline_error=(a[omitted]@naive-target[omitted])*100
            cv.append(dict(regularization=lam,first_hidden_window=WINDOWS[begin],
              last_hidden_window=WINDOWS[begin+5],hidden_windows=6,
              mean_absolute_error_pp=float(np.abs(residual[omitted]).mean()),
              simple_linear_interpolation_mae_pp=float(np.abs(baseline_error).mean()),
              p95_absolute_error_pp=float(np.percentile(np.abs(residual[omitted]),95)),
              max_absolute_error_pp=float(np.abs(residual[omitted]).max()),
              validation_type='CONTIGUOUS_HIDDEN_MOVING_WINDOWS_WITH_2015_BOUNDARY__NOT_FUTURE_FORECAST'))
    cvdf=pd.DataFrame(cv)
    chosen=float(cvdf.groupby('regularization').mean_absolute_error_pp.mean().idxmin())
    for sc in scenarios:
        # One canonical share vector on the ICML completo, transfer counts via
        # each universe's *own employed*, not by a population expansion factor.
        yy=ymap[(sc,'ICML_COMPLETO')]
        q=inverse_rolling(a,yy,anchor,chosen)
        r=(a@q-yy)*100
        volatility=np.diff(q,axis=0)*100
        summary.append(dict(scenario=sc,regularization=chosen,rolling_fit_mae_pp=float(np.abs(r).mean()),
              rolling_fit_p95_pp=float(np.percentile(np.abs(r),95)),
              rolling_fit_max_pp=float(np.abs(r).max()),
              month_jump_p95_pp=float(np.percentile(np.abs(volatility),95)),
              month_jump_max_pp=float(np.abs(volatility).max()),
              jump_count_over_5pp=int((np.abs(volatility)>5).sum()),
              minimum_share=float(q.min()),maximum_monthly_total_residual=float(np.abs(q.sum(axis=1)-1).max()),
              observation_status='MONTHLY_LATENT_NOT_DANE_DIRECT'))
        for universe in national_types:
            n=nationals[nationals.national_type.eq(universe)].set_index('period').reindex(MONTHS)
            ee=n.employed.to_numpy(float)
            for idx,p in enumerate(MONTHS):
                # 2015 uses official 13 monthly for anchors, but B/D_E split not official
                status=('DIRECT_2015_MONTHLY_13_GROUPS_WITH_ESTIMATED_B_DE_SPLIT' if idx>=162
                    else ('BACKCAST_EARLY_MONTH_NO_FULL_WINDOW' if idx<2 else 'LATENT_MONTH_FROM_MOVING_3M_WINDOWS'))
                for j,s in enumerate(CATEGORIES):
                    result.append(dict(period=p,national_type=universe,scenario=sc,
                     sector_code=s,sector_share=float(q[idx,j]),
                     employed_sector_persons=float(ee[idx]*q[idx,j]),
                     employed_total_persons=float(ee[idx]),
                     observation_status=status,temporal_support='estimated_calendar_month',
                     direct_official_observation=False,source_rolling_window='2001-09_to_2015-03',
                     sector_classification='EXPERIMENTAL_REV3_REV4_HARMONIZED',
                     shared_composition_assumption=True,
                     selected_regularization=chosen))
            d_y=ymap[(sc,universe)]
            aa=build_rolling_matrix(ee)
            fit=aa@q
            for i,w in enumerate(WINDOWS):
                for j,sector in enumerate(CATEGORIES):
                    audit_sector.append(dict(scenario=sc,national_type=universe,window_end=w,
                         sector_code=sector,source_window_share=float(d_y[i,j]),
                         reconstructed_rolling_share=float(fit[i,j]),
                         residual_pp=float((fit[i,j]-d_y[i,j])*100),
                         status='EXPERIMENTAL_INVERSION__NOT_AN_OBSERVED_MONTH'))
                audit.append(dict(scenario=sc,national_type=universe,window_end=w,
                     mean_absolute_error_pp=float(np.abs(fit[i]-d_y[i]).mean()*100),
                     max_absolute_error_pp=float(np.abs(fit[i]-d_y[i]).max()*100),
                     source_window='observed_3_months',estimated_monthly_sources='modelled_from_rolling_windows'))
    resultdf=pd.DataFrame(result);aud=pd.DataFrame(audit);summarydf=pd.DataFrame(summary)
    # quality checks of every monthly domain, not just national totals
    checks=resultdf.groupby(['period','national_type','scenario'],sort=True).agg(
        sector_sum=('employed_sector_persons','sum'),employed=('employed_total_persons','first'),
        n_categories=('sector_code','nunique'),min_share=('sector_share','min'))
    if checks.n_categories.ne(15).any() or checks.min_share.lt(-1e-11).any():
        raise ValueError('H11_MONTHLY_CATEGORIES_OR_NEGATIVE_LEVELS')
    if (checks.sector_sum-checks.employed).abs().max()>1e-5:
        raise ValueError('H11_MONTHLY_EMPLOYMENT_IDENTITY_BROKEN')
    reports={
      '11_estimaciones_mensuales_2001_2015_EXP_NO_OFICIALES.csv':resultdf,
      '11_validacion_ventanas_ocultas.csv':cvdf,
      '11_comparacion_regularizaciones_y_escenarios.csv':summarydf,
      '11_fidelidad_ventanas_3m_por_universo.csv':aud,
      '11_residuales_por_sector_y_ventana.csv':pd.DataFrame(audit_sector),
    }
    for filename,frame in reports.items():frame.to_csv(dest/filename,index=False,float_format='%.12g',encoding='utf-8')
    information={
       'status':'H11_COMPUTATIONAL_CANDIDATE__NOT_CANONICAL',
       'historical_months_estimated':162,'recent_2015_months_boundary':3,
       'windows_observed':163,'source_window_months':3,
       'observed_direct_monthly_13_groups_preserved':True,
       'real_official_monthly_historical_14_sector_rows':0,
       'starts':'2001-07','ends':'2015-03','future_2015_2026_13_groups':'INPUT_PRESERVED_OUTSIDE_THIS_CANDIDATE',
       'before_2001':'NOT_ESTIMATED__NO_SECTORAL_ANNEX_ANCHORS',
       'two_universes':'ONE_ICML_COMPLETE_RATE_VECTOR_WITH_DANE_REPRESENTED_EMPLOYED_TRANSFER',
       'cv_approach':'HIDDEN_CONTIGUOUS_ROLLING_WINDOWS_INTERPOLATION_NOT_REAL_FORWARD_FORECAST',
       'regularization_selected_on_cv':chosen,
       'B_DE_2015_split_ratio_assumed_from_last_legacy_window':ratio,
       'limitations':['Rolling windows do not uniquely identify individual months.',
          '2015 B/D_E boundary split is assumed, not official directly monthly.',
          'CIIU3->CIIU4 and two national vintage discrepancies are approximations.',
          'No sectoral 1993-2001 anchors; no backcast to 1993 claimed.',
          'Regularization penalizes implausible oscillation only in latent estimates, not observed monthly DANE.',
          'Blocked-window validation reuses following windows/2015 boundary, not a forward prediction test.'],
       'input_sha256':{p.name:_sha256(p) for p in [rolling_csv,recent_csv,totals_csv,nationals_csv]},
       'files':{k:{'rows':len(df),'sha256':_sha256(dest/k)} for k,df in reports.items()},
       'max_monthly_count_residual_persons':float((checks.sector_sum-checks.employed).abs().max()),
       'max_source_window_fit_error_pp':float(aud.max_absolute_error_pp.max()),
       'holdout_mae_by_penalty_pp':{str(k):float(v) for k,v in cvdf.groupby('regularization').mean_absolute_error_pp.mean().items()},
       'simple_interpolation_baseline_cv_mae_pp':float(cvdf.simple_linear_interpolation_mae_pp.mean()),
       'source_window_large_errors_over_1pp':int((pd.DataFrame(audit_sector).residual_pp.abs()>1).sum()),
       'quality_publication_status':'BLOCKED__UNIQUE_MONTHS_NOT_IDENTIFIED_AND_PRE_2001_UNANCHORED',
    }
    (dest/'11_puerta_calidad.json').write_text(json.dumps(information,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
    return information
