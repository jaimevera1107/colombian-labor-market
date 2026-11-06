"""Reproducible isolated experiment of the author's original informal MLP.

All labels are *latent urban reconstructions*. No departmental truth is used.
The experiment is deliberately distinct from `icml run` and cannot publish
canonical departmental informal employment.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from icml.informality.mlp import MLPConfig, MLPInformality, group_p90_mape
from icml.domain.cutoff import N_MONTHS

STRATA={'OLD_T5_LATENT':'T2016_2019','NEW_GEIH_LATENT':'T2022_2025'}
PROTOCOL='2.2.6.dev0-mlp-original-architecture-corrected'


def sha256(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(y:np.ndarray,p:np.ndarray,groups:np.ndarray)->dict:
    return {'mae_pp':float(100*np.mean(np.abs(y-p))),
            'rmse_pp':float(100*np.sqrt(np.mean((y-p)**2))),
            'p90_group_mape_pct':group_p90_mape(y,p,groups),
            'max_abs_error_pp':float(100*np.max(np.abs(y-p)))}


def inner_split(df:pd.DataFrame,definition:str)->tuple[pd.DataFrame,pd.DataFrame]:
    """Strict train-city-only split; do not use geographic outer fold for stopping."""
    maxyear=int(df.year.max())
    if definition=='OLD_T5_LATENT':
        inner=df[df.year==maxyear]
        core=df[df.year<maxyear]
    else:
        # Recent GEIH in 2021 is all that T2022 fold exposes to the model.
        inner=df[(df.year==maxyear)&(df.month>=10)]
        core=df[(df.year<maxyear)|((df.year==maxyear)&(df.month<10))]
    if len(inner)<30 or len(core)<100:
        raise ValueError(f'No defensible inner time split: {definition}, {len(core)}+{len(inner)}')
    return core,inner


def _run_impl(features_folder:Path,output:Path,max_folds_per_definition:int=5,
        epochs:int=120)->dict:
    """Fit on existing fold-safe Ward data; preserve all upstream artifacts."""
    features_folder=Path(features_folder);output=Path(output)
    if output.exists() and any(output.iterdir()):raise FileExistsError('Immutable experiment output already exists')
    contract=json.loads((features_folder/'04_feature_contract.json').read_text())
    features=tuple(contract['model_feature_columns'])
    expected=92
    if len(features)!=expected:raise ValueError(f'Unexpected feature count: {len(features)}')
    if set(features)&set(contract['do_not_use_as_features']):raise ValueError('Target leakage in features')
    usecols=['fold_id','split','dep_code','period','year','month','target_latent_informal_rate',
             'label_definition',*features]
    folds=pd.read_csv(features_folder/'04_fold_safe_training_validation.csv',usecols=list(dict.fromkeys(usecols)))
    if folds[list(features)].isna().any().any():raise ValueError('Missing predictor in a fold')
    old_count=int(folds.label_definition.eq('OLD_T5_LATENT').sum())
    if old_count<=0:raise ValueError('Missing historical labels')
    # Neither this table nor the full-fit tables have official monthly outcomes.
    eval_rows=[];prediction_rows=[];best_loss={}
    for definition,period_suffix in STRATA.items():
        selected=sorted(f for f in folds.fold_id.unique() if f.endswith(period_suffix))[:max_folds_per_definition]
        if not selected:raise ValueError(f'No matching fold for {definition}')
        allscores=[]
        for fold_name in selected:
            part=folds[(folds.fold_id==fold_name)&(folds.label_definition==definition)]
            tr=part[part.split=='train'].copy();te=part[part.split=='validation'].copy()
            if min(len(tr),len(te))<40:raise ValueError(f'Insufficient rows in {fold_name}')
            tr0,vi=inner_split(tr,definition)
            yy=te.target_latent_informal_rate.to_numpy(float)
            group=te.dep_code.to_numpy()
            xcols=list(features)
            # No true urban direct-transfer baseline can be evaluated here:
            # it is IDENTICAL to the city target supplied to the model.
            naive=np.repeat(float(tr0.target_latent_informal_rate.mean()),len(te))
            ridge=make_pipeline(StandardScaler(),Ridge(alpha=10.))
            ridge.fit(tr0[xcols],tr0.target_latent_informal_rate)
            ridge_pred=np.clip(ridge.predict(te[xcols]),0,1)
            for name,p in [('train_city_mean',naive),('ridge_reference',ridge_pred)]:
                mm=metrics(yy,p,group)
                eval_rows.append({'fold_id':fold_name,'definition':definition,'model':name,
                                  'n_train':len(tr),'n_test':len(te),**mm})
                allscores.append((name,mm['p90_group_mape_pct']))
            for loss_name in ('beta_nll','logit_huber'):
                config=MLPConfig(feature_cols=features,loss_type=loss_name,
                          epochs=epochs,seed=42,patience=15)
                trained=MLPInformality(config).fit(tr0,vi)
                # Refit on outer training only with epochs selected internally;
                # outer holdout was never used to choose epochs.
                final=MLPInformality(config).fit(tr,fixed_epochs=max(1,trained.best_epoch))
                pred=final.predict(te)
                mm=metrics(yy,pred,group)
                eval_rows.append({'fold_id':fold_name,'definition':definition,'model':loss_name,
                    'n_train':len(tr),'n_test':len(te),'inner_best_epoch':trained.best_epoch,**mm})
                allscores.append((loss_name,mm['p90_group_mape_pct']))
                for code,date,truth,estimate in zip(te.dep_code,te.period,yy,pred):
                    prediction_rows.append({'fold_id':fold_name,'definition':definition,
                        'model':loss_name,'dep_code':code,'period':date,
                        'latent_urban_target':truth,'prediction':estimate})
        # aggregate fold comparison, not a claim of independent monthly labels
        frame=pd.DataFrame([r for r in eval_rows if r['definition']==definition])
        scores=frame.groupby('model').agg({'p90_group_mape_pct':'mean','mae_pp':'mean'})
        # choose model within model family, never silently substitute ridge.
        best_loss[definition]=min(['beta_nll','logit_huber'],
                      key=lambda key:float(scores.loc[key,'p90_group_mape_pct']))
    output.mkdir(parents=True)
    report=pd.DataFrame(eval_rows)
    report.to_csv(output/'05_urban_cross_validation.csv',index=False,float_format='%.10g',lineterminator='\n')
    pd.DataFrame(prediction_rows).to_csv(output/'05_heldout_urban_predictions.csv',index=False,float_format='%.10g',lineterminator='\n')
    # Fit artifact from 2007–2019 OR 2021–2025, strictly disjoint definitions.
    fit_meta={}
    dept=pd.read_csv(features_folder/'04_prediction_full_fit_33_departments.csv',
                     usecols=['dep_code','period','employed',*features])
    # years/month are in features; a single full history has 13,332 rows
    if len(dept)!=33*N_MONTHS or dept[['dep_code','period']].duplicated().any():
        raise ValueError('Wrong frozen department grid')
    results=dept[['dep_code','period','employed']].copy()
    for definition,file_name in [('OLD_T5_LATENT','04_training_full_fit_old_t5.csv'),
                                  ('NEW_GEIH_LATENT','04_training_full_fit_new_geih.csv')]:
        inp=pd.read_csv(features_folder/file_name,
                        usecols=['dep_code','period','year','month','target_latent_informal_rate',*features])
        cfg=MLPConfig(feature_cols=features,loss_type=best_loss[definition],epochs=epochs,
                      seed=42,patience=15)
        base,inner=inner_split(inp,definition)
        choose=MLPInformality(cfg).fit(base,inner)
        final=MLPInformality(cfg).fit(inp,fixed_epochs=max(1,choose.best_epoch))
        col='candidate_old_rate' if definition=='OLD_T5_LATENT' else 'candidate_recent_rate'
        results[col]=final.predict(dept)
        target_dir=output/'models'/definition
        final.export(target_dir)
        fit_meta[definition]={**final.metadata(), 'inner_selection_epochs':choose.best_epoch,
                         'training_rows':len(inp),'target_period':f'{inp.period.min()} to {inp.period.max()}',
                         'mean_target':float(inp.target_latent_informal_rate.mean())}
    # This is an EXTRAPOLATION, not a published joined time series. 2020
    # also has no comparable definition and is deliberately kept separate.
    results['year']=results.period.str.slice(0,4).astype(int)
    results['candidate_rate_provisional']=np.where(results.year>=2021,
         results.candidate_recent_rate,results.candidate_old_rate)
    results['candidate_informal_people_provisional']=results.employed*results.candidate_rate_provisional
    results['candidate_formal_people_provisional']=results.employed-results.candidate_informal_people_provisional
    results['candidate_definition']=np.select([results.year<=2019,results.year==2020,results.year>=2021],
       ['OLD_T5_EXTRAPOLATION','NO_2020_BRIDGE','NEW_GEIH_EXTRAPOLATION'],default='UNDEFINED')
    # Never expose a fabricated homogeneous 2020 or bridged 1993+ series
    # as a usable product: 2020 candidate explicitly masked.
    results.loc[results.year==2020,['candidate_rate_provisional',
             'candidate_informal_people_provisional','candidate_formal_people_provisional']]=np.nan
    results.to_csv(output/'05_department_predictions_EXPERIMENTAL.csv',index=False,float_format='%.12g',lineterminator='\n')
    # Extrapolation risk: standardized department covariate values far from
    # training city sample, across all 92 input dimensions.
    drift=[]
    for definition,filename in [('OLD_T5_LATENT','04_training_full_fit_old_t5.csv'),
                                ('NEW_GEIH_LATENT','04_training_full_fit_new_geih.csv')]:
        tr=pd.read_csv(features_folder/filename,usecols=list(features))
        scaler=StandardScaler().fit(tr[list(features)].to_numpy(float))
        z=np.abs(scaler.transform(dept[list(features)].to_numpy(float)))
        drift.append({'definition':definition,'percent_rows_any_abs_z_gt_4':float(100*np.mean((z>4).any(axis=1))),
                      'percent_cells_abs_z_gt_4':float(100*np.mean(z>4)),
                      'max_abs_z':float(np.nanmax(z))})
    pd.DataFrame(drift).to_csv(output/'05_transfer_feature_drift.csv',index=False,lineterminator='\n')
    summary=report.groupby(['definition','model'],as_index=False)[['mae_pp','rmse_pp','p90_group_mape_pct']].mean()
    summary.to_csv(output/'05_cv_summary.csv',index=False,float_format='%.10g',lineterminator='\n')
    manifest={'experiment':PROTOCOL,'status':'EXPERIMENTAL_NOT_CERTIFIED',
          'strata_models':best_loss,'model_metadata':fit_meta,'cross_validation_folds':len(report.fold_id.unique()),
          'label_warning':'Latent urban rates, not observed monthly outcomes',
          'benchmark_warning':'Do NOT compare predicted cities to their own urban proxy as baseline: identical to label',
          'domain_shift_warning':'City to department has no observed target for definitive validation',
          '2020_warning':'Undefined definition bridge, canonical prediction deliberately null for 2020',
          'evaluation_warning':'Retrospective covariates may use future-vintage reconstruction; not as-of validation',
          'source_sha256':{n:sha256(features_folder/n) for n in
                  ('04_feature_contract.json','04_fold_safe_training_validation.csv',
                  '04_training_full_fit_old_t5.csv','04_training_full_fit_new_geih.csv',
                  '04_prediction_full_fit_33_departments.csv')},
          'outputs_sha256':{p.name:sha256(p) for p in output.glob('*.csv')}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    return {'n_folds':len(report.fold_id.unique()),'n_predictions':len(results),
            'best_loss':best_loss,'results':summary.to_dict(orient='records')}


def run(features_folder:Path,output:Path,max_folds_per_definition:int=5,
        epochs:int=120)->dict:
    """Atomically promote a completed experiment; never publish partial folds."""
    output=Path(output)
    staging=output.with_name(output.name+'._in_progress')
    if output.exists() or staging.exists():
        raise FileExistsError('Existing output or unfinished experiment: inspect first')
    result=_run_impl(features_folder,staging,max_folds_per_definition,epochs)
    staging.rename(output)
    return result
