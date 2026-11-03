"""H10 historic DANE GEIH annex contract: preserve observed temporal support.

No microdata. No silent rolling-quarter -> calendar-month conversion. The
historical publication index is NOT an observations dataset. Only parsed and
source-traceable records from real annexes may enter the historical evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
from icml.domain.cutoff import month_periods

DANE_INDEX = ('https://www.dane.gov.co/index.php/estadisticas-por-tema/'
              'mercado-laboral/empleo-y-desempleo/geih-historicos')
DANE_FILE_PREFIX = 'https://www.dane.gov.co/files/investigaciones/boletines/ech/ech/'
KNOWN_VERIFIED_DECEMBER_URLS = {
    (2007, 4): 'anexo_ech_abr07.xls',
    (2008, 2): 'anexo_ech_feb08.xls',
    (2009, 12): 'anexo_ech_dic09.xls',
    (2010, 12): 'anexo_ech_dic10.xls',
    (2011, 12): 'anexo_ech_dic11.xls',
    (2012, 12): 'anexo_ech_dic12.xls',
    (2013, 12): 'anexo_ech_dic13.xls',
    (2014, 12): 'anexo_empleo_dic_14.xls',
}
PUBLISHED = {2007: [4], 2008: [2], 2009: [1, 4, 5, 6, 7, 10, 11, 12],
             **{y:list(range(1,13)) for y in range(2010,2015)}}
SUPPORT_MONTHS = {'calendar_month': 1, 'moving_3m': 3, 'annual': 12}
REQUIRED = {'source_id','source_file','source_sha256','source_url',
            'domain','ciiu_revision','source_branch','mapped_sector_code',
            'mapping_status','source_review_status','period_start','period_end','temporal_support',
            'value','unit'}
FINAL_CODES = {'A','B','C','D_E','F','G','H','I','J','K','L',
               'M_N','O_P_Q','R_S_T_U'}


def publication_inventory() -> pd.DataFrame:
    """An annex link is NOT proof of a monthly sector observation."""
    out=[]
    for y, months in PUBLISHED.items():
        for m in months:
            fname=KNOWN_VERIFIED_DECEMBER_URLS.get((y,m))
            out.append({'publication_period':f'{y}-{m:02d}',
                 'source_index':DANE_INDEX,
                 'verified_file_url':DANE_FILE_PREFIX+fname if fname else '',
                 'link_status':'DIRECT_LINK_VERIFIED' if fname else 'LISTED_ON_DANE_INDEX',
                 'annex_locally_parsed':False,
                 'sector_data_identified':False,
                 'month_observed':False,
                 'source_domain_verified':False,
                 'ciiu_revision_verified':False,
                 'notes':('Published annex may contain historic data; the publication date '
                          'is not its temporal measurement support.')})
    return pd.DataFrame(out).sort_values('publication_period').reset_index(drop=True)


def _month_diff(first: str, last: str) -> int:
    try:
        a=pd.Period(first,freq='M');b=pd.Period(last,freq='M')
        return b.ordinal-a.ordinal+1
    except Exception as e:
        raise ValueError('FECHA_INVALIDA: require YYYY-MM') from e


def validate_annex_observations(data: pd.DataFrame, source_files: Path|None = None) -> pd.DataFrame:
    """Validate user-transcribed annex rows with *explicit* year/month support.

    A verified source sha must match a locally available original annex file. Rows
    with unavailable originals may be stored as candidates, never promoted to
    an official verified observation. Historical branches without deterministic
    CIIU equivalence stay UNMAPPED. Numeric values are not inferred or smoothed.
    """
    if len(data)==0:
        return pd.DataFrame(columns=sorted(REQUIRED)+['value_persons','sha256_checked','eligible_anchor','monthly_direct','observation_status'])
    absent=REQUIRED-set(data.columns)
    if absent:
        raise ValueError('CONTRATO_FALTANTE: '+', '.join(sorted(absent)))
    df=data.copy()
    for col in ('source_id','source_file','source_sha256','source_url','domain',
                'ciiu_revision','source_branch','mapped_sector_code',
                'mapping_status','source_review_status','period_start','period_end','temporal_support','unit'):
        df[col]=df[col].fillna('').astype(str).str.strip()
    for col in ('source_id','source_file','source_url','domain','source_branch','ciiu_revision'):
        if df[col].eq('').any():
            raise ValueError('PROCEDENCIA_INCOMPLETA: '+col)
    if not df.temporal_support.isin(SUPPORT_MONTHS).all():
        raise ValueError('SOPORTE_TEMPORAL_DESCONOCIDO')
    months=df.apply(lambda x:_month_diff(x.period_start,x.period_end),axis=1)
    wanted=df.temporal_support.map(SUPPORT_MONTHS).astype(int)
    if not (months==wanted).all():
        raise ValueError('VENTANA_INCOMPATIBLE: calendar_month=1, moving_3m=3, annual=12')
    if not df.unit.isin(['persons','thousands_persons']).all():
        raise ValueError('UNIDADES_INCOMPATIBLES: persons or thousands_persons')
    vals=pd.to_numeric(df['value'],errors='coerce')
    if not np.isfinite(vals).all() or (vals<0).any():
        raise ValueError('VALOR_INVALIDO: nonnegative finite numbers required')
    df['value_persons']=vals.to_numpy()*np.where(df.unit=='thousands_persons',1000,1)
    if not df.mapping_status.isin(['DIRECT_VERIFIED','AGGREGATE_ONLY','UNMAPPED']).all():
        raise ValueError('HOMOLOGACION_INCORRECTA')
    direct=df.mapping_status=='DIRECT_VERIFIED'
    if (direct & ~df.mapped_sector_code.isin(FINAL_CODES)).any():
        raise ValueError('CODIGO_CIIU_NO_HOMOLOGADO')
    if ((~direct) & df.mapped_sector_code.ne('')).any():
        raise ValueError('NO_ASIGNAR_CODIGO_A_CATEGORIA_AMBIGUA')
    keys=['source_id','domain','period_start','period_end','source_branch','ciiu_revision']
    if df.duplicated(keys).any():
        raise ValueError('OBSERVACIONES_DUPLICADAS: '+','.join(keys))
    if not df.source_review_status.isin(['REVIEWED_OFFICIAL_ANNEX','UNREVIEWED']).all():
        raise ValueError('REQUIERE_REVISION_DE_FUENTE')
    df['sha256_checked']=False
    if source_files is not None:
        base=Path(source_files).resolve()
        for (fname,sha), idx in df.groupby(['source_file','source_sha256']).groups.items():
            if not re.fullmatch('[a-fA-F0-9]{64}',sha):
                raise ValueError('HASH_FUENTE_INVALIDO')
            # No traversal/symlinks; read only a file directly inside source folder.
            target=(base/fname).resolve()
            if not target.is_relative_to(base) or Path(fname).name!=fname:
                raise ValueError('RUTA_FUENTE_INSEGURA')
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest().lower()!=sha.lower():
                    raise ValueError('HASH_FUENTE_NO_COINCIDE: '+fname)
                df.loc[idx,'sha256_checked']=True
    df['eligible_anchor']=(df.sha256_checked & direct & df.source_review_status.eq('REVIEWED_OFFICIAL_ANNEX'))
    df['observation_status']=np.where(df.eligible_anchor,'DANE_ANNEX_SOURCE_HASH_AND_REVIEW_CONFIRMED',
                                      'ANNEX_CANDIDATE_UNVERIFIED__NOT_ANCHOR')
    df['monthly_direct']=df.temporal_support.eq('calendar_month') & df.eligible_anchor
    return df.sort_values(keys).reset_index(drop=True)


def audit_overlap(historical: pd.DataFrame, monthly_recent: pd.DataFrame) -> pd.DataFrame:
    """Compare ONLY exact compatible calendar-month classification/domain pairs."""
    columns=['period','sector_code','hist_value_persons','recent_value_persons','diff_people','comparison_status']
    if historical.empty:return pd.DataFrame(columns=columns)
    approved=historical.loc[historical.monthly_direct &
                            historical.domain.eq('total_nacional_GEIH')].copy()
    if approved.empty:return pd.DataFrame(columns=columns)
    approved['period']=approved.period_start
    approved=approved.rename(columns={'mapped_sector_code':'sector_code','value_persons':'hist_value_persons'})
    recent=monthly_recent.rename(columns={'employed_persons':'recent_value_persons'})
    # Source CIIU revision must be explicitly comparable for direct join.
    approved=approved.loc[approved.ciiu_revision.eq('CIIU_Rev4_AC')]
    merged=approved.merge(recent[['period','sector_code','recent_value_persons']],
        on=['period','sector_code'],how='inner',validate='one_to_one')
    if merged.empty:return pd.DataFrame(columns=columns)
    merged['diff_people']=merged.hist_value_persons-merged.recent_value_persons
    merged['comparison_status']='SAME_DOMAIN_SAME_MONTH_CIIU4'
    return merged[columns].sort_values(['period','sector_code']).reset_index(drop=True)


def run(output:Path, recent_monthly:Path, annex_csv:Path|None=None,
        source_files:Path|None=None) -> dict:
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    recent=pd.read_csv(recent_monthly,encoding='utf-8-sig')
    needed={'period','sector_code','employed_persons','temporal_support','window_months'}
    if not needed <= set(recent):raise ValueError('FUENTE_RECIENTE_INVALIDA')
    if not (recent.temporal_support=='calendar_month').all() or not (recent.window_months==1).all():
        raise ValueError('FUENTE_RECIENTE_NO_ES_MENSUAL')
    idx=publication_inventory()
    if annex_csv is None:
        verified=validate_annex_observations(pd.DataFrame(columns=list(REQUIRED)),source_files)
    else:
        verified=validate_annex_observations(pd.read_csv(annex_csv,keep_default_na=False),source_files)
    overlap=audit_overlap(verified,recent)
    months=month_periods().strftime('%Y-%m')
    matrix=pd.DataFrame({'period':months})
    direct=recent.groupby('period').sector_code.nunique()
    matrix['official_direct_recent_group_count']=matrix.period.map(direct).fillna(0).astype(int)
    matrix['historical_verified_direct_group_count']=matrix.period.map(
        verified.loc[verified.monthly_direct].groupby('period_start').mapped_sector_code.nunique()).fillna(0).astype(int)
    matrix['historical_confirmed_rolling_window_count']=matrix.period.map(
        verified.loc[verified.eligible_anchor & verified.temporal_support.ne('calendar_month')]
          .groupby('period_end').size()).fillna(0).astype(int)
    published=idx.set_index('publication_period').index
    matrix['annex_publication_listed']=matrix.period.isin(published)
    matrix['full_14_direct_observed']=False # Missing B & D_E even in recent official monthly source.
    matrix['status']=np.select([
        matrix.official_direct_recent_group_count.eq(13),
        matrix.historical_verified_direct_group_count.gt(0),
        matrix.annex_publication_listed],
        ['DANE_OFFICIAL_MONTHLY_13_GROUPS','HISTORIC_MONTHLY_VERIFIED_PARTIAL',
         'ANNEX_LISTED_NOT_EXTRACTED'],default='NO_VERIFIED_SECTOR_OBSERVATIONS')
    for fname, dataframe in [
        ('10_inventario_publicaciones_dane_2007_2014.csv',idx),
        ('10_anclas_historicas_CON_TRAZABILIDAD.csv',verified),
        ('10_solapamientos_homologados.csv',overlap),
        ('10_cobertura_sectorial_1993_2026.csv',matrix)]:
        dataframe.to_csv(output/fname,index=False,encoding='utf-8-sig',float_format='%.10f')
    summary={'stage':'H10_HISTORICAL_ANNEX_INVENTORY_AND_STRICT_INGESTION',
             'reference_index':DANE_INDEX,'published_annex_entries_2007_2014':int(len(idx)),
             'historic_numeric_observations_received':int(len(verified)),
             'historic_verified_rows':int(verified.eligible_anchor.sum()) if len(verified) else 0,
             'historic_verified_direct_monthly_rows':int(verified.monthly_direct.sum()) if len(verified) else 0,
             'recent_direct_months':int(direct.size),
             'recent_groups':int(recent.sector_code.nunique()),
             'historic_14_months_verified':0,
             'status':'BLOCKED_HISTORIC_EXTRACTION_AND_14_BRANCH_MAPPING',
             'no_microdata':True,'no_smoothing':True,
             'note':'Published annex link does not imply sectoral observations or a calendar month.'}
    (output/'10_puerta_historicos.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary
