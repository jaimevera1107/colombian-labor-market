"""H12 — transparent departmental sector composition priors (NONCANONICAL).

This module does NOT train an identified sectoral predictor: the checkpoint has
national sector observations, monthly departmental labor totals and annual
urban/rural population projections, but NO departmental sector labels. The
non-neutral scenarios are *explicit counterfactual priors*, not estimated
regression coefficients or statistically validated regional compositions.

H13 must reconcile the departmental-by-sector matrix to national sector
margins. No source CSV is mutated in this H12 stage.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from icml.domain.cutoff import ACTIVE_CUTOFF, FIRST_MONTH, SECTORAL_MONTHS, month_periods

SECTORS = ("A", "B", "C", "D_E", "F", "G", "H", "I", "J", "K", "L", "M_N", "O_P_Q", "R_S_T_U", "NO_INFO")
SCENARIOS = {"NEUTRAL_NATIONAL": 0.0, "RURAL_PROXY_WEAK": 0.75, "RURAL_PROXY_MODERATE": 1.5}
# Hypothetical log-share loadings on the difference between departmental and
# employment-weighted national RURAL *population* fractions. NOT trained.
RURAL_LOADINGS = dict(zip(SECTORS, (1.0, 0.2, -0.20, -0.15, -0.10, -0.10, -0.25, -0.10, -0.40, -0.40, -0.35, -0.35, -0.10, -0.15, 0.0)))


def _csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path, dtype={"dep_code": "string"}, low_memory=False)


def _unique(frame: pd.DataFrame, keys: list[str], name: str) -> None:
    if frame.duplicated(keys).any():
        raise ValueError(f"{name}: duplicated primary keys {keys}")


def _strict_panel(frame: pd.DataFrame, keys: list[str], name: str) -> None:
    _unique(frame, keys, name)
    if frame.empty:
        raise ValueError(f"{name}: empty")
    for key in keys:
        if frame[key].isna().any():
            raise ValueError(f"{name}: null key {key}")


def national_composition(historical: pd.DataFrame, backcast: pd.DataFrame,
                         observed: pd.DataFrame, totals: pd.DataFrame) -> pd.DataFrame:
    """Assemble a no-overlap 1993–2026 national composition (15 categories).

    1993–2001/06: H11 September principal. 2001/07–2014/12: H11 FULL.
    2015/01–2026/08: directly published DANE 13-group monthly shares,
    split B_D_E using the LAST H11 2015/03 estimate as an UNOBSERVED proxy.
    The 13 published values are never edited; roundoff at most two persons is
    handled by normalizing the shares against their nonnegative sum.
    """
    h = historical.loc[(historical['national_type'] == 'ICML_COMPLETO') &
                       (historical['method'] == 'ENH_SEP_PRINCIPAL')].copy()
    b = backcast.loc[(backcast['national_type'] == 'ICML_COMPLETO') &
                     (backcast['scenario'] == 'FULL_2015_BRIDGE')].copy()
    h = h[h['period'] <= '2001-06']
    b = b[(b['period'] >= '2001-07') & (b['period'] <= '2014-12')]
    if len(h) != 102 * 15 or len(b) != 162 * 15:
        raise ValueError(f"H11 historical coverage invalid: {len(h)} / {len(b)}")
    _strict_panel(h, ['period', 'sector_code'], 'H11 pre-2001')
    _strict_panel(b, ['period', 'sector_code'], 'H11 2001–2014')
    # The H11 2015/03 B:D_E ratio is NOT an observation from the 13-group DANE annex.
    bridge = backcast.loc[(backcast['national_type'] == 'ICML_COMPLETO') &
                          (backcast['scenario'] == 'FULL_2015_BRIDGE') &
                          (backcast['period'] == '2015-03') &
                          (backcast['sector_code'].isin(['B', 'D_E']))]
    if set(bridge['sector_code']) != {'B', 'D_E'}:
        raise ValueError('Missing H11 B/D_E transition proxy 2015-03')
    mining = float(bridge.loc[bridge['sector_code']=='B','sector_share'].iloc[0])
    util = float(bridge.loc[bridge['sector_code']=='D_E','sector_share'].iloc[0])
    if mining <= 0 or util <= 0:
        raise ValueError('H11 bridge share must be positive')
    ratio = mining/(mining+util)
    frames=[]
    for part, tag in ((h,'ENH_SEP_ESTIMATED_1993_2001'),
                      (b,'H11_INVERSE_ROLLING_ESTIMATED_2001_2014')):
        c=part[['period','sector_code','sector_share']].copy()
        c['source_status']=tag
        c['split_status']='H11_ESTIMATED_BRANCHES'
        frames.append(c)
    _strict_panel(observed,['period','sector_code'],'DANE monthly 13')
    _strict_panel(totals,['period'],'DANE totals')
    if set(observed['sector_code'].unique()) != ((set(SECTORS)-{'B','D_E','NO_INFO'})|{'B_D_E_COMBINED'}):
        raise ValueError('Unrecognized monthly 13-group classification')
    if 'NO_INFO' in observed['sector_code'].unique():
        raise ValueError('NO_INFO must come from total minus 13 groups')
    period_obs=set(observed.period)
    if period_obs != set(totals.period) or len(period_obs) != SECTORAL_MONTHS:
        raise ValueError('DANE monthly period coverage mismatch')
    built=[]
    for period, group in observed.groupby('period',sort=True):
        t=totals.loc[totals.period==period].iloc[0]
        n=float(t['occupied_official_persons'])
        v=group.set_index('sector_code')['employed_persons'].astype(float).to_dict()
        if min(v.values()) < 0 or n <= 0:
            raise ValueError(f'Invalid observed sector levels {period}')
        difference=n-sum(v.values())
        if difference < -3:
            raise ValueError(f'Non-rounding negative NO_INFO {period}: {difference}')
        v['B']=v.pop('B_D_E_COMBINED')*ratio
        v['D_E']=sum(group.loc[group.sector_code=='B_D_E_COMBINED','employed_persons'])*(1-ratio)
        v['NO_INFO']=max(0.0,difference)
        denom=sum(v.values())
        status=('DANE_13_PUBLISHED_PLUS_ROUNDING_NORMALIZATION' if difference<0
                else 'DANE_13_PUBLISHED_PLUS_NO_INFO_REMAINDER')
        for code in SECTORS:
            built.append({'period':period,'sector_code':code,'sector_share':v[code]/denom,
                          'source_status':status,
                          'split_status':('ASSUMED_FIXED_H11_2015_03_B_D_E_RATIO' if code in ('B','D_E')
                                          else ('NO_INFO_RESIDUAL_FROM_OFFICIAL_TOTAL' if code=='NO_INFO'
                                                else 'DANE_PUBLISHED_13_GROUP'))})
    frames.append(pd.DataFrame(built))
    out=pd.concat(frames,ignore_index=True).sort_values(['period','sector_code']).reset_index(drop=True)
    _strict_panel(out,['period','sector_code'],'combined national composition')
    all_periods=month_periods().astype(str)
    if sorted(out.period.unique().tolist()) != sorted(all_periods.tolist()):
        raise ValueError('National sector composition has missing/extra months')
    if (out.groupby('period').sector_code.nunique()!=15).any():
        raise ValueError('National composition must have 15 sectors each month')
    if out.sector_share.isna().any() or (out.sector_share<0).any():
        raise ValueError('Invalid national sector fractions')
    residual=(out.groupby('period').sector_share.sum()-1).abs().max()
    if residual>1e-10:raise ValueError(f'National sector simplex residual {residual}')
    return out


def build_covariates(departments: pd.DataFrame, population: pd.DataFrame) -> pd.DataFrame:
    d=departments.copy()
    d['dep_code']=d['dep_code'].astype('string').str.zfill(2)
    _strict_panel(d,['period','dep_code'],'department labor')
    if sorted(d.period.unique()) != list(month_periods().astype(str)):
        raise ValueError(f'Labor panel is not {FIRST_MONTH} to {ACTIVE_CUTOFF}')
    if (d.groupby('period').dep_code.nunique()!=33).any():
        raise ValueError('33 territories required each month')
    d['year']=d['period'].str[:4].astype(int)
    pop=population.copy()
    pop['dep_code']=pop['dep_code'].astype('string').str.zfill(2)
    _strict_panel(pop,['dep_code','year','area_type'],'annual population projections')
    pop['year']=pop['year'].astype(int)
    pivot=pop.pivot(index=['dep_code','year'],columns='area_type',values='population')
    necessary={'Total','Cabecera','Centros Poblados y Rural Disperso'}
    if not necessary <= set(pivot.columns):raise ValueError('Annual rural/urban projections are incomplete')
    pivot=pivot.reset_index().rename(columns={'Total':'population_projection',
                'Centros Poblados y Rural Disperso':'rural_projection','Cabecera':'urban_projection'})
    pivot['rural_fraction']=pivot.rural_projection/pivot.population_projection
    if (pivot.rural_fraction<0).any() or (pivot.rural_fraction>1).any():
        raise ValueError('Invalid rural fraction')
    cov=d.merge(pivot[['dep_code','year','rural_fraction','urban_projection','rural_projection']],
                on=['dep_code','year'],how='left',validate='many_to_one')
    if cov.rural_fraction.isna().any():
        raise ValueError('No rurality projection for one or more department-years')
    for col in ['employed','employed_represented']:
        if cov[col].isna().any() or (cov[col]<0).any():
            raise ValueError(f'Invalid departmental employment {col}')
    weighted=(cov.rural_fraction*cov.employed).groupby(cov.period).sum()/cov.groupby('period').employed.sum()
    cov['national_employment_weighted_rural_fraction']=cov.period.map(weighted)
    cov['rural_fraction_centered']=cov.rural_fraction-cov.national_employment_weighted_rural_fraction
    return cov.sort_values(['period','dep_code']).reset_index(drop=True)


def calculate_priors(national:pd.DataFrame, cov:pd.DataFrame, scenario:str) -> pd.DataFrame:
    if scenario not in SCENARIOS:raise ValueError(f'Unknown scenario {scenario}')
    months=sorted(national.period.unique().tolist())
    dep_codes=sorted(cov.dep_code.unique().tolist())
    nsec=len(SECTORS); ndep=len(dep_codes)
    shares=national.pivot(index='period',columns='sector_code',values='sector_share').reindex(
        index=months,columns=list(SECTORS))
    if shares.isna().any().any():raise ValueError('Missing national shares')
    batch=cov.set_index(['period','dep_code']).reindex(pd.MultiIndex.from_product(
        [months,dep_codes],names=['period','dep_code']))
    if batch.rural_fraction_centered.isna().any():raise ValueError('Missing spatial covariate')
    centered=batch.rural_fraction_centered.to_numpy().reshape(len(months),ndep)
    prior=shares.to_numpy()[:,None,:]*np.exp(
        SCENARIOS[scenario]*centered[:,:,None]*np.array([RURAL_LOADINGS[x] for x in SECTORS])[None,None,:])
    prior /= prior.sum(axis=2,keepdims=True)
    if not np.isfinite(prior).all() or (prior<0).any():raise ValueError('Nonfinite predicted composition')
    # Assemble with explicit grid coordinates; use only observed departmental
    # employed totals, NOT population ratios, for both employment universes.
    out=pd.DataFrame({
        'period':np.repeat(months,ndep*nsec),
        'dep_code':np.tile(np.repeat(dep_codes,nsec),len(months)),
        'sector_code':np.tile(SECTORS,len(months)*ndep),
        'sector_share':prior.ravel(),
        'scenario':scenario,
        'estimation_status':'H12_DEPARTMENTAL_SECTOR_PRIOR_UNVALIDATED',
        'prior_information':'NATIONAL_SECTOR_PLUS_ANNUAL_RURAL_POPULATION_PROXY',
        'direct_department_sector_observation':False,
    })
    return out


def run(departments_csv:Path, nationals_csv:Path, population_csv:Path,
        historical_csv:Path, backcast_csv:Path, observed_csv:Path,
        recent_totals_csv:Path, output:Path) -> dict:
    """Write H12 independent prior artifact and audits, never edit inputs."""
    paths=dict(departments=Path(departments_csv),nationals=Path(nationals_csv),
               population=Path(population_csv),historical=Path(historical_csv),
               backcast=Path(backcast_csv),observed=Path(observed_csv),
               recent_totals=Path(recent_totals_csv))
    inputs={name:_csv(p) for name,p in paths.items()}
    national=national_composition(inputs['historical'], inputs['backcast'],inputs['observed'],inputs['recent_totals'])
    cov=build_covariates(inputs['departments'],inputs['population'])
    nationals=inputs['nationals']
    _strict_panel(nationals,['period','national_type'],'national labor')
    nf=nationals.loc[nationals.national_type=='ICML_COMPLETO'].set_index('period').employed
    nd=nationals.loc[nationals.national_type=='DANE_REFERENCIA'].set_index('period').employed
    if set(nf.index)!=set(cov.period) or set(nd.index)!=set(cov.period):
        raise ValueError('National labor and department month coverage differs')
    full=cov.groupby('period').employed.sum();repre=cov.groupby('period').employed_represented.sum()
    if ((full-nf).abs()>1e-4).any():
        raise ValueError('Input department employed does not reconcile to national ICML; hard stop')
    # Prior to 2001 there is no proper departmental GEIH representativeness
    # bridge in this checkpoint. Expose that coverage issue, do not correct it.
    geih_mismatch=(repre-nd).abs()>1e-3
    if geih_mismatch.loc[geih_mismatch.index>='2001-01'].any():
        raise ValueError('Unexpected post-2000 GEIH universe employment mismatch')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    national.to_csv(output/'12_composicion_nacional_unificada_1993_2026.csv',index=False)
    cov[['period','dep_code','territory_name','employed','employed_represented',
         'source','rural_fraction','national_employment_weighted_rural_fraction',
         'rural_fraction_centered','factor_employed','factor_is_assumed']].to_csv(
             output/'12_covalidadores_departamentales.csv',index=False)
    all_shares=[];audits=[];margins=[]
    nq=national.pivot(index='period',columns='sector_code',values='sector_share').reindex(columns=SECTORS)
    for scenario in SCENARIOS:
        prior=calculate_priors(national,cov,scenario)
        # Row simplex check BEFORE employment transfer
        simplex=prior.groupby(['period','dep_code']).sector_share.sum()
        if (simplex-1).abs().max()>1e-12:raise ValueError('Sector prior not in simplex')
        cols=['period','dep_code','employed','employed_represented','source','factor_is_assumed']
        p=prior.merge(cov[cols],on=['period','dep_code'],validate='many_to_one')
        p['employed_full_sector']=p.sector_share*p.employed
        p['employed_geih_sector_proxy']=p.sector_share*p.employed_represented
        p['geih_universe_status']=np.where(p.period<'2001-01',
                          'PRE2001_NOT_RECONCILED_TO_DANE_NATIONAL',
                          'POST2000_REPRESENTED_DANE_CLOSURE')
        all_shares.append(p[['period','dep_code','sector_code','scenario','sector_share',
           'employed_full_sector','employed_geih_sector_proxy',
           'estimation_status','geih_universe_status','direct_department_sector_observation']])
        row=p.groupby(['period','dep_code'],as_index=False).agg(
            full_sector_sum=('employed_full_sector','sum'),
            geih_sector_sum=('employed_geih_sector_proxy','sum'),
            full_input=('employed','first'),geih_input=('employed_represented','first'))
        row['scenario']=scenario
        row['full_residual_persons']=row.full_sector_sum-row.full_input
        row['geih_residual_persons']=row.geih_sector_sum-row.geih_input
        if row[['full_residual_persons','geih_residual_persons']].abs().max().max()>1e-5:
            raise ValueError('H12 monthly department row closure failed')
        audits.append(row)
        margins_sec=p.groupby(['period','sector_code'],as_index=False).agg(
            full_prior_sector=('employed_full_sector','sum'),
            geih_proxy_sector=('employed_geih_sector_proxy','sum'))
        margins_sec=margins_sec.merge(national[['period','sector_code','sector_share']],
                         on=['period','sector_code'],validate='many_to_one')
        margins_sec['national_icml_target']=margins_sec.sector_share*margins_sec.period.map(nf)
        margins_sec['national_dane_target']=margins_sec.sector_share*margins_sec.period.map(nd)
        margins_sec['full_prior_minus_national']=margins_sec.full_prior_sector-margins_sec.national_icml_target
        margins_sec['geih_proxy_minus_national']=margins_sec.geih_proxy_sector-margins_sec.national_dane_target
        margins_sec['full_prior_gap_pp_of_national_employed']=100*margins_sec.full_prior_minus_national/margins_sec.period.map(nf)
        margins_sec['scenario']=scenario
        margins_sec['h13_status']='NOT_RECONCILED_TO_SECTOR_MARGINS_H13_PENDING'
        margins.append(margins_sec)
    output_prior=pd.concat(all_shares,ignore_index=True)
    output_prior.to_csv(output/'12_candidatos_depto_sector_1993_2026_NO_CANONICOS.csv',index=False,float_format='%.12g')
    check=pd.concat(audits,ignore_index=True)
    check.to_csv(output/'12_auditoria_cierre_filas.csv',index=False)
    margin=pd.concat(margins,ignore_index=True)
    margin.to_csv(output/'12_brechas_margenes_nacionales_PRE_H13.csv',index=False)
    universe=pd.DataFrame({'period':full.index,'full_dept_sum':full.to_numpy(),
          'full_national_icml':nf.reindex(full.index).to_numpy(),
          'geih_dept_sum':repre.reindex(full.index).to_numpy(),
          'national_dane':nd.reindex(full.index).to_numpy()})
    universe['full_difference']=universe.full_dept_sum-universe.full_national_icml
    universe['geih_difference']=universe.geih_dept_sum-universe.national_dane
    universe['geih_status']=np.where(universe.period<'2001-01',
            'NO_DEPARTMENTAL_GEIH_IDENTIFICATION_PRE2001',
            'REPRESENTED_TOTAL_RECONCILED')
    universe.to_csv(output/'12_auditoria_universos.csv',index=False)
    by_scenario=margin.groupby('scenario').agg(max_abs_full_gap_pp=(
                 'full_prior_gap_pp_of_national_employed',lambda x:float(x.abs().max())),
                 mean_abs_full_gap_pp=('full_prior_gap_pp_of_national_employed',lambda x:float(x.abs().mean()))).reset_index()
    by_scenario.to_csv(output/'12_sensibilidad_escenarios_resumen.csv',index=False)
    metadata={
       'version':'H12_2_2_18_EXPERIMENTAL_1','status':'EXPERIMENTAL_PRIOR_NOT_SECTOR_LABELS',
       'months':int(cov.period.nunique()),'departments':int(cov.dep_code.nunique()),
       'sectors':15,'scenarios':list(SCENARIOS),
       'candidate_rows':len(output_prior),
       'max_row_residual_persons':float(check[['full_residual_persons','geih_residual_persons']].abs().max().max()),
       'max_national_dept_residual_persons':float(universe.full_difference.abs().max()),
       'pre_2001_geih_months_not_reconciled':int((universe.geih_status=='NO_DEPARTMENTAL_GEIH_IDENTIFICATION_PRE2001').sum()),
       'post_2000_geih_max_residual_persons':float(universe.loc[universe.period>='2001-01','geih_difference'].abs().max()),
       'estimated_geographic_sector_observations':0,
       'national_employment_target_requires_H13':True,
       'rural_loadings_hypothetical_not_fitted':RURAL_LOADINGS,
       'scenario_strengths_assumed':SCENARIOS,
       'sector_margin_gap_by_scenario':by_scenario.to_dict('records'),
       'sources_sha256':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()},
       'publication_gate':'BLOCKED_NO_SUBNATIONAL_SECTOR_ANCHORS_OR_OOS_LABEL_VALIDATION',
       'interpretation':'Rural fraction is population, never used as expansion factor for employed; only optional log-share tilt',
    }
    (output/'12_puerta_calidad.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
    return metadata
