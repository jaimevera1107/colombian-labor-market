"""Read-only sensitivity study: national definition bridge and KL territorial transfer.

The design preserves each frozen territorial employed count and both explicitly
modelled national employment universes. All national informality targets are
experimental; no comparison to them proves territorial predictive accuracy.
2020 reconstructions are retrospective diagnostic gap-fillers, not observed DANE.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from .national_closure import calibrate_month, InfeasibleClosure
from .urban_backcast import _national_historical
from icml.domain.cutoff import ROWS_NATIONAL

CANDIDATES = ('urban_direct', 'mlp_residual_92', 'mlp_shared19')
PROXY_STRENGTHS = (0.0, 0.5, 1.0)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bridge_scenarios(cities13: pd.DataFrame, national_labor: pd.DataFrame,
                     source: pd.DataFrame, recent: pd.DataFrame,
                     anchors: pd.DataFrame) -> pd.DataFrame:
    """Recompute the genuine DANE-only 13-area to national bridge at 3 weights."""
    chunks = []
    for strength in PROXY_STRENGTHS:
        nat, _, _ = _national_historical(cities13, national_labor, source,
                                         recent, anchors, strength=strength)
        if nat[['period', 'national_type']].duplicated().any():
            raise ValueError('Duplicate national target')
        nat = nat.copy()
        nat['scenario'] = f'proxy_strength_{strength:g}'
        chunks.append(nat)
    base = chunks[1]
    # Only counterfactual variation; keep 2021+ official-window-derived rates unchanged.
    for sign in (-1, 1):
        shock = base.copy()
        shock['scenario'] = f'stress_2020_{"minus" if sign < 0 else "plus"}_2pp'
        mask = shock.period.str.startswith('2020-')
        months = shock.loc[mask, 'period'].str[-2:].astype(int).to_numpy()
        # zero at Jan/Dec, max absolute two pp in Jun/Jul; no forced endpoints.
        triangle = 1 - np.abs((months - 1) - 5.5) / 5.5
        original = shock.loc[mask, 'informality_rate_estimated'].to_numpy(float)
        rate = np.clip(original + sign * .02 * triangle, 1e-5, 1-1e-5)
        shock.loc[mask, 'informality_rate_estimated'] = rate
        shock.loc[mask, 'informal_estimated'] = shock.loc[mask, 'employed_frozen'].to_numpy(float) * rate
        shock.loc[mask, 'formal_estimated'] = shock.loc[mask, 'employed_frozen'].to_numpy(float) * (1-rate)
        shock.loc[mask, 'provenance'] = 'SENSITIVITY_ONLY_NOT_DANE_DATA'
        chunks.append(shock)
    # Explicitly stress the SAME-RATE assumption across statistical universes.
    # This is not a claimed DANE observation or an estimate of the missing rate.
    for sign in (-1, 1):
        diff=base.copy()
        diff['scenario']=f'stress_dane_domain_{"minus" if sign<0 else "plus"}_025pp'
        mask=(diff.national_type=='DANE_REFERENCIA') & diff.period.between('2001-01','2020-12')
        rate=np.clip(diff.loc[mask,'informality_rate_estimated'].to_numpy(float)+sign*.0025,1e-5,1-1e-5)
        diff.loc[mask,'informality_rate_estimated']=rate
        diff.loc[mask,'informal_estimated']=diff.loc[mask,'employed_frozen'].to_numpy(float)*rate
        diff.loc[mask,'formal_estimated']=diff.loc[mask,'employed_frozen'].to_numpy(float)*(1-rate)
        diff.loc[mask,'provenance']='SENSITIVITY_DOMAIN_DIFFERENCE_NOT_OBSERVED'
        chunks.append(diff)
    full = pd.concat(chunks, ignore_index=True)
    if len(full) != 7*ROWS_NATIONAL or full[['scenario', 'period', 'national_type']].duplicated().any():
        raise AssertionError('Seven full two-universe national scenarios are required')
    if (full.informality_rate_estimated.lt(0) | full.informality_rate_estimated.gt(1)).any():
        raise ValueError('Invalid national rates')
    return full


def fill_gap_2020(priors: pd.DataFrame, urban: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Fill MLP 2020 for comparison only; existing MLP months are unmodified.

    seasonal_2019: forward last-year seasonal repeat (no future information).
    interpolated: retrospective logit interpolation using 2021 endpoint.
    urban_shock: retrospective interpolation plus the difference in urban logit
    between 2020 path and its own endpoint interpolation (not urban labels).
    """
    if mode not in ('seasonal_2019', 'interpolated', 'urban_shock'):
        raise ValueError('Unrecognized gap-filling mode')
    old = priors[['dep_code', 'period', 'rate_prior']].copy()
    old.dep_code = old.dep_code.astype(int)
    urb = urban[['dep_code', 'period', 'rate_prior']].copy()
    urb.dep_code = urb.dep_code.astype(int)
    ref = urb.set_index(['dep_code', 'period']).rate_prior
    records=[]
    if old[['dep_code','period']].duplicated().any():
        raise ValueError('Duplicate model prior')
    for code, block in old.groupby('dep_code'):
        lookup = block.set_index('period').rate_prior
        if any(f'2020-{m:02d}' in lookup.index for m in range(1,13)):
            raise ValueError('Not a complete 2020 gap; refusing overwrite')
        if not {'2019-12', '2021-01'}.issubset(set(lookup.index)):
            raise ValueError('Missing 2020 bridge endpoints')
        left, right = float(lookup['2019-12']), float(lookup['2021-01'])
        uleft, uright = (float(ref.loc[(code,'2019-12')]),float(ref.loc[(code,'2021-01')]))
        for month in range(1,13):
            period=f'2020-{month:02d}'
            if mode=='seasonal_2019':
                rate=float(lookup[f'2019-{month:02d}'])
            else:
                a=month/13
                z=(1-a)*logit(np.clip(left,1e-6,1-1e-6))+a*logit(np.clip(right,1e-6,1-1e-6))
                if mode=='urban_shock':
                    uz=(1-a)*logit(np.clip(uleft,1e-6,1-1e-6))+a*logit(np.clip(uright,1e-6,1-1e-6))
                    current=float(ref.loc[(code,period)])
                    z+=logit(np.clip(current,1e-6,1-1e-6))-uz
                rate=float(expit(z))
            records.append({'dep_code':code,'period':period,'rate_prior':rate,
                            'mode':mode,'origin':'2020_RETROSPECTIVE_NONOFFICIAL'})
    result=pd.DataFrame(records).sort_values(['period','dep_code']).reset_index(drop=True)
    if len(result)!=396 or result.rate_prior.isna().any():
        raise AssertionError('2020 bridge requires 12 months × 33 departments')
    return result


def retrospective_pseudogaps(priors:pd.DataFrame,urban:pd.DataFrame,
                              years=(2017,2018,2023,2024)) -> pd.DataFrame:
    """Hide complete years in previously fitted priors: self-consistency only.

    No original DANE departmental informality labels exist for comparison.
    The same-definition endpoint condition is required for a valid diagnostic.
    """
    urban_lookup=urban.set_index(['dep_code','period']).rate_prior
    rows=[]
    for candidate in CANDIDATES[1:]:
        panel=priors[priors.candidate==candidate]
        for year in years:
            for code, block in panel.groupby('dep_code'):
                rates=block.set_index('period').rate_prior
                left=f'{year-1}-12';right=f'{year+1}-01'
                if left not in rates or right not in rates:
                    continue
                if (year<2021 and year+1>=2021) or (year>=2021 and year-1<=2020):
                    continue
                for m in range(1,13):
                    key=f'{year}-{m:02d}'
                    if key not in rates:continue
                    t=m/13
                    z=(1-t)*logit(np.clip(float(rates[left]),1e-6,1-1e-6))+t*logit(np.clip(float(rates[right]),1e-6,1-1e-6))
                    orig=float(rates[key]); inter=float(expit(z))
                    zl=(1-t)*logit(np.clip(float(urban_lookup.loc[(code,left)]),1e-6,1-1e-6))+t*logit(np.clip(float(urban_lookup.loc[(code,right)]),1e-6,1-1e-6))
                    extra=logit(np.clip(float(urban_lookup.loc[(code,key)]),1e-6,1-1e-6))-zl
                    est={'seasonal_2019':float(rates[f'{year-1}-{m:02d}']),
                         'interpolated':inter,'urban_shock':float(expit(z+extra))}
                    for method,value in est.items():
                        rows.append({'candidate':candidate,'heldout_year':year,'dep_code':code,
                                     'period':key,'method':method,'original_fitted_rate':orig,
                                     'backcast_rate':value,'abs_delta_pp':100*abs(value-orig),
                                     'validation':'PSEUDOGAP_AGAINST_FITTED_PRIOR_NOT_OBSERVED'})
    return pd.DataFrame(rows)


def calibrate_scenarios(national_scenarios: pd.DataFrame, labor:pd.DataFrame,
                        priors:pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    """KL across scenarios, including a 2020 sensitivity baseline.

    Returns every rate in every scenario; unresolvable cases fail explicitly.
    """
    national_scenarios=national_scenarios.copy()
    labor=labor.copy(); priors=priors.copy()
    labor.dep_code= labor.dep_code.astype(int)
    if labor[['dep_code','period']].duplicated().any() or (labor.employed<=0).any():
        raise ValueError('Invalid frozen department panel')
    n=national_scenarios.set_index(['scenario','period','national_type'])
    nat_ref=national_scenarios[national_scenarios.scenario=='proxy_strength_0.5']
    if nat_ref.groupby('period').size().ne(2).any():raise ValueError('Broken national pair')
    if priors[['candidate','dep_code','period']].duplicated().any():
        raise ValueError('Duplicated candidate keys')
    full=priors.merge(labor[['dep_code','period','employed','factor_employed']],
            on=['dep_code','period'],validate='many_to_one')
    outputs=[]; audits=[]
    grouped = {c:{p:g.sort_values('dep_code') for p,g in d.groupby('period')}
             for c,d in full.groupby('candidate')}
    for scenario in sorted(national_scenarios.scenario.unique()):
        for candidate,months in grouped.items():
            for period, block in months.items():
                if len(block)!=33:raise ValueError(f'Incomplete month {candidate}/{period}')
                e=block.employed.to_numpy(float);f=block.factor_employed.to_numpy(float)
                r=block.rate_prior.to_numpy(float)
                if not np.isfinite(r).all():raise ValueError('Missing rate prior')
                target=float(n.at[(scenario,period,'ICML_COMPLETO'),'informal_estimated'])
                target_dane=float(n.at[(scenario,period,'DANE_REFERENCIA'),'informal_estimated']) if period>='2001-01' else None
                if abs(e.sum()-float(n.at[(scenario,period,'ICML_COMPLETO'),'employed_frozen']))>.01:
                    raise ValueError('Altered frozen employed ICML')
                if target_dane is not None and abs(e@f-float(n.at[(scenario,period,'DANE_REFERENCIA'),'employed_frozen']))>.01:
                    raise ValueError('Altered frozen employed DANE')
                fit=calibrate_month(r,e,f,target,target_dane)
                q=np.asarray(fit['calibrated_rate'])
                local=block[['period','dep_code','employed','factor_employed','candidate']].copy()
                local['scenario']=scenario;local['rate_prior']=r;local['rate_calibrated']=q
                local['informal']=e*q;local['formal']=e*(1-q)
                local['is_canonical']=False
                outputs.append(local)
                audits.append({'scenario':scenario,'candidate':candidate,'period':period,
                    'mean_correction_pp':100*float(np.average(abs(q-r),weights=e)),
                    'max_correction_pp':100*float(np.max(abs(q-r))),
                    'residual_icml_people':float(e@q-target),
                    'residual_dane_people':float((e*f)@q-target_dane) if target_dane is not None else np.nan,
                    'national_rate':target/e.sum(),
                    'mean_calibrated_rate':float(np.average(q,weights=e))})
    return pd.concat(outputs,ignore_index=True),pd.DataFrame(audits)


def evaluate_pseudogap_postclosure(pseudogaps: pd.DataFrame, labor: pd.DataFrame,
                                   national_base: pd.DataFrame, closure_root:Path) -> pd.DataFrame:
    """Recalibrate gap-filled rates; compare with *fitted* full model, not observed data."""
    nat=national_base.set_index(['period','national_type'])
    frozen=labor.set_index(['period','dep_code'])
    rows=[]
    for (candidate,year,method), part in pseudogaps.groupby(['candidate','heldout_year','method']):
        control=pd.read_csv(closure_root/candidate/'08_department_informality_CALIBRATION_EXPERIMENTAL.csv',
                            usecols=['period','dep_code','rate_calibrated'])
        truth=control.set_index(['period','dep_code']).rate_calibrated
        for period,g in part.groupby('period'):
            g=g.sort_values('dep_code')
            if len(g)!=33:raise ValueError('Missing pseudo-gap territories')
            refs=frozen.loc[[(period,int(i)) for i in g.dep_code]]
            e=refs.employed.to_numpy(float);f=refs.factor_employed.to_numpy(float)
            ti=float(nat.at[(period,'ICML_COMPLETO'),'informal_estimated'])
            td=float(nat.at[(period,'DANE_REFERENCIA'),'informal_estimated']) if period>='2001-01' else None
            q=np.asarray(calibrate_month(g.backcast_rate.to_numpy(float),e,f,ti,td)['calibrated_rate'])
            reference=np.array([truth.at[(period,int(i))] for i in g.dep_code])
            for code,observed,value in zip(g.dep_code,reference,q):
                rows.append({'candidate':candidate,'heldout_year':year,'method':method,'period':period,
                             'dep_code':int(code),'fitted_full_model_calibrated':observed,
                             'pseudogap_calibrated':value,'abs_delta_pp':100*abs(observed-value),
                             'validation':'SELF_CONSISTENCY_AFTER_CLOSURE_NOT_OFFICIAL_TRUTH'})
    return pd.DataFrame(rows)


def run(*,labor_path:Path,national_labor_path:Path,source_path:Path, recent_path:Path,
        anchors_path:Path,cities13_path:Path, closure_root:Path,output:Path)->dict:
    """Run full reproducible experiment in a new directory, refusing overwrite."""
    input_paths=list(map(Path,(labor_path,national_labor_path,source_path,recent_path,
                                 anchors_path,cities13_path)))
    closure_root,output=map(Path,(closure_root,output))
    if output.exists():raise FileExistsError('Audit output must be new')
    inputs={str(p):_hash(p) for p in input_paths}
    for candidate in CANDIDATES:
        prior_path = closure_root/candidate/'08_department_informality_CALIBRATION_EXPERIMENTAL.csv'
        inputs[str(prior_path)] = _hash(prior_path)
    labor=pd.read_csv(labor_path)
    natlabor=pd.read_csv(national_labor_path)
    source=pd.read_csv(source_path)
    recent=pd.read_csv(recent_path)
    anchors=pd.read_csv(anchors_path)
    cities13=pd.read_csv(cities13_path)
    scenarios=bridge_scenarios(cities13,natlabor,source,recent,anchors)
    priors=[]
    for candidate in CANDIDATES:
        path=closure_root/candidate/'08_department_informality_CALIBRATION_EXPERIMENTAL.csv'
        original=pd.read_csv(path,usecols=['dep_code','period','rate_prior'])
        original['candidate']=candidate
        priors.append(original)
    prior=pd.concat(priors,ignore_index=True)
    urban=prior[prior.candidate=='urban_direct'].copy()
    imputed=[]
    for candidate in CANDIDATES[1:]:
        own=prior[prior.candidate==candidate]
        for method in ('seasonal_2019','interpolated','urban_shock'):
            fill=fill_gap_2020(own,urban,method)
            fill['candidate']=candidate
            imputed.append(fill)
    gap=pd.concat(imputed,ignore_index=True)
    pseudogaps=retrospective_pseudogaps(prior,urban)
    # KL scenarios preserve prior 2020 embargo for MLP: evaluate only matched months.
    calibrated, audit=calibrate_scenarios(scenarios,labor,prior)
    pseudogaps_closed=evaluate_pseudogap_postclosure(pseudogaps,labor,
         scenarios[scenarios.scenario=='proxy_strength_0.5'],closure_root)
    # Additional 2020 alternatives, each separately calibrated on the base target.
    base=scenarios[scenarios.scenario=='proxy_strength_0.5'].copy()
    gap_outputs=[];gap_audits=[]
    for (candidate,method),g in gap.groupby(['candidate','mode']):
        g=g[['period','dep_code','rate_prior']].copy();g['candidate']=candidate
        c,a=calibrate_scenarios(base[base.period.str.startswith('2020-')],
                labor[labor.period.str.startswith('2020-')],g)
        c['gap_mode']=method;gap_outputs.append(c)
        a['gap_mode']=method;gap_audits.append(a)
    gap_calibrated=pd.concat(gap_outputs,ignore_index=True)
    gap_audit=pd.concat(gap_audits,ignore_index=True)
    # Monthly compared only within each definition, not across pandemic boundary.
    s=calibrated.groupby(['scenario','candidate','dep_code','period'],as_index=False).rate_calibrated.first()
    s=s.sort_values(['scenario','candidate','dep_code','period'])
    s['month']=pd.to_datetime(s.period)
    s['previous']=s.groupby(['scenario','candidate','dep_code']).rate_calibrated.shift()
    s['prev_month']=s.groupby(['scenario','candidate','dep_code']).month.shift()
    s['jump_pp']=100*(s.rate_calibrated-s.previous).abs()
    s['consecutive'] = (s.month.dt.year*12+s.month.dt.month-s.prev_month.dt.year*12-s.prev_month.dt.month==1)
    s['comparable']=(s.period.str[:4]!='2021') | (s.period!='2021-01')
    flags=s[s.consecutive.fillna(False)&s.comparable& (s.jump_pp>5)].copy()
    q=calibrated.pivot_table(index=['candidate','period','dep_code'],columns='scenario',values='rate_calibrated',aggfunc='first')
    base_rate=q['proxy_strength_0.5']
    sensitivity=[]
    for scenario in sorted(scenarios.scenario.unique()):
        if scenario=='proxy_strength_0.5':continue
        v=(q[scenario]-base_rate).dropna().abs()*100
        sensitivity.append({'scenario':scenario,'n':len(v),'mean_abs_pp':float(v.mean()),
                            'p95_abs_pp':float(v.quantile(.95)),
                            'max_abs_pp':float(v.max())})
    # Controlled publication gate: numeric feasibility is NOT accuracy.
    domain=sensitivity
    domain_worst=max(x['max_abs_pp'] for x in domain if x['scenario'].startswith('stress_dane_domain'))
    proxy_worst=max(x['max_abs_pp'] for x in domain if x['scenario'].startswith('proxy_strength'))
    pgs=pseudogaps_closed.groupby(['candidate','method']).abs_delta_pp.agg(['mean','max']).reset_index()
    gate=pd.DataFrame([
        {'gate':'G1_COVERAGE_AND_INVARIANT_OCCUPIED','status':'PASS',
         'evidence':'Frozen employed, 33 territories per modeled month; no mutations'},
        {'gate':'G2_NATIONAL_KL_CONSTRAINTS','status':'PASS' if audit.residual_icml_people.abs().max()<.01 and audit.residual_dane_people.abs().max()<.01 else 'FAIL',
         'evidence':'Maximum person residual <0.01 on every feasible simulated month'},
        {'gate':'G3_PROXY_WEIGHT_SENSITIVITY','status':'WARNING' if proxy_worst>2 else 'PASS',
         'evidence':f'Maximum local perturbation {proxy_worst:.3f} pp (proxy 0 vs 1)'},
        {'gate':'G4_DANE_ICML_DOMAIN_DIFFERENTIAL','status':'BLOCKED',
         'evidence':f'An unobserved ±0.25pp divergence moves a department up to {domain_worst:.3f} pp'},
        {'gate':'G5_2020_MODEL_PRIORS','status':'BLOCKED',
         'evidence':'Only diagnostic gap-fills; no independent 2020 MLP prediction'},
        {'gate':'G6_REAL_HOLDOUT_VALIDATION','status':'BLOCKED',
         'evidence':'Pseudogaps measure consistency with already-fitted priors, not unseen DANE informality labels'},
        {'gate':'G7_DEFINITION_BRIDGE','status':'BLOCKED',
         'evidence':'Historical pension/non-pension proxy and T5 not equivalent to current GEIH informality'},
        {'gate':'G8_SNAPSHOT_PRESERVATION','status':'PASS',
         'evidence':'Prior versions read only; experiments create new directory and SHA256 manifest'},
    ])
    output.mkdir(parents=True)
    scenario_base=scenarios[scenarios.national_type=='ICML_COMPLETO'][['scenario','period','informality_rate_estimated']]
    for name,df in [('11_national_scenarios.csv',scenario_base),
                    ('11_kl_calibrated_scenarios_EXPERIMENTAL.csv',calibrated),
                    ('11_calibration_monthly_audit.csv',audit),
                    ('11_2020_gap_priors_EXPERIMENTAL.csv',gap),
                    ('11_2020_gap_calibrated_EXPERIMENTAL.csv',gap_calibrated),
                    ('11_2020_gap_closure_audit.csv',gap_audit),
                    ('11_pseudogap_self_consistency.csv',pseudogaps),
                    ('11_pseudogap_postclosure_self_consistency.csv',pseudogaps_closed),
                    ('11_temporal_flags.csv',flags),
                    ('11_territorial_sensitivity.csv',pd.DataFrame(sensitivity)),
                    ('11_pseudogap_postclosure_summary.csv',pgs),
                    ('11_quality_gate.csv',gate)]:
        df.to_csv(output/name,index=False,float_format='%.12g',lineterminator='\n')
    summary={'status':'EXPERIMENTAL_NOT_CANONICAL',
       'reference':'ICML 2.2.9 frozen employed and KL calibration',
       'scenarios':scenarios.scenario.unique().tolist(),
       'national_targets_from':'DANE-only _national_historical; no ILOSTAT',
       'candidate_models':list(CANDIDATES),
       'n_calibrated_rows':len(calibrated),'n_gap_filled_rows':len(gap_calibrated),
       'max_icml_residual_people':float(audit.residual_icml_people.abs().max()),
       'max_dane_residual_people':float(audit.residual_dane_people.abs().max()),
       'n_pseudogap_rows':len(pseudogaps),
       'n_pseudogap_postclosure_rows':len(pseudogaps_closed),'n_temporal_flags':len(flags),
       'gate_status':'BLOCKED_NOT_CANONICAL',
       'sensitivity':sensitivity,'input_sha256':inputs,
       'limitations':['2020 bridge is inferential, not observed',
        'Pseudogap compares previously fitted MLP priors, not DANE labels',
        'Baseline national informal targets share same inferred rate; ±0.25pp represented-domain stress is not observed',
        'Closure of two national margins does not validate geographic precision',
        'Historical T5 and new GEIH definitions differ, no observed conversion',
        'No 2020 MLP result is promoted as canonical']}
    (output/'11_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf8')
    man={p.name:_hash(p) for p in output.iterdir() if p.is_file()}
    (output/'manifest.json').write_text(json.dumps(man,indent=2),encoding='utf8')
    return summary
