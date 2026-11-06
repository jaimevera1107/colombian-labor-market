"""DANE-only sequential experimental informal-employment chain.

Actual dependencies: 13-city reconstructed history -> national bridge ->
23 cities extended by that national history -> 33 urban proxies and a
33-department feature/baseline panel. No simulated department *labels*.

Every official DANE rolling window is retained as a window; latent monthly
signals are never passed off as monthly observed data. This is experimental.
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from icml.informality.national import OLD_CITY, NEW
from icml.informality.urban_backcast import (
    ALIAS, FIRST_13, MONTHS, OLD_MONTHS, NEW_MONTHS,
    _apply_13_anchors, _check_labor, _city_windows, _hash,
    _nearest_donor, _national_historical, _normal, _pre2007_trajectory,
    _rate_13, _urban_table,
)
from icml.domain.cutoff import N_MONTHS, ROWS_NATIONAL

EXPERIMENT = '2.2.4.dev0-sequential-DANE-only'


@dataclass(frozen=True)
class SequentialPolicy:
    old_window_lambda: float = 0.025
    new_window_lambda: float = 0.012
    national_proxy_strength: float = 0.5
    national_change_weight: float = 0.7
    unemployment_gap_weight: float = 0.3
    donor_unemployment_weight: float = 0.35
    cluster_reference_k: int = 4
    cluster_seed: int = 20261031


def load_policy(path: Path | None) -> SequentialPolicy:
    if path is None:
        return SequentialPolicy()
    data=tomllib.loads(Path(path).read_text(encoding='utf8'))
    vals=data['informality']['sequential']
    expected=set(SequentialPolicy.__dataclass_fields__)
    if set(vals)!=expected:raise ValueError('Sequential configuration contract has changed')
    policy=SequentialPolicy(**vals)
    if policy.old_window_lambda<=0 or policy.new_window_lambda<=0:
        raise ValueError('Invalid rolling-window penalty')
    if not (0<=policy.national_proxy_strength<=1 and
            0<=policy.national_change_weight<=1 and
            0<=policy.unemployment_gap_weight<=1 and
            0<=policy.donor_unemployment_weight<=1 and
            2<=policy.cluster_reference_k<=6):
        raise ValueError('Invalid extrapolation/cluster policy')
    return policy

DIRECT_23 = 23
FIRST_OTHER_10 = 10


def _check_rates(arr: np.ndarray, where: str) -> np.ndarray:
    if not np.isfinite(arr).all() or np.min(arr) < 0 or np.max(arr) > 1:
        raise ValueError(f'Invalid rates in {where}')
    return arr


def _write(df: pd.DataFrame, output: Path, name: str) -> None:
    df.to_csv(output/name, index=False, encoding='utf-8-sig', float_format='%.12g',lineterminator='\n')


def _win_match(x: pd.DataFrame, source: pd.DataFrame, codes: set[int], definition: str) -> pd.DataFrame:
    """Audit each DANE source rolling window in its own definition/domain.

    A modeled city rate multiplied by ICML urban employed is NOT the DANE
    window count. We audit a *rate approximation* and keep that caveat.
    """
    obs=source[(source.definition==definition)&(source.domain=='city')].copy()
    obs['city_code']=obs.concept.map(lambda s: ALIAS.get(_normal(s)))
    obs=obs[obs.city_code.isin(codes)&obs.eligible_for_training.astype(bool)]
    lookup=x.set_index(['city_code','period'])['source_rate_for_window']
    rows=[]
    for r in obs.itertuples(index=False):
        months=pd.date_range(r.period_start,r.period_end,freq='MS').strftime('%Y-%m')
        try:
            rr=np.array([lookup.loc[(int(r.city_code),p)] for p in months],float)
        except KeyError as e:
            raise ValueError(f'No estimate for DANE window: {r.concept}') from e
        rows.append({'city_code':int(r.city_code),'period_start':r.period_start,
                     'period_end':r.period_end,'definition':definition,
                     'dane_rate':float(r.informality_rate),
                     'equal_month_rate_estimate':float(rr.mean()),
                     'rate_residual_pp':100*(float(rr.mean())-float(r.informality_rate)),
                     'window_uses_icml_occupation_weights':False,
                     'is_independent_monthly_observation':False})
    return pd.DataFrame(rows)


def build_13(sources: pd.DataFrame, urban_labor: pd.DataFrame,
             anchors: pd.DataFrame, policy:SequentialPolicy) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    """Reconstruct 13 individual city signals, then audit 13-area aggregate.

    2001-06 individual T5 observations are absent; six DANE aggregate T5
    anchors constrain the joint urban employment-weighted proxy only.
    Individual T10 observations are not imposed as T5 constraints.
    """
    labor=_urban_table(urban_labor)
    old, aud_old=_city_windows(sources,OLD_CITY,OLD_MONTHS,lam=policy.old_window_lambda)
    new, aud_new=_city_windows(sources,NEW,NEW_MONTHS,lam=policy.new_window_lambda)
    if not set(FIRST_13).issubset(old) or not set(FIRST_13).issubset(new):
        raise ValueError('Missing historic or recent DANE individual series in primary 13')
    older={}
    idx_old=MONTHS.get_indexer(OLD_MONTHS)
    idx_new=MONTHS.get_indexer(NEW_MONTHS)
    for c in FIRST_13:
        signal=np.full(len(MONTHS),np.nan)
        signal[idx_old]=old[c]
        signal[:idx_old[0]]=_pre2007_trajectory(old[c],c,labor)
        older[c]=signal
    older,agg=_apply_13_anchors(older,labor,anchors)
    # True leave-one-anchor-year-out check: rebuild the *intermediate* 13 city
    # histories without the withheld aggregate anchor.
    cv=[]
    for held in anchors[(anchors.definition=='hasta_5_trabajadores')&anchors.year.between(2001,2006)].itertuples(index=False):
        unadjusted={}
        for c in FIRST_13:
            s=np.full(len(MONTHS),np.nan)
            s[idx_old]=old[c]
            s[:idx_old[0]]=_pre2007_trajectory(old[c],c,labor)
            unadjusted[c]=s
        updated,_=_apply_13_anchors(unadjusted,labor,anchors[~((anchors.year==held.year)&
                                                       (anchors.definition=='hasta_5_trabajadores'))])
        estimate=_rate_13(updated,labor)
        ix=MONTHS.get_indexer(pd.date_range(held.period_start,held.period_end,freq='MS'))
        pred=float(np.mean(estimate[ix]))
        cv.append({'year':int(held.year),'target':held.rate_pct/100,
                   'prediction':pred,'error_pp':100*(pred-held.rate_pct/100),
                   'target_level':'13_areas_aggregate_not_individual_city'})
    records=[]
    for c in FIRST_13:
        oldrate=older[c]
        # Logit offset estimates a definition bridge. DANE does not observe
        # monthly points directly; new latest-month quantities are latent.
        shift=float(np.mean(logit(np.clip(new[c][:3],.005,.995))-
                            logit(np.clip(oldrate[idx_new[:3]],.005,.995))))
        current=expit(logit(np.clip(oldrate,.005,.995))+shift)
        current[idx_new]=new[c]
        current=_check_rates(current,f'13-city {c}')
        employed=labor[c].employed.to_numpy(float)
        records.append(pd.DataFrame({'city_code':c,'period':MONTHS.strftime('%Y-%m'),
            'city_name':str(labor[c].city_name.iloc[0]),
            'employed_frozen':employed,'informality_rate':current,
            'old_t5_rate_auxiliary':oldrate,
            'informal_estimated':employed*current,
            'formal_estimated':employed*(1-current),
            'source_rate_for_window':np.where(np.arange(len(MONTHS))<idx_new[0],oldrate,current),
            'provenance':np.where(MONTHS.year<2001,'RETROPOLATION_NO_NUMERIC_ENH_ANCHOR',
                  np.where(MONTHS.year<2007,'DANE_13_AREAS_T5_AGGREGATE_NOT_INDIVIDUAL',
                     np.where(MONTHS.year<2021,'DANE_INDIVIDUAL_OLD_T5_ROLLING3',
                              'DANE_INDIVIDUAL_NEW_GEIH_LATENT_ROLLING3'))),
            'status':'EXPERIMENTAL_NOT_CANONICAL','monthly_observed_DANE':False}))
    result=pd.concat(records,ignore_index=True).sort_values(['period','city_code'])
    if len(result)!=len(FIRST_13)*len(MONTHS): raise AssertionError('13-city coverage')
    # Keep DANE window fidelity audits by the inversion methods, not by the
    # bridged monthly publication rates.
    win=pd.concat([aud_old[aud_old.city_code.isin(FIRST_13)],
                   aud_new[aud_new.city_code.isin(FIRST_13)]],ignore_index=True)
    return result,agg,pd.DataFrame(cv),win


def build_national(cities13:pd.DataFrame,national_labor:pd.DataFrame,
                   sources:pd.DataFrame,recent:pd.DataFrame,
                   anchors:pd.DataFrame,policy:SequentialPolicy|None=None) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    if cities13.city_code.nunique()!=13 or len(cities13)!=13*N_MONTHS:
        raise ValueError('Stage 13 absent or incomplete')
    nation,sens,group=_national_historical(cities13,national_labor,sources,recent,anchors,
                    strength=(policy or SequentialPolicy()).national_proxy_strength)
    if nation.national_type.nunique()!=2 or len(nation)!=ROWS_NATIONAL:
        raise ValueError('National series incomplete')
    return nation,sens,group


def _bridge_10_city(pre2007_old:np.ndarray, national:np.ndarray,
                    unemployment_city:np.ndarray, unemployment_national:np.ndarray,
                    anchor_value:float, month0:int, national_weight:float=.7,
                    unemployment_weight:float=.3) -> np.ndarray:
    """Backward extrapolation from city 2007 based on *already built* national.

    Uses national logit change, centered at first city T5 trimester; unemployment
    gap is a secondary shape. The signal is model-based, not an official city
    datum. Keeping the anchor in T5 units prevents false definition matching.
    """
    natlog=logit(np.clip(national,.005,.995))
    gap=(unemployment_city-unemployment_national)
    nref=float(np.mean(natlog[month0:month0+3]))
    gref=float(np.mean(gap[month0:month0+3]))
    old=expit(logit(np.clip(anchor_value,.005,.995))+
              national_weight*(natlog[:month0]-nref)+unemployment_weight*(gap[:month0]-gref))
    return _check_rates(old,'national-driven 10-city retropolation')


def build_23_and_33(cities13:pd.DataFrame,national:pd.DataFrame,sources:pd.DataFrame,
                    urban_labor:pd.DataFrame,policy:SequentialPolicy) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    """Independent stage after national reconstruction; retain 13 exactly."""
    frozen=_urban_table(urban_labor)
    t5,aud_old=_city_windows(sources,OLD_CITY,OLD_MONTHS,lam=policy.old_window_lambda)
    new,aud_new=_city_windows(sources,NEW,NEW_MONTHS,lam=policy.new_window_lambda)
    if len(t5)!=23 or set(t5)!=set(new) or len(set(t5)-set(FIRST_13))!=10:
        raise ValueError('Expected precisely 13+10 DANE city domains')
    nat=national[national.national_type=='DANE_REFERENCIA'].sort_values('period')
    nat_rate=nat.informality_rate_estimated.to_numpy(float)
    if len(nat_rate)!=N_MONTHS:raise ValueError('National history missing')
    # National unemployment is a frozen labor indicator, not informal target.
    all_emp=np.vstack([frozen[c].employed.to_numpy(float) for c in frozen])
    all_unemp=np.vstack([frozen[c].unemployed.to_numpy(float) for c in frozen])
    national_u=all_unemp.sum(axis=0)/(all_emp.sum(axis=0)+all_unemp.sum(axis=0))
    iold=MONTHS.get_indexer(OLD_MONTHS)
    inew=MONTHS.get_indexer(NEW_MONTHS)
    m0=int(iold[0]); series={}
    table13=cities13.copy()
    for c in FIRST_13:
        z=table13[table13.city_code==c].sort_values('period')
        series[c]=z.informality_rate.to_numpy(float)
    rows=[];backcast=[]
    for c in sorted(set(t5)-set(FIRST_13)):
        u=(frozen[c].unemployed/frozen[c].labor_force).to_numpy(float)
        old=np.full(N_MONTHS,np.nan)
        old[iold]=t5[c]
        old[:m0]=_bridge_10_city(old,nat_rate,u,national_u,float(np.mean(t5[c][:3])),m0,
                    national_weight=policy.national_change_weight,
                    unemployment_weight=policy.unemployment_gap_weight)
        # Official definition bridge estimated only using overlapping months.
        delta=float(np.mean(logit(np.clip(new[c][:3],.005,.995))-
                            logit(np.clip(old[inew[:3]],.005,.995))))
        rate=expit(logit(np.clip(old,.005,.995))+delta)
        rate[inew]=new[c]
        series[c]=_check_rates(rate,f'city {c}')
        backcast.append({'city_code':int(c),'source_from':'DANE_T5_CITY_2007',
          'retropolation_to':'1993-01', 'second_stage_signal':'NATIONAL_AFTER_13_CITIES',
          'national_weight_on_logit_change':policy.national_change_weight,
          'unemployment_gap_weight':policy.unemployment_gap_weight,'definition_bridge_logit_shift':delta,
          'is_DANE_observed':False})
    for c in sorted(frozen):
        if c in series:continue
        donor,dist=_nearest_donor(c,sorted(t5),frozen)
        uc=(frozen[c].unemployed/frozen[c].labor_force).to_numpy(float)
        ud=(frozen[donor].unemployed/frozen[donor].labor_force).to_numpy(float)
        off=np.clip(policy.donor_unemployment_weight*(uc-ud),-.2,.2)
        series[c]=_check_rates(expit(logit(np.clip(series[donor],.005,.995))+off),f'donor city {c}')
        backcast.append({'city_code':int(c),'source_from':f'DONOR_{donor}',
            'retropolation_to':'1993-01','second_stage_signal':'DONOR_PLUS_LABOR_GAP',
            'national_weight_on_logit_change':np.nan,'unemployment_gap_weight':policy.donor_unemployment_weight,
            'definition_bridge_logit_shift':np.nan,'distance':dist,
            'is_DANE_observed':False})
    for c in sorted(frozen):
        employed=frozen[c].employed.to_numpy(float)
        r=series[c]
        rows.append(pd.DataFrame({'city_code':c,'city_name':frozen[c].city_name.iloc[0],
            'period':MONTHS.strftime('%Y-%m'),'employed_frozen':employed,
            'informality_rate':r,'informal_estimated':employed*r,
            'formal_estimated':employed*(1-r),
            'informality_source_stage':('FIRST_13' if c in FIRST_13 else
                   'NATIONAL_RETROPOLATED_SECOND_10' if c in t5 else 'DONOR_INFERRED_TEN'),
            'has_DANE_individual_windows':c in t5,
            'monthly_observed_DANE':False,'status':'EXPERIMENTAL_NOT_CANONICAL'}))
    whole=pd.concat(rows,ignore_index=True).sort_values(['period','city_code'])
    # Hard preservation: nothing in stage 23/33 may revise the 13-city stage.
    test=whole[whole.city_code.isin(FIRST_13)].sort_values(['period','city_code'])
    prior=table13.sort_values(['period','city_code'])
    if not np.allclose(test.informality_rate,prior.informality_rate,atol=1e-12,rtol=0):
        raise AssertionError('Stage23 silently changed stage13')
    if len(whole)!=33*N_MONTHS or whole[list(['informal_estimated','formal_estimated'])].isna().any().any():
        raise AssertionError('Incomplete 33 signals')
    return whole,pd.DataFrame(backcast),pd.concat([aud_old,aud_new],ignore_index=True)


def build_predictor_and_baseline(urban:pd.DataFrame,depts:pd.DataFrame,
                                 national:pd.DataFrame,
                                 urban_labor:pd.DataFrame,
                                 policy:SequentialPolicy) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    """Features and explicit no-label urban-rate baseline, NOT a trained MLP.

    A city is not a department observation. Do not use this baseline as a
    ground-truth training target or measure it as an out-of-sample fit.
    """
    if len(depts)!=33*N_MONTHS or depts.duplicated(['dep_code','period']).any():
        raise ValueError('Frozen department labor coverage changed')
    u=urban[['city_code','period','informality_rate','employed_frozen','informality_source_stage']].rename(
        columns={'city_code':'dep_code','informality_rate':'urban_informal_rate',
                 'employed_frozen':'urban_employed','informality_source_stage':'urban_provenance'})
    frame=depts.merge(u,on=['dep_code','period'],validate='1:1',how='left')
    nat=national[national.national_type=='ICML_COMPLETO'][['period','informality_rate_estimated']].rename(
        columns={'informality_rate_estimated':'national_icml_informal_rate'})
    frame=frame.merge(nat,on='period',how='left',validate='m:1')
    frame['year']=frame.period.str[:4].astype(int)
    frame['month']=frame.period.str[5:7].astype(int)
    # Urban labor variables are separate from departmental values.
    urban_cov=urban_labor[['city_code','period','unemployed','labor_force','working_age','employed','population']].rename(
        columns={'city_code':'dep_code','unemployed':'urban_unemployed',
            'labor_force':'urban_labor_force','working_age':'urban_working_age',
            'employed':'urban_labor_employed','population':'urban_population'})
    frame=frame.merge(urban_cov,on=['dep_code','period'],validate='1:1')
    frame['urban_unemployment_rate']=frame.urban_unemployed/frame.urban_labor_force
    frame['urban_employment_rate']=frame.urban_labor_employed/frame.urban_working_age
    frame['department_unemployment_rate']=frame.unemployed/frame.labor_force
    frame['department_participation_rate']=frame.labor_force/frame.working_age
    frame['department_employment_rate']=frame.employed/frame.working_age
    frame['urban_to_department_employment_ratio']=frame.urban_employed/frame.employed
    frame['urban_minus_department_unemployment_pp']=100*(
        frame.urban_unemployment_rate-frame.department_unemployment_rate)
    # A frozen descriptive partition from urban labor covariates only. It is
    # NOT a CV-safe training feature: refit clusters within each spatial fold.
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    profile=frame[(frame.year>=2007)&(frame.year<=2019)].groupby('dep_code').agg(
        urban_unemployment_rate=('urban_unemployment_rate','median'),
        urban_employment_rate=('urban_employment_rate','median'),
        urban_population=('urban_population','median'),
        urban_to_department_employment_ratio=('urban_to_department_employment_ratio','median'))
    profile['urban_population']=np.log1p(profile.urban_population)
    direct_codes=set(urban[urban.has_DANE_individual_windows].city_code.unique())
    train_codes=sorted(direct_codes)
    scale=StandardScaler().fit(profile.loc[train_codes])
    km=KMeans(n_clusters=policy.cluster_reference_k,n_init=15,
              random_state=policy.cluster_seed).fit(scale.transform(profile.loc[train_codes]))
    memberships=km.predict(scale.transform(profile))
    cluster=pd.DataFrame({'dep_code':profile.index.astype(int),
                          'cluster_descriptive_2007_2019':memberships.astype(int)})
    frame=frame.merge(cluster,on='dep_code',validate='m:1')
    frame['cluster_is_fold_safe']=False
    frame['month_sin']=np.sin(2*np.pi*frame.month/12)
    frame['month_cos']=np.cos(2*np.pi*frame.month/12)
    frame['informality_training_target_available']=False
    frame['target_informality_observed_DANE']=np.nan
    frame['urban_transfer_baseline_rate']=frame.urban_informal_rate
    # No assumption that the urban rates alone are valid departmental labels.
    frame['urban_transfer_baseline_informal']=frame.urban_transfer_baseline_rate*frame.employed
    frame['urban_transfer_baseline_formal']=frame.employed-frame.urban_transfer_baseline_informal
    if frame[['urban_transfer_baseline_rate','urban_transfer_baseline_informal',
              'urban_transfer_baseline_formal']].isna().any().any():
        raise ValueError('Predictor baseline missing')
    if (frame.urban_transfer_baseline_rate.lt(0)|frame.urban_transfer_baseline_rate.gt(1)).any():
        raise ValueError('Baseline invalid rate')
    baseline=frame[['dep_code','period','employed','urban_transfer_baseline_rate',
                    'urban_transfer_baseline_informal','urban_transfer_baseline_formal',
                    'urban_provenance']].copy()
    diag=baseline.groupby('period').agg({'urban_transfer_baseline_informal':'sum',
                                        'employed':'sum'}).reset_index()
    diag=diag.merge(nat,on='period',validate='1:1')
    diag['baseline_national_informal_rate']=diag.urban_transfer_baseline_informal/diag.employed
    diag['uncalibrated_gap_to_national_pp']=100*(diag.baseline_national_informal_rate-
                                                 diag.national_icml_informal_rate)
    diag['is_nationally_calibrated']=False
    return frame,baseline,diag


def _supervised_design(urban:pd.DataFrame, frame:pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Create *city* labels and *department* predictor rows, never vice-versa.

    City labels are modeled latent monthly rates, not directly monthly DANE
    observations. The reference clustering label is descriptive and must be
    refitted within each cross-validation fold if used by a future model.
    """
    cols=['year','month_sin','month_cos','urban_unemployment_rate',
          'urban_employment_rate','cluster_descriptive_2007_2019']
    urban_cov=frame[['dep_code','period',*cols,'urban_labor_force',
                     'urban_working_age','urban_population','urban_labor_employed']].copy()
    urban_cov=urban_cov.rename(columns={'urban_unemployment_rate':'unemployment_rate',
        'urban_employment_rate':'employment_rate',
        'urban_labor_force':'labor_force','urban_working_age':'working_age',
        'urban_population':'population','urban_labor_employed':'employed'})
    urban_cov['participation_rate']=urban_cov.labor_force/urban_cov.working_age
    urban_cov['working_age_share']=urban_cov.working_age/urban_cov.population
    urban_cov['log_employed']=np.log1p(urban_cov.employed)
    urban_cov['log_population']=np.log1p(urban_cov.population)
    direct=urban[urban.has_DANE_individual_windows][['city_code','period','informality_rate']].rename(
        columns={'city_code':'dep_code','informality_rate':'target_latent_informal_rate'})
    train=urban_cov.merge(direct,on=['dep_code','period'],how='inner',validate='1:1')
    train=train[(train.year>=2007)&(train.year<=2025)].copy()
    train['eligible_for_model_validation']=train.year.ne(2020)
    train['target_is_official_monthly']=False
    train['label_definition']=np.where(train.year>=2021,'GEIH_NEW_LATENT',
                                      'DANE_T5_OLD_LATENT')
    # Department predictors reuse the same feature contract, but all their
    # informativeness comes from frozen DEPARTMENT labor, not city targets.
    dep=frame[['dep_code','period','year','month_sin','month_cos',
         'department_unemployment_rate','department_employment_rate',
         'department_participation_rate','employed','working_age','population',
         'cluster_descriptive_2007_2019']].copy()
    dep=dep.rename(columns={'department_unemployment_rate':'unemployment_rate',
           'department_employment_rate':'employment_rate',
           'department_participation_rate':'participation_rate'})
    dep['working_age_share']=dep.working_age/dep.population
    dep['log_employed']=np.log1p(dep.employed)
    dep['log_population']=np.log1p(dep.population)
    dep['target_latent_informal_rate']=np.nan
    dep['has_independent_informality_department_label']=False
    dep['cluster_requires_fold_refit']=True
    if train.target_latent_informal_rate.isna().any() or len(dep)!=33*N_MONTHS:
        raise ValueError('Supervised design lost expected rows')
    if set(train.dep_code.unique())!=set(urban[urban.has_DANE_individual_windows].city_code.unique()):
        raise ValueError('City label domains changed')
    return train,dep


def run(source_path:Path,city_path:Path,dep_path:Path,national_path:Path,
        recent_path:Path,anchors13_path:Path,output:Path,
        config_path:Path|None=None) -> dict:
    """Run the four sequential stages into an immutable experimental output."""
    policy=load_policy(config_path)
    inputs=[Path(p) for p in (source_path,city_path,dep_path,national_path,recent_path,anchors13_path)]
    if config_path is not None:inputs.append(Path(config_path))
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Experiment output already exists; refusing overwrite')
    hashes={p.name:_hash(p) for p in inputs}
    output.mkdir(parents=True,exist_ok=True)
    sources=pd.read_csv(source_path)
    cities=pd.read_csv(city_path)
    departments=pd.read_csv(dep_path)
    national_labor=pd.read_csv(national_path)
    recent=pd.read_csv(recent_path)
    anchors=pd.read_csv(anchors13_path)
    _check_labor(cities,national_labor)
    if not set(anchors.definition)>= {'hasta_5_trabajadores','hasta_10_trabajadores'}:
        raise ValueError('13-areas historical definitions lost')
    thirteen,agg,cv,win13=build_13(sources,cities,anchors,policy)
    _write(thirteen,output,'01_ciudades_13.csv')
    _write(agg,output,'01_anclas_agregado_13.csv')
    _write(cv,output,'01_validacion_13_anio_excluido.csv')
    _write(win13,output,'01_ventanas_13.csv')
    national,sensitivity,signal=build_national(thirteen,national_labor,sources,recent,anchors,policy)
    _write(national,output,'02_nacionales.csv')
    _write(sensitivity,output,'02_sensibilidad_puente_nacional.csv')
    _write(signal,output,'02_senal_agregada_13.csv')
    full,backcast,win23=build_23_and_33(thirteen,national,sources,cities,policy)
    _write(full[full.informality_source_stage != 'DONOR_INFERRED_TEN'],
           output,'03_ciudades_23.csv')
    _write(full,output,'03_ciudades_33.csv')
    _write(backcast,output,'03_catalogo_retro_y_donantes.csv')
    _write(win23,output,'03_auditoria_ventanas_fuente.csv')
    features,baseline,diagnostics=build_predictor_and_baseline(full,departments,national,cities,policy)
    if features[['urban_unemployment_rate','urban_employment_rate']].isna().any().any():
        raise ValueError('Urban predictor gap')
    _write(features,output,'04_panel_predictores_sin_etiqueta_departamental.csv')
    _write(baseline,output,'04_baseline_transferencia_urbana_no_calibrada.csv')
    _write(diagnostics,output,'04_diagnostico_base_vs_nacional.csv')
    calibrated,calib_diag=diagnostic_dual_calibration(baseline,departments,national)
    _write(calibrated,output,'05_calibracion_dual_contrafactual_no_canonica.csv')
    _write(calib_diag,output,'05_auditoria_intervencion_calibracion.csv')
    city_train,dept_infer=_supervised_design(full,features)
    _write(city_train,output,'04_entrenamiento_23_ciudades_etiquetas_latentes.csv')
    _write(dept_infer,output,'04_inferencia_33_departamentos_sin_etiquetas.csv')
    # The same temporal diagnostics used at the preceding quality gate.
    from icml.informality.quality_gate import _temporal
    fl,br=_temporal(full,'city_code','informality_rate',level='city')
    fn,bn=_temporal(national,'national_type','informality_rate_estimated',level='national')
    alerts=pd.concat([v for v in (fl,fn) if len(v)],ignore_index=True)
    breaks=pd.concat([v for v in (br,bn) if len(v)],ignore_index=True)
    _write(alerts,output,'AUDITORIA_SALTOS.csv')
    _write(breaks,output,'AUDITORIA_QUIEBRES.csv')
    for p in inputs:
        if _hash(p)!=hashes[p.name]:
            raise AssertionError(f'Frozen input changed: {p.name}')
    # Truly hard gates: complete, finite, bounded and accounting; separate
    # readiness gates are intentionally not allowed to silently pass.
    hard=[]
    for label,df,key,count in [('13',thirteen,'city_code',13),('33',full,'city_code',33),
                                ('NATIONAL',national,'national_type',2)]:
        if len(df)!=count*N_MONTHS or df.duplicated([key,'period']).any():
            hard.append(f'{label}: INCOMPLETE')
        if (df.informal_estimated+df.formal_estimated-df.employed_frozen).abs().max()>1e-5:
            hard.append(f'{label}: ACCOUNTING')
    if len(full[full.informality_source_stage=='NATIONAL_RETROPOLATED_SECOND_10'])!=10*N_MONTHS:
        hard.append('23-CITY: NOT REALLY NATIONAL RETROPOLATED')
    if len(full[full.informality_source_stage=='DONOR_INFERRED_TEN'])!=10*N_MONTHS:
        hard.append('33-CITY: MISSING DONOR TEN')
    if hard:raise AssertionError('; '.join(hard))
    dups=bool(features.duplicated(['dep_code','period']).any())
    if dups or len(features)!=33*N_MONTHS:raise AssertionError('Features not complete')
    mae_cv=float(cv.error_pp.abs().mean())
    gap_max=float(diagnostics.uncalibrated_gap_to_national_pp.abs().max())
    quality=pd.DataFrame([
        {'gate':'01_THIRTEEN_INDEPENDENT','result':'PASS','detail':f'13×404; LOYO MAE {mae_cv:.3f} pp at aggregate, not city'},
        {'gate':'02_NATIONAL_AFTER_13','result':'PASS','detail':'2×404; bridge transfer experimental'},
        {'gate':'03_TWENTY_THREE_AFTER_NATIONAL','result':'PASS','detail':'23×404; ten extended backward from national'},
        {'gate':'04_TEN_DONOR_SIGNALS','result':'PASS','detail':'33×404 including ten donor/synthetic signals'},
        {'gate':'05_LABOR_FIXED_AND_IDENTITIES','result':'PASS','detail':'Occupations not altered; all formality identities'},
        {'gate':'06_HISTORICAL_DEFINITION_BRIDGE','result':'WARN','detail':'T5/T10/new definitions not equivalent; no homogeneous official series before 2021'},
        {'gate':'07_MONTHLY_LATENT_REGULARITY','result':'WARN','detail':'Moving-window inversion can be unstable; quantify before publishing'},
        {'gate':'08_DEPARTMENT_MLP_VALIDATION','result':'BLOCK','detail':'No independent department informal labels/LOGO-validated MLP yet'},
        {'gate':'09_CALIBRATION_AND_POSTCLOSURE','result':'BLOCK','detail':f'Counterfactual dual calibration closes, but peak monthly rate intervention {calib_diag.max_abs_intervention_pp.max():.3f} pp; no department predictor validation'},
        {'gate':'10_HISTORICAL_OFFICIAL_ANCHORS_1993_2000','result':'WARN','detail':'No numerical DANE ENH city anchors recovered for early period'},
    ])
    _write(quality,output,'AUDITORIA_PUERTAS_SECUENCIA.csv')
    summary={'version':EXPERIMENT,'publication_status':'EXPERIMENTAL_NOT_CANONICAL',
       'stage_order':['13_city','national_after_13','23_city_using_national','33_signal_features_baseline'],
       'n_13':len(thirteen),'n_23':23*N_MONTHS,'n_33':len(full),'n_national':len(national),
       'n_predictor_rows':len(features),'n_city_training_rows':len(city_train),
       'calibration_counterfactual_max_intervention_pp':float(calib_diag.max_abs_intervention_pp.max()),
       'calibration_counterfactual_mean_monthly_intervention_pp':float(calib_diag.mean_abs_intervention_pp.mean()),
       'policy':dict(policy.__dict__),
       'n_department_inference_rows':len(dept_infer),
       'n_temporal_alerts':len(alerts),'n_break_candidates':len(breaks),
       'n_gt_200pct':int(alerts.greater_than_200pct_equiv.sum()) if len(alerts) else 0,
       'cv_13_aggregate_MAE_pp':mae_cv,
       'max_unadjusted_baseline_gap_pp':gap_max,'hard_gates_passed':True,
       'remaining_blockers':['independent_training_labels_and_cross_validation','postclosure_calibration'],
       'input_sha256':hashes,
       'output_sha256':{p.name:_hash(p) for p in sorted(output.glob('*.csv'))},
       'frozen_labor_verified':True}
    (output/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    return summary


def diagnostic_dual_calibration(baseline:pd.DataFrame, departments:pd.DataFrame,
                                national:pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Counterfactual postclosure: preserve E, reconcile two national *rates*.

    This intentionally tests the present equal-rate national-universe transfer
    assumption, not an official identity between DANE and ICML definitions.
    Using a constrained two-multiplier logit shift, not artificial rescaling
    of observed labor or claiming the output is a trained department model.
    """
    from scipy.optimize import root
    b=baseline[['dep_code','period','urban_transfer_baseline_rate']].merge(
        departments[['dep_code','period','employed','factor_employed']],
        on=['dep_code','period'],validate='1:1')
    alln=national.pivot(index='period',columns='national_type',
                        values=['informality_rate_estimated','employed_frozen'])
    results=[];diagnostics=[]
    for period,group in b.groupby('period',sort=True):
        group=group.sort_values('dep_code')
        e=group.employed.to_numpy(float)
        w=group.factor_employed.to_numpy(float)
        rate=group.urban_transfer_baseline_rate.to_numpy(float)
        y=logit(np.clip(rate,.00001,.99999))
        target_full=float(alln.loc[period,('informality_rate_estimated','ICML_COMPLETO')])
        target_rep=float(alln.loc[period,('informality_rate_estimated','DANE_REFERENCIA')])
        denom=e.sum(); denom_rep=float((e*w).sum())
        if denom<=0 or denom_rep<=0:raise ValueError('Missing calibration denominators')
        represented_target_occup=float(alln.loc[period,('employed_frozen','DANE_REFERENCIA')])
        # factor weights may differ from rounded DANE total by <= 1 person;
        # preserve exact frozen weighted denominator instead of changing E.
        has_official_reference=period>='2001-01'
        # represented sum >= DANE is correct (nine territories now contribute real capital).
        # Only fail if we fall below the reference.
        # Smoothed GEIH factors of the nine partial territories may leave the
        # weighted sum slightly below DANE (< 0.1 %); tolerate up to 2 %.
        if has_official_reference and denom_rep < represented_target_occup * 0.98:
            raise ValueError('Factor-based national occupation inconsistent')
        # 1993-2000 DANE_REFERENCIA is a historical reconstruction, NOT an
        # observed GEIH monthly margin. Factor=1 by construction; do not force
        # a false equality between two distinct historical reconstructed totals.
        has_two=bool(has_official_reference and np.ptp(w)>1e-8)
        if has_two:
            def objective(z):
                r=expit(y+z[0]+z[1]*w)
                return [(e*r).sum()/denom-target_full,
                        (e*w*r).sum()/denom_rep-target_rep]
            solution=root(objective,np.array([0.,0.]),method='hybr',tol=1e-11)
            if not solution.success and max(map(abs,objective(solution.x)))>1e-9:
                raise ValueError(f'No converged two-universe calibration at {period}')
            a,weight=float(solution.x[0]),float(solution.x[1])
        else:
            lo,hi=-30.,30.
            for _ in range(70):
                mid=(lo+hi)/2
                if np.dot(e,expit(y+mid))/denom<target_full:lo=mid
                else:hi=mid
            a=(lo+hi)/2;weight=0.
        new=expit(y+a+weight*w)
        residual_full=100*(np.dot(e,new)/denom-target_full)
        residual_repr=100*(np.dot(e*w,new)/denom_rep-target_rep) if has_official_reference else np.nan
        if abs(residual_full)>1e-6 or (has_official_reference and abs(residual_repr)>1e-6):
            raise AssertionError(f'Postclosure national mismatch: {period}')
        z=group[['period','dep_code','employed','factor_employed']].copy()
        z['rate_before']=rate
        z['rate_after_diagnostic']=new
        z['informal_diagnostic']=e*new
        z['formal_diagnostic']=e*(1-new)
        z['intervention_pp']=100*(new-rate)
        z['status']='COUNTERFACTUAL_CALIBRATION_NOT_FINAL_MODEL'
        results.append(z)
        diagnostics.append({'period':period,'icml_target_rate':target_full,
              'dane_reference_target_rate':target_rep,
              'pre_full_rate':float(np.dot(e,rate)/denom),
              'pre_repr_rate':float(np.dot(e*w,rate)/denom_rep),
              'post_full_residual_pp':residual_full,
              'post_repr_residual_pp':residual_repr,
              'max_abs_intervention_pp':float(np.max(abs(100*(new-rate)))),
              'mean_abs_intervention_pp':float(np.mean(abs(100*(new-rate)))),
              'dual_universe_constraint':has_two, 'dane_reference_comparable':has_official_reference,
              'note':'Assumes national ICML and DANE informality rates equal; NOT empirically validated'})
    return pd.concat(results,ignore_index=True),pd.DataFrame(diagnostics)
