"""Audit of the informality methodological sequence (13→National→23→ML→closure).

It neither estimates nor corrects figures. It uses the candidate products and
the frozen labor market, and separates accounting gates, historical evidence
and ML readiness.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from icml.domain.cutoff import ACTIVE_CUTOFF, FIRST_MONTH, month_periods

from icml.informality.urban_backcast import FIRST_13

CALENDAR = month_periods()
DIRECT_23 = 23
PERIOD_START = FIRST_MONTH
PERIOD_END = ACTIVE_CUTOFF


def _hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f'File required by the audit: {path}')
    return pd.read_csv(path, encoding='utf-8-sig', dtype={'period': 'string'})


def _complete(df: pd.DataFrame, entity: str, count: int) -> tuple[bool, int]:
    if df.duplicated([entity, 'period']).any():
        return False, int(df.duplicated([entity, 'period']).sum())
    if len(df) != count * len(CALENDAR) or df[entity].nunique() != count:
        return False, abs(count * len(CALENDAR)-len(df))
    expected = set(CALENDAR.astype(str))
    bad = sum(set(g.period.astype(str)) != expected for _, g in df.groupby(entity))
    return bad == 0, int(bad)


def _counts_check(frame: pd.DataFrame, labor: pd.DataFrame, keys: list[str],
                  id_col: str, toler: float = 0.001) -> dict:
    require = ['employed_frozen','informal_estimated','formal_estimated']
    if frame[require].isna().any().any():
        return {'passed': False, 'max_residual_persons': None,
                'missing_rows': int(frame[require].isna().any(axis=1).sum())}
    merged=frame.merge(labor[keys+['employed']],on=keys,validate='1:1',how='left',indicator=True)
    missing=int((merged['_merge']!='both').sum())
    diffs=np.concatenate([
        (merged['employed_frozen']-merged['employed']).abs().to_numpy(),
        (merged['informal_estimated']+merged['formal_estimated']-merged['employed_frozen']).abs().to_numpy()
    ])
    mx=float(np.nanmax(diffs)) if diffs.size and np.isfinite(diffs).any() else float('inf')
    negative=int((merged[['informal_estimated','formal_estimated']] < -toler).any(axis=1).sum())
    return {'passed': missing==0 and negative==0 and mx<toler,
            'max_residual_persons':mx,'missing_rows':missing,'negative_rows':negative}


def _temporal(df: pd.DataFrame, key: str, rate: str, *, level: str) -> tuple[pd.DataFrame,pd.DataFrame]:
    alerts=[]; breaks=[]
    for unit,g in df.groupby(key):
        g=g.sort_values('period').reset_index(drop=True)
        vals=pd.to_numeric(g[rate],errors='coerce').to_numpy(float)
        inf=pd.to_numeric(g['informal_estimated'],errors='coerce').to_numpy(float)
        months=g.period.astype(str).tolist()
        for i in range(1,len(g)):
            mom_pp=100*(vals[i]-vals[i-1])
            yoy_pp=100*(vals[i]-vals[i-12]) if i>=12 else np.nan
            ratio=(inf[i]/inf[i-1]) if inf[i-1]>0 else np.nan
            is_pct200=bool(np.isfinite(ratio) and (ratio>3 or ratio<1/3))
            if abs(mom_pp)>5 or (i>=12 and abs(yoy_pp)>15) or is_pct200:
                alerts.append({'level':level,'unit':str(unit),'period':months[i],
                    'change_mom_pp':float(mom_pp),'change_yoy_pp':float(yoy_pp),
                    'informal_level_ratio':float(ratio),'greater_than_200pct_equiv':is_pct200,
                    'source_regime_change':months[i].startswith('2021-'),
                    'pandemic_2020_2021':months[i][:4] in ('2020','2021'),
                    'decision':'REVIEW_NOT_AUTO_CORRECT'})
        # cambio de nivel sostenido: diferencia de 12 meses anteriores vs 12 siguientes;
        # picos locales separados por >=6 meses para evitar 12 alertas por el mismo evento.
        shifts=[]
        for i in range(12,len(vals)-12):
            delta=100*(float(np.mean(vals[i:i+12]))-float(np.mean(vals[i-12:i])))
            if abs(delta)>=5: shifts.append((i,delta))
        selected=[]
        for i,delta in sorted(shifts,key=lambda x:abs(x[1]),reverse=True):
            if all(abs(i-j)>=6 for j,_ in selected): selected.append((i,delta))
        for i,delta in selected:
            breaks.append({'level':level,'unit':str(unit),'period':months[i],
                'delta_12mo_means_pp':float(delta),
                'pandemic_2020_2021':months[i][:4] in ('2020','2021'),
                'near_definition_change_2021':months[i][:4] in ('2020','2021','2022'),
                'status':'POTENTIAL_BREAK_NOT_CAUSAL_PROOF'})
    alert_cols=['level','unit','period','change_mom_pp','change_yoy_pp','informal_level_ratio',
                'greater_than_200pct_equiv','source_regime_change','pandemic_2020_2021','decision']
    break_cols=['level','unit','period','delta_12mo_means_pp','pandemic_2020_2021',
                'near_definition_change_2021','status']
    return pd.DataFrame(alerts,columns=alert_cols),pd.DataFrame(breaks,columns=break_cols)


def audit(candidate:Path,cities_labor:Path,nationals_labor:Path,output:Path,
          previous_national:Path|None=None)->dict:
    """Produce audit trail; fails fast only for malformed inputs; never alters input."""
    candidate=Path(candidate);output=Path(output)
    inputs={str(p):_hash(p) for p in (candidate/'ciudades_informalidad_candidata.csv',
        candidate/'nacionales_informalidad_candidata.csv',candidate/'auditoria_ventanas_t5_2007_2021.csv',
        candidate/'auditoria_ventanas_nueva_2021_2026.csv',candidate/'auditoria_anclas_13_areas_t5.csv',
        candidate/'validacion_13_areas_ano_oculto.csv',candidate/'catalogo_donantes.csv',
        candidate/'auditoria_tradeoff_fidelidad_suavidad.csv',cities_labor,nationals_labor)}
    if previous_national is not None:
        inputs[str(previous_national)] = _hash(Path(previous_national))
    city=_load(candidate/'ciudades_informalidad_candidata.csv')
    nat=_load(candidate/'nacionales_informalidad_candidata.csv')
    cl=_load(cities_labor);nl=_load(nationals_labor)
    t5=_load(candidate/'auditoria_ventanas_t5_2007_2021.csv')
    new=_load(candidate/'auditoria_ventanas_nueva_2021_2026.csv')
    anchors=_load(candidate/'auditoria_anclas_13_areas_t5.csv')
    cv=_load(candidate/'validacion_13_areas_ano_oculto.csv')
    donors=_load(candidate/'catalogo_donantes.csv')
    trade=_load(candidate/'auditoria_tradeoff_fidelidad_suavidad.csv')
    checks=[]
    def record(code,stage,result,evidence,kind='CHECK'):
        checks.append({'gate':code,'stage':stage,'result':result,'evidence':evidence,'kind':kind})
    city_ok,city_bad=_complete(city,'city_code',33)
    nat_ok,nat_bad=_complete(nat,'national_type',2)
    record('G1','Coverage: 33 cities, 2 nationals','PASS' if city_ok and nat_ok else 'BLOCK',
           f'cities={len(city)}, nationals={len(nat)}, anomalies={city_bad+nat_bad}')
    record('G1B','Range and no nulls', 'PASS' if (
        city[['informality_rate','informal_estimated','formal_estimated']].notna().all().all() and
        nat[['informality_rate_estimated','informal_estimated','formal_estimated']].notna().all().all() and
        city.informality_rate.between(0,1).all() and nat.informality_rate_estimated.between(0,1).all()) else 'BLOCK',
        'Rates in [0,1], no null quantities')
    cc=_counts_check(city,cl,['period','city_code'],'city_code')
    nc=_counts_check(nat,nl,['period','national_type'],'national_type',toler=1.1)
    record('G4','Identities and frozen urban employment','PASS' if cc['passed'] else 'BLOCK',str(cc))
    record('G4B','Identities and frozen national employment','PASS' if nc['passed'] else 'BLOCK',str(nc))
    codes13=set(FIRST_13);direct=set(t5.city_code.dropna().astype(int))&set(new.city_code.dropna().astype(int))
    c13=city[city.city_code.isin(codes13)].copy()
    c23=city[city.city_code.isin(direct)].copy()
    record('G2','13 historical areas: source and evidence limit',
           'WARN','6 aggregate T5 anchors 2001–2006; the individual T10 ones are not T5. Non-existent DANE observations are not demanded.',
           'SOURCE_LIMITATION')
    record('G2C','Independent 13-city stage before the national one',
           'BLOCK','2.2.2 generates the joint urban candidate first and the national one afterwards; there is no approved and frozen 13-city gate before using it',
           'PIPELINE_COMPLETENESS')
    record('G2A','13 aggregate areas: reproduction of the T5 anchors',
           'PASS' if anchors.residual_pp.abs().max()<=0.1 else 'WARN',
           f'6 anchors, max residual={anchors.residual_pp.abs().max():.4f} pp; they do not validate the 13 cities separately')
    record('G2B','13 aggregate areas: held-out year validation',
           'PASS' if cv.holdout_error_pp.abs().mean()<=0.5 else 'WARN',
           f'MAE={cv.holdout_error_pp.abs().mean():.3f} pp, max={cv.holdout_error_pp.abs().max():.3f} pp; only 6 anchors')
    record('G3','Historical national: 13-area reference + old proxy',
           'WARN','A candidate with a definition bridge exists. The rate DANE_REFERENCIA=ICML_COMPLETO is a transfer, not evidence of equality')
    same=nat.pivot(index='period',columns='national_type',values='informality_rate_estimated')
    equal=bool(np.allclose(same['ICML_COMPLETO'],same['DANE_REFERENCIA'],atol=1e-12,rtol=0))
    record('G3B','Difference between national universes','WARN' if equal else 'PASS',
           f'identical national rates={equal}; they require a transfer evaluation')
    record('G3C','Historical national re-estimated after validating the 13 cities','BLOCK',
           'The individual quality of the 13 areas has to be shown before promoting the bridge to the national level',
           'METHODOLOGICAL_READINESS')
    record('G4C','23 cities with T5 windows and recent definition',
           'PASS' if len(direct)==DIRECT_23 else 'BLOCK',
           f'cities with individual sources={len(direct)}; expected mapping=23')
    record('G4D','10 synthetic/donor territories','WARN' if len(donors)==10 else 'BLOCK',
           f'donors={len(donors)}, maximum distance={donors.distance.max():.3f}; transfer validity not proven')
    record('G4E','Second backcast of the 23 cities using the previously reconstructed national',
           'BLOCK','The original has SplicingInformalityCities with the national as donor; 2.2.2 runs no later national→23 cities stage',
           'PIPELINE_COMPLETENESS')
    record('G5','Fidelity of the historical T5 windows','WARN' if t5.residual_pp.abs().max()>1 else 'PASS',
           f'{len(t5)} windows, MAE={t5.residual_pp.abs().mean():.3f} pp, max={t5.residual_pp.abs().max():.3f} pp')
    record('G5B','Recent GEIH windows (exact counts)','PASS' if new.residual_pp.abs().max()<1e-7 else 'BLOCK',
           f'{len(new)} windows, maximum rate error={new.residual_pp.abs().max():.2g} pp')
    record('G5C','Latent months: sensitivity to smoothness','WARN' if trade.exact_max_monthly_rate_jump_pp.max()>5 else 'PASS',
           f'exact peak={trade.exact_max_monthly_rate_jump_pp.max():.2f} pp, alternative={trade.regularized_max_monthly_rate_jump_pp.max():.2f} pp')
    record('G6','Cities+departments panel, labor, demography and clusters','BLOCK',
           'There is no 2.2.2 informality feature-target matrix; the original uses LaborMarketRateCalculator and clusters',
           'PIPELINE_COMPLETENESS')
    record('G6B','MLP vs urban signal, temporal LOGO, after the closure','BLOCK',
           'No trained/validated models nor 2.2.2 departmental predictions',
           'PIPELINE_COMPLETENESS')
    record('G7','Closure by factors over 33 departments, without touching employment','BLOCK',
           'The final product of 33 departments x 404 months is missing',
           'PIPELINE_COMPLETENESS')
    c_alert,c_break=_temporal(city,'city_code','informality_rate',level='city')
    n_alert,n_break=_temporal(nat,'national_type','informality_rate_estimated',level='national')
    alerts=pd.concat([df for df in (c_alert,n_alert) if not df.empty],ignore_index=True) if (len(c_alert)+len(n_alert)) else c_alert.copy()
    breaks=pd.concat([df for df in (c_break,n_break) if not df.empty],ignore_index=True) if (len(c_break)+len(n_break)) else c_break.copy()
    n200=int(alerts.greater_than_200pct_equiv.sum()) if len(alerts) else 0
    record('G5D','Extraordinary changes and possible breaks','WARN' if len(alerts) else 'PASS',
           f'alerts={len(alerts)}, >200% increase or symmetric fall={n200}, 12m breaks={len(breaks)}; no automatic correction')
    risk=[]
    for code,g in city.groupby('city_code'):
        a=c_alert[c_alert.unit==str(code)]
        b=c_break[c_break.unit==str(code)]
        risk.append({'city_code':int(code),'city_name':g.city_name.iloc[0],
             'belongs_to_13':int(code) in codes13,'has_DANE_individual_windows':int(code) in direct,
             'n_temporal_flags':len(a),'max_abs_mom_pp':float((100*g.sort_values('period').informality_rate.diff()).abs().max()),
             'n_structural_break_candidates':len(b),
             'more_than_200pct_level_flags':int(a.greater_than_200pct_equiv.sum()) if len(a) else 0,
             'uncertainty_historical':'HIGH_NO_CITY_ANCHOR_PRE_2001'})
    risk=pd.DataFrame(risk).sort_values(['n_temporal_flags','max_abs_mom_pp'],ascending=False)
    status='NOT_CERTIFIED_PIPELINE_INCOMPLETE' if any(x['result']=='BLOCK' for x in checks) else 'REVIEW_REQUIRED'
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('The audit does not overwrite previous runs')
    output.mkdir(parents=True,exist_ok=True)
    comparison=None
    if previous_national is not None:
        previous=_load(Path(previous_national))
        comparison=nat[['period','national_type','informality_rate_estimated']].merge(
            previous[['period','national_type','informality_rate_estimated']],
            on=['period','national_type'],how='outer',validate='1:1',indicator=True,
            suffixes=('_222','_221'))
        if (comparison['_merge'] != 'both').any():
            raise ValueError('Vintages nacionales no comparables: distinta cobertura')
        comparison['change_pp']=100*(comparison.informality_rate_estimated_222-
                                      comparison.informality_rate_estimated_221)
        comparison['period_group']=np.select([
            comparison.period.str[:4].astype(int).le(2000),
            comparison.period.str[:4].astype(int).le(2006),
            comparison.period.str[:4].astype(int).le(2020)],
            ['1993-2000','2001-2006','2007-2020'],default='2021-2026')
        record('G3D','Historical sensitivity against the 2.2.1 candidate','WARN',
               f'maximum difference={comparison.change_pp.abs().max():.3f} pp, '
               '2011–2020 and the earlier stretch depend on bridge decisions')
    artifacts={
       'auditoria_puertas.csv':pd.DataFrame(checks),
       'alertas_temporales.csv':alerts,
       'quiebres_potenciales.csv':breaks,
       'riesgo_por_ciudad.csv':risk,
       'diagnostico_13_ciudades_no_canonico.csv':c13,
       'diagnostico_23_ciudades_no_canonico.csv':c23,
    }
    if comparison is not None:
        artifacts['comparacion_nacional_2_2_1_vs_2_2_2.csv']=comparison.drop(columns=['_merge'])
    # Refresh the gates after the vintage comparison, when requested.
    artifacts['auditoria_puertas.csv']=pd.DataFrame(checks)
    for name,df in artifacts.items(): df.to_csv(output/name,index=False,encoding='utf-8-sig',lineterminator='\n')
    if any(_hash(Path(p))!=h for p,h in inputs.items()): raise RuntimeError('An input was modified')
    report={'status':status,'version':'2.2.3.dev0-quality-only','source_candidate':'2.2.2.dev0',
        'audit_scope':'13_ciudades_nacional_23_ciudades_variables_MLP_departamentos',
        'n_cities':33,'n_direct_DANE_cities':len(direct),'n_donor_cities':len(donors),
        'rows_13_diagnostic':len(c13),'rows_23_diagnostic':len(c23),
        'nacional_rows':len(nat),'n_flags':len(alerts),'n_gt_200pct_equivalent':n200,
        'n_potential_breaks':len(breaks),'status_counts':pd.DataFrame(checks).result.value_counts().to_dict(),
        'prior_national_max_abs_change_pp':float(comparison.change_pp.abs().max()) if comparison is not None else None,
        'max_abs_monthly_city_pp':float(risk.max_abs_mom_pp.max()),
        'max_abs_recent_exact_city_pp':float(trade.exact_max_monthly_rate_jump_pp.max()),
        'input_sha256':inputs,'output_sha256':{n:_hash(output/n) for n in artifacts},
        'immutable_inputs_verified':True,
        'warning':'The 13 and 23 views are DIAGNOSTIC cuts of a simultaneous candidate, NOT a certified sequential execution.'}
    (output/'resumen.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
