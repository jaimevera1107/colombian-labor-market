"""H10: source-aware 2001-2015 moving-window CIIU3/CIIU4 vintage bridge.

DANE monthly published CIIU4 observations remain untouched. Historical CIIU3
rolling-quarter rows are never promoted to directly observed monthly rows.
No microdata, interpolation, or artificial monthwise smoothing is performed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from icml.domain.cutoff import month_periods

HIST_CODES = (
    'AGRICULTURA_PESCA', 'MINERIA', 'INDUSTRIA', 'SERVICIOS_PUBLICOS',
    'CONSTRUCCION', 'COMERCIO_HOTELES', 'TRANSPORTE_COMUNICACIONES',
    'FINANCIERAS', 'INMOBILIARIAS_EMPRESARIALES',
    'COMUNITARIOS_PERSONALES', 'NO_INFO',
)
RECENT_CODES = (
    'A', 'B_D_E_COMBINED', 'C', 'F', 'G', 'I', 'H', 'J', 'K', 'L',
    'M_N', 'O_P_Q', 'R_S_T_U', 'NO_INFO',
)
FINAL_14 = ('A','B','C','D_E','F','G','H','I','J','K','L','M_N','O_P_Q','R_S_T_U')
# Comparable *broad* buckets, not asserted exact CIIU Rev 3 -> Rev 4 codes.
BUCKET_DEFINITION = {
    'AGRICULTURA_PESCA':'A', 'MINERIA':'B_DE', 'SERVICIOS_PUBLICOS':'B_DE',
    'INDUSTRIA':'C', 'CONSTRUCCION':'F', 'COMERCIO_HOTELES':'G_I',
    'TRANSPORTE_COMUNICACIONES':'H_J', 'FINANCIERAS':'K',
    'INMOBILIARIAS_EMPRESARIALES':'L_MN',
    'COMUNITARIOS_PERSONALES':'OPQ_RSTU','NO_INFO':'NO_INFO',
}
RECENT_BUCKET = {
    'A':'A','B_D_E_COMBINED':'B_DE','C':'C','F':'F',
    'G':'G_I','I':'G_I','H':'H_J','J':'H_J','K':'K',
    'L':'L_MN','M_N':'L_MN','O_P_Q':'OPQ_RSTU',
    'R_S_T_U':'OPQ_RSTU','NO_INFO':'NO_INFO',
}
PARTS = {
    'AGRICULTURA_PESCA':('A',), 'MINERIA':('B',),
    'SERVICIOS_PUBLICOS':('D_E',), 'INDUSTRIA':('C',),
    'CONSTRUCCION':('F',),'COMERCIO_HOTELES':('G','I'),
    'TRANSPORTE_COMUNICACIONES':('H','J'),
    'FINANCIERAS':('K',),'INMOBILIARIAS_EMPRESARIALES':('L','M_N'),
    'COMUNITARIOS_PERSONALES':('O_P_Q','R_S_T_U'),
    'NO_INFO':('NO_INFO',),
}
CLASSIFICATION_WARNINGS = {
    'A':'CIIU_REV3_TO_REV4_CLASSIFICATION_SHIFT_NOT_EXACT',
    'B_DE':'MINING_AND_UTILITIES_COMBINED_FOR_VINTAGE_ANCHOR',
    'C':'CIIU_REV3_TO_REV4_CLASSIFICATION_SHIFT_NOT_EXACT',
    'F':'CIIU_REV3_TO_REV4_CLASSIFICATION_SHIFT_NOT_EXACT',
    'G_I':'LEGACY_COMMERCE_HOTELS_MODERN_G_I_APPROXIMATION',
    'H_J':'LEGACY_TRANSPORT_COMMUNICATIONS_MODERN_H_J_APPROXIMATION',
    'K':'CIIU_REV3_TO_REV4_CLASSIFICATION_SHIFT_NOT_EXACT',
    'L_MN':'LEGACY_BUSINESS_REAL_ESTATE_MODERN_L_MN_APPROXIMATION',
    'OPQ_RSTU':'LEGACY_SOCIAL_PERSONAL_MODERN_OPQ_RSTU_APPROXIMATION',
    'NO_INFO':'NOT_A_SECTOR',
}


def check_old(old: pd.DataFrame, original_xls: Path|None=None) -> pd.DataFrame:
    req={'period_start','period_end','domain','legacy_sector_code',
         'employed_persons','window_months','source_sha256','sector_system'}
    if req-set(old):raise ValueError('HISTORICAL_COLUMNS_MISSING')
    sub=old.loc[old.domain.eq('NACIONAL')].copy()
    expected=pd.period_range('2001-09','2015-03',freq='M').strftime('%Y-%m')
    if set(sub.period_end)!=set(expected) or len(sub)!=163*len(HIST_CODES):
        raise ValueError('HISTORICAL_WINDOWS_OR_CARDINALITY')
    if (sub.duplicated(['period_end','legacy_sector_code']).any() or
        set(sub.legacy_sector_code)!=set(HIST_CODES)):
        raise ValueError('HISTORICAL_KEYS_OR_CATEGORIES')
    if not sub.window_months.eq(3).all():raise ValueError('ROLLING_SOURCE_MISLABELLED')
    if not sub.sector_system.str.contains('Rev3').all():raise ValueError('HISTORICAL_CIIU_INVALID')
    expected_start=(pd.PeriodIndex(sub.period_end,freq='M')-2).strftime('%Y-%m')
    if not np.all(sub.period_start.to_numpy()==expected_start):
        raise ValueError('ROLLING_WINDOW_DATES_INVALID')
    values=sub.employed_persons.to_numpy(float)
    if not np.isfinite(values).all() or (values<0).any():
        raise ValueError('HISTORICAL_VALUES_INVALID')
    hashes=set(sub.source_sha256)
    if len(hashes)!=1:raise ValueError('HISTORICAL_MULTIPLE_UNAPPROVED_VINTAGES')
    if original_xls is not None:
        digest=hashlib.sha256(Path(original_xls).read_bytes()).hexdigest()
        if digest!=next(iter(hashes)):raise ValueError('HISTORICAL_XLS_SHA_MISMATCH')
    return sub.sort_values(['period_end','legacy_sector_code']).reset_index(drop=True)


def check_recent(recent:pd.DataFrame, monthly_totals:pd.DataFrame)->tuple[pd.DataFrame,pd.DataFrame]:
    r=recent.copy(); c=monthly_totals.copy()
    if not {'period','sector_code','employed_persons','window_months','temporal_support'} <=set(r):
        raise ValueError('RECENT_COLUMNS_MISSING')
    if not r.window_months.eq(1).all() or not r.temporal_support.eq('calendar_month').all():
        raise ValueError('RECENT_MUST_BE_DIRECT_MONTHLY')
    if r.duplicated(['period','sector_code']).any() or set(r.sector_code)!=set(RECENT_CODES)-{'NO_INFO'}:
        raise ValueError('RECENT_SECTOR_KEY_INVALID')
    if r.groupby('period').sector_code.nunique().ne(13).any():
        raise ValueError('RECENT_NOT_13_GROUPS')
    if c.duplicated('period').any() or not {'period','no_informa_persons','occupied_official_persons'}<=set(c):
        raise ValueError('RECENT_TOTALS_INVALID')
    if 'domain' in r.columns and not r.domain.eq('total_nacional_GEIH').all():
        raise ValueError('RECENT_SOURCE_UNIVERSE_NOT_GEIH_NATIONAL')
    if 'classification' in r.columns and not r.classification.eq('CIIU_Rev4_AC').all():
        raise ValueError('RECENT_SOURCE_CLASSIFICATION_NOT_CIIU4')
    closure=r.groupby('period').employed_persons.sum().rename('group_total').to_frame().join(
        c.set_index('period')[['no_informa_persons','occupied_official_persons']],how='left')
    if closure.isna().any().any() or (closure.group_total+closure.no_informa_persons-
           closure.occupied_official_persons).abs().max()>10:
        raise ValueError('RECENT_MONTHLY_TOTALS_DONT_RECONCILE')
    return r,c


def overlap_and_crosswalk(old:pd.DataFrame,recent:pd.DataFrame,totals:pd.DataFrame):
    old_m=old.loc[old.period_end.eq('2015-03')].copy()
    if len(old_m)!=len(HIST_CODES):raise ValueError('2015_SOURCE_OVERLAP_MISSING')
    new=recent.loc[recent.period.isin(['2015-01','2015-02','2015-03'])]
    if new.period.nunique()!=3:raise ValueError('2015_RECENT_OVERLAP_MISSING')
    nvals=new.groupby('sector_code').employed_persons.mean().to_dict()
    no_info=totals.loc[totals.period.isin(['2015-01','2015-02','2015-03']),'no_informa_persons']
    if len(no_info)!=3:raise ValueError('2015_NO_INFO_MISSING')
    nvals['NO_INFO']=float(no_info.mean())
    ov=old_m.groupby('legacy_sector_code').employed_persons.sum().to_dict()
    old_total=sum(ov.values());new_total=sum(nvals.values())
    rows=[];ratios={};group_splits={}
    for bucket in dict.fromkeys(BUCKET_DEFINITION.values()):
        keys=[k for k,v in BUCKET_DEFINITION.items() if v==bucket]
        target=[k for k,v in RECENT_BUCKET.items() if v==bucket]
        lv=sum(ov[k] for k in keys);nv=sum(nvals[k] for k in target)
        if lv<=0 or nv<=0:raise ValueError('2015_BRIDGE_BUCKET_ZERO '+bucket)
        old_share=lv/old_total;new_share=nv/new_total
        ratios[bucket]=new_share/old_share
        rows.append(dict(bucket=bucket,old_codes='|'.join(keys),recent_codes='|'.join(target),
                         historical_2015_count=lv,recent_2015_count=nv,
                         old_share=old_share,recent_share=new_share,
                         difference_pp=(new_share-old_share)*100,
                         vintage_multiplier=ratios[bucket],
                         status=CLASSIFICATION_WARNINGS[bucket],
                         old_vintage_2015_total=old_total,new_vintage_2015_total=new_total))
        group_splits[bucket]={k:nvals[k]/nv for k in target}
    crosswalk=[]
    for legacy,bucket in BUCKET_DEFINITION.items():
        for newcode in PARTS[legacy]:
            source='LEGACY_MINING_VS_UTILITIES_SPLIT' if legacy in {'MINERIA','SERVICIOS_PUBLICOS'} else (
               'RECENT_2015_GROUP_RATIO_ASSUMED_CONSTANT_BACKWARD' if len(PARTS[legacy])>1 else 'DIRECT_NAME_APPROXIMATE_CIIU_REVISION')
            crosswalk.append(dict(legacy_code=legacy,common_bucket=bucket,modern_code=newcode,
                                  split_basis=source,classification_warning=CLASSIFICATION_WARNINGS[bucket],
                                  not_independent_official_14_observation=True))
    return pd.DataFrame(rows),pd.DataFrame(crosswalk),ratios,group_splits,ov,nvals


def _national_rolling(nationals:pd.DataFrame)->pd.DataFrame:
    req={'period','national_type','employed'}
    if req-set(nationals):raise ValueError('NATIONAL_REQUIRED_COLUMNS_MISSING')
    n=nationals.loc[nationals.national_type.isin(['ICML_COMPLETO','DANE_REFERENCIA'])].copy()
    if n.duplicated(['period','national_type']).any():raise ValueError('NATIONAL_DUPLICATED_MONTHS')
    if (n.employed<=0).any():raise ValueError('NATIONAL_EMPLOYMENT_NOT_POSITIVE')
    frames=[]
    for u,d in n.groupby('national_type'):
        d=d.sort_values('period').reset_index(drop=True)
        if not np.all(np.diff(pd.PeriodIndex(d.period,freq='M').asi8)==1):
            raise ValueError('NATIONAL_MONTHLY_GAPS')
        d['rolling_employed_persons']=d.employed.rolling(3,min_periods=3).mean()
        frames.append(d[['period','national_type','rolling_employed_persons']])
    return pd.concat(frames,ignore_index=True).rename(columns={'period':'period_end'})


def make_candidates(old:pd.DataFrame,ratios:dict,split:dict, recent_vals:dict,
                    nationals:pd.DataFrame,*,strengths=(0.0,0.5,1.0)) -> pd.DataFrame:
    levels=old.pivot(index='period_end',columns='legacy_sector_code',values='employed_persons')
    old_group=levels.groupby(BUCKET_DEFINITION,axis=1).sum() if False else pd.DataFrame({
        bucket:levels[[k for k,v in BUCKET_DEFINITION.items() if v==bucket]].sum(axis=1)
        for bucket in dict.fromkeys(BUCKET_DEFINITION.values())})
    source_total=old_group.sum(axis=1)
    target=_national_rolling(nationals)
    out=[]
    target_keys=set(target.period_end)
    if not set(old_group.index).issubset(target_keys):raise ValueError('NATIONAL_REFERENCE_MISSING_WINDOW')
    for strength in strengths:
        scen='RAW_HIST_VINTAGE' if strength==0 else ('HALF_2015_BRIDGE' if strength==0.5 else 'FULL_2015_BRIDGE')
        correction=pd.Series({b:ratios[b]**strength for b in old_group.columns})
        mixed=old_group.mul(correction,axis=1)
        mixed=mixed.div(mixed.sum(axis=1),axis=0)  # retains all monthly-window observed composition before adjustment
        shares={code:pd.Series(0.0,index=mixed.index) for code in (*FINAL_14,'NO_INFO')}
        for legacy,bucket in BUCKET_DEFINITION.items():
            # Different groups in B_DE retain actual old-vintage mining / utilities ratio in each window.
            within_old=levels[legacy]/old_group[bucket]
            within_old=within_old.fillna(0)
            for newcode in PARTS[legacy]:
                if bucket=='B_DE':split_share=1.0
                else:split_share=split[bucket][newcode]
                shares[newcode]=shares[newcode]+mixed[bucket]*within_old*split_share
        shareframe=pd.DataFrame(shares)
        if not np.allclose(shareframe.sum(axis=1),1,atol=1e-12):
            raise ValueError('BRIDGE_SHARES_NOT_SUM_ONE')
        for _,item in target.loc[target.period_end.isin(shareframe.index)].iterrows():
            p=item.period_end;u=item.national_type;e=float(item.rolling_employed_persons)
            for code,sh in shareframe.loc[p].items():
                status=('ASSUMED_2015_SUBSPLIT_WITH_RETROPOLATED_CIIU_COMPOSITION'
                    if code in {'G','I','H','J','L','M_N','O_P_Q','R_S_T_U'}
                    else 'RETROPOLATED_CIIU_REVISION__NOT_DIRECT_OBSERVATION')
                if code in {'B','D_E'}:
                    status='LEGACY_CIIU3_MINING_UTILITIES_SPLIT__NOT_MODERN_DIRECT'
                if code=='NO_INFO':status='LEGACY_NONRESPONSE_REWEIGHTED'
                out.append(dict(period_start=(pd.Period(p,freq='M')-2).strftime('%Y-%m'),
                    period_end=p,national_type=u,scenario=scen,bridge_strength=strength,
                    sector_code=code,sector_share=float(sh),
                    reconstructed_window_persons=float(sh)*e,
                    rolling_3m_occupied_reference_persons=e,
                    old_vintage_rolling_3m_occupied_persons=float(source_total.loc[p]),
                    temporal_support='moving_3m',window_months=3,
                    observation_status=status,
                    is_official_monthly_sector_observation=False,
                    is_direct_CIIU4_sector_observation=False,
                    single_model_universe='ICML_COMPLETO',
                    bridge_policy=('ICML_REFERENCE_DENOMINATOR' if u=='ICML_COMPLETO'
                                   else 'REPRESENTED_GEIH_DERIVED_FROM_SAME_COMPOSITION'),
                    source_window_observed=True))
    return pd.DataFrame(out).sort_values(['scenario','national_type','period_end','sector_code']).reset_index(drop=True)


def run(*,historic_csv:Path,recent_monthly_csv:Path,recent_totals_csv:Path,
        nationals_csv:Path,source_xls:Path,output:Path)->dict:
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    old=check_old(pd.read_csv(historic_csv,encoding='utf-8-sig'),source_xls)
    recent,totals=check_recent(pd.read_csv(recent_monthly_csv,encoding='utf-8-sig'),
                               pd.read_csv(recent_totals_csv,encoding='utf-8-sig'))
    overlap,crosswalk,ratios,split,old_vals,new_vals=overlap_and_crosswalk(old,recent,totals)
    n=pd.read_csv(nationals_csv,encoding='utf-8-sig')
    candidates=make_candidates(old,ratios,split,new_vals,n)
    controls=candidates.groupby(['scenario','national_type','period_end'],as_index=False).agg(
        sectors=('sector_code','nunique'),all_groups=('reconstructed_window_persons','sum'),
        target=('rolling_3m_occupied_reference_persons','first'),
        max_is_observed_monthly=('is_official_monthly_sector_observation','max'))
    controls['identity_residual_people']=controls.all_groups-controls.target
    if not controls.sectors.eq(15).all() or controls.identity_residual_people.abs().max()>1e-5:
        raise ValueError('MARGIN_CLOSURE_FAILED')
    # Sensitivity between full and zero correction (all 14 sector shares; excludes NO_INFO).
    pivot=candidates.loc[candidates.national_type.eq('ICML_COMPLETO') & candidates.sector_code.ne('NO_INFO')].pivot(
        index=['period_end','sector_code'],columns='scenario',values='sector_share').reset_index()
    pivot['sensitivity_pp']=100*(pivot.FULL_2015_BRIDGE-pivot.RAW_HIST_VINTAGE)
    # Full-bridge Q1 2015 common buckets match new monthly Q1 by *construction*.
    full=candidates.loc[candidates.scenario.eq('FULL_2015_BRIDGE') & candidates.national_type.eq('DANE_REFERENCIA') & candidates.period_end.eq('2015-03')]
    groups=full.assign(bucket=full.sector_code.map({
        'A':'A','B':'B_DE','D_E':'B_DE','C':'C','F':'F','G':'G_I','I':'G_I',
        'H':'H_J','J':'H_J','K':'K','L':'L_MN','M_N':'L_MN',
        'O_P_Q':'OPQ_RSTU','R_S_T_U':'OPQ_RSTU','NO_INFO':'NO_INFO'})).groupby('bucket').sector_share.sum()
    new_g=pd.Series({k:v/sum(new_vals.values()) for k,v in new_vals.items()}).groupby(RECENT_BUCKET).sum()
    assert max(abs(groups[b]-new_g[b]) for b in new_g.index)<1e-12
    months=month_periods().strftime('%Y-%m')
    coverage=pd.DataFrame({'period':months})
    coverage['old_CIIU3_rolling_window_ends_here']=coverage.period.isin(set(old.period_end))
    coverage['recent_CIIU4_13_direct_calendar_month']=coverage.period.isin(set(recent.period))
    coverage['historic_14_CIIU4_months_directly_observed']=False
    coverage['historic_14_CIIU4_window_candidate']=coverage.old_CIIU3_rolling_window_ends_here
    coverage['temporal_evidence_status']=np.select([
        coverage.old_CIIU3_rolling_window_ends_here & coverage.recent_CIIU4_13_direct_calendar_month,
        coverage.old_CIIU3_rolling_window_ends_here,
        coverage.recent_CIIU4_13_direct_calendar_month],
        ['OVERLAP_CIIU3_MOVING_WINDOW_AND_CIIU4_DIRECT_MONTH',
         'CIIU3_ROLLING_WINDOW_ONLY_NOT_A_CALENDAR_MONTH',
         'CIIU4_DIRECT_MONTHLY_13_GROUPS_ONLY'],
        default='NO_NATIONAL_SECTOR_OBSERVATION_VERIFIED')
    labels=candidates.groupby('scenario').apply(
        lambda d: int(d.period_end.nunique()),include_groups=False).to_dict()
    # Original source only; working source is normalized CSV and hash-protected xls.
    audit={'stage':'H10_SOURCE_AWARE_VINTAGE_BRIDGE_2001_2015','historical_source_sha256':hashlib.sha256(Path(source_xls).read_bytes()).hexdigest(),
        'source_reference_periods':int(old.period_end.nunique()),'observed_old_CIIU3_groups':len(HIST_CODES)-1,
        'modern_months_direct_13_groups':int(recent.period.nunique()),
        'common_2015_buckets':int(len(overlap)),
        'historical_14_CIIU4_direct_months_observed':0,
        'historical_14_experimental_rolling_window_rows':int(len(candidates)),
        'scenarios':labels,'max_reconciliation_residual_people':float(controls.identity_residual_people.abs().max()),
        'max_compositional_scenario_difference_pp':float(pivot.sensitivity_pp.abs().max()),
        'max_2015_overlap_original_difference_pp':float(overlap.difference_pp.abs().max()),
        '2015_group_overlap_exact_after_bridge_BY_CONSTRUCTION':True,
        'current_monthly_observations_modified':False,'historical_window_relabelled_as_month':False,
        'source_issue_2004_01':'Historical national 2004-01 window-vs-monthly total discrepancy preserved in source; source vintages are not corrected.',
        'status':'EXPERIMENTAL_HISTORIC_WINDOW_BRIDGE_NOT_MONTHLY_NOT_CLASSIFICATION_CERTIFIED',
        'method':'one_2015_Q1_compositional_log_ratio_bridge__fixed_within_legacy_group_splits__no_temporal_smoothing',
        'notes':'2015 Q1 matching is fitted and not independent validation. Quarter-to-month inverse not identified without extra assumptions. Cross-universe same-sector-share transfer is an assumption, not a fact.'}
    for name,df in [
        ('10_crosswalk_CIIU3_to_14_CIIU4_CON_SUPUESTOS.csv',crosswalk),
        ('10_empalme_2015_grupos_comunes.csv',overlap),
        ('10_candidatos_historicos_2001_2015_TRIMESTRES_NO_MESES.csv',candidates),
        ('10_auditoria_margenes_2001_2015.csv',controls),
        ('10_sensibilidad_historica_escenarios_pp.csv',pivot),
        ('10_cobertura_temporal_1993_2026_CON_EVIDENCIA.csv',coverage)]:
        df.to_csv(output/name,index=False,encoding='utf-8-sig',float_format='%.12g')
    (output/'10_puerta_empalme.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return audit
