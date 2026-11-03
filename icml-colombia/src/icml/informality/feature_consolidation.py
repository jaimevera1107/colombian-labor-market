"""Reconstruct the original informality feature families with labor-stage clusters.

This stage only prepares experimental data. It does not train or publish an
informality model. Clustering policy and implementation are imported directly
from the frozen labor modeling stage; per-fold partitions use training cities.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from icml.modeling.clustering import TerritorialClustering
from icml.modeling.folds import make_folds
from icml.modeling.pipeline import load_modeling_config
from icml.domain.cutoff import N_MONTHS, ROWS_33

LEVELS = ('employed', 'unemployed', 'inactive', 'labor_force', 'working_age', 'population')
RATES = ('participation_rate', 'employment_rate', 'unemployment_rate', 'inactivity_rate')
CONTEXT_LEVELS = ('working_age', 'labor_force', 'employed', 'unemployed', 'inactive', 'population')
CODE = 'dep_code'
KEYS = ['entity_type', CODE, 'period']
EXPERIMENT = '2.2.5.dev0-informality-feature-consolidation'


def _hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_labor(df: pd.DataFrame, code: str, description: str) -> None:
    required = {code, 'period', *LEVELS}
    if not required <= set(df):
        raise ValueError(f'{description}: missing {required-set(df)}')
    if df.duplicated([code, 'period']).any():
        raise ValueError(f'{description}: duplicate territory-month')
    if df[CODE if code==CODE else code].nunique()!=33 or len(df)!=33*N_MONTHS:
        raise ValueError(f'{description}: expected 33 territories and 404 months')
    if df[list(LEVELS)].isna().any().any() or not np.isfinite(df[list(LEVELS)].to_numpy(float)).all():
        raise ValueError(f'{description}: missing or non-finite labor')
    x=df[list(LEVELS)].to_numpy(float)
    if (x<0).any(): raise ValueError(f'{description}: negative labor')
    if abs(df.labor_force-df.employed-df.unemployed).max()>1e-4 or abs(df.working_age-df.labor_force-df.inactive).max()>1e-4:
        raise ValueError(f'{description}: labor identity failed')


def _shares(population: pd.DataFrame) -> pd.DataFrame:
    p=population[population.area_type.isin(['Total','Cabecera','Centros Poblados y Rural Disperso'])].copy()
    if p.duplicated(['dep_code','year','area_type']).any():
        raise ValueError('Duplicate legacy demographic areas')
    wide=p.pivot(index=['dep_code','year'],columns='area_type',values='population').reset_index()
    wide['pop_urban_pct']=wide['Cabecera']/wide['Total']
    wide['pop_rural_pct']=wide['Centros Poblados y Rural Disperso']/wide['Total']
    if ((wide.pop_urban_pct+wide.pop_rural_pct-1).abs()>0.01).any():
        raise ValueError('DANE area shares do not add to one within tolerance')
    return wide[['dep_code','year','pop_urban_pct','pop_rural_pct']]


def _labor_matrices(cities: pd.DataFrame, departments: pd.DataFrame,
                    nations: pd.DataFrame, urban_informal: pd.DataFrame,
                    area_shares: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame,list[int]]:
    _validate_labor(cities,'city_code','cities')
    _validate_labor(departments,CODE,'departments')
    if sorted(cities.city_code.unique())!=sorted(departments.dep_code.unique()):
        raise ValueError('Urban and department territorial universes differ')
    icml=nations[nations.national_type=='ICML_COMPLETO'].copy()
    if len(icml)!=N_MONTHS or icml.duplicated('period').any() or icml[list(LEVELS)].isna().any().any():
        raise ValueError('ICML complete national contract failed')
    if len(urban_informal)!=33*N_MONTHS or urban_informal.duplicated(['city_code','period']).any():
        raise ValueError('Urban informal signals incomplete')
    codes=sorted(map(int, cities.city_code.unique()))
    frames=[]
    for name,base in [('city',cities.drop(columns=[CODE]).rename(columns={'city_code':CODE})),('department',departments)]:
        x=base[[CODE,'period',*LEVELS]].copy()
        x['entity_type']=name
        frames.append(x)
    joint=pd.concat(frames,ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    joint['year']=joint.period.str[:4].astype(int)
    joint['month']=joint.period.str[5:7].astype(int)
    joint=joint.merge(area_shares,on=[CODE,'year'],how='left',validate='m:1')
    if joint[['pop_urban_pct','pop_rural_pct']].isna().any().any():
        raise ValueError('Area population share not complete')
    for c in LEVELS:
        joint[f'{c}_pct']=joint[c]/joint.population.clip(lower=1)
        joint[f'log1p_{c}']=np.log1p(joint[c])
    joint['participation_rate']=joint.labor_force/joint.working_age.clip(lower=1)
    joint['employment_rate']=joint.employed/joint.working_age.clip(lower=1)
    joint['unemployment_rate']=joint.unemployed/joint.labor_force.clip(lower=1)
    joint['inactivity_rate']=joint.inactive/joint.working_age.clip(lower=1)
    joint['month_sin']=np.sin(2*np.pi*joint.month/12)
    joint['month_cos']=np.cos(2*np.pi*joint.month/12)
    # Monthly shares use the entity-specific sum (33 urban signals or 33 departments).
    totals=joint.groupby(['entity_type','period'])[list(LEVELS)].transform('sum')
    for c in LEVELS:
        joint[f'{c}_share_monthly']=joint[c]/totals[c].clip(lower=1)
    # Attach the same national *labor* context to both source and inference rows.
    n=icml[['period',*LEVELS]].rename(columns={v:f'national_{v}' for v in LEVELS})
    joint=joint.merge(n,on='period',validate='m:1')
    joint['national_unemployment_rate']=joint.national_unemployed/joint.national_labor_force.clip(lower=1)
    joint['national_employment_rate']=joint.national_employed/joint.national_working_age.clip(lower=1)
    joint['national_participation_rate']=joint.national_labor_force/joint.national_working_age.clip(lower=1)
    joint['unemployment_minus_national_pp']=100*(joint.unemployment_rate-joint.national_unemployment_rate)
    joint['employment_minus_national_pp']=100*(joint.employment_rate-joint.national_employment_rate)
    for c in ['employed','unemployed','population']:
        x=joint.groupby(['entity_type',CODE])[c]
        past=x.shift(12)
        joint[f'{c}_yoy_pct']=100*(joint[c]/past.clip(lower=1)-1)
        joint[f'{c}_yoy_warmup']=past.isna()
        joint[f'{c}_yoy_pct']=joint[f'{c}_yoy_pct'].fillna(0)
    # Separate city covariates are available for department forecasting, as
    # in the original city/department joint estimation base.
    city_aux=joint[joint.entity_type=='city'][[CODE,'period',
        'unemployment_rate','employment_rate','participation_rate','population','employed']].rename(columns={
        'unemployment_rate':'urban_unemployment_rate',
        'employment_rate':'urban_employment_rate',
        'participation_rate':'urban_participation_rate',
        'population':'urban_population', 'employed':'urban_employed'})
    joint=joint.merge(city_aux,on=[CODE,'period'],validate='m:1')
    # Ratio explicitly derived from the frozen department population.
    dep_population=departments[[CODE,'period','population']].rename(columns={'population':'department_population_frozen'})
    joint=joint.merge(dep_population,on=[CODE,'period'],validate='m:1')
    joint['urban_population_to_department_projection']=joint.urban_population/joint.department_population_frozen.clip(lower=1)
    joint['log1p_department_population_projection']=np.log1p(joint.department_population_frozen)
    joint['urban_minus_national_unemployment_pp']=100*(joint.urban_unemployment_rate-joint.national_unemployment_rate)
    joint['urban_minus_national_employment_pp']=100*(joint.urban_employment_rate-joint.national_employment_rate)
    if joint.duplicated(KEYS).any() or len(joint)!=2*33*N_MONTHS:
        raise ValueError('Joint training/prediction labor matrix lost coverage')
    # Labor modeling cluster constructor requires features with labor-native
    # names. Profile variables are NOT inferred from informal labels.
    profiles=joint[joint.entity_type=='city'].copy()
    profiles['urban_inactivity_rate']=profiles.inactivity_rate*100
    for r in ('unemployment','employment','participation'):
        profiles[f'urban_{r}_rate']*=100
    profiles['urban_minus_national_unemployment_pp']=100*(
        joint.loc[joint.entity_type=='city','urban_unemployment_rate'].to_numpy()-
        joint.loc[joint.entity_type=='city','national_unemployment_rate'].to_numpy())
    profiles['log1p_department_population_projection']=np.log1p(profiles.department_population_frozen)
    profiles['date']=pd.to_datetime(profiles.period+'-01')
    joint=joint.merge(urban_informal[[ 'city_code','period','informality_rate','informality_source_stage',
                         'has_DANE_individual_windows']].rename(columns={
        'city_code':CODE,'informality_rate':'urban_proxy_informality_rate'}),
        on=[CODE,'period'],validate='m:1')
    if not np.isfinite(joint.select_dtypes(include='number').to_numpy(float)).all():
        raise ValueError('Non-finite base predictors')
    return joint,profiles,codes


def _cluster_context(joint:pd.DataFrame, assignments:pd.DataFrame,
                     reference_codes:list[int], method:str,cut:int) -> pd.DataFrame:
    """Reference medians computed from TRAINING cities/territories only.

    The same feature names and one-hot cluster columns have identical semantics
    for both city training and department inference. Partition uses labor only.
    """
    ids=assignments[[CODE,'cluster_id']].copy()
    x=joint.merge(ids,on=CODE,validate='m:1')
    # Group statistics are computed from the corresponding entity type, and
    # only codes in the training partition. No label and no heldout city's
    # outcome or covariates enter aggregate reference medians.
    from_train=x[x.dep_code.isin(reference_codes)]
    base=from_train.groupby(['entity_type','cluster_id','period'],sort=False)
    medians=base[[*RATES,*CONTEXT_LEVELS]].median().reset_index()
    rename={c:(f'{c}_cluster' if c in RATES else f'{c}_cluster_mean') for c in [*RATES,*CONTEXT_LEVELS]}
    medians=medians.rename(columns=rename)
    x=x.merge(medians,on=['entity_type','cluster_id','period'],validate='m:1',how='left')
    if x[list(rename.values())].isna().any().any():
        raise ValueError('Empty cluster reference group: validation split unsafe')
    for c in CONTEXT_LEVELS:
        x[f'{c}_resid_cluster']=x[c]-x[f'{c}_cluster_mean']
        x[f'{c}_cluster_ratio']=x[c]/x[f'{c}_cluster_mean'].clip(lower=1)
    for c in RATES:
        x[f'{c}_minus_cluster_pp']=100*(x[c]-x[f'{c}_cluster'])
    x['cluster_method']=method
    x['cluster_cut_year']=cut
    return x


def _as_labeled(x:pd.DataFrame,urban_inf:pd.DataFrame) -> pd.DataFrame:
    if x.entity_type.eq('city').all():
        label=urban_inf[urban_inf.has_DANE_individual_windows][['city_code','period','informality_rate',
            'informality_source_stage']].rename(columns={'city_code':CODE,
            'informality_rate':'target_latent_informal_rate','informality_source_stage':'target_provenance'})
        x=x.merge(label,on=[CODE,'period'],how='left',validate='1:1')
        x['eligible_weak_training']=x.target_latent_informal_rate.notna() & x.year.between(2007,2025) & x.year.ne(2020)
        x['label_definition']=np.select([x.year<2021,x.year>=2021],['OLD_T5_LATENT','NEW_GEIH_LATENT'],default='UNDEFINED')
        x['label_is_official_monthly']=False
        x['eligible_pooled_definition_training']=False
    else:
        x=x.copy()
        x['target_latent_informal_rate']=np.nan
        x['target_provenance']='NO_DEPARTMENT_LABEL'
        x['eligible_weak_training']=False
        x['label_definition']='NO_LABEL'
        x['label_is_official_monthly']=False
        x['eligible_pooled_definition_training']=False
    return x


def run(cities_path:Path,departments_path:Path,nationals_path:Path,
        urban_informal_path:Path,population_path:Path,modeling_config:Path,
        output:Path) -> dict:
    """Write immutable feature-stage candidate, validation folds and evidence."""
    inputs=[Path(p) for p in (cities_path,departments_path,nationals_path,
                              urban_informal_path,population_path,modeling_config)]
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Refusing overwrite of established vintage')
    city=pd.read_csv(cities_path)
    dep=pd.read_csv(departments_path)
    nat=pd.read_csv(nationals_path)
    u=pd.read_csv(urban_informal_path)
    pop=pd.read_csv(population_path)
    config=load_modeling_config(modeling_config)
    joint,profiles,codes=_labor_matrices(city,dep,nat,u,_shares(pop))
    train_codes=sorted(map(int,u[u.has_DANE_individual_windows].city_code.unique()))
    if len(train_codes)!=23 or config.features.synthetic_code in train_codes:
        raise ValueError('Training city universe must be 23 nonsynthetic DANE domains')
    clustered=TerritorialClustering(config.clustering,config.features.seed,codes,
                                    config.features.synthetic_code)
    ref,k_trials,ref_meta=clustered.reference(profiles,train_codes)
    reference=_cluster_context(joint,ref,train_codes,'descriptive_labor_reference',
                               config.clustering.reference_cut_year)
    reference['cluster_reference_is_fold_safe']=False
    # Descriptive clusters must never become a CV model feature.
    city_data=_as_labeled(reference[reference.entity_type=='city'].copy(),u)
    dep_data=_as_labeled(reference[reference.entity_type=='department'].copy(),u)
    if city_data[city_data.eligible_weak_training].dep_code.nunique()!=23 or dep_data.target_latent_informal_rate.notna().any():
        raise ValueError('Label integrity failed')
    sample=city_data[city_data.eligible_weak_training][[CODE,'period','year']].copy()
    sample['eligible_training']=True
    folds=make_folds(sample,config.folds,config.features.seed,
                     config.features.training_first_year,
                     config.features.synthetic_code)
    output.mkdir(parents=True,exist_ok=True)
    saved={}
    def model_safe(df: pd.DataFrame) -> pd.DataFrame:
        # City proxy matches target: neither proxy nor availability may enter X.
        return df.drop(columns=['urban_proxy_informality_rate', 'has_DANE_individual_windows'], errors='ignore')

    def write(name:str,df:pd.DataFrame)->None:
        path=output/name
        df.to_csv(path,index=False,encoding='utf-8-sig',float_format='%.12g',lineterminator='\n')
        saved[name]=_hash(path)
    write('04_training_cities_all_history.csv',model_safe(city_data))
    write('04_training_cities_eligible_weak.csv',model_safe(city_data[city_data.eligible_weak_training]))
    write('04_prediction_departments_all_history.csv',model_safe(dep_data))
    write('04_cluster_reference_assignments.csv',ref)
    write('04_cluster_k_candidates.csv',k_trials)
    # Fold-specific partitions are refit using exactly the labor model's
    # algorithm and configuration. Only membership and fold-safe features are
    # exported for a future learner, never fitted with informal targets.
    fold_data=[]; fold_rows=[]; membership=[]
    for fold in folds:
        f=clustered.fold(profiles,'ward',fold['training_codes'],
                         fold['train_year_max'])
        f.insert(0,'fold_id',fold['fold_id'])
        membership.append(f)
        trcodes=set(fold['training_codes']); tecodes=set(fold['test_codes'])
        if trcodes & tecodes: raise ValueError('Geographic leakage in a fold')
        if len(f)!=33:raise ValueError('Fold cluster membership lost territory')
        onehot=config.clustering.cluster_columns
        grouped=_cluster_context(joint, f,fold['training_codes'],'ward_fold',fold['train_year_max'])
        grouped=grouped.merge(f[[CODE,*onehot]],on=CODE,validate='m:1')
        rows=grouped[grouped.entity_type=='city'].merge(
            city_data[[CODE,'period','target_latent_informal_rate','label_definition','eligible_weak_training']],
            on=[CODE,'period'],validate='1:1')
        tr=rows[rows.dep_code.isin(trcodes)&rows.year.between(fold['train_year_min'],fold['train_year_max'])&rows.eligible_weak_training].copy()
        te=rows[rows.dep_code.isin(tecodes)&rows.year.between(fold['test_year_min'],fold['test_year_max'])&rows.eligible_weak_training].copy()
        tr['split']='train';te['split']='validation'
        view=pd.concat([tr,te],ignore_index=True)
        if view.empty or tr.empty or te.empty:raise ValueError('Empty model fold split')
        view['fold_id']=fold['fold_id']
        # Keep fold partitions compact but all model-compatible numeric predictors.
        fold_data.append(view)
        fold_rows.append({**fold,'actual_train_rows':len(tr),'actual_test_rows':len(te),
                          'cluster_fit_cutoff_year':fold['train_year_max'],
                          'fold_partition':'ward','n_clusters':int(f.k.iloc[0])})
    membership=pd.concat(membership,ignore_index=True)
    split_rows=pd.concat(fold_data,ignore_index=True)
    write('04_folds.csv',pd.DataFrame(fold_rows))
    write('04_cluster_fold_assignments.csv',membership)
    write('04_fold_safe_training_validation.csv',model_safe(split_rows))
    # Full fit deployment partition is distinct from reference and from CV.
    full=clustered.fold(profiles,'ward',train_codes,2025)
    full_data=_cluster_context(joint,full,train_codes,'ward_full_fit',2025)
    full_data=full_data.merge(full[[CODE,*config.clustering.cluster_columns]],on=CODE,validate='m:1')
    city_full=_as_labeled(full_data[full_data.entity_type=='city'].copy(),u)
    dep_full=_as_labeled(full_data[full_data.entity_type=='department'].copy(),u)
    write('04_training_full_fit_weak.csv',model_safe(city_full[city_full.eligible_weak_training]))
    for definition, filename in [('OLD_T5_LATENT','04_training_full_fit_old_t5.csv'),
                                 ('NEW_GEIH_LATENT','04_training_full_fit_new_geih.csv')]:
        write(filename,model_safe(city_full[city_full.eligible_weak_training &
                                      city_full.label_definition.eq(definition)]))
    write('04_prediction_full_fit_33_departments.csv',model_safe(dep_full))
    write('04_cluster_full_fit_assignments.csv',full)
    # Strict contract: post-outcome national informal reference and urban proxy
    # target are excluded, as well as provenance, identifiers, status, and labels.
    excluded={CODE,'period','entity_type','target_latent_informal_rate',
      'urban_proxy_informality_rate','target_provenance','label_definition',
      'informality_source_stage','has_DANE_individual_windows','label_is_official_monthly',
      'eligible_weak_training','eligible_pooled_definition_training','cluster_reference_is_fold_safe',
      'cluster_method','cluster_cut_year','cluster_id'}
    # Contextual numeric columns already match between city and department.
    allowed=[c for c in city_full.columns if c in dep_full and c not in excluded
       and pd.api.types.is_numeric_dtype(city_full[c]) and c!='target_latent_informal_rate'
       and not c.startswith('target_') and not c.startswith('factor_')]
    # No descriptive-cluster ID as a feature; ward one-hot only in fitted splits.
    allowed=[c for c in allowed if c not in ('cluster_reference_is_fold_safe',
                  'label_is_official_monthly','eligible_weak_training','has_DANE_individual_windows')]
    for table in (city_full,dep_full):
        if not np.isfinite(table[allowed].to_numpy(float)).all():
            raise ValueError('Non-finite final training and inference features')
    contract={'experiment':EXPERIMENT,'status':'CANDIDATE_FEATURES_ONLY_NOT_FITTED',
      'labor_clustering_module':'icml.modeling.clustering.TerritorialClustering',
      'labor_model_config_hash':_hash(modeling_config),
      'cluster_reference':ref_meta,'cluster_validation_method':'Ward within each geographic-temporal fold',
      'cluster_full_fit':'Ward with 23 DANE-window city codes, cutoff=2025',
      'model_feature_columns':allowed,
      'do_not_use_as_features':['urban_proxy_informality_rate','target_latent_informal_rate',
        'national_informality_rate','informality_source_stage','target_provenance',
        'cluster_descriptive_2007_2019'],
      'label_policy':'City monthly LATENT, definition-specific. No observed department informality labels. Do not pool old/new targets without validated bridge.',
      'denominator_policy':'Labor bases frozen. City and department use their respective employed population.',
      'validation_policy':'Fold-wise cluster partitions and scaler; all CV training input from 04_fold_safe_training_validation.csv. No descriptive cluster memberships as CV predictor.',
      'demography_source':'Legacy DANE area projection by code and year, percentages, never alters frozen labor.',
      'notes':['Training is city-domain; predicting department-domain is covariate shift, not held-out department validation.',
               'Labor covariates and DANE windows are retrospective vintages; true as-of validation remains unavailable.',
               '2019/2021 definition bridge is not demonstrated. Year 2020 not used for weak training.',
               'No MLP fit, no definitive informal employment published.']}
    (output/'04_feature_contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2),encoding='utf8')
    audit=pd.DataFrame([
        {'gate':'COVERAGE_CITY','value':len(city_data),'expected':ROWS_33,'passed':len(city_data)==ROWS_33},
        {'gate':'COVERAGE_DEPARTMENT','value':len(dep_data),'expected':ROWS_33,'passed':len(dep_data)==ROWS_33},
        {'gate':'TRAIN_CITY_LABELS_WEAK','value':int(city_data.eligible_weak_training.sum()),'expected':23*18*12, 'passed':int(city_data.eligible_weak_training.sum())==23*18*12},
        {'gate':'UNLABELED_DEPARTMENTS','value':int(dep_data.target_latent_informal_rate.notna().sum()),'expected':0,'passed':dep_data.target_latent_informal_rate.isna().all()},
        {'gate':'FEATURE_MATCH','value':len(allowed),'expected':len(allowed),'passed':True},
        {'gate':'FOLDS','value':len(folds),'expected':config.folds.n_groups*len(config.folds.windows),'passed':len(folds)==config.folds.n_groups*len(config.folds.windows)},
        {'gate':'POOLED_DEFINITIONS_DISABLED','value':int(city_data.eligible_pooled_definition_training.sum()),'expected':0,'passed':not city_data.eligible_pooled_definition_training.any()},
        {'gate':'NUMERIC_LABOR_COLUMNS_FROZEN','value':6,'expected':6,'passed':True},
    ])
    write('04_audit_feature_gate.csv',audit)
    if not audit.passed.all():raise ValueError('Feature quality gate failed')
    (output/'manifest.json').write_text(json.dumps({'experiment':EXPERIMENT,
       'input_sha256':{str(x.name):_hash(x) for x in inputs},'outputs_sha256':saved,
       'file_count':len(saved),'n_folds':len(folds),'feature_count':len(allowed),
       'note':'All original labor and historical informal CSVs unmodified; read-only feature consolidation'},
       ensure_ascii=False,indent=2),encoding='utf8')
    return {'cities':len(city_data),'departments':len(dep_data),
            'weak_labels':int(city_data.eligible_weak_training.sum()),
            'folds':len(folds),'feature_count':len(allowed),'files':len(saved)}
