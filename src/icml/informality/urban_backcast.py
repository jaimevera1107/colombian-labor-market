"""DANE-only, experimental urban-first historical informal-employment reconstruction.

The 2001-2009 13-city T5 aggregate, 2005/06 individual T10 observations,
2007-2021 city T5 rolling windows, and 2021+ newer GEIH definitions are
*distinct estimands*. Never label inferred monthly points as DANE observations.
Frozen labor bases are read-only; official windows remain separately auditable.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.linalg import solve
from scipy.special import expit, logit
from icml.domain.cutoff import (
    CITY13_WINDOWS,
    INFORMALITY_NEW_FIRST_MONTH,
    N_MONTHS,
    ROWS_33,
    ROWS_NATIONAL,
    month_starts,
)

from icml.informality.national import OLD_CITY, OLD_NAT, NEW, _exact_min_curvature

MONTHS = month_starts()
OLD_MONTHS = pd.date_range('2007-01-01', '2021-03-01', freq='MS')
NEW_MONTHS = month_starts(INFORMALITY_NEW_FIRST_MONTH)
FIRST_13 = (5, 8, 11, 13, 17, 23, 50, 52, 54, 66, 68, 73, 76)
ALIAS = {
    'medellin a.m.': 5, 'medellin': 5, 'barranquilla a.m.': 8,
    'barranquilla': 8, 'bogota d.c.': 11, 'bogota': 11,
    'cartagena': 13, 'tunja': 15, 'manizales a.m.': 17, 'manizales': 17,
    'florencia': 18, 'popayan': 19, 'valledupar': 20,
    'monteria': 23, 'quibdo': 27, 'neiva': 41, 'riohacha': 44,
    'santa marta': 47, 'villavicencio': 50, 'pasto': 52,
    'cucuta a.m.': 54, 'cucuta': 54, 'armenia': 63,
    'pereira a.m.': 66, 'pereira': 66, 'bucaramanga a.m.': 68,
    'bucaramanga': 68, 'sincelejo': 70, 'ibague': 73, 'cali a.m.': 76,
    'cali': 76,
}
LABOR = ('population', 'working_age', 'labor_force', 'employed', 'unemployed', 'inactive')


def _normal(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).lower())
                   if not unicodedata.combining(c)).strip()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_labor(city: pd.DataFrame, national: pd.DataFrame) -> None:
    if city.duplicated(['city_code', 'period']).any() or national.duplicated(['national_type', 'period']).any():
        raise ValueError('Duplicate frozen labor keys')
    if city.city_code.nunique() != 33 or len(city) != 33*N_MONTHS:
        raise ValueError('Urban labor input not complete')
    if set(national.national_type) != {'ICML_COMPLETO', 'DANE_REFERENCIA'} or len(national) != ROWS_NATIONAL:
        raise ValueError('National frozen labor universe changed')
    for df in (city, national):
        tolerance = 1.1 if df is national else .001  # DANE source whole-person rounding
        if df[list(LABOR)].isna().any().any() or (df[list(LABOR)] < 0).any().any():
            raise ValueError('Missing/negative labor levels')
        if (df.employed - df.labor_force + df.unemployed).abs().max() > tolerance:
            raise ValueError('Labor market identity broken')
        if (df.working_age - df.labor_force - df.inactive).abs().max() > tolerance:
            raise ValueError('Inactive identity broken')
    for _, group in city.groupby('city_code'):
        if not pd.DatetimeIndex(pd.to_datetime(group.period)).sort_values().equals(MONTHS):
            raise ValueError('City calendar incomplete')


def _solve_rolling_rates(sources: pd.DataFrame, calendar: pd.DatetimeIndex,
                         lam: float = 0.02) -> tuple[np.ndarray, pd.DataFrame]:
    """Regularized inversion of overlapping *rates*, not published monthly observations.

    Count-based official ratios need varying monthly employment weights; here each
    official window rate is approximated by an equal-weight mean. Residuals and
    limitations are reported; no exact reproduction is asserted.
    """
    source = sources.copy()
    source = source[(source.occupied_thousands > 0) &
                    (source.informal_thousands >= 0) &
                    source.eligible_for_training.astype(bool)]
    if source.empty:
        raise ValueError('No valid rolling windows')
    A = np.zeros((len(source), len(calendar)))
    for j, r in enumerate(source.itertuples(index=False)):
        start = pd.Timestamp(r.period_start)
        idx = calendar.get_indexer(pd.date_range(start, periods=3, freq='MS'))
        if (idx < 0).any():
            raise ValueError(f'Window out of calendar: {r.period_start}')
        A[j, idx] = 1/3
    y = source.informality_rate.to_numpy(dtype=float)
    d2 = np.diff(np.eye(len(calendar)), n=2, axis=0)
    d1 = np.diff(np.eye(len(calendar)), axis=0)
    # weak centering prevents singular long holes without erasing measured trends
    h = A.T@A + lam*(d2.T@d2) + 0.00005*(d1.T@d1) + 1e-7*np.eye(len(calendar))
    b = A.T@y + 1e-7*np.mean(y)
    x = np.clip(solve(h, b, assume_a='pos'), 0.005, 0.995)
    report = source[['period_start','period_end','concept','definition','informality_rate']].copy()
    report['recovered_rate_window_equal_weight'] = A@x
    report['residual_pp'] = 100*(report.recovered_rate_window_equal_weight - y)
    report['is_exact_official_monthly'] = False
    return x, report


def _city_windows(sources: pd.DataFrame, definition: str, calendar: pd.DatetimeIndex,
                  lam: float) -> tuple[dict[int,np.ndarray],pd.DataFrame]:
    data = sources[(sources.definition == definition)&(sources.domain=='city')].copy()
    data['code'] = data.concept.map(lambda c: ALIAS.get(_normal(c)))
    if data[data.code.notna()].duplicated(['code','period_end']).any():
        raise ValueError('Aliased duplicates in DANE city source')
    output={}; audits=[]
    for code, sub in data[data.code.notna()].groupby('code'):
        if definition == NEW:
            ordered = sub.sort_values('period_start').reset_index(drop=True)
            if len(ordered) != len(calendar)-2 or not ordered.eligible_for_training.all():
                raise ValueError('Incomplete recent official urban windows')
            occ = _exact_min_curvature(ordered.occupied_thousands.to_numpy(float)*1000)
            informal = _exact_min_curvature(ordered.informal_thousands.to_numpy(float)*1000)
            if not (np.isfinite(occ).all() and np.isfinite(informal).all() and
                    (occ>0).all() and (informal>=0).all() and (informal<=occ).all()):
                raise ValueError('Recent windows require constrained inversion')
            x = informal/occ
            report=ordered[['period_start','period_end','concept','definition','informality_rate']].copy()
            rr=[]; ir=[]; er=[]
            for j in range(len(ordered)):
                ir.append(float(np.mean(informal[j:j+3])-ordered.informal_thousands.iloc[j]*1000))
                er.append(float(np.mean(occ[j:j+3])-ordered.occupied_thousands.iloc[j]*1000))
                rr.append(float(np.mean(informal[j:j+3])/np.mean(occ[j:j+3])))
            report['recovered_rate_window_equal_weight'] = rr
            report['residual_pp'] = 100*(report.recovered_rate_window_equal_weight-report.informality_rate)
            report['informal_count_residual_persons'] = ir
            report['employed_count_residual_persons'] = er
            report['window_method']='exact_count_inversion_min_second_difference'
            report['is_exact_official_monthly']=False
        else:
            x, report = _solve_rolling_rates(sub, calendar,lam)
            report['window_method']='regularized_rate_inversion_missing_2020'
        report['city_code']=int(code)
        audits.append(report)
        output[int(code)] = x
    return output, pd.concat(audits,ignore_index=True)


def _urban_table(df: pd.DataFrame) -> dict[int,pd.DataFrame]:
    out={}
    for code, group in df.groupby('city_code'):
        g=group.copy();g.index=pd.to_datetime(g.period)
        out[int(code)]=g.reindex(MONTHS)
    return out


def _rate_13(est: dict[int,np.ndarray], labor: dict[int,pd.DataFrame]) -> np.ndarray:
    e=np.vstack([labor[c].employed.to_numpy(float) for c in FIRST_13])
    r=np.vstack([est[c] for c in FIRST_13])
    return (e*r).sum(axis=0)/e.sum(axis=0)


def _apply_13_anchors(old_values: dict[int,np.ndarray], labor: dict[int,pd.DataFrame],
                      anchors: pd.DataFrame) -> tuple[dict[int,np.ndarray],pd.DataFrame]:
    """Apply ONLY historical DANE T5 13-city aggregate, 2001-2006.

    City-specific T10 readings are an auxiliary structure diagnostic, never
    treated as T5 rates. Shared logit offsets preserve relative city ordering.
    """
    target=anchors[(anchors.definition=='hasta_5_trabajadores')&anchors.year.between(2001,2006)]
    ix = MONTHS.get_indexer(pd.date_range('2001-01-01','2006-12-01',freq='MS'))
    shift_anchor=[]
    for r in target.itertuples(index=False):
        months=pd.date_range(r.period_start, r.period_end,freq='MS')
        pos=MONTHS.get_indexer(months)
        occ=np.array([labor[c].employed.to_numpy(float)[pos] for c in FIRST_13])
        rates=np.array([old_values[c][pos] for c in FIRST_13])
        target_r=r.rate_pct/100
        lo,hi=-2.0,2.0
        for _ in range(48):
            mid=(lo+hi)/2
            avg=np.mean((occ*expit(logit(np.clip(rates,.001,.999))+mid)).sum(axis=0)/occ.sum(axis=0))
            if avg < target_r:lo=mid
            else:hi=mid
        shift_anchor.append((int(pos[1]),(lo+hi)/2))
    # extrapolate correction at the 2001 and 2006 boundaries; smoothly join 2007
    x=np.array([s[0] for s in shift_anchor]+[int(MONTHS.get_loc(pd.Timestamp('2007-01-01')))])
    y=np.array([s[1] for s in shift_anchor]+[0.0])
    off=np.interp(ix,x,y,left=y[0],right=0.0)
    for code in FIRST_13:
        old_values[code][ix] = expit(logit(np.clip(old_values[code][ix],.001,.999))+off)
    # Numerical adjustment per 3-month target: levels exact to floating precision,
    # other months get smooth interpolation, so slight residuals may remain.
    logs=[]
    aggregate=_rate_13(old_values,labor)
    for r in target.itertuples(index=False):
        pos=MONTHS.get_indexer(pd.date_range(r.period_start,r.period_end,freq='MS'))
        achieved=float(np.mean(aggregate[pos]))
        logs.append({'year':int(r.year),'definition':r.definition,'official_rate':r.rate_pct/100,
                     'reconstructed_rate':achieved,'residual_pp':(achieved-r.rate_pct/100)*100,
                     'window':'apr_jun','is_city_specific_anchor':False,
                     'source_url':r.source_url})
    return old_values,pd.DataFrame(logs)


def _nearest_donor(code: int, available: list[int], labor:dict[int,pd.DataFrame]) -> tuple[int,float]:
    sl=slice('2014-01-01','2019-12-01')
    def descriptors(c):
        z=labor[c].loc[sl]
        return np.array([(z.unemployed/z.labor_force).mean(),
                         (z.employed/z.working_age).mean(),
                         np.log(z.employed.mean())])
    one=descriptors(code)
    donors=np.vstack([descriptors(c) for c in available])
    std=np.std(donors,axis=0);std[std<1e-5]=1.
    distance=np.linalg.norm((donors-one)/std,axis=1)
    j=int(np.argmin(distance))
    return available[j],float(distance[j])


def _pre2007_trajectory(r2007: np.ndarray, code:int, labor: dict[int,pd.DataFrame],
                        coeff: float=0.45) -> np.ndarray:
    ix=MONTHS.get_indexer(pd.date_range('1993-01-01','2006-12-01',freq='MS'))
    u=(labor[code].unemployed / labor[code].labor_force).to_numpy(float)
    center=np.mean(u[MONTHS.get_indexer(pd.date_range('2007-01-01','2007-03-01',freq='MS'))])
    head=float(np.mean(r2007[:3]))
    return expit(logit(np.clip(head,.01,.99)) + coeff*(u[ix]-center))


def _national_old_proxy(sources: pd.DataFrame) -> np.ndarray:
    sub=sources[(sources.definition==OLD_NAT)&(sources.domain=='national')]
    x,_=_solve_rolling_rates(sub, OLD_MONTHS,0.06)
    return x


def _national_historical(urban:pd.DataFrame, national:pd.DataFrame, sources:pd.DataFrame,
                         recent:pd.DataFrame, anchors13:pd.DataFrame, strength:float=.5) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    first = urban[urban.city_code.isin(FIRST_13)].copy()
    first['period']=pd.to_datetime(first.period)
    g=first.groupby('period',sort=True).apply(
        lambda d: (d.employed_frozen*d.informality_rate).sum()/d.employed_frozen.sum(),
        include_groups=False).reindex(MONTHS)
    old_urban=first.groupby('period',sort=True).apply(
        lambda d: (d.employed_frozen*d.old_t5_rate_auxiliary).sum()/d.employed_frozen.sum(),
        include_groups=False).reindex(MONTHS)
    # The actual DANE 13-area *aggregate* is not the same as a 13-city
    # ICML employment-weighted average. Preserve this domain distinction.
    old13_source=sources[(sources.definition==OLD_CITY)&
                         (sources.concept=='Total 13 áreas')]
    new13_source=sources[(sources.definition==NEW)&
                         (sources.concept=='13 ciudades y A.M.')]
    old13_src,_=_solve_rolling_rates(old13_source,OLD_MONTHS,.025)
    n13=new13_source.sort_values('period_start')
    occ13=_exact_min_curvature(n13.occupied_thousands.to_numpy(float)*1000)
    inf13=_exact_min_curvature(n13.informal_thousands.to_numpy(float)*1000)
    if len(n13)!=CITY13_WINDOWS or not ((occ13>0)&(inf13>=0)&(inf13<=occ13)).all():
        raise ValueError('Incompatible 13-area recent official windows')
    new13_src=inf13/occ13
    old13=old_urban.to_numpy(float).copy()
    ixold=MONTHS.get_indexer(OLD_MONTHS)
    old13[ixold]=old13_src
    group13=old13.copy()
    i2021=MONTHS.get_indexer(NEW_MONTHS)
    # Transfer the OLD T5 to NEW level through observed overlap,
    # but retain the DANE 13-area pre-2021 time profile.
    overlap_delta=float(np.mean(logit(new13_src[:3])-
                                logit(np.clip(old13[i2021[:3]],.005,.995))))
    group13[:i2021[0]]=expit(logit(np.clip(old13[:i2021[0]],.005,.995))+overlap_delta)
    group13[i2021]=new13_src
    r13=np.clip(group13,.01,.99)
    old_nat=_national_old_proxy(sources)
    # Difference between two official DANE historical concepts, used
    # as an auxiliary feature. Their *levels* are not declared comparable.
    iold=MONTHS.get_indexer(OLD_MONTHS)
    diff=logit(np.clip(old_nat,.01,.99))-logit(np.clip(old13_src,.01,.99))
    # Unmeasured pre-2007 gap is held at its first 2007 estimate, not invented.
    differential=np.full(len(MONTHS),diff[0]); differential[iold]=diff
    pivot=int(MONTHS.get_loc(pd.Timestamp('2021-01-01')))
    relative=logit(r13)-logit(r13[pivot])
    baseline=relative+strength*(differential-differential[pivot])
    latest=recent.set_index(pd.to_datetime(recent.period)).sort_index()
    rec_rate=latest.informality_rate_latent
    if not rec_rate.index.equals(NEW_MONTHS):
        raise ValueError('Recent GEIH national latent window calendar changed')
    pivot_rate=float(rec_rate.iloc[0]);logitr=logit(pivot_rate)
    rate=expit(logitr+baseline)
    rate[pivot:]=rec_rate.to_numpy(float)
    # Provenance of approximate, definition-transferred pre-2021 estimate.
    uncertainty=np.where(MONTHS.year<=2000,'VERY_HIGH',
                         np.where(MONTHS.year<=2006,'HIGH',
                                  np.where(MONTHS.year<=2020,'HIGH_DEFINITION_BRIDGE','MODELLED_CURRENT_DEFINITION')))
    national_out=[]
    for kind, block in national.groupby('national_type'):
        block=block.set_index(pd.to_datetime(block.period)).reindex(MONTHS)
        employed=block.employed.to_numpy(float)
        ind=employed*rate
        national_out.append(pd.DataFrame({
            'period':MONTHS.strftime('%Y-%m'),'dep_code':'00','national_type':kind,
            'employed_frozen':employed,'informal_estimated':ind,
            'formal_estimated':employed-ind,'informality_rate_estimated':rate,
            'provenance':np.where(MONTHS.year<=2000,'URBAN_13_RETROPOLATION_NO_OFFICIAL_ANCHOR',
                np.where(MONTHS.year<=2006,'DANE_T5_13_AREAS_AGGREGATE_WITH_REST_TRANSFER',
                    np.where(MONTHS.year<=2020,'DANE_URBAN_T5_PLUS_NONPENSION_PROXY_DEFINITION_BRIDGE',
                             'DANE_GEIH_NEW_ROLLING3_LATENT'))),
            'uncertainty_class':uncertainty,
            'is_official_monthly':False,'publication_status':'EXPERIMENTAL_NOT_CANONICAL',
            'universe_transfer_assumed':kind=='ICML_COMPLETO',
            'national_model_proxy_weight':strength}))
    model=pd.concat(national_out,ignore_index=True).sort_values(['period','national_type'])
    sensitivity=[]
    for alpha in (0.0,.25,.5,.75,1.0):
        rates=expit(logitr+relative+alpha*(differential-differential[pivot]))
        delta=np.abs(rates[:pivot]-rate[:pivot])
        sensitivity.append({'proxy_weight':alpha,'mean_abs_change_pp':100*float(delta.mean()),
                            'max_abs_change_pp':100*float(delta.max()),
                            'last_2020_rate':float(rates[pivot-1])})
    group=pd.DataFrame({'period':MONTHS.strftime('%Y-%m'),
        'dane_13_area_backcast_rate':r13,
        'old_dane_t5_auxiliary':old13,
        'icml_13_area_weighted_rate':g.to_numpy(float),
        'dane_vs_icml_group_gap_pp':100*(r13-g.to_numpy(float)),
        'provenance':np.where(MONTHS.year<=2000,'RETROPOLATED_13_URBAN_ICML_SHAPE',
            np.where(MONTHS.year<=2006,'DANE_T5_13_AREAS_ANCHORS_PLUS_DEFINITION_TRANSFER',
                np.where(MONTHS.year<=2020,'DANE_T5_13_AREAS_ROLLING3_PLUS_DEFINITION_TRANSFER',
                         'DANE_NEW_13_AREAS_ROLLING3'))),
        'is_official_monthly':False})
    return model,pd.DataFrame(sensitivity),group


def run(source_path:Path,city_path:Path,national_path:Path,recent_path:Path,
        anchors13_path:Path,city_anchor_path:Path,output:Path) -> dict:
    """Create detached experimental artifacts, preserving labor input byte hashes."""
    inputs={str(p.name):_hash(p) for p in (source_path,city_path,national_path,recent_path,
                                          anchors13_path,city_anchor_path)}
    source=pd.read_csv(source_path)
    city=pd.read_csv(city_path)
    national=pd.read_csv(national_path)
    recent=pd.read_csv(recent_path)
    anchors13=pd.read_csv(anchors13_path)
    city_anchors=pd.read_csv(city_anchor_path)
    _check_labor(city,national)
    if not (set(anchors13.definition)=={'hasta_5_trabajadores','hasta_10_trabajadores'}):
        raise ValueError('Historical definition catalog has changed')
    if set(city_anchors.city_code.unique())!=set(FIRST_13):
        raise ValueError('13 city anchor geography changed')
    if not set(source.definition.unique()) == {OLD_CITY, OLD_NAT, NEW}:
        raise ValueError('DANE source definitions changed')
    labor=_urban_table(city)
    t5, old_audit=_city_windows(source,OLD_CITY,OLD_MONTHS,lam=.025)
    latest, new_audit=_city_windows(source,NEW,NEW_MONTHS,lam=.012)
    if set(t5)!=set(latest) or len(t5)!=23:
        raise ValueError('Expected 23 city observations in both DANE regimes')
    old_values={}; estimates={}; donor_log=[]
    iold=MONTHS.get_indexer(OLD_MONTHS); inew=MONTHS.get_indexer(NEW_MONTHS)
    for code in sorted(labor):
        if code in t5:
            series=np.full(len(MONTHS),np.nan)
            series[iold]=t5[code]
            series[:iold[0]]=_pre2007_trajectory(t5[code],code,labor)
            old_values[code]=series
        else:
            donor,distance=_nearest_donor(code,sorted(t5),labor)
            base=old_values.get(donor)
            if base is None:
                base=np.full(len(MONTHS),np.nan);base[iold]=t5[donor]
                base[:iold[0]]=_pre2007_trajectory(t5[donor],donor,labor)
            # Modest unemployment differential is a *model assumption*, not an anchor.
            ut=(labor[code].unemployed/labor[code].labor_force).to_numpy(float)
            ud=(labor[donor].unemployed/labor[donor].labor_force).to_numpy(float)
            offset=np.clip(.35*(ut-ud),-.20,.20)
            old_values[code]=expit(logit(np.clip(base,.005,.995))+offset)
            donor_log.append({'city_code':code,'city_name':labor[code].city_name.iloc[0],
                              'donor_city_code':donor,'distance':distance,
                              'reason':'NO_OFFICIAL_INFORMALITY_CITY_WINDOW','method':'donor_plus_unemployment_gap'})
    # Independently anchor old T5 rate of the 13 main areas, 2001-2006.
    # Keep the unanchored candidate for proper out-of-year validation.
    unanchored_13={c:old_values[c].copy() for c in FIRST_13}
    old_values,aggregate_audit=_apply_13_anchors(old_values,labor,anchors13)
    validation=[]
    official_13=anchors13[(anchors13.definition=='hasta_5_trabajadores')&anchors13.year.between(2001,2006)]
    for held in official_13.itertuples(index=False):
        x={c:unanchored_13[c].copy() for c in FIRST_13}
        train=anchors13[~((anchors13.definition=='hasta_5_trabajadores')&(anchors13.year==held.year))]
        updated,_=_apply_13_anchors(x,labor,train)
        vals=_rate_13(updated,labor)
        pos=MONTHS.get_indexer(pd.date_range(held.period_start,held.period_end,freq='MS'))
        pred=float(np.mean(vals[pos]))
        validation.append({'heldout_year':int(held.year),'target_T5_rate':held.rate_pct/100,
                           'predicted_T5_rate':pred,'holdout_error_pp':100*(pred-held.rate_pct/100),
                           'source':'DANE_T5_13_AREAS_APR_JUN','independent_holdout':True})
    anchor_cv=pd.DataFrame(validation)
    dates=MONTHS
    start2021=int(dates.get_loc(pd.Timestamp('2021-01-01')))
    for code in sorted(labor):
        old=old_values[code]
        if code in latest:
            new=latest[code]
            compare=old[inew[:3]]
            offset=float(np.mean(logit(np.clip(new[:3],.005,.995))-
                                 logit(np.clip(compare,.005,.995))))
            stitched=expit(logit(np.clip(old,.005,.995))+offset)
            stitched[inew]=new
            direct=True
        else:
            donor=next(z['donor_city_code'] for z in donor_log if z['city_code']==code)
            # Borrow same-definition *new* donor series, not the old T5 measure.
            offset=float(np.mean(logit(np.clip(latest[donor][:3],.005,.995))-
                                 logit(np.clip(old_values[donor][inew[:3]],.005,.995))))
            stitched=expit(logit(np.clip(old,.005,.995))+offset)
            donor_new=latest[donor]
            ut=(labor[code].unemployed/labor[code].labor_force).to_numpy(float)
            ud=(labor[donor].unemployed/labor[donor].labor_force).to_numpy(float)
            stitched[inew]=expit(logit(np.clip(donor_new,.005,.995))+
                                  np.clip(.35*(ut[inew]-ud[inew]),-.2,.2))
            direct=False
        estimates[code]=(stitched,old,direct)
    rec=[]
    for code in sorted(labor):
        frozen=labor[code].employed.to_numpy(float)
        r,old,direct=estimates[code]
        source_status=np.where(dates.year<=2000,'RETROPOLACION_1993_2000',
                          np.where(dates.year<=2006,
                              'DANE_13_T5_AGGREGATE_BACKCAST' if code in FIRST_13 else 'DONOR_BACKCAST',
                          np.where(dates.year<=2020,
                              'DANE_CITY_OLD_T5_WINDOWS' if code in t5 else 'DONOR_INFERRED',
                              'DANE_CITY_NEW_GEIH_WINDOWS' if direct else 'DONOR_INFERRED')))
        if code==25:
            source_status[:]='SYNTHETIC_CUNDINAMARCA_DONOR'
        rec.append(pd.DataFrame({'period':dates.strftime('%Y-%m'),'city_code':code,
            'city_name':labor[code].city_name.iloc[0],
            'employed_frozen':frozen,'informal_estimated':frozen*r,
            'formal_estimated':frozen*(1-r),'informality_rate':r,
            'old_t5_rate_auxiliary':old,'provenance':source_status,
            'source_definition':np.where(dates.year>=2021,NEW,'HISTORICAL_T5_TO_NEW_DEF_ESTIMATED_BRIDGE'),
            'is_official_monthly':False,'publication_status':'EXPERIMENTAL_NOT_CANONICAL',
            'has_city_DANE_windows':bool(direct),'synthetic_urban_unit':code==25,
            'uncertainty_class':np.where(dates.year<=2000,'VERY_HIGH',
                np.where(dates.year<=2006,'HIGH',np.where(dates.year<=2020,
                    'HIGH_DEFINITION_BRIDGE','LATENT_OR_DONOR')))}))
    urban=pd.concat(rec,ignore_index=True).sort_values(['period','city_code'])
    national_new, national_sens,group13 = _national_historical(urban,national,source,recent,anchors13)
    # DANE 13-area T5 historical benchmarks (2001-2009) must be checked
    # against the old-definition auxiliary, NOT the new-definition backcast.
    retrospective=[]
    for r in anchors13[anchors13.definition.eq('hasta_5_trabajadores')].itertuples(index=False):
        dates=pd.date_range(r.period_start,r.period_end,freq='MS')
        pred=group13[group13.period.isin(dates.strftime('%Y-%m'))]
        pred_rate=float(pred.old_dane_t5_auxiliary.mean())
        retrospective.append({'year':int(r.year),'definition':'hasta_5_trabajadores',
            'dane_rate':r.rate_pct/100,'modelled_old_t5_rate':pred_rate,
            'difference_pp':100*(pred_rate-r.rate_pct/100),
            'calibrated_directly':int(r.year)<=2006,
            'transfer_to_new_definition_applied_to_this_comparison':False,
            'source_url':r.source_url})
    historical_comparison=pd.DataFrame(retrospective)
    # Legacy 2005-06 CITY T10 is a secondary validation of different estimand;
    # NEVER claim it calibrates a T5 or post-2021 rate at the city level.
    t10=[]
    for r in city_anchors.itertuples(index=False):
        code=int(r.city_code)
        mid=pd.date_range(r.period_start,r.period_end,freq='MS')
        selection=urban[(urban.city_code==code)&(urban.period.isin(mid.strftime('%Y-%m')))]
        t10.append({'city_code':code,'year':int(r.year),'old_definition':'hasta_10_trabajadores',
                    't10_informal_persons_published':float(r.informal_thousands)*1000,
                    't10_rate_published':float(r.informality_rate_pct)/100 if pd.notna(r.informality_rate_pct) else np.nan,
                    't5_model_rate_same_months':float(selection.old_t5_rate_auxiliary.mean()),
                    'city_level_t5_equivalence_assumed':False,'source_url':r.source_url})
    t10=pd.DataFrame(t10)
    donor=pd.DataFrame(donor_log)
    # Explicit fidelity-vs-regularity comparison for the underidentified
    # 2021+ moving-window inversion; both variants stay experimental.
    tradeoff=[]
    recent_src=source[(source.definition==NEW)&source.domain.eq('city')].copy()
    recent_src['city_code']=recent_src.concept.map(lambda x:ALIAS.get(_normal(x)))
    for code, sub in recent_src[recent_src.city_code.notna()].groupby('city_code'):
        soft, soft_audit=_solve_rolling_rates(sub,NEW_MONTHS,lam=.012)
        exact=estimates[int(code)][0][inew]
        tradeoff.append({'city_code':int(code),
            'exact_max_monthly_rate_jump_pp':100*float(np.max(np.abs(np.diff(exact)))),
            'regularized_max_monthly_rate_jump_pp':100*float(np.max(np.abs(np.diff(soft)))),
            'regularized_window_mean_abs_error_pp':float(soft_audit.residual_pp.abs().mean()),
            'regularized_window_max_abs_error_pp':float(soft_audit.residual_pp.abs().max()),
            'exact_rolling_official_counts_reproduced':True,
            'selection':'EXACT_ONLY_AS_EXPERIMENTAL_CANDIDATE'})
    fidelity_tradeoff=pd.DataFrame(tradeoff)
    # Diagnostic flags are not silently smoothed: real structural breaks may
    # occur and require expert review rather than automatic replacement.
    extreme=[]
    for level, table, key, rate in (
        ('city',urban,'city_code','informality_rate'),
        ('national',national_new,'national_type','informality_rate_estimated')):
        for ident, group in table.groupby(key):
            d=group.sort_values('period').copy()
            mom=100*d[rate].diff()
            yoy=100*d[rate].diff(12)
            growth=d.informal_estimated.div(d.informal_estimated.shift(1))
            mask=mom.abs().gt(5)|yoy.abs().gt(15)|growth.gt(3)
            for pos in np.flatnonzero(mask.fillna(False).to_numpy()):
                extreme.append({'level':level,'unit':str(ident),'period':d.period.iloc[pos],
                    'change_monthly_pp':mom.iloc[pos],
                    'change_yoy_pp':yoy.iloc[pos],
                    'informal_growth_ratio':growth.iloc[pos],
                    'pandemic_year':str(d.period.iloc[pos])[:4] in ('2020','2021'),
                    'audit_class':'REVIEW_NOT_AUTOMATIC_CORRECTION'})
    discontinuities=pd.DataFrame(extreme,columns=['level','unit','period','change_monthly_pp',
        'change_yoy_pp','informal_growth_ratio','pandemic_year','audit_class'])
    # Formal accounting and frozen labor check: all 33 urban, both nationals.
    assert len(urban)==ROWS_33 and len(national_new)==ROWS_NATIONAL
    assert not urban[['informal_estimated','formal_estimated','informality_rate']].isna().any().any()
    assert not national_new[['informal_estimated','formal_estimated','informality_rate_estimated']].isna().any().any()
    for f in (urban,national_new):
        assert (f.informal_estimated >= 0).all() and (f.formal_estimated>=0).all()
        assert ((f.informal_estimated+f.formal_estimated)-f.employed_frozen).abs().max()<.001
    assert all(_hash(p)==inputs[p.name] for p in (source_path,city_path,national_path,recent_path,
                                                    anchors13_path,city_anchor_path))
    output.mkdir(parents=True,exist_ok=True)
    artifacts={'ciudades_informalidad_candidata.csv':urban,
               'nacionales_informalidad_candidata.csv':national_new,
               'auditoria_ventanas_t5_2007_2021.csv':old_audit,
               'auditoria_ventanas_nueva_2021_2026.csv':new_audit,
               'auditoria_anclas_13_areas_t5.csv':aggregate_audit,
               'auditoria_anclas_ciudad_t10_no_equivalentes.csv':t10,
               'catalogo_donantes.csv':donor,
               'validacion_13_areas_ano_oculto.csv':anchor_cv,
               'sensibilidad_puente_nacional.csv':national_sens,
               'comparacion_dane_t5_13_areas_2001_2009.csv':historical_comparison,
               'senal_dane_13_areas.csv':group13,
               'auditoria_saltos_informalidad.csv':discontinuities,
               'auditoria_tradeoff_fidelidad_suavidad.csv':fidelity_tradeoff}
    for name,table in artifacts.items():
        table.to_csv(output/name,index=False,encoding='utf-8-sig',lineterminator='\n')
    report={'status':'EXPERIMENTAL_NOT_CANONICAL',
        'method':'DANE_URBAN_FIRST_BACKCAST_HISTORICAL_DEFINITION_BRIDGE',
        'urban_rows':int(len(urban)),'urban_territories':int(urban.city_code.nunique()),
        'national_rows':int(len(national_new)),
        'n_old_city_windows_valid':int(len(old_audit)),
        'n_new_city_windows':int(len(new_audit)),
        'old_city_max_abs_window_residual_pp':float(old_audit.residual_pp.abs().max()),
        'old_city_mean_abs_window_residual_pp':float(old_audit.residual_pp.abs().mean()),
        'new_city_max_abs_window_residual_pp':float(new_audit.residual_pp.abs().max()),
        'new_city_mean_abs_window_residual_pp':float(new_audit.residual_pp.abs().mean()),
        'aggregate_2001_2006_max_abs_residual_pp':float(aggregate_audit.residual_pp.abs().max()),
        'aggregate_leave_year_out_mae_pp':float(anchor_cv.holdout_error_pp.abs().mean()),
        'aggregate_leave_year_out_max_pp':float(anchor_cv.holdout_error_pp.abs().max()),
        'n_change_flags':int(len(discontinuities)),
        'max_recent_exact_city_mom_pp':float(fidelity_tradeoff.exact_max_monthly_rate_jump_pp.max()),
        'max_recent_regularized_city_mom_pp':float(fidelity_tradeoff.regularized_max_monthly_rate_jump_pp.max()),
        'source_sha256':inputs,
        'outputs_sha256':{k:_hash(output/k) for k in artifacts},
        'warning':'Pre-2021 values are transferred across non-equivalent definitions and do not represent observed current-definition rates. No ILOSTAT used.'}
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
