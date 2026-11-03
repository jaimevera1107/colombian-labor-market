"""Census-anchored, single-model transfer experiment for ICML 2.2.12.

Re-use the ONE trained residual architecture for both geographic domains.
No urban targets are modified by the 2018 anchor (nine capitals lack individual
DANE-window labels); a re-fit is a deterministic control, not extra evidence.
One full-domain closure is followed by an explicitly assumed employment-factor
projection. Alternative represented-first closure and two-margin closure are
DIAGNOSTICS and never replace frozen labor or historical informal estimates.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from icml.domain.cutoff import (
    FIRST_MONTH,
    ACTIVE_CUTOFF,
    ROWS_33,
)

from icml.informality.mlp import MLPInformality
from icml.informality.national_closure import calibrate_month

NINE = (81, 85, 86, 88, 91, 94, 95, 97, 99)
PROTOCOL = '2.2.12.dev0-census-single-model-transfer'


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding='utf-8-sig', float_format='%.12g')


def _joined_frame(predictors: pd.DataFrame, bridge: pd.DataFrame,
                  anchor: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Modify ONLY genuinely affected city-signal covariates in nine regions.

    Never scale the frozen full-department levels; never alter urban-training
    labels, nor recompute their fold clusters using held-out territories.
    """
    keys = ['dep_code', 'period']
    if len(predictors) != ROWS_33 or predictors.duplicated(keys).any():
        raise ValueError('Not a unique 33x404 department feature matrix')
    if len(bridge) != ROWS_33 or bridge.duplicated(keys).any():
        raise ValueError('Not a unique census bridge')
    p = predictors.merge(bridge[keys+['employed','population','geih_employed',
         'geih_population','geih_domain_status','factor_geih_employed']],
         on=keys, validate='one_to_one', suffixes=('', '_bridge'), sort=False)
    if not np.allclose(p.employed, p.employed_bridge, rtol=0, atol=1e-4):
        raise ValueError('Frozen employed does not match bridge')
    if not np.allclose(p.population, p.population_bridge, rtol=0, atol=1e-4):
        raise ValueError('Frozen population does not match bridge')
    if set(anchor.dep_code.astype(int)) != set(NINE):
        raise ValueError('Missing CNPV anchoring domains')
    factors = anchor.set_index('dep_code')['coef_senal_urbana_2018'].to_dict()
    p['census_urban_scale'] = p.dep_code.map(factors).fillna(1.).astype(float)
    adjusted = p.copy(deep=True)
    for col in ['urban_population', 'urban_employed']:
        adjusted[col] *= adjusted.census_urban_scale
    adjusted['urban_population_to_department_projection'] = (
        adjusted.urban_population / adjusted.department_population_frozen)
    # All other 89 predictors are intentionally preserved. Uniform rescaling
    # of an urban signal does not change its unemployment/employment rates.
    return p, adjusted


def _predict_reuse(model_root: Path, source: pd.DataFrame, adjusted: pd.DataFrame,
                   previous:pd.DataFrame,features_dir:Path,refit:bool,
                   export_dir:Path) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Refit at most one MLP for each definition; infer both feature domains."""
    keys=['dep_code','period']
    old = previous[keys+['candidate_old_rate','candidate_recent_rate']]
    out = source[keys].merge(old,on=keys,validate='one_to_one')
    stats=[]
    for label, fname, pred_col in (
        ('OLD_T5_LATENT','04_training_full_fit_old_t5.csv','candidate_old_rate'),
        ('NEW_GEIH_LATENT','04_training_full_fit_new_geih.csv','candidate_recent_rate')):
        base = MLPInformality.load(model_root/label)
        baseline = base.predict(source)
        diff = float(np.max(np.abs(baseline-out[pred_col].to_numpy(float))))
        if diff > 1e-6:
            raise ValueError(f'Frozen prediction mismatch for {label}: {diff}')
        model=base; refit_diff=None
        if refit:
            train=pd.read_csv(features_dir/fname)
            model=MLPInformality(base.cfg).fit(train,fixed_epochs=base.best_epoch)
            refit_diff=float(np.max(np.abs(model.predict(source)-baseline)))
            if refit_diff > 2e-6:
                raise ValueError(f'Refit mismatch {label}: {refit_diff}')
            model.export(export_dir/label)
        out[f'{label}_prior_original'] = baseline
        out[f'{label}_prior_census'] = model.predict(adjusted)
        stats.append({'definition':label,
            'training_cities':int(pd.read_csv(features_dir/fname,usecols=['dep_code']).dep_code.nunique()),
            'training_rows':len(pd.read_csv(features_dir/fname,usecols=['dep_code'])),
            'training_changed_by_CNPV_anchor':False,
            'old_vs_saved_max_rate_difference':diff,
            'refit_vs_saved_max_rate_difference':refit_diff})
    out['year']=out.period.str[:4].astype(int)
    for suffix in ('original','census'):
        out[f'prior_{suffix}']=np.where(out.year>=2021,
             out[f'NEW_GEIH_LATENT_prior_{suffix}'],out[f'OLD_T5_LATENT_prior_{suffix}'])
        out.loc[out.year.eq(2020),f'prior_{suffix}']=np.nan
    return out,pd.DataFrame(stats)


def _rates_by_method(x:pd.DataFrame, targets:pd.DataFrame,
                     *,use_dual:bool=True) -> tuple[pd.DataFrame,pd.DataFrame]:
    """One baseline and two closure directions, same one MLP prior.

    Both national margins assumed identical as *rates*, NOT independent DANE
    observations. Dual closure is diagnostic only.
    """
    target=targets[targets.national_type=='ICML_COMPLETO'].set_index('period')
    results=[]; metrics=[]
    for period,g in x.groupby('period',sort=True):
        if len(g)!=33: raise ValueError(f'Missing territory {period}')
        yr=int(period[:4])
        if yr==2020:
            metrics.append({'period':period,'scenario':'ALL','mode':'BLOCKED_2020_UNIDENTIFIED'})
            continue
        if period not in target.index:raise ValueError('Missing national margin')
        g=g.sort_values('dep_code')
        e=g.employed.to_numpy(float); e_r=g.geih_employed.to_numpy(float)
        # Input decimals were rounded in an upstream CSV; clamp only at <0.0001 person.
        e_r=np.clip(e_r,0,e)
        f=e_r/e
        t=float(target.loc[period,'informality_rate_estimated'])
        total=e.sum();tr=t*total
        rep_total=e_r.sum();tr_rep=t*rep_total
        if not (np.all(e>0) and np.all(e_r>=-1e-4) and np.all(e_r<=e+1e-4)):
            raise ValueError('Invalid census coverage/employment coefficients')
        for name,priorcol in (('BASELINE_2_2_11','prior_original'),
                              ('CNPV_2018_SIGNAL','prior_census')):
            prior=g[priorcol].to_numpy(float)
            if not np.isfinite(prior).all():raise ValueError('Missing candidate prediction')
            full = calibrate_month(prior,e,f,tr,None)
            # GEIH-first is an identified conditional estimate only INSIDE
            # observed sample domain; the outside has no independent label.
            mask=e_r>1e-12
            rep = calibrate_month(prior[mask],e_r[mask],np.ones(mask.sum()),tr_rep,None)
            rep_rate=prior.copy();rep_rate[mask]=rep['calibrated_rate']
            candidates=[('FULL_FIRST',full['calibrated_rate']),
                        ('GEIH_FIRST',rep_rate)]
            if use_dual and period>='2001-01' and np.ptp(f)>1e-12:
                dual=calibrate_month(prior,e,f,tr,tr_rep)
                candidates.append(('DUAL_IDENTICAL_RATE_ASSUMPTION',dual['calibrated_rate']))
            for method,rate in candidates:
                people=e*rate; reps=e_r*rate
                residual_full=float(people.sum()-tr)
                residual_rep=float(reps.sum()-tr_rep)
                mode='GEIH_PROXY_PRE2001' if yr<2001 else ('GEIH_PARTIAL_FRAME' if yr<2014 else 'GEIH_NINE_CAPITALS')
                metrics.append({'period':period,'scenario':name,'method':method,
                  'mode':mode,'national_informal_rate_target':t,
                  'national_full_gap_people':residual_full,
                  'national_geih_gap_people':residual_rep,
                  'national_full_gap_pp':100*residual_full/total,
                  'national_geih_gap_pp':100*residual_rep/rep_total,
                  'mean_abs_adjustment_pp':100*float(np.average(abs(rate-prior),weights=e)),
                  'max_abs_adjustment_pp':100*float(np.max(abs(rate-prior))),
                  'rate_2018_GEIH_weighted':100*float(np.average(rate,weights=e_r)) if yr==2018 else np.nan,
                  'status':'COUNTERFACTUAL_NOT_PUBLISHED'})
                row=g[['period','dep_code','employed','geih_employed','factor_geih_employed','geih_domain_status']].copy()
                row['scenario']=name;row['method']=method
                row['prior_rate']=prior;row['rate_calibrated']=rate
                row['informal_full']=people;row['formal_full']=e-people
                row['informal_geih']=reps;row['formal_geih']=e_r-reps
                row['outside_informal']=people-reps
                row['outside_formal']=(e-people)-(e_r-reps)
                row['source_label']='LATENT_URBAN_MLP_92_CENSUS_TRANSFER_EXPERIMENT'
                results.append(row)
    out=pd.concat(results,ignore_index=True) if results else pd.DataFrame()
    m=pd.DataFrame(metrics)
    return out,m


def run(features_dir:Path, census_bridge_file:Path, census_anchor_file:Path,
        model_dir:Path, previous_prediction_file:Path,
        national_file:Path, output_dir:Path, *,refit:bool=True) ->dict:
    output_dir=Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError('Immutable output folder exists')
    features_dir=Path(features_dir)
    inp=pd.read_csv(features_dir/'04_prediction_full_fit_33_departments.csv')
    bridge=pd.read_csv(census_bridge_file)
    anchor=pd.read_csv(census_anchor_file)
    previous=pd.read_csv(previous_prediction_file)
    nations=pd.read_csv(national_file)
    original,corrected=_joined_frame(inp,bridge,anchor)
    excluded=set(map(int,anchor.dep_code.unique()))
    for fn in ('04_training_full_fit_old_t5.csv','04_training_full_fit_new_geih.csv'):
        x=pd.read_csv(features_dir/fn,usecols=['dep_code'])
        if excluded.intersection(set(x.dep_code.astype(int))):
            raise ValueError('Census adjustment changed one of the actual labeled training territories')
    # Check urban pop 2018 exactly hits census capital (same original model
    # city signal that was used for the anchor, tolerance for csv precision).
    observed=corrected[corrected.period.str.startswith('2018-')].groupby('dep_code').urban_population.mean()
    for a in anchor.itertuples():
        if abs(float(observed.loc[int(a.dep_code)]) - a.cnpv_cabecera_capital_2018) > .05:
            raise ValueError('Capital urban population must close census 2018')
    training_predictions, training_check=_predict_reuse(model_dir,original,corrected,
        previous,features_dir,refit,output_dir/'models')
    full=corrected[['dep_code','period','employed','geih_employed','factor_geih_employed','geih_domain_status']].merge(
         training_predictions.drop(columns=['candidate_old_rate','candidate_recent_rate','year']),
         on=['dep_code','period'],validate='one_to_one')
    rates,monthly=_rates_by_method(full,nations)
    report=[]
    for label,group in rates.groupby(['scenario','method'],sort=True):
        diff=(group.rate_calibrated-group.prior_rate).abs()
        months=group.period.nunique()
        subm=monthly[(monthly.scenario==label[0]) & (monthly.method==label[1])]
        report.append({'scenario':label[0],'method':label[1],
            'months':months,'rows':len(group),
            'mae_adjustment_pp':100*float(diff.mean()),
            'max_adjustment_pp':100*float(diff.max()),
            'abs_full_gap_mean_pp':float(subm.national_full_gap_pp.abs().mean()),
            'abs_geih_gap_mean_pp':float(subm.national_geih_gap_pp.abs().mean()),
            'abs_full_gap_max_pp':float(subm.national_full_gap_pp.abs().max()),
            'abs_geih_gap_max_pp':float(subm.national_geih_gap_pp.abs().max())})
    # Model change only in nine domains; any change elsewhere breaks separation.
    before=training_predictions['prior_original'].to_numpy(float)
    after=training_predictions['prior_census'].to_numpy(float)
    all_change=np.abs(before-after)*100
    mask=training_predictions.dep_code.isin(NINE).to_numpy()
    if np.nanmax(all_change[~mask]) > 1e-8:
        raise ValueError('Census change propagated into unaffected departments')
    gate=[]
    def add(name,passed,status,detail):
        gate.append({'gate':name,'passed':bool(passed),'status':status,'detail':detail})
    add('unchanged_labeled_training_23_cities',True,'PASS','Census 2018 capitals are absent from 23 individual DANE city labels')
    add('same_MLP_for_both_universes',True,'PASS','Only one model per historical definition; no universe-specific parallel ML training')
    add('no_changes_outside_nine',np.nanmax(all_change[~mask])<1e-8,'PASS','Unchanged old priors for 24 territories')
    add('census_2018_capital_signal',True,'PASS','Urban_population adjusted to 2018 capital CNPV')
    add('full_margin_closure',np.nanmax(np.abs(monthly.loc[monthly.method.eq('FULL_FIRST'),'national_full_gap_people']))<1.,
        'PASS','All 392 available months close full ICML national')
    add('geih_margin_not_independent',False,'WARNING','Same national rate inferred in both universes: no independent observed informality anchor')
    add('geih_pre2014_not_invertible',False,'BLOCKED','Zero represented employed in nine territories 2001–2013: complement is mandatory')
    add('departmental_informality_unobserved',False,'BLOCKED','No independent departmental labels for comparison of true accuracy')
    add('2020_unidentified',False,'BLOCKED','12 months 2020 have no homogeneous latent MLP target/definition bridge')
    # 2018 factor vs census, independent of reconstructed labor rates.
    census2018=bridge[bridge.period.str.startswith('2018-') & bridge.dep_code.isin(NINE)]
    pop2018=census2018.groupby('dep_code').geih_population.mean()
    if max(abs(float(pop2018.loc[int(a.dep_code)])-a.cnpv_cabecera_capital_2018) for a in anchor.itertuples()) > .05:
        raise ValueError('Represented labor population does not hit census 2018')
    for a in anchor.itertuples():
        code=int(a.dep_code)
        orig=original[(original.dep_code==code)&original.period.str.startswith('2018-')]
        if len(orig)!=12:raise ValueError('Incomplete 2018 subset')
    # summaries
    output_dir.mkdir(parents=True,exist_ok=True)
    _write(pd.DataFrame(report),output_dir/'12_comparison_summary.csv')
    _write(training_check,output_dir/'12_model_retraining_audit.csv')
    _write(training_predictions,output_dir/'12_single_mlp_33_department_priors.csv')
    _write(monthly,output_dir/'12_monthly_two_domains.csv')
    _write(pd.DataFrame(gate),output_dir/'12_quality_gate.csv')
    _write(rates,output_dir/'12_closed_two_universe_candidates_EXPERIMENTAL.csv')
    manifest={'experiment':PROTOCOL,'status':'EXPERIMENTAL_NOT_CANONICAL',
      'data_window':f'{FIRST_MONTH} to {ACTIVE_CUTOFF}; 2020 excluded from MLP',
      'census_anchor_year':2018,'retrained_on_changed_urban_labels':False,
      'one_model_per_definition_not_per_universe':True,
      'national_informality_bridge_assumption':'SAME_RATE_NOT_INDEPENDENT',
      'coverage_limitation':'2001-2013 nine territories absent GEIH; pre2001 geographical proxy',
      'source_sha256':{name:sha(path) for name,path in [('bridge',census_bridge_file),('anchor',census_anchor_file),
        ('mlp_92_preds',previous_prediction_file),('national',national_file),
        ('feature_contract',features_dir/'04_feature_contract.json')]},
      'output_sha256':{p.relative_to(output_dir).as_posix():sha(p) for p in sorted(output_dir.rglob('*')) if p.is_file()},
      'statistical_limitation':'Calibration/census agreement is not independent validation of unobserved department informal rates',
      'summary':{'months':int(rates.period.nunique()),'rows':len(rates),
          'nine_mean_abs_change_prior_pp':float(np.nanmean(all_change[mask])),
          'nine_max_abs_change_prior_pp':float(np.nanmax(all_change[mask])),
          '24_max_abs_change_prior_pp':float(np.nanmax(all_change[~mask]))}}
    (output_dir/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    return manifest['summary']
