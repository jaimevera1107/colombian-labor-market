"""Read-only transfer-domain gate for the experimental informality MLP.

The national closure is a *counterfactual cost diagnostic*, never a published
estimate. No department informality labels are created. No labor source changes.
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
from icml.domain.cutoff import N_MONTHS, ROWS_33

# Chosen from shared labor rates and calendar. Unlike the 92-column family,
# these features do not contain raw city/department size or city-domain totals.
TRANSFER_STABLE_FEATURES = (
    'year', 'month_sin', 'month_cos', 'pop_urban_pct', 'pop_rural_pct',
    'participation_rate', 'employment_rate', 'unemployment_rate',
    'inactivity_rate', 'national_unemployment_rate',
    'national_employment_rate', 'national_participation_rate',
    'unemployment_minus_national_pp', 'employment_minus_national_pp',
    'urban_unemployment_rate', 'urban_employment_rate',
    'urban_participation_rate', 'urban_minus_national_unemployment_pp',
    'urban_minus_national_employment_pp',
)
DEFINITIONS = {'OLD_T5_LATENT': 'T2016_2019', 'NEW_GEIH_LATENT': 'T2022_2025'}


def logit_shift_to_target(rates: np.ndarray, weights: np.ndarray,
                          target_rate: float) -> tuple[np.ndarray, float]:
    """Unique common log-odds shift satisfying one national weighted margin.

    This solves *only* an accounting constraint. Its magnitude is evidence of
    intervention, not evidence of department predictive accuracy.
    """
    r=np.asarray(rates,dtype=np.float64)
    w=np.asarray(weights,dtype=np.float64)
    if not (len(r)==len(w) and len(r)>0 and np.isfinite(r).all()
            and np.isfinite(w).all() and np.all((r>=0)&(r<=1))
            and np.all(w>0) and np.isfinite(target_rate) and 0<target_rate<1):
        raise ValueError('Invalid rates, positive weights, or target')
    r=np.clip(r,1e-8,1-1e-8)
    logodds=np.log(r)-np.log1p(-r)
    lo,hi=-100.,100.
    for _ in range(100):
        mid=(lo+hi)/2
        probs=1/(1+np.exp(-np.clip(logodds+mid,-700,700)))
        achieved=float(np.average(probs,weights=w))
        if achieved<target_rate:lo=mid
        else:hi=mid
    shift=(lo+hi)/2
    probs=1/(1+np.exp(-np.clip(logodds+shift,-700,700)))
    return probs,shift


def quality_shift_report(series: pd.DataFrame, targets: pd.DataFrame,
                         *,rate_col:str,model:str)->pd.DataFrame:
    """Compute monthly smallest *uniform-logit* intervention, no mutation."""
    x=series[['dep_code','period','employed',rate_col]].dropna().copy()
    if x.duplicated(['dep_code','period']).any():raise ValueError('Duplicate key')
    x=x.merge(targets[['period','informality_rate_estimated']],on='period',validate='m:1')
    rows=[]
    for period,g in x.groupby('period',sort=True):
        if len(g)!=33:raise ValueError('Every assessed period needs all 33 territories')
        rates=g[rate_col].to_numpy(float);w=g.employed.to_numpy(float)
        target=float(g.informality_rate_estimated.iloc[0])
        after,shift=logit_shift_to_target(rates,w,target)
        diff=100*(after-rates)
        rows.append({'period':period,'model':model,'target_rate':target,
           'raw_rate':float(np.average(rates,weights=w)),
           'gap_before_pp':100*(np.average(rates,weights=w)-target),
           'uniform_logit_shift':shift,
           'weighted_mean_abs_intervention_pp':float(np.average(abs(diff),weights=w)),
           'max_abs_intervention_pp':float(np.max(abs(diff))),
           'share_territories_gt_5pp':float(np.mean(abs(diff)>5)),
           'share_territories_gt_10pp':float(np.mean(abs(diff)>10)),
           'residual_after_pp':100*(np.average(after,weights=w)-target),
           'status':'COUNTERFACTUAL_NOT_A_PREDICTION'})
    return pd.DataFrame(rows)


def feature_domain_diagnostic(features_dir:Path,department:pd.DataFrame,
                               features:tuple[str,...])->pd.DataFrame:
    rows=[]
    for definition,name in [('OLD_T5_LATENT','04_training_full_fit_old_t5.csv'),
                            ('NEW_GEIH_LATENT','04_training_full_fit_new_geih.csv')]:
        city=pd.read_csv(features_dir/name,usecols=['period',*features])
        dept=department[department.period.isin(city.period.unique())]
        for col in features:
            source=city[col].to_numpy(float);target=dept[col].to_numpy(float)
            if not np.isfinite(source).all() or not np.isfinite(target).all():raise ValueError('Nonfinite feature '+col)
            low,high=np.quantile(source,[.01,.99]);scale=max(float(np.std(source)),1e-12)
            rows.append({'definition':definition,'feature':col,
               'city_p01':low,'city_p99':high,'city_std':scale,
               'department_outside_city_p01_p99_pct':100*float(np.mean((target<low)|(target>high))),
               'median_shift_city_std':float((np.median(target)-np.median(source))/scale),
               'test_window_same_calendar':True})
    return pd.DataFrame(rows)


def constrained_rural_test(dept:pd.DataFrame,baseline:pd.DataFrame,
                           targets:pd.DataFrame)->tuple[pd.DataFrame,pd.DataFrame]:
    """Falsifiable what-if; population rural share IS NOT rural employment share."""
    d=dept[['dep_code','period','employed','urban_employed','pop_rural_pct']].merge(
      baseline[['dep_code','period','urban_transfer_baseline_rate']],on=['dep_code','period'],validate='1:1')
    d=d.merge(targets[['period','informality_rate_estimated']],on='period',validate='m:1')
    d['city_employed_over_department']=d.urban_employed/d.employed
    d['invalid_city_subregion_assumption']=d.city_employed_over_department>1+1e-9
    r=d.urban_transfer_baseline_rate;rho=d.pop_rural_pct
    d['rural_high_max_contribution']=d.employed*(r+rho*(1-r))
    d['rural_city_baseline_contribution']=d.employed*r
    month=(d.groupby('period',as_index=False).agg(
         employed=('employed','sum'),national_max_people=('rural_high_max_contribution','sum'),
         baseline_people=('rural_city_baseline_contribution','sum'),
         invalid_urban_subregions=('invalid_city_subregion_assumption','sum')))
    month=month.merge(targets[['period','informality_rate_estimated']],on='period',validate='1:1')
    month['rural_high_max_rate']=month.national_max_people/month.employed
    month['baseline_rate']=month.baseline_people/month.employed
    month['national_above_rural_high_max']=month.informality_rate_estimated>month.rural_high_max_rate+1e-10
    month['missing_if_infeasible_pp']=100*np.maximum(month.informality_rate_estimated-month.rural_high_max_rate,0)
    month['assumption']='Population rural share proxies employment share; rural informality >= city; rural ceiling 100%. NOT observed decomposition.'
    return d[['dep_code','period','city_employed_over_department','invalid_city_subregion_assumption']],month


def cv_ridge_reference(features_dir:Path,departments:pd.DataFrame,
                       features:tuple[str,...])->tuple[pd.DataFrame,pd.DataFrame]:
    """Small domain-comparable reference, not a replacement for the residual MLP."""
    fold_cols=['fold_id','split','dep_code','period','label_definition','target_latent_informal_rate',*features]
    fold=pd.read_csv(features_dir/'04_fold_safe_training_validation.csv',usecols=fold_cols)
    result=[]
    for definition,suffix in DEFINITIONS.items():
        for fold_id in sorted(x for x in fold.fold_id.unique() if x.endswith(suffix)):
            sub=fold[(fold.fold_id==fold_id)&(fold.label_definition==definition)]
            train=sub[sub.split=='train'];test=sub[sub.split=='validation']
            if min(len(train),len(test))<20:raise ValueError('Insufficient heldout fold')
            model=make_pipeline(StandardScaler(),Ridge(alpha=10))
            model.fit(train[list(features)],train.target_latent_informal_rate)
            pred=np.clip(model.predict(test[list(features)]),0,1)
            err=abs(pred-test.target_latent_informal_rate.to_numpy(float))
            result.append({'fold_id':fold_id,'definition':definition,'model':'ridge_shared_rates',
                         'n_test':len(test),'mae_pp':100*float(np.mean(err)),
                         'p90_city_mape_pct':float(np.percentile(
                              (pd.DataFrame({'dep_code':test.dep_code.to_numpy(),
                                'ape':100*err/np.maximum(test.target_latent_informal_rate.to_numpy(float),1e-6)})
                               .groupby('dep_code').ape.mean()),90))})
    out=departments[['dep_code','period','employed']].copy()
    for definition,filename,col in [
        ('OLD_T5_LATENT','04_training_full_fit_old_t5.csv','candidate_old_rate'),
        ('NEW_GEIH_LATENT','04_training_full_fit_new_geih.csv','candidate_recent_rate')]:
        city=pd.read_csv(features_dir/filename,usecols=['target_latent_informal_rate',*features])
        model=make_pipeline(StandardScaler(),Ridge(alpha=10))
        model.fit(city[list(features)],city.target_latent_informal_rate)
        out[col]=np.clip(model.predict(departments[list(features)]),0,1)
    out['year']=out.period.str[:4].astype(int)
    out['candidate_rate_provisional']=np.where(out.year>=2021,out.candidate_recent_rate,out.candidate_old_rate)
    out.loc[out.year==2020,'candidate_rate_provisional']=np.nan
    return pd.DataFrame(result),out


def _sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()


def run(features_dir:Path, sequential_dir:Path,mlp_dir:Path,output:Path)->dict:
    """Reconstruct validation evidence; never rewrite historical artifacts."""
    features_dir=Path(features_dir);sequential_dir=Path(sequential_dir);mlp_dir=Path(mlp_dir);output=Path(output)
    if output.exists() and any(output.iterdir()):raise FileExistsError('Immutable output directory')
    path_dept=features_dir/'04_prediction_full_fit_33_departments.csv'
    path_nat=sequential_dir/'02_nacionales.csv'
    path_baseline=sequential_dir/'04_baseline_transferencia_urbana_no_calibrada.csv'
    path_mlp=mlp_dir/'05_department_predictions_EXPERIMENTAL.csv'
    feature_contract=json.loads((features_dir/'04_feature_contract.json').read_text())
    all_features=tuple(feature_contract['model_feature_columns'])
    if not set(TRANSFER_STABLE_FEATURES).issubset(all_features):raise ValueError('Feature contract incompatible')
    dept=pd.read_csv(path_dept); baseline=pd.read_csv(path_baseline)
    preds=pd.read_csv(path_mlp)
    nationals=pd.read_csv(path_nat)
    targets=nationals[nationals.national_type=='ICML_COMPLETO'][['period','informality_rate_estimated']]
    if (len(dept)!=ROWS_33 or len(preds)!=ROWS_33 or len(baseline)!=ROWS_33 or len(targets)!=N_MONTHS):
        raise ValueError('Unexpected canonical frozen labor coverage')
    if any(frame.duplicated(['dep_code','period']).any() for frame in (dept,baseline,preds)):
        raise ValueError('Duplicate territorial keys')
    if not np.allclose(dept.employed.to_numpy(float),
                       preds.employed.to_numpy(float),rtol=0,atol=1e-5):
        chk=dept[['dep_code','period','employed']].merge(preds[['dep_code','period','employed']],
            on=['dep_code','period'],validate='1:1',suffixes=('_base','_prediction'))
        if not np.allclose(chk.employed_base,chk.employed_prediction,rtol=0,atol=1e-5):
            raise ValueError('Frozen employment changed')
    domains=feature_domain_diagnostic(features_dir,dept,all_features)
    dratio,rural=constrained_rural_test(dept,baseline,targets)
    cv_ridge,ridge=cv_ridge_reference(features_dir,dept,TRANSFER_STABLE_FEATURES)
    base=baseline.rename(columns={'urban_transfer_baseline_rate':'candidate_rate_provisional'})
    mlp=preds
    closure=pd.concat([
        quality_shift_report(base,targets,rate_col='candidate_rate_provisional',model='urban_direct'),
        quality_shift_report(mlp,targets,rate_col='candidate_rate_provisional',model='residual_mlp_92'),
        quality_shift_report(ridge,targets,rate_col='candidate_rate_provisional',model='ridge_shared_rates_19')
    ],ignore_index=True)
    old_cv=pd.read_csv(mlp_dir/'05_urban_cross_validation.csv')
    comparisons=pd.concat([old_cv[old_cv.model.isin(['beta_nll','logit_huber','ridge_reference','train_city_mean'])][
              ['fold_id','definition','model','mae_pp','p90_group_mape_pct']],
              cv_ridge.rename(columns={'p90_city_mape_pct':'p90_group_mape_pct'})[
              ['fold_id','definition','model','mae_pp','p90_group_mape_pct']]],ignore_index=True)
    output.mkdir(parents=True,exist_ok=True)
    files={'feature_domain_shift':domains,'urban_subset_domain_violations':dratio,
           'rural_proxy_feasibility':rural,'ridge_shared_rates_cv':cv_ridge,
           'urban_model_cv_comparison':comparisons,'ridge_shared_rates_department_candidate':ridge,
           'national_closure_intervention_frontier':closure}
    for key,d in files.items():d.to_csv(output/f'06_{key}.csv',index=False,float_format='%.12g')
    summary={'status':'EXPERIMENTAL_NOT_CERTIFIED',
            'month_count':len(targets),'department_rows':len(dept),
            'urban_employed_greater_than_department_rows':int(dratio.invalid_city_subregion_assumption.sum()),
            'rural_proxy_national_infeasible_months':int(rural.national_above_rural_high_max.sum()),
            'rural_proxy_max_shortfall_pp':float(rural.missing_if_infeasible_pp.max()),
            'national_closure_by_model':{},'cv_summary':{},'feature_extremes':{}}
    for name,g in closure.groupby('model'):
        summary['national_closure_by_model'][name]={
              'max_gap_before_pp':float(g.gap_before_pp.abs().max()),
              'mean_abs_gap_before_pp':float(g.gap_before_pp.abs().mean()),
              'max_intervention_pp':float(g.max_abs_intervention_pp.max()),
              'share_months_max_intervention_gt10pp':float(np.mean(g.max_abs_intervention_pp>10)),
              'max_residual_post_pp':float(g.residual_after_pp.abs().max())}
    for (definition,model),g in comparisons.groupby(['definition','model']):
        summary['cv_summary'][f'{definition}/{model}']={'mae_pp':float(g.mae_pp.mean()),
              'p90_group_mape_pct':float(g.p90_group_mape_pct.mean())}
    for definition,g in domains.groupby('definition'):
        summary['feature_extremes'][definition]={
              'median_outside_city_p01_p99_pct':float(g.department_outside_city_p01_p99_pct.median()),
              'n_features_gt50pct_outside':int((g.department_outside_city_p01_p99_pct>50).sum())}
    # Identical input files can be replayed and independently verified.
    summary['input_sha256']={str(p.relative_to(p.parent.parent)): _sha(p) for p in (path_dept,path_nat,path_baseline,path_mlp)}
    summary['input_sha256']['feature_contract']=_sha(features_dir/'04_feature_contract.json')
    (output/'06_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf8')
    (output/'06_quality_gate.csv').write_text(
       'gate,status,reason\n'
       'FROZEN_EMPLOYMENT,PASS,No labor baseline changed\n'
       'CITY_SUBREGION_ASSUMPTION,BLOCKED,Some city employed exceeds department\n'
       'RURAL_SHARE_APPROXIMATION,BLOCKED,Population share not equivalent to employment share\n'
       'GEOGRAPHIC_CV,WARN,Urban latent labels only\n'
       'NATIONAL_TARGET_INDEPENDENCE,WARN,Historic national reconstructed from urban signals\n'
       'DEPARTMENT_TRUTH,NOT_AVAILABLE,No independent departmental informal labels\n'
       'POSTCLOSURE_G6,BLOCKED,Closure diagnostics cannot validate department prediction\n'
       'PUBLISH_INFORMALITY,BLOCKED,Definitions and transfer not certified\n',encoding='utf8')
    manifest={p.name:_sha(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    return summary
