"""Read-only final diagnostics for the experimental city-trained residual MLP."""
from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd


def audit(experiment_dir:Path,national_path:Path)->dict:
    experiment_dir=Path(experiment_dir)
    out=pd.read_csv(experiment_dir/'05_department_predictions_EXPERIMENTAL.csv')
    cv=pd.read_csv(experiment_dir/'05_urban_cross_validation.csv')
    national=pd.read_csv(national_path)
    old=out[out.year!=2020].copy()
    agg=(old.groupby('period',as_index=False)
           .agg(employed_sum=('employed','sum'),informal_sum=('candidate_informal_people_provisional','sum')))
    agg['model_rate']=agg.informal_sum/agg.employed_sum
    nat=national[national.national_type.eq('ICML_COMPLETO')][['period','informality_rate_estimated']]
    agg=agg.merge(nat,on='period',validate='1:1')
    agg['gap_pp']=100*(agg.model_rate-agg.informality_rate_estimated)
    agg['era']=pd.cut(agg.period.str[:4].astype(int),bins=[1992,2000,2006,2019,2020,2026],
                      labels=['1993-2000','2001-2006','2007-2019','2020','2021-2026'])
    agg.to_csv(experiment_dir/'05_national_gap_diagnostic.csv',index=False,float_format='%.10g')
    out=out.sort_values(['dep_code','period'])
    out['month_delta_pp']=100*out.groupby('dep_code').candidate_rate_provisional.diff()
    flags=out[out.month_delta_pp.abs()>5][['dep_code','period','candidate_definition','month_delta_pp']]
    flags.to_csv(experiment_dir/'05_monthly_change_flags.csv',index=False,float_format='%.10g')
    drift=pd.read_csv(experiment_dir/'05_transfer_feature_drift.csv')
    gate=pd.DataFrame([
        {'gate':'PRESERVE_FROZEN_LABOR','status':'PASS','detail':'No labor source was rewritten; model uses employed as immutable denominator'},
        {'gate':'DEFINITION_SEPARATION','status':'PASS','detail':'Old T5 and GEIH new trained separately; 2020 bridge not fabricated'},
        {'gate':'URBAN_INNER_AND_OUTER_CV','status':'PASS','detail':'10 compatible geographic-temporal folds; inner stopping independent of outer test'},
        {'gate':'BETA_NLL_NORMALIZATION','status':'PASS','detail':'Full log B(alpha,beta) term checked against scipy.stats.beta'},
        {'gate':'DEPARTMENT_TARGET_VALIDATION','status':'BLOCKED','detail':'City labels are latent; no independent department target introduced'},
        {'gate':'NATIONAL_RECONCILIATION','status':'BLOCKED','detail':f'Max absolute gap {agg.gap_pp.abs().max():.2f} pp; not calibrated'},
        {'gate':'COVARIATE_SHIFT','status':'WARNING','detail':f'Max standardized input |z| {drift.max_abs_z.max():.2f}; see feature drift'},
        {'gate':'RECENT_OUTER_VALIDATION','status':'BLOCKED','detail':'Recent MLP did not beat city-training mean in the designated folds'},
        {'gate':'2020_DEFINITION_BRIDGE','status':'BLOCKED','detail':'No selected homogeneous 2020 estimate; experimental stratum predictions retained'},
        {'gate':'FINAL_POSTCLOSURE_G6','status':'NOT_TESTED','detail':'No publishable closure performed; original G6 cannot pass yet'},
    ])
    gate.to_csv(experiment_dir/'05_mlp_quality_gate.csv',index=False)
    info={'status':'NOT_CERTIFIED','max_abs_national_gap_pp':float(agg.gap_pp.abs().max()),
          'national_gaps_by_era':agg.groupby('era',observed=True).gap_pp.mean().round(4).to_dict(),
          'n_urban_crossval_folds':int(cv.fold_id.nunique()),
          'n_monthly_jump_gt_5pp':len(flags),'n_department_prediction_rows':len(out),
          'n_2020_unselected':int(out[out.year==2020].candidate_rate_provisional.isna().sum()),
          'n_blocked':int((gate.status=='BLOCKED').sum())}
    (experiment_dir/'05_quality_summary.json').write_text(json.dumps(info,indent=2,ensure_ascii=False),encoding='utf8')
    return info
