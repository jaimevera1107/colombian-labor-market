"""H13: constrained KL-raking of *non-observed* departmental sector priors.

For each month, reweight probabilities p[department,sector] by minimal
employment-weighted KL divergence from H12, subject to:
 - departmental composition sums to one;
 - national complete-ICML sector shares equal national H11/H10 shares;
 - from 2001-01, represented-GEIH sector shares equal the SAME national shares,
   while keeping a single sector composition for both universes.

Pre-2001 represented-department sums do NOT close to national DANE, so the
GEIH national margin is not constrained. No observed sector-level labels are
claimed. Nothing in H12 or national historical source is overwritten.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from icml.domain.cutoff import month_periods

SECTORS = ('A','B','C','D_E','F','G','H','I','J','K','L','M_N','O_P_Q','R_S_T_U','NO_INFO')
SCENARIOS = ('NEUTRAL_NATIONAL', 'RURAL_PROXY_WEAK', 'RURAL_PROXY_MODERATE')
ALGORITHM = 'WEIGHTED_KL_DUAL_NEWTON_V1'


def _softmax_with_log_base(p0: np.ndarray, expo: np.ndarray) -> np.ndarray:
    logits = np.where(p0 > 0, np.log(np.maximum(p0, 1e-300)) + expo, -np.inf)
    logits -= np.max(logits, axis=1, keepdims=True)
    v = np.exp(logits)
    return v / v.sum(axis=1, keepdims=True)


def solve_joint_margins(p0: np.ndarray, full: np.ndarray, geih: np.ndarray,
                        target: np.ndarray, *, fit_geih: bool,
                        tol: float = 2e-12, max_iter: int = 70) -> tuple[np.ndarray,dict]:
    """KL projection, row simplex + complete columns + optional represented columns.

    Uses normalized department weights and centered/standardized GEIH/full
    exposure, so that constraints are numerically stable and compatible.
    The last sector is baseline and is fixed; zero-target sectors stay zero.
    Stops ONLY on demonstrated margin precision, otherwise throws.
    """
    p0=np.asarray(p0,dtype=float)
    full=np.asarray(full,dtype=float)
    geih=np.asarray(geih,dtype=float)
    target=np.asarray(target,dtype=float)
    if p0.ndim!=2 or p0.shape != (len(full),len(target)) or full.shape != geih.shape:
        raise ValueError('Incompatible dimensions')
    if not np.all(np.isfinite(p0)) or not np.all(np.isfinite(full)) or not np.all(np.isfinite(geih)) or not np.all(np.isfinite(target)):
        raise ValueError('Nonfinite input')
    if np.any(p0<0) or np.any(full<=0) or np.any(geih<0) or np.any(target<0):
        raise ValueError('Negative sectors or zero row employment')
    if np.max(np.abs(p0.sum(axis=1)-1))>1e-8 or abs(target.sum()-1)>1e-9:
        raise ValueError('Non-simplex prior or target')
    active=target>0
    if np.any((p0[:,active]<=0).all(axis=0)):
        raise ValueError('Positive target sector without positive prior support')
    if np.any((p0[:,~active]>1e-10)):
        raise ValueError('Zero target sector has positive prior')
    # Avoid structural zeros in active sectors. Zero-target sectors are exactly zero.
    if np.any(p0[:,active]<=0):
        raise ValueError('Active sector has prohibited structural zero in prior')
    p=p0[:,active].copy(); q=target[active].copy()
    # The share weighted by full employment is the main target.
    w=full/full.sum()
    ratio=geih/full
    ratio_avg=np.dot(w,ratio)
    ratio_sd=float(np.sqrt(np.dot(w,(ratio-ratio_avg)**2)))
    if fit_geih and (geih.sum()<=0 or ratio_sd<1e-10):
        # If ratio is constant, represented share equals full share identically.
        fit_geih=False
    z=(ratio-ratio_avg)/ratio_sd if fit_geih else np.zeros_like(w)
    K=len(q); m=K-1
    if K==1:
        result=np.zeros_like(p0); result[:,active]=1.0
        return result, {'iterations':0,'joint_geih':fit_geih,'max_national_share_residual':0.0,
                        'max_geih_share_residual':0.0,'solved':True,'objective_kl':0.0}

    def evaluate(par: np.ndarray, jac: bool=False):
        a=np.zeros(K); a[:m]=par[:m]
        if fit_geih:
            b=np.zeros(K); b[:m]=par[m:]
            expo=a[None,:]+z[:,None]*b[None,:]
        else:
            expo=np.broadcast_to(a,(len(w),K))
        x=_softmax_with_log_base(p,expo)
        d_full=w @ x - q
        if fit_geih:
            d_cov=(w*z) @ x
            grad=np.r_[d_full[:m],d_cov[:m]]
        else:
            grad=d_full[:m]
        obj=float(np.dot(w,np.log(np.maximum((p*np.exp(np.clip(expo-expo.max(axis=1,keepdims=True),-700,0))).sum(axis=1),1e-300)) + expo.max(axis=1)) - np.dot(q,a))
        # Above stable log-partition equals logsumexp(log(p)+expo), computed separately.
        # Objective used only for damping; conservative residual norm used for fallback.
        if not jac:return x,grad,obj
        h=np.zeros((K,K)); hz=np.zeros((K,K)); hzz=np.zeros((K,K))
        for wi,zi,xi in zip(w,z,x):
            cov=np.diag(xi)-np.outer(xi,xi)
            h+=wi*cov
            if fit_geih:
                hz+=wi*zi*cov
                hzz+=wi*zi*zi*cov
        if fit_geih:
            J=np.block([[h[:m,:m],hz[:m,:m]],[hz[:m,:m],hzz[:m,:m]]])
        else:
            J=h[:m,:m]
        return x,grad,J

    par=np.zeros(m*(2 if fit_geih else 1))
    converged=False; last=1e10
    for iteration in range(max_iter+1):
        x,grad,J=evaluate(par,jac=True)
        # With the reference-sector normalization, omitted sector residual equals
        # negative sum of all included; check ALL sector equations explicitly.
        full_diff=w @ x - q
        if fit_geih:
            g_share=(w*ratio) @ x / ratio_avg
            g_diff=g_share-q
            err=max(np.max(np.abs(full_diff)),np.max(np.abs(g_diff)))
        else:
            g_diff=np.full(K,np.nan)
            err=np.max(np.abs(full_diff))
        if err<tol:
            converged=True
            break
        if iteration==max_iter:break
        try:
            direction=np.linalg.solve(J+np.eye(J.shape[0])*1e-13,grad)
        except np.linalg.LinAlgError as e:
            raise RuntimeError('KL dual Hessian singular') from e
        norm=float(np.linalg.norm(grad))
        step=1.0
        for _ in range(25):
            candidate=par-step*direction
            if np.max(np.abs(candidate))>100:step*=0.5;continue
            _,newgrad,_=evaluate(candidate)
            if np.linalg.norm(newgrad)<norm or step<1e-7:
                par=candidate
                break
            step*=0.5
        else:raise RuntimeError('KL dual line search failed')
        last=err
    if not converged:
        raise RuntimeError(f'H13 margins did not converge: max error {err}, iterations={iteration}, joint={fit_geih}')
    final=np.zeros_like(p0);final[:,active]=x
    kl=float(np.dot(w, np.sum(np.where(x>0,x*np.log(x/p),0),axis=1)))
    return final, {'iterations':iteration,'joint_geih':fit_geih,
                   'max_national_share_residual':float(np.max(np.abs(full_diff))),
                   'max_geih_share_residual':float(np.max(np.abs(g_diff))) if fit_geih else None,
                   'solved':True,'objective_kl':kl}


def _read(path: Path, dep: bool=False) -> pd.DataFrame:
    if not Path(path).is_file():raise FileNotFoundError(path)
    return pd.read_csv(path,dtype={'dep_code':'string'} if dep else None,low_memory=False)


def _check_unique(df: pd.DataFrame, keys: list[str], name: str) -> None:
    if df.empty or df[keys].isna().any().any() or df.duplicated(keys).any():
        raise ValueError(f'{name}: missing/duplicate keys')


def run(priors_csv: Path, national_csv: Path, covariates_csv: Path,
        universe_csv: Path, output: Path) -> dict:
    """Run independent H13 from H12 frozen outputs; write audited noncanonical CSVs."""
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    p=_read(Path(priors_csv),dep=True); n=_read(Path(national_csv)); cov=_read(Path(covariates_csv),dep=True)
    uni=_read(Path(universe_csv))
    _check_unique(p,['period','dep_code','sector_code','scenario'],'H12 priors')
    _check_unique(n,['period','sector_code'],'H12 national')
    _check_unique(cov,['period','dep_code'],'H12 covariates')
    _check_unique(uni,['period'],'H12 universe audit')
    periods=list(month_periods().astype(str))
    departments=sorted(cov.dep_code.unique())
    if sorted(cov.period.unique())!=periods or len(departments)!=33:
        raise ValueError('Expected 404 months and 33 territories')
    if sorted(n.period.unique())!=periods or sorted(p.period.unique())!=periods:
        raise ValueError('National/prior monthly coverage not complete')
    if set(p.scenario.unique())!=set(SCENARIOS) or set(n.sector_code.unique())!=set(SECTORS):
        raise ValueError('Scenario or sector classification inconsistent')
    if len(p)!=len(periods)*len(departments)*len(SECTORS)*len(SCENARIOS):
        raise ValueError('H12 candidate panel has incomplete keys')
    if len(n)!=len(periods)*len(SECTORS):
        raise ValueError('H12 national sector panel incomplete')
    if len(cov)!=len(periods)*len(departments):
        raise ValueError('H12 covariates panel incomplete')
    full_mat=cov.pivot(index='period',columns='dep_code',values='employed').loc[periods,departments].to_numpy(float)
    geih_mat=cov.pivot(index='period',columns='dep_code',values='employed_represented').loc[periods,departments].to_numpy(float)
    national_mat=n.pivot(index='period',columns='sector_code',values='sector_share').loc[periods,list(SECTORS)].to_numpy(float)
    expected=uni.set_index('period').loc[periods]
    if np.max(np.abs(full_mat.sum(axis=1)-expected.full_national_icml.to_numpy(float)))>1e-4:
        raise ValueError('H12 complete labor totals do not reconcile to national')
    if np.max(np.abs(geih_mat[96:].sum(axis=1)-expected.national_dane.to_numpy(float)[96:]))>1e-4:
        raise ValueError('Post2000 represented labor totals do not reconcile to DANE')
    if np.max(np.abs(national_mat.sum(axis=1)-1))>1e-10:
        raise ValueError('National sector shares not in simplex')
    if (p['sector_share']<0).any():raise ValueError('Negative H12 prior shares')
    p['dep_code']=p.dep_code.astype('string').str.zfill(2)
    p=p.set_index(['scenario','period','dep_code','sector_code']).sort_index()
    outputs=[]; diag=[]; margin=[]; rows=[]; full_only_comparison=[]; full_only_matrices=[]
    for scenario in SCENARIOS:
        view=p.loc[scenario]
        for i,period in enumerate(periods):
            # The exact panel is validated through reindex + notna check.
            keys=pd.MultiIndex.from_product([[period],departments,SECTORS],names=['period','dep_code','sector_code'])
            sub=view.reindex(keys)
            if sub['sector_share'].isna().any():raise ValueError(f'H12 incomplete {scenario} {period}')
            before=sub.sector_share.to_numpy(float).reshape(len(departments),len(SECTORS))
            f=full_mat[i]; g=geih_mat[i]; q=national_mat[i]
            after,meta=solve_joint_margins(before,f,g,q,fit_geih=(period>='2001-01'))
            # Strict sensitivity: imposing complete national margins alone does
            # not require an assumed represented-national sector margin. This
            # alternative is used to quantify the cost of fitting both.
            if period>='2001-01' and scenario!='NEUTRAL_NATIONAL':
                full_only,other=solve_joint_margins(before,f,g,q,fit_geih=False)
                delta_full_only=float(np.max(np.abs((full_only-before)*100)))
                delta_joint=float(np.max(np.abs((after-before)*100)))
                gap_geih_fullonly=float(np.max(np.abs((g@full_only/g.sum()-q)*100)))
                delta_methods=float(np.max(np.abs((full_only-after)*100)))
            else:
                full_only=after
                delta_full_only=float(np.max(np.abs((after-before)*100)))
                delta_joint=delta_full_only
                gap_geih_fullonly=(0.0 if scenario=='NEUTRAL_NATIONAL' else np.nan)
                delta_methods=0.0
            full_only_comparison.append(dict(period=period,scenario=scenario,
                 full_only_max_adjustment_pp=delta_full_only,
                 joint_max_adjustment_pp=delta_joint,
                 full_only_max_geih_national_gap_pp=gap_geih_fullonly,
                 joint_minus_full_only_max_share_pp=delta_methods,
                 geih_national_identified=(period>='2001-01')))
            # Save the full-only alternative only where it differs materially:
            # before 2001 both methods coincide, and neutral never changes.
            if period>='2001-01' and scenario!='NEUTRAL_NATIONAL':
                full_only_matrices.append(pd.DataFrame({
                    'period':period,'dep_code':np.repeat(departments,len(SECTORS)),
                    'sector_code':list(SECTORS)*len(departments),'scenario':scenario,
                    'share_prior_h12':before.ravel(),
                    'sector_share_full_only':full_only.ravel(),
                    'adjustment_pp':((full_only-before)*100).ravel(),
                    'employed_full_sector':(full_only*f[:,None]).ravel(),
                    'employed_geih_sector_proxy':(full_only*g[:,None]).ravel(),
                    'geih_national_margin_status':'NOT_CONSTRAINED_SENSITIVITY'
                }))
            level_f=after*f[:,None]; level_g=after*g[:,None]
            diff_pp=(after-before)*100
            check_f=level_f.sum(axis=0)-q*f.sum()
            check_g=level_g.sum(axis=0)-q*g.sum()
            max_f=max(abs(check_f)); max_g=max(abs(check_g))
            if max_f>0.001 or (period>='2001-01' and max_g>0.001):
                raise ValueError(f'H13 margin failure {scenario} {period} {max_f} {max_g}')
            if np.max(np.abs(level_f.sum(axis=1)-f))>1e-5 or np.max(np.abs(level_g.sum(axis=1)-g))>1e-5:
                raise ValueError(f'H13 row closure failure {scenario} {period}')
            temp=pd.DataFrame({'period':period,'dep_code':np.repeat(departments,len(SECTORS)),
                         'sector_code':list(SECTORS)*len(departments),'scenario':scenario,
                         'share_prior_h12':before.ravel(),'sector_share_h13':after.ravel(),
                         'adjustment_pp':diff_pp.ravel(),
                         'employed_full_sector':level_f.ravel(),
                         'employed_geih_sector_proxy':level_g.ravel()})
            # Never mark represented sector numbers as observed; both universes
            # use the same reconstructed departmental sector composition.
            temp['status']='ESTIMATED_H13_RECONCILED_NOT_OBSERVED'
            outputs.append(temp)
            diag.append(dict(period=period,scenario=scenario,iterations=meta['iterations'],
                 solver=ALGORITHM,fit_geih_national=(period>='2001-01'),
                 kl_employment_weighted=meta['objective_kl'],
                 max_abs_correction_pp=float(np.abs(diff_pp).max()),
                 mean_abs_correction_pp=float(np.abs(diff_pp).mean()),
                 max_full_national_error_persons=float(max_f),
                 max_geih_national_error_persons=float(max_g) if period>='2001-01' else np.nan,
                 max_full_dept_error_persons=float(max(abs(level_f.sum(axis=1)-f))),
                 max_geih_dept_error_persons=float(max(abs(level_g.sum(axis=1)-g))),
                 represented_pre2001_not_anchored=(period<'2001-01')))
            for j,s in enumerate(SECTORS):
                margin.append(dict(period=period,scenario=scenario,sector_code=s,
                     sector_share_national_target=q[j],national_full_target=q[j]*f.sum(),
                     national_full_reconciled=level_f[:,j].sum(),full_residual_persons=check_f[j],
                     national_geih_target=(q[j]*g.sum() if period>='2001-01' else np.nan),
                     national_geih_reconciled=level_g[:,j].sum(),
                     geih_residual_persons=(check_g[j] if period>='2001-01' else np.nan),
                     geih_national_constraint_status=('CONSTRAINED_POST2000' if period>='2001-01' else 'NOT_IDENTIFIED_PRE2001')))
            for j,d in enumerate(departments):
                rows.append(dict(period=period,scenario=scenario,dep_code=d,
                    full_input=f[j],full_sum=level_f[j].sum(),full_residual=level_f[j].sum()-f[j],
                    geih_input=g[j],geih_sum=level_g[j].sum(),geih_residual=level_g[j].sum()-g[j]))
    out=pd.concat(outputs,ignore_index=True)
    audit=pd.DataFrame(diag); margins=pd.DataFrame(margin); row_audit=pd.DataFrame(rows)
    out.to_csv(output/'13_matriz_depto_sector_1993_2026_RECONCILIADA_EXPERIMENTAL.csv',index=False,float_format='%.14g')
    audit.to_csv(output/'13_auditoria_ajustes_y_convergencia.csv',index=False,float_format='%.14g')
    margins.to_csv(output/'13_auditoria_margenes_nacionales.csv',index=False,float_format='%.14g')
    row_audit.to_csv(output/'13_auditoria_cierre_departamental.csv',index=False,float_format='%.14g')
    by_scenario=audit.groupby('scenario',sort=False).agg(
         max_abs_correction_pp=('max_abs_correction_pp','max'),
         mean_abs_correction_pp=('mean_abs_correction_pp','mean'),
         max_full_error_persons=('max_full_national_error_persons','max'),
         max_geih_error_persons=('max_geih_national_error_persons','max'),
         max_iterations=('iterations','max')).reset_index()
    by_scenario.to_csv(output/'13_sensibilidad_escenarios.csv',index=False,float_format='%.14g')
    if full_only_matrices:
        pd.concat(full_only_matrices,ignore_index=True).to_csv(
            output/'13_matriz_alternativa_solo_cierre_completo_2001_2026.csv',
            index=False,float_format='%.14g')
    full_only_comparison=pd.DataFrame(full_only_comparison)
    full_only_comparison.to_csv(output/'13_comparacion_cierre_completo_vs_conjunto.csv',index=False,float_format='%.14g')
    covariate_labels=cov[['period','dep_code','territory_name','rural_fraction']]
    biggest=out.iloc[np.argsort(-out.adjustment_pp.abs().to_numpy())[:100]].merge(
        covariate_labels,on=['period','dep_code'],validate='many_to_one')
    biggest.to_csv(output/'13_ajustes_mayores_puntuales.csv',index=False,float_format='%.14g')
    per_department_sector=out.groupby(['scenario','dep_code','sector_code'],sort=True).agg(
        max_abs_correction_pp=('adjustment_pp',lambda x: float(np.abs(x).max())),
        mean_abs_correction_pp=('adjustment_pp',lambda x: float(np.abs(x).mean()))).reset_index()
    per_department_sector.to_csv(output/'13_concentracion_ajustes_depto_sector.csv',index=False,float_format='%.14g')
    sha={name:hashlib.sha256(Path(path).read_bytes()).hexdigest() for name,path in [
      ('h12_priors',priors_csv),('national_composition',national_csv),
      ('departmental_covariates',covariates_csv),('universe_audit',universe_csv)]}
    gate=dict(version='H13_2_2_18_EXPERIMENTAL_1',publication_gate='BLOCKED_NO_DEPARTMENT_SECTOR_TRUTH',
              description='Exact constrained sector totals, not validated geographical allocations',
              months=len(periods),departments=len(departments),sectors=len(SECTORS),
              scenarios=list(SCENARIOS),rows=len(out),
              two_universe_sector_closure_from='2001-01',pre2001_geih_constraint='NOT_APPLIED',
              max_full_national_error_persons=float(audit.max_full_national_error_persons.max()),
              max_geih_national_error_persons_post2000=float(audit.max_geih_national_error_persons.max()),
              max_full_department_error_persons=float(audit.max_full_dept_error_persons.max()),
              max_geih_department_error_persons=float(audit.max_geih_dept_error_persons.max()),
              max_adjustment_pp=float(audit.max_abs_correction_pp.max()),
              max_joint_minus_full_only_adjustment_pp=float(full_only_comparison.joint_minus_full_only_max_share_pp.max()),
              operational_large_adjustment_alert_threshold_pp=3.0,
              months_exceeding_3pp=int((audit.max_abs_correction_pp>3).sum()),
              cells_exceeding_3pp=int((out.adjustment_pp.abs()>3).sum()),
              large_adjustments_require_substantive_review=True,
              identical_composition_for_both_universes=True,
              not_departmental_observations=True,sha256_inputs=sha)
    (output/'13_puerta_calidad.json').write_text(json.dumps(gate,indent=2,ensure_ascii=False),encoding='utf-8')
    return gate
