"""Pilot: residual MLP on only domain-comparable labor features.

This is an ablation of INPUT DOMAIN (not a valid final architecture selection).
It never fits national labels, does not alter frozen labor, and cannot certify
unobserved departmental informal employment.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

from icml.informality.mlp import MLPConfig, MLPInformality, group_p90_mape
from icml.informality.mlp_experiment import inner_split
from icml.informality.transfer_review import (TRANSFER_STABLE_FEATURES,
    DEFINITIONS, quality_shift_report)


def run(features_dir:Path, sequential_dir:Path,output:Path,
        *,folds_per_definition:int=2,epochs:int=55)->dict:
    features_dir=Path(features_dir);sequential_dir=Path(sequential_dir);output=Path(output)
    if output.exists() and any(output.iterdir()):raise FileExistsError('Immutable pilot exists')
    features=list(TRANSFER_STABLE_FEATURES)
    fields=['fold_id','split','dep_code','period','year','month',
            'label_definition','target_latent_informal_rate',*features]
    fold=pd.read_csv(features_dir/'04_fold_safe_training_validation.csv',usecols=list(dict.fromkeys(fields)))
    rows=[];fit_info={}
    for definition,suffix in DEFINITIONS.items():
        names=sorted(x for x in fold.fold_id.unique() if x.endswith(suffix))[:folds_per_definition]
        for name in names:
            sub=fold[(fold.fold_id==name)&(fold.label_definition==definition)]
            tr=sub[sub.split=='train'];te=sub[sub.split=='validation']
            inside,v=inner_split(tr,definition)
            cfg=MLPConfig(feature_cols=tuple(features),epochs=epochs,
                    loss_type='beta_nll',patience=12,seed=42)
            chosen=MLPInformality(cfg).fit(inside,v)
            final=MLPInformality(cfg).fit(tr,fixed_epochs=max(1,chosen.best_epoch))
            p=final.predict(te)
            y=te.target_latent_informal_rate.to_numpy(float)
            rows.append({'definition':definition,'fold_id':name,'model':'residual_beta_shared_rates_19',
                'n_test':len(y),'selected_epochs':chosen.best_epoch,
                'mae_pp':100*np.mean(abs(y-p)),
                'p90_group_mape_pct':group_p90_mape(y,p,te.dep_code.to_numpy())})
    dept=pd.read_csv(features_dir/'04_prediction_full_fit_33_departments.csv',usecols=list(dict.fromkeys(
            ['dep_code','period','employed',*features])))
    prediction=dept[['dep_code','period','employed']].copy()
    for definition,filename,col in [
        ('OLD_T5_LATENT','04_training_full_fit_old_t5.csv','candidate_old_rate'),
        ('NEW_GEIH_LATENT','04_training_full_fit_new_geih.csv','candidate_recent_rate')]:
        tr=pd.read_csv(features_dir/filename,usecols=list(dict.fromkeys(
            ['dep_code','period','year','month','target_latent_informal_rate',*features])))
        core,iv=inner_split(tr,definition)
        cfg=MLPConfig(feature_cols=tuple(features),epochs=epochs,
            loss_type='beta_nll',patience=12,seed=42)
        choose=MLPInformality(cfg).fit(core,iv)
        final=MLPInformality(cfg).fit(tr,fixed_epochs=max(1,choose.best_epoch))
        prediction[col]=final.predict(dept)
        fit_info[definition]={'best_epochs':choose.best_epoch,'n_training_rows':len(tr)}
        final.export(output/'models'/definition)
    prediction['year']=prediction.period.str[:4].astype(int)
    prediction['candidate_rate_provisional']=np.where(prediction.year>=2021,
       prediction.candidate_recent_rate,prediction.candidate_old_rate)
    prediction.loc[prediction.year==2020,'candidate_rate_provisional']=np.nan
    nat=pd.read_csv(sequential_dir/'02_nacionales.csv')
    targets=nat[nat.national_type=='ICML_COMPLETO'][['period','informality_rate_estimated']]
    closure=quality_shift_report(prediction,targets,rate_col='candidate_rate_provisional',
                                model='residual_mlp_shared_rates_19')
    output.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(output/'07_pilot_spatial_cv.csv',index=False,float_format='%.12g',lineterminator='\n')
    prediction.to_csv(output/'07_pilot_department_predictions_EXPERIMENTAL.csv',index=False,float_format='%.12g',lineterminator='\n')
    closure.to_csv(output/'07_pilot_national_gap_and_closure_DIAGNOSTIC.csv',index=False,float_format='%.12g',lineterminator='\n')
    report={'status':'PILOT_NOT_CERTIFIED','epochs_cap':epochs,'n_folds':len(rows),
            'features':list(TRANSFER_STABLE_FEATURES),
            'cv':pd.DataFrame(rows).groupby('definition').mae_pp.mean().to_dict(),
            'national_mean_abs_gap_pp':float(closure.gap_before_pp.abs().mean()),
            'national_max_abs_gap_pp':float(closure.gap_before_pp.abs().max()),
            'max_counterfactual_intervention_pp':float(closure.max_abs_intervention_pp.max()),
            'fit_info':fit_info}
    (output/'07_summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    hashlist={p.relative_to(output).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob('*')) if p.is_file()}
    (output/'manifest.json').write_text(json.dumps(hashlist,indent=2),encoding='utf8')
    return report
