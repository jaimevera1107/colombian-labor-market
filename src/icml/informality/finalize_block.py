"""ICML Hito 9: one-MLP, CNPV-anchored, dual-domain informality series.

Closure means a COMPLETE, internally coherent *reconstructed* candidate; it does
NOT imply the unobserved departmental rates or pre-2021 definitions are validated.

Input labor/census/vintage files are immutable. The full territory is the only
calibrated national margin. GEIH is derived via occupied-domain coefficients
rather than an independent fitted model or an artificial second target.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from icml.informality.regime_splice import RegimeSplice, splice_regime
from icml.domain.cutoff import (
    N_MONTHS,
    ROWS_33,
    ROWS_NATIONAL,
    month_labels,
)

from .national_closure import calibrate_month

MONTHS = month_labels()
NINE = (81, 85, 86, 88, 91, 94, 95, 97, 99)
SIX = ('population','working_age','labor_force','employed','unemployed','inactive')


def _read(path):
    return pd.read_csv(path)


def _keys(df, keys, expected, name):
    if df.duplicated(keys).any():
        raise ValueError(f'{name}: duplicate keys {keys}')
    if len(df) != expected:
        raise ValueError(f'{name}: expected {expected} rows, got {len(df)}')
    if sorted(df.period.unique()) != MONTHS:
        raise ValueError(f'{name}: incomplete month coverage')


def _one_model_prior(priors:pd.DataFrame, retrospective:pd.DataFrame, mode:str) -> pd.DataFrame:
    x=priors[['period','dep_code','prior_census','year']].copy()
    x=x.rename(columns={'prior_census':'prior_rate'})
    x['prior_provenance']=np.where(x.year>=2021,'MLP_RECENT_GEIH_LATENT',
                          'MLP_HISTORICAL_T5_LATENT')
    if 'extension_status' in priors.columns:
        # Months past the frozen cutoff carry a forwarded prior (see
        # icml.recalculation.extension); the product says so.
        extended=priors['extension_status'].fillna('').astype(str).ne('').to_numpy()
        x.loc[extended,'prior_provenance']=priors.loc[extended,'extension_status'].to_numpy()
    mask=x.year.eq(2020)
    x.loc[mask,'prior_rate']=np.nan
    repl=retrospective[(retrospective.candidate=='mlp_residual_92') &
                       (retrospective['mode']==mode)][['period','dep_code','rate_prior']]
    if len(repl)!=396:
        raise ValueError(f'Incomplete 2020 retrospective mode {mode}')
    x=x.merge(repl,on=['period','dep_code'],how='left',validate='one_to_one')
    x.loc[mask,'prior_rate']=x.loc[mask,'rate_prior']
    x.loc[mask,'prior_provenance']='2020_RETROSPECTIVE_'+mode.upper()
    x=x.drop(columns=['rate_prior','year'])
    _keys(x,['period','dep_code'],N_MONTHS*33,'single-model priors')
    if not np.isfinite(x.prior_rate).all() or not x.prior_rate.between(0,1).all():
        raise ValueError('Invalid/missing one-model rates')
    return x


#: Levels of the census bridge that follow the current labor product.
_BRIDGE_LEVELS = ('population', 'working_age', 'labor_force', 'employed', 'unemployed', 'inactive')

#: Differences below this many persons are float noise, not a different vintage.
_BRIDGE_REFRESH_TOLERANCE = 1e-3

#: A residual between the departments and the national employed larger than
#: this share of the national figure means mismatched inputs, not a method gap.
_EMPLOYED_TOTAL_GUARD = 1e-2


def _align_partial_factors_with_labor(bridge: pd.DataFrame, labor: pd.DataFrame) -> pd.DataFrame:
    """Give the nine partial territories the GEIH factors of the labor product.

    The labor product carries one smooth GEIH factor per partial territory
    (shared by all labor components) and a smooth demographic factor for
    population. Using the same factors here makes the GEIH employed of the
    informality product identical to the GEIH employed of the labor product
    in every month, so both products describe one and the same universe.
    """
    out = bridge.copy()
    lab = labor[['period', 'dep_code', 'factor_employed', 'factor_population']].copy()
    lab['_k'] = lab['dep_code'].astype(int)
    out['_k'] = out['dep_code'].astype(int)
    merged = out[['period', '_k']].merge(lab.drop(columns='dep_code'), on=['period', '_k'],
                                         how='left', validate='one_to_one')
    rows = out['_k'].isin(NINE).to_numpy()
    f_lab = merged['factor_employed'].to_numpy(float)
    f_pop = merged['factor_population'].to_numpy(float)
    if not (np.isfinite(f_lab[rows]).all() and np.isfinite(f_pop[rows]).all()):
        raise ValueError('Labor factors missing for the partial territories')
    for name in ('employed', 'unemployed', 'inactive'):
        out.loc[rows, f'factor_geih_{name}'] = f_lab[rows]
        out.loc[rows, f'geih_{name}'] = out.loc[rows, name].to_numpy(float) * f_lab[rows]
    out.loc[rows, 'geih_labor_force'] = (out.loc[rows, 'geih_employed'].to_numpy(float)
                                         + out.loc[rows, 'geih_unemployed'].to_numpy(float))
    out.loc[rows, 'geih_working_age'] = (out.loc[rows, 'geih_labor_force'].to_numpy(float)
                                         + out.loc[rows, 'geih_inactive'].to_numpy(float))
    out.loc[rows, 'factor_geih_labor_force'] = f_lab[rows]
    out.loc[rows, 'factor_geih_working_age'] = f_lab[rows]
    out.loc[rows, 'factor_geih_population'] = f_pop[rows]
    out.loc[rows, 'geih_population'] = out.loc[rows, 'population'].to_numpy(float) * f_pop[rows]
    if 'geih_domain_status' in out.columns:
        zero = rows & out['geih_domain_status'].eq('FUERA_GEIH_2001_2013_FACTOR_CERO').to_numpy()
        out.loc[zero, 'geih_domain_status'] = 'CAPITAL_2001_2013_FACTOR_LABORAL_SUAVIZADO'
    return out.drop(columns='_k')


def _refresh_bridge_levels(bridge: pd.DataFrame, labor: pd.DataFrame,
                           tolerance: float = _BRIDGE_REFRESH_TOLERANCE
                           ) -> tuple[pd.DataFrame, dict]:
    """Bring the bridge's full levels in line with the current labor product.

    The census bridge is a frozen *parameter* (its GEIH/full factors), but it
    also carries the department levels of the vintage it was built with.
    When the labor product is recomputed for another cutoff, the months from
    2021 are re-identified and those levels no longer match it. Rows whose
    full levels differ from the labor product by more than ``tolerance``
    persons take the labor levels; the GEIH levels follow through the frozen
    factors of the components, and their aggregates are rebuilt as sums so the
    GEIH identities hold. Rows that already
    match are untouched, so for the frozen vintage this is a no-op.
    """
    def key(frame: pd.DataFrame) -> pd.Series:
        return frame['dep_code'].astype(str).str.zfill(2)
    current = labor[['period', 'dep_code', *_BRIDGE_LEVELS]].copy()
    current['_k'] = key(current)
    current = current.drop(columns='dep_code')
    base = bridge[['period', 'dep_code', *_BRIDGE_LEVELS]].copy()
    base['_k'] = key(base)
    merged = base.merge(current, on=['period', '_k'], how='left', suffixes=('', '_current'),
                        validate='one_to_one')
    if merged[f'{_BRIDGE_LEVELS[0]}_current'].isna().any():
        raise ValueError('The labor product does not cover every month of the census bridge')
    gap = np.zeros(len(merged))
    for level in _BRIDGE_LEVELS:
        gap = np.maximum(gap, (merged[level] - merged[f'{level}_current']).abs().to_numpy(float))
    stale = gap > tolerance
    refreshed = bridge.copy()
    for level in _BRIDGE_LEVELS:
        refreshed.loc[stale, level] = merged.loc[stale, f'{level}_current'].to_numpy(float)
    def column(name: str) -> np.ndarray:
        return refreshed.loc[stale, name].to_numpy(float)
    # The GEIH universe is rebuilt hierarchically, like the labor product:
    # the frozen factors give the components, the aggregates are their sums.
    # Applying one factor per level would break labor_force = employed +
    # unemployed, because each factor encodes the composition of the levels
    # the bridge was built with.
    geih_employed = column('factor_geih_employed') * column('employed')
    geih_unemployed = column('factor_geih_unemployed') * column('unemployed')
    geih_inactive = column('factor_geih_inactive') * column('inactive')
    geih_labor_force = geih_employed + geih_unemployed
    geih_working_age = geih_labor_force + geih_inactive
    geih_population = column('factor_geih_population') * column('population')
    for name, values in (('geih_employed', geih_employed), ('geih_unemployed', geih_unemployed),
                         ('geih_inactive', geih_inactive), ('geih_labor_force', geih_labor_force),
                         ('geih_working_age', geih_working_age), ('geih_population', geih_population)):
        refreshed.loc[stale, name] = values
    for level in ('labor_force', 'working_age'):
        full = column(level)
        refreshed.loc[stale, f'factor_geih_{level}'] = np.divide(
            column(f'geih_{level}'), full, out=np.ones_like(full), where=full > 0)
    months = sorted(bridge.loc[stale, 'period'].unique())
    return refreshed, {
        'rows_refreshed': int(stale.sum()),
        'months_refreshed': len(months),
        'first_month': months[0] if months else None,
        'last_month': months[-1] if months else None,
        'max_level_change_people': float(gap.max()),
        'tolerance_people': tolerance,
    }


def _calibrate_full(priors:pd.DataFrame, bridge:pd.DataFrame, national:pd.DataFrame
                   ) -> tuple[pd.DataFrame,pd.DataFrame]:
    fields=['period','dep_code','geographic_employed','geih_domain_status']
    fields += list(SIX) + [f'geih_{x}' for x in SIX] + [f'factor_geih_{x}' for x in SIX]
    p=bridge[fields].merge(priors,on=['period','dep_code'],validate='one_to_one')
    rates=national[national.national_type.eq('ICML_COMPLETO')][
        ['period','employed_frozen','informality_rate_estimated','provenance',
         'uncertainty_class']].rename(columns={'employed_frozen':'national_employed',
         'informality_rate_estimated':'national_target_rate'})
    if len(rates)!=bridge.period.nunique():
        raise ValueError('Missing reconstructed ICML national target')
    p=p.merge(rates,on='period',validate='many_to_one')
    outputs=[]; audits=[]
    for period,g in p.groupby('period',sort=True):
        g=g.sort_values('dep_code').copy()
        if len(g)!=33:
            raise ValueError(f'Incomplete departments in {period}')
        e=g.employed.to_numpy(float)
        e_geih=g.geih_employed.to_numpy(float)
        factor=e_geih/e
        target=float(g.national_target_rate.iloc[0])
        national_employed=float(g.national_employed.iloc[0])
        employed_residual=national_employed-float(e.sum())
        if abs(employed_residual)>_EMPLOYED_TOTAL_GUARD*national_employed:
            raise ValueError(f'Incompatible occupied total {period}: residual {employed_residual:.1f}')
        if (e<=0).any() or (e_geih<-1e-5).any() or (e_geih>e+1e-5).any():
            raise ValueError(f'Invalid GEIH subset {period}')
        if not np.isfinite(g.prior_rate).all():
            raise ValueError(f'Nonfinite rate {period}')
        c=calibrate_month(g.prior_rate.to_numpy(float),e,factor,target*e.sum(),None)
        calibrated=np.asarray(c['calibrated_rate'],float)
        g['informality_rate']=calibrated
        g['informal_full']=e*calibrated
        g['formal_full']=e-g['informal_full'].to_numpy(float)
        g['informal_geih']=e_geih*calibrated
        g['formal_geih']=e_geih-g['informal_geih'].to_numpy(float)
        for variable in SIX:
            g[f'outside_geih_{variable}']=g[variable]-g[f'geih_{variable}']
        g['outside_geih_employed']=e-e_geih
        g['outside_geih_informal']=g.informal_full-g.informal_geih
        g['outside_geih_formal']=g.formal_full-g.formal_geih
        g['geih_rate_derived']=np.where(e_geih>0,g.informal_geih/np.where(e_geih>0,e_geih,1),np.nan)
        g['informality_complement_rate_assumed_equal']=True
        g['is_official_monthly_rate']=False
        g['estimation_status']=np.select([
            g.period.lt('2001-01'),g.period.lt('2007-01'),g.period.lt('2020-01'),
            g.period.lt('2021-01'),g.period.lt('2023-01')],
            ['VERY_HIGH_UNCERTAINTY_PRE2001','HIGH_UNCERTAINTY_2001_2006',
             'RECONSTRUCTED_HISTORICAL_2007_2019','2020_BRIDGE_NOT_OBSERVED',
             'NEW_DEFINITION_TRANSITION'],default='RECENT_RECONSTRUCTED_MONTHLY')
        g['universe_modelled']='ICML_FULL_CNPV_2018'
        outputs.append(g)
        audits.append({'period':period,
            'national_full_rate_target':target,
            'national_full_rate_fitted':float(g.informal_full.sum()/e.sum()),
            'national_geih_rate_derived':float(g.informal_geih.sum()/e_geih.sum()),
            'difference_geih_vs_full_target_pp':float(100*(g.informal_geih.sum()/e_geih.sum()-target)),
            'residual_full_people':float(g.informal_full.sum()-target*e.sum()),
            'identity_max_people':float(np.max(np.abs(g.informal_full+g.formal_full-e))),
            'geih_identity_max_people':float(np.max(np.abs(g.informal_geih+g.formal_geih-e_geih))),
            'mean_calibration_pp':float(100*np.average(np.abs(calibrated-g.prior_rate),weights=e)),
            'max_calibration_pp':float(100*np.max(np.abs(calibrated-g.prior_rate))),
            'source':'SINGLE_MLP_PLUS_SINGLE_FULL_KL',
            'geih_second_margin_imposed':False,
            # Recorded only when the departments do not add exactly to the
            # national employed (methodology breaks, re-identified months): it is
            # absorbed through the national rate, never a reason to stop.
            **({'employed_total_residual_people':employed_residual}
               if abs(employed_residual)>0.001 else {})})
    return pd.concat(outputs,ignore_index=True),pd.DataFrame(audits)


def _cities(city:pd.DataFrame, city_labor:pd.DataFrame, bridge:pd.DataFrame) -> pd.DataFrame:
    city=_read(city) if isinstance(city,(Path,str)) else city.copy()
    _keys(city,['period','city_code'],ROWS_33,'urban informality')
    labor=city_labor[['period','city_code','population','employed','source_status',
        'is_additive_member']].rename(columns={'population':'population_signal',
                                            'employed':'employed_signal_labour'})
    x=city.merge(labor,on=['period','city_code'],validate='one_to_one')
    if np.max(np.abs(x.employed_frozen-x.employed_signal_labour))>0.001:
        raise ValueError('Informality city employed changed relative to frozen labor')
    nine=bridge[bridge.dep_code.isin(NINE)][['period','dep_code','geographic_population',
         'geographic_employed']].rename(columns={'dep_code':'city_code'})
    x=x.merge(nine,on=['period','city_code'],how='left',validate='one_to_one')
    flag=x.city_code.isin(NINE)
    if x.loc[flag,'geographic_employed'].isna().any():
        raise ValueError('CNPV adjusted urban geographic occupation absent')
    x['population_cnpv_geographic_signal']=np.where(flag,x.geographic_population,x.population_signal)
    x['employed_cnpv_geographic_signal']=np.where(flag,x.geographic_employed,x.employed_frozen)
    x['informal_cnpv_geographic_signal']=x.employed_cnpv_geographic_signal*x.informality_rate
    x['formal_cnpv_geographic_signal']=x.employed_cnpv_geographic_signal-x.informal_cnpv_geographic_signal
    x['non_additive_urban_signal']=True
    x['is_official_monthly_rate']=False
    x['is_census_adjusted_capital']=flag
    x['publication_status']='RECONSTRUCTED_RESEARCH_CANDIDATE'
    x=x.drop(columns=['geographic_population','geographic_employed'])
    return x.sort_values(['period','city_code']).reset_index(drop=True)


def _nationals(dept:pd.DataFrame, monthly:pd.DataFrame, old_national:pd.DataFrame,
               bridge:pd.DataFrame) -> pd.DataFrame:
    base=old_national[old_national.national_type=='ICML_COMPLETO'][
      ['period','provenance','uncertainty_class','informality_rate_estimated']]
    rows=[]
    for name,prefix,inf,for_ in (
      ('ICML_COMPLETO','','informal_full','formal_full'),
      ('GEIH_REPRESENTADO_CNPV2018','geih_','informal_geih','formal_geih')):
        required={f'{prefix}{v}':'sum' for v in SIX}
        required[inf]='sum';required[for_]='sum'
        g=dept.groupby('period',as_index=False).agg(required)
        g=g.rename(columns={f'{prefix}{v}':v for v in SIX}|{inf:'informal',for_:'formal'})
        g['informality_rate']=g.informal/g.employed
        g['national_type']=name
        g['official_geih_national_observation']=False
        g['is_additive_member']=False
        g['reference_quality']=np.select([g.period.lt('2001-01'),g.period.lt('2020-01'),
                               g.period.lt('2021-01')],
                              ['PRE2001_RECONSTRUCTED_GEOGRAPHIC_PROXY',
                               'HISTORICAL_RECONSTRUCTED','2020_BRIDGE_NOT_OBSERVED'],
                               default='RECENT_MONTHLY_LATENT_FROM_DANE_WINDOWS')
        rows.append(g)
    out=pd.concat(rows,ignore_index=True).merge(base,on='period',validate='many_to_one')
    out['difference_to_reconstructed_national_rate_pp']=(
        out.informality_rate-out.informality_rate_estimated)*100
    out['publication_status']='RECONSTRUCTED_RESEARCH_CANDIDATE'
    return out.sort_values(['period','national_type']).reset_index(drop=True)


def _quality(city,dep,national,bridge,monthly,anchors):
    issues=[]
    def check(name,ok,metric,kind='REQUIRED'):
        issues.append({'control':name,'passed':bool(ok),'criticality':kind,
                       'metric':str(metric), 'status':'PASS' if ok else 'FAIL'})
    check('complete_33_urban_x_404',len(city)==ROWS_33 and city.city_code.nunique()==33,len(city))
    check('complete_33_department_x_404',len(dep)==ROWS_33 and dep.dep_code.nunique()==33,len(dep))
    check('complete_two_national_x_404',len(national)==ROWS_NATIONAL,len(national))
    check('no_missing_rates', bool(city.informality_rate.notna().all() and
          dep.informality_rate.notna().all() and national.informality_rate.notna().all()),
          int(city.informality_rate.isna().sum()+dep.informality_rate.isna().sum()+national.informality_rate.isna().sum()))
    c_err=float((city.informal_estimated+city.formal_estimated-city.employed_frozen).abs().max())
    d_err=float((dep.informal_full+dep.formal_full-dep.employed).abs().max())
    geih_err=float((dep.informal_geih+dep.formal_geih-dep.geih_employed).abs().max())
    check('urban_people_identity',c_err<.001,c_err)
    check('department_people_identity',d_err<.001,d_err)
    check('geih_people_identity',geih_err<.001,geih_err)
    check('full_national_kl_closure',float(monthly.residual_full_people.abs().max())<.001,
          float(monthly.residual_full_people.abs().max()))
    check('subset_coverage', bool((dep.geih_employed>=-1e-5).all() and
          (dep.geih_employed<=dep.employed+1e-5).all()),'0<=geih<=full')
    check('universe_decomposition',float((dep.informal_geih+dep.outside_geih_informal-
         dep.informal_full).abs().max())<.001,'GEIH+outside=full')
    cap=(city.loc[city.is_census_adjusted_capital & city.period.str.startswith('2018-')]
         .groupby('city_code').population_cnpv_geographic_signal.mean())
    target=anchors.set_index('dep_code').cnpv_cabecera_capital_2018
    cap_error=float((cap.reindex(target.index)-target).abs().max())
    check('2018_nine_capitals_anchored',len(cap)==9 and cap_error<.05,cap_error)
    for v in SIX:
        full_nat=national[national.national_type.eq('ICML_COMPLETO')].set_index('period')
        rep_nat=national[national.national_type.eq('GEIH_REPRESENTADO_CNPV2018')].set_index('period')
        residual=float((dep.groupby('period')[v].sum()-full_nat[v]).abs().max())
        check('national_full_'+v,residual<.001,residual)
        residual=float((dep.groupby('period')[f'geih_{v}'].sum()-rep_nat[v]).abs().max())
        check('national_geih_'+v,residual<.001,residual)
    for domain in ('','geih_'):
        residual=(dep[f'{domain}employed']+dep[f'{domain}unemployed']-dep[f'{domain}labor_force']).abs().max()
        check('PEA_identity_'+(domain or 'complete'),residual<.001,residual)
        residual=(dep[f'{domain}labor_force']+dep[f'{domain}inactive']-dep[f'{domain}working_age']).abs().max()
        check('PET_identity_'+(domain or 'complete'),residual<.001,residual)
    check('2020_retrospective_no_official_claim' ,bool((dep.loc[dep.period.str.startswith('2020-'),
          'prior_provenance'].str.startswith('2020_RETROSPECTIVE')).all()),'12_months')
    # Scientific publication gates are intentionally NOT conflated with successful
    # numerical closure. The user receives a completed candidate, not an official series.
    check('pre2021_definition_independently_identified',False,
          'historical T5 / new GEIH bridge is a reconstruction', 'EVIDENCE')
    check('2020_independent_monthly_informal_observations',False,
          '2020 inferred via tested pseudogap model', 'EVIDENCE')
    check('departmental_noncovered_informal_rate_independently_observed',False,
          'no observed informal labels in excluded rural complement', 'EVIDENCE')
    check('geih_national_rate_independent_from_icml',False,
          'GEIH rate is a projected count ratio, not independent observed margin', 'EVIDENCE')
    return pd.DataFrame(issues)


def run(root:Path, output:Path, *,gap_method='interpolated',splice:RegimeSplice|None=None)->dict:
    """Write 33 urban + 33 department + 2 national complete experimental products.

    Expects the original 2.2.12 full checkpoint root and its immutable inputs.
    Output directory must be empty; all outputs deterministic.

    ``splice`` (a ``RegimeSplice``) shifts the unobserved segment, before the
    first anchored month, to the anchored regime. ``None`` or disabled leaves
    every number exactly as the frozen method produces it.
    """
    root,output=Path(root),Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Output directory already populated')
    lab=root/'datos/2_procesamiento/productos_congelados/laboral'
    seq=root/'datos/2_procesamiento/parametros_congelados/informalidad_secuencia_h5_h6'
    census=root/'datos/2_procesamiento/parametros_congelados/puente_censal_cnpv2018'
    trans=root/'datos/2_procesamiento/parametros_congelados/priors_mlp_h9'
    stress=root/'datos/2_procesamiento/parametros_congelados/stress_puente_nacional'
    city_lab=_read(lab/'ciudades.csv')
    dept_lab=_read(lab/'departamentos.csv')
    b=_read(census/'02_puente_dos_universos_33_territorios.csv')
    anchors=_read(census/'01_ancla_cnpv_2018_nueve.csv')
    n=_read(seq/'02_nacionales.csv')
    c=_read(seq/'03_ciudades_33.csv')
    p=_read(trans/'12_single_mlp_33_department_priors.csv')
    r=_read(stress/'11_2020_gap_priors_EXPERIMENTAL.csv')
    _keys(dept_lab,['period','dep_code'],ROWS_33,'frozen departments')
    _keys(b,['period','dep_code'],ROWS_33,'census bridge')
    _keys(city_lab,['period','city_code'],ROWS_33,'frozen city signals')
    b,bridge_refresh=_refresh_bridge_levels(b,dept_lab)
    b=_align_partial_factors_with_labor(b,dept_lab)
    priors=_one_model_prior(p,r,gap_method)
    splice_report=None
    if splice is not None and splice.enabled:
        # Departments are calibrated once without the splice to measure their
        # own breaks; the priors are then corrected and calibrated again to the
        # spliced national target, so they stay continuous and keep adding up.
        unspliced,_=_calibrate_full(priors,b,n)
        n,c,priors,splice_report=splice_regime(national=n,cities=c,priors=priors,
                                               departments=unspliced,config=splice)
    d,monthly=_calibrate_full(priors,b,n)
    urban=_cities(c,city_lab,b)
    nat=_nationals(d,monthly,n,b)
    quality=_quality(urban,d,nat,b,monthly,anchors)
    # Twelve months of alternative 2020 estimates: uncertainty instead of
    # hiding the choice of an interpolator.
    alternatives=[]
    for scenario in ('interpolated','seasonal_2019','urban_shock'):
        alt=_one_model_prior(p,r,scenario)
        if scenario==gap_method:
            t=d[d.period.str.startswith('2020-')][['period','dep_code','informality_rate']].copy()
        else:
            subb=b[b.period.str.startswith('2020-')]
            subn=n[n.period.str.startswith('2020-')]
            tmp,_=_calibrate_full(alt[alt.period.str.startswith('2020-')],subb,subn)
            t=tmp[['period','dep_code','informality_rate']].copy()
        t['2020_scenario']=scenario
        alternatives.append(t)
    sensitivity=pd.concat(alternatives,ignore_index=True)
    span=sensitivity.groupby(['period','dep_code']).informality_rate.agg(['min','max'])
    max_range_pp=float(((span['max']-span['min'])*100).max())
    city_jumps=(urban.sort_values(['city_code','period']).groupby('city_code').informality_rate.diff().abs()*100)
    dep_jumps=(d.sort_values(['dep_code','period']).groupby('dep_code').informality_rate.diff().abs()*100)
    quality=pd.concat([quality,pd.DataFrame([
       {'control':'urban_monthly_jumps_over_5pp','passed':bool((city_jumps>5).sum()==0),
         'criticality':'DIAGNOSTIC','metric':str(int((city_jumps>5).sum())),
         'status':'PASS' if (city_jumps>5).sum()==0 else 'WARNING'},
       {'control':'department_monthly_jumps_over_5pp','passed':bool((dep_jumps>5).sum()==0),
         'criticality':'DIAGNOSTIC','metric':str(int((dep_jumps>5).sum())),
         'status':'PASS' if (dep_jumps>5).sum()==0 else 'WARNING'},
    ])],ignore_index=True)
    qual_report={'version':'2.2.13.dev0',
        'urban_rows':len(urban),'department_rows':len(d),'national_rows':len(nat),
        'month_count':len(MONTHS),'gap_method':gap_method,
        **({'bridge_level_refresh':bridge_refresh} if bridge_refresh['rows_refreshed'] else {}),
        **({'regime_splice':splice_report} if splice_report else {}),
        'full_closure_max_people':float(monthly.residual_full_people.abs().max()),
        'geih_vs_full_rate_mae_pp':float(monthly.difference_geih_vs_full_target_pp.abs().mean()),
        'geih_vs_full_rate_max_pp':float(monthly.difference_geih_vs_full_target_pp.abs().max()),
        '2020_max_range_scenarios_pp':max_range_pp,
        'urban_monthly_jumps_over_5pp':int((city_jumps>5).sum()),
        'department_monthly_jumps_over_5pp':int((dep_jumps>5).sum()),
        'numeric_quality_passed':bool(quality[quality.criticality=='REQUIRED'].passed.all()),
        'independent_scientific_quality_passed':bool(quality[quality.criticality=='EVIDENCE'].passed.all()),
        'publication_status':'RECONSTRUCTED_RESEARCH_CANDIDATE_NOT_OFFICIAL',
        'frozen_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest()
               for f in (lab/'ciudades.csv',lab/'departamentos.csv',lab/'nacionales.csv')},
        'assumptions':['2020 interpolated latent MLP prior','pre-2021 definition bridge reconstructed',
              'geih informal rate transferred under equal domain/complement rate assumption',
              'city series are nonadditive signals; national sums only full departments']}
    if not qual_report['numeric_quality_passed']:
        raise ValueError('Critical numerical gates fail: '+quality.to_string(index=False))
    def annualize(df,keys,emp,inf):
        x=df.copy()
        x['year']=x.period.str[:4].astype(int)
        summary=x.groupby(['year']+keys,as_index=False).agg(
           mean_monthly_occupied=(emp,'mean'),
           mean_monthly_informal=(inf,'mean'),
           observed_month_count=('period','nunique'))
        summary['annual_informality_rate']=summary.mean_monthly_informal/summary.mean_monthly_occupied
        summary['full_calendar_year']=summary.observed_month_count.eq(12)
        summary['is_official_yearly_rate']=False
        return summary
    annual_cities=annualize(urban,['city_code','city_name'],'employed_frozen','informal_estimated')
    annual_dept=annualize(d,['dep_code'],'employed','informal_full')
    annual_national=annualize(nat,['national_type'],'employed','informal')
    output.mkdir(parents=True,exist_ok=True)
    for filename,data in (
       ('13_ciudades_33_1993_2026_RECONSTRUIDAS.csv',urban),
       ('13_departamentos_33_dos_universos_1993_2026_RECONSTRUIDOS.csv',d),
       ('13_nacionales_2_universos_1993_2026_RECONSTRUIDOS.csv',nat),
       ('13_auditoria_mensual_de_cierre.csv',monthly),
       ('13_puerta_calidad.csv',quality),
       ('13_2020_alternativas_33_departamentos.csv',sensitivity),
       ('13_ciudades_serie_anual.csv',annual_cities),
       ('13_departamentos_serie_anual.csv',annual_dept),
       ('13_nacionales_serie_anual.csv',annual_national)):
        data.to_csv(output/filename,index=False,float_format='%.12g',lineterminator='\n')
    (output/'13_resumen.json').write_text(json.dumps(qual_report,ensure_ascii=False,indent=2),encoding='utf-8')
    files=sorted(x for x in output.iterdir() if x.is_file())
    (output/'manifest.json').write_text(json.dumps({'version':'2.2.13.dev0',
       'files_sha256':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in files}},
       ensure_ascii=False,indent=2),encoding='utf-8')
    return qual_report
