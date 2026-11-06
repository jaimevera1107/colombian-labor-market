"""Experimental alternative calibrations of INFORMAL employment rates.

All candidates are constrained to frozen employed counts and the exact ICML
(and, since 2001, represented DANE) monthly targets. None validates actual
territorial accuracy: these targets share the same inferred informality rate.

Five alternatives: legacy Bernoulli-KL, employed-weighted quadratic (L2),
variance-scaled quadratic, and temporal correction-regularized quadratic with
1x/4x weights. Temporal penalty acts on the *correction*, preserving prior
monthly movements. It is forward-only, resets across the definition boundary,
and never edits the original data or published results.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import root, minimize
from scipy.stats import spearmanr

from .national_closure import calibrate_month, InfeasibleClosure

CANDIDATES = ('urban_direct','mlp_residual_92','mlp_shared19')
VARIANTS = ('kl_original','l2_employment','l2_variance','l2_temporal_1','l2_temporal_4')


def _valid_vectors(prior: np.ndarray, e: np.ndarray, f: np.ndarray, target: float,
                   rep_target: float | None) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    p,e,f = [np.asarray(x,dtype=float) for x in (prior,e,f)]
    if p.ndim!=1 or not len(p) or p.shape!=e.shape or p.shape!=f.shape:
        raise ValueError('Nonempty equal-length rate, employment, and factor vectors required')
    if not all(np.isfinite(x).all() for x in (p,e,f)):
        raise ValueError('Nonfinite input')
    if np.any(e<=0) or np.any((f<0)|(f>1)) or np.any((p<0)|(p>1)):
        raise ValueError('Invalid rates, employment or coverage factors')
    if not np.isfinite(target) or target<0 or target>e.sum():
        raise InfeasibleClosure('Invalid full-universe national target')
    if rep_target is not None:
        if not np.isfinite(rep_target) or rep_target<0 or rep_target>e@f:
            raise InfeasibleClosure('Invalid represented national target')
        if np.ptp(f)<1e-12:
            raise InfeasibleClosure('Second target is linearly dependent on first')
    return p,e,f


def calibrate_quadratic(prior: np.ndarray, employed: np.ndarray, factor: np.ndarray,
                        target: float, rep_target: float | None = None,
                        *, variant: str='l2_employment', previous_correction: np.ndarray | None=None,
                        tolerance_people: float=1e-3) -> np.ndarray:
    """Bounded convex quadratic, weighted by employed counts; solve dual KKT.

    For l2_variance, use inverse Bernoulli variance on a clipped prior. For
    temporal, minimize squared current correction plus lambda times squared
    change to previous correction, with previous correction defined by a
    PAST month and not crossing source-definition transitions.
    """
    p,e,f = _valid_vectors(prior,employed,factor,target,rep_target)
    if variant not in VARIANTS[1:]: raise ValueError('Unknown quadratic variant')
    total=e.sum()
    w=e/total
    if variant=='l2_variance':
        # Bound influence from estimates close to 0 or 1. Fixed prior weights.
        precision=1.0/np.maximum(p*(1-p),0.04)
    else: precision=np.ones_like(p)
    lam={'l2_employment':0.,'l2_variance':0.,'l2_temporal_1':1.,'l2_temporal_4':4.}[variant]
    if previous_correction is None: lam=0.
    if previous_correction is not None:
        prev=np.asarray(previous_correction,float)
        if prev.shape!=p.shape or not np.isfinite(prev).all():
            raise ValueError('Invalid previous correction')
    else: prev=np.zeros_like(p)
    # 1/2 sum_i e_i [precision_i (q_i-p_i)^2 + lam (q_i-(p_i+prev_i))^2]
    # => 1/2 sum_i e_i c_i (q_i-center_i)^2 + constant
    c=precision+lam
    center=p+lam*prev/c
    trg=np.array([target/total] + ([rep_target/total] if rep_target is not None else []))
    def build(z):
        x=z[0]+(z[1]*f if len(z)==2 else 0.)
        q=np.clip(center+x/c,0,1)
        return q
    def residual(z):
        q=build(z)
        return np.array([w@q] + ([(w*f)@q] if len(z)==2 else []))-trg
    def jac(z):
        q=build(z)
        inside=(q>1e-13)&(q<1-1e-13)
        v=w*inside/c
        if len(z)==1: return np.array([[np.sum(v)]])
        return np.array([[v.sum(),v@f],[v@f,v@(f*f)]])
    # Reproducible, small-dimensional dual solve. SLSQP provides a robust
    # bounded primal fallback for active-set or nearly degenerate factors.
    x0=np.zeros(len(trg))
    if len(trg)==1:
        lo,hi=-200.,200.
        for _ in range(90):
            mid=(lo+hi)/2
            if residual([mid])[0]<0: lo=mid
            else: hi=mid
        q=build([(lo+hi)/2])
    else:
        sol=root(residual,x0,jac=jac,tol=1e-12)
        q=build(sol.x)
    r=np.array([float(e@q-target)] +
               ([float((e*f)@q-rep_target)] if rep_target is not None else []))
    if max(abs(r))>tolerance_people:
        # Explicitly constrained primal fallback; no silent normalization.
        A=np.vstack([w] + ([w*f] if rep_target is not None else []))
        def cost(x):return .5*np.sum(w*c*(x-center)**2)
        def gradient(x):return w*c*(x-center)
        constraints={'type':'eq','fun':lambda x:A@x-trg,'jac':lambda x:A}
        res=minimize(cost,np.clip(q,0,1),jac=gradient,bounds=[(0.,1.)]*len(p),
                     constraints=[constraints],method='SLSQP',
                     options={'maxiter':1000,'ftol':1e-13})
        q=np.clip(res.x,0,1)
        r=np.array([float(e@q-target)] +
                   ([float((e*f)@q-rep_target)] if rep_target is not None else []))
        if max(abs(r))>tolerance_people:
            raise InfeasibleClosure(f'Quadratic calibration failed {variant}: residuals {r.tolist()}')
    return q


def _rank(x: np.ndarray,y: np.ndarray) -> float:
    if np.ptp(x)<1e-12 or np.ptp(y)<1e-12:return float('nan')
    return float(spearmanr(x,y).statistic)


def _hash(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()


def run(closure_root:Path, labor_path:Path, national_path:Path, output:Path,
        *,candidates:tuple[str,...]=CANDIDATES, variants:tuple[str,...]=VARIANTS)->dict[str,Any]:
    """Run five immutable counterfactual solvers on the three frozen priors."""
    closure_root,labor_path,national_path,output=map(Path,(closure_root,labor_path,national_path,output))
    if output.exists():raise FileExistsError('Output must be a new immutable path')
    labor=pd.read_csv(labor_path)
    national=pd.read_csv(national_path)
    required={'period','dep_code','employed','factor_employed'}
    if required-set(labor):raise ValueError('Missing frozen labor fields')
    if labor[['dep_code','period']].duplicated().any():raise ValueError('Duplicate labor keys')
    national['period']=national.period.astype(str)
    n=national.set_index(['period','national_type'])
    if national[['period','national_type']].duplicated().any():raise ValueError('Duplicated national')
    outputs=[];stats=[];monthly=[];audit=[]
    for candidate in candidates:
        src=closure_root/candidate/'08_department_informality_CALIBRATION_EXPERIMENTAL.csv'
        frame=pd.read_csv(src)
        if frame[['dep_code','period']].duplicated().any():raise ValueError('Duplicated prior keys')
        if len(frame)!=len(frame.merge(labor[['period','dep_code']],on=['period','dep_code'])):
            raise ValueError('Candidate/labor key mismatch')
        # Validate frozen employed and factors: never trust a stale candidate.
        frame=frame.merge(labor[['period','dep_code','employed','factor_employed']],
                          on=['period','dep_code'],suffixes=('','_labor'),validate='one_to_one')
        if not np.allclose(frame.employed,frame.employed_labor,rtol=0,atol=.01) or not np.allclose(frame.factor_employed,frame.factor_employed_labor,rtol=0,atol=1e-10):
            raise ValueError('Frozen labor changed in prior')
        for variant in variants:
            prev=None;prev_period=None
            calibrated=[]
            for period,group in frame.groupby('period',sort=True):
                group=group.sort_values('dep_code')
                if len(group)!=33:raise ValueError(f'{candidate} {period}: incomplete 33 territories')
                p=group.rate_prior.to_numpy(float);e=group.employed.to_numpy(float)
                f=group.factor_employed.to_numpy(float)
                ti=float(n.at[(period,'ICML_COMPLETO'),'informal_estimated'])
                td=float(n.at[(period,'DANE_REFERENCIA'),'informal_estimated']) if period>='2001-01' else None
                if abs(e.sum()-float(n.at[(period,'ICML_COMPLETO'),'employed_frozen']))>.01:
                    raise ValueError('Frozen ICML national denominator changed')
                if td is not None and abs(e@f-float(n.at[(period,'DANE_REFERENCIA'),'employed_frozen']))>.01:
                    raise ValueError('Frozen DANE denominator changed')
                # Reset history at discontinuity, missing months, and method transition.
                contiguous=(prev_period is not None and pd.Period(period,freq='M').ordinal-pd.Period(prev_period,freq='M').ordinal==1)
                keep_prev=contiguous and period!='2021-01'
                correction=prev if keep_prev else None
                if variant=='kl_original':
                    q=np.asarray(calibrate_month(p,e,f,ti,td)['calibrated_rate'])
                else:
                    q=calibrate_quadratic(p,e,f,ti,td,variant=variant,previous_correction=correction)
                if not np.isfinite(q).all() or np.any((q<0)|(q>1)):
                    raise ValueError('Nonfinite or impossible calibrated rates')
                if abs(e@q-ti)>.01 or (td is not None and abs((e*f)@q-td)>.01):
                    raise ValueError(f'Constraint violation {candidate}/{variant}/{period}')
                correction=q-p
                prev=correction.copy();prev_period=period
                g=group[['dep_code','period']].copy()
                g['candidate']=candidate;g['variant']=variant;g['rate_prior']=p
                g['rate_calibrated']=q;g['employed']=e;g['factor_employed']=f
                g['informal']=e*q;g['formal']=e*(1-q)
                g['informal_represented']=e*f*q
                calibrated.append(g)
                weighted=np.average(abs(q-p),weights=e)*100
                top_prior=set(group.iloc[np.argsort(p)[-5:]].dep_code)
                top_after=set(group.iloc[np.argsort(q)[-5:]].dep_code)
                monthly.append({'candidate':candidate,'variant':variant,'period':period,
                    'weighted_abs_intervention_pp':weighted,
                    'max_abs_intervention_pp':100*np.max(abs(q-p)),
                    'spearman_rank_pre_post':_rank(p,q),'top5_overlap':len(top_prior&top_after),
                    'max_local_identity_people':np.max(abs(g.informal+g.formal-e)),
                    'icml_residual_people':float(e@q-ti),
                    'dane_residual_people':float((e*f)@q-td) if td is not None else float('nan')})
            result=pd.concat(calibrated,ignore_index=True)
            outputs.append(result)
            for dep,g in result.groupby('dep_code',sort=True):
                g=g.sort_values('period')
                date=pd.PeriodIndex(g.period,freq='M'); q=g.rate_calibrated.to_numpy(float)
                p=g.rate_prior.to_numpy(float)
                delta=q-p
                for i in range(1,len(g)):
                    if date[i].ordinal-date[i-1].ordinal!=1:continue
                    if str(date[i])=='2021-01':continue
                    j=100*(q[i]-q[i-1]); jp=100*(p[i]-p[i-1]); jdelta=100*(delta[i]-delta[i-1])
                    stats.append({'candidate':candidate,'variant':variant,'period':str(date[i]),
                        'dep_code':int(dep),'jump_final_pp':j,'jump_prior_pp':jp,
                        'jump_correction_pp':jdelta,'new_flag_5pp':abs(j)>5 and abs(jp)<=5,
                        'new_flag_10pp':abs(j)>10 and abs(jp)<=10})
            audit.append({'candidate':candidate,'variant':variant,'months':result.period.nunique(),
                'rows':len(result),'target_provenance':'TWO_NATIONALS_SHARE_INFERRED_RATE',
                'independent_spatial_validation':False})
    output.mkdir(parents=True)
    df=pd.concat(outputs,ignore_index=True)
    m=pd.DataFrame(monthly);t=pd.DataFrame(stats);a=pd.DataFrame(audit)
    # Equivalent target constraints: assess how much the algorithms distort an
    # unchanged predictive prior; do NOT assess true departmental prediction error.
    agg=[]
    for (c,v),g in m.groupby(['candidate','variant']):
        ts=t[(t.candidate==c)&(t.variant==v)]
        agg.append({'candidate':c,'variant':v,'months':len(g),
            'avg_weighted_abs_change_pp':g.weighted_abs_intervention_pp.mean(),
            'p95_weighted_abs_change_pp':g.weighted_abs_intervention_pp.quantile(.95),
            'max_local_change_pp':g.max_abs_intervention_pp.max(),
            'avg_spearman_prepost':g.spearman_rank_pre_post.mean(),
            'pct_exact_top5':100*(g.top5_overlap==5).mean(),
            'new_5pp_jumps':int(ts.new_flag_5pp.sum()),
            'new_10pp_jumps':int(ts.new_flag_10pp.sum()),
            'avg_abs_correction_jump_pp':ts.jump_correction_pp.abs().mean(),
            'max_icml_residual_people':g.icml_residual_people.abs().max(),
            'max_dane_residual_people':g.dane_residual_people.abs().max()})
    summary=pd.DataFrame(agg)
    a['G0_inputs_and_occupations']='PASS'
    a['G1_national_margins']='PASS'
    a['G2_bounded_rates_and_identities']='PASS'
    a['G3_temporal_stability']='REVIEW'
    a['G4_independent_department_accuracy']='NOT_VERIFIABLE'
    a['G5_definition_bridge']='BLOCKED'
    a['G6_full_2020_coverage']=np.where(a.candidate=='urban_direct','PASS','BLOCKED')
    paths={'10_calibrated_all_candidates_EXPERIMENTAL.csv':df,
           '10_monthly_metrics.csv':m,'10_temporal_comparisons.csv':t,
           '10_method_summary.csv':summary,'10_gate.csv':a}
    for name,data in paths.items():data.to_csv(output/name,index=False,float_format='%.12g',lineterminator='\n')
    meta={'status':'EXPERIMENTAL_NOT_CANONICAL','methods':list(variants),
          'candidates':list(candidates),'source_files':{
            'labor':_hash(labor_path),'national_informality':_hash(national_path),
            **{x:_hash(closure_root/x/'08_department_informality_CALIBRATION_EXPERIMENTAL.csv') for x in candidates}},
          'exclusions':'2020 has no MLP predictions; temporal penalty resets at missing months and 2021-01',
          'limitations':['Neither national target validates departmental accuracy.',
           'City-held-out predictive scores are unchanged; these are calibration experiments.',
           'Temporal penalty is forward-only and cannot distinguish economic changes from noise.',
           'All 5 methods preserve published employment and do not alter existing canonical CSVs.']}
    (output/'10_manifest.json').write_text(json.dumps({**meta,'outputs_sha256':{
        x:_hash(output/x) for x in paths}},indent=2,ensure_ascii=False),encoding='utf-8')
    return {'summary':summary.to_dict(orient='records'),'manifest':str(output/'10_manifest.json')}
