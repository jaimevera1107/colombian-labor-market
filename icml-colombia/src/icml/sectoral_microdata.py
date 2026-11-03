"""H10 microdata-backed, honest disaggregation of DANE calendar-month B+D+E.

A monthly 13-group DANE annex is the LEVEL source. The month-specific GEIH
sample, after correct CIIU4 join and survey weighting, is only the B vs D+E
SHARE source. Thus the 14-group levels are reproducible MONTHLY ESTIMATES, not
independent DANE 14-group published observations.

2015–2019 require an external CIIU Rev4 classification module joined on exact
person keys; for 2020+, RAMA2D_R4 is provided with the occupied module.
Missing/incompatible data ALWAYS block the corresponding month.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .sectoral_monthly import MONTHLY_GROUPS, REQUIRED_FINAL_14, read_normalized_monthly

IDENTIFIERS = ("DIRECTORIO", "SECUENCIA_P", "ORDEN")
CLASS_COLS = ("RAMA2D_R4", "RAMA4D_R4")
WEIGHT_COLS = ("FEX_C18", "FEX_C_2011", "FEX_C")
MEMBER_FORMAT = 'path.zip::folder/file.csv'


def _norm(x):
    text = ''.join(y for y in unicodedata.normalize('NFKD', str(x)) if not unicodedata.combining(y))
    return re.sub(r'\s+', '_', text.strip().upper())


def _read_csv_bytes(payload: bytes, desc: str) -> pd.DataFrame:
    txt = None
    for enc in ('utf-8-sig', 'cp1252', 'latin1'):
        try:
            txt = payload.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    if txt is None:
        raise ValueError(f'Cannot decode CSV {desc}')
    first = txt[:16000]
    try:
        delimiter = csv.Sniffer().sniff(first, delimiters=',;|\t').delimiter
    except csv.Error:
        delimiter = ';' if first.split('\n')[0].count(';') > first.split('\n')[0].count(',') else ','
    frame = pd.read_csv(io.StringIO(txt), sep=delimiter, dtype=str, keep_default_na=False, low_memory=False)
    frame.columns = [_norm(c) for c in frame.columns]
    if frame.columns.duplicated().any():
        raise ValueError(f'Collision among normalized CSV column names in {desc}')
    return frame


def _read_table(source: str | Path, kind: str) -> tuple[pd.DataFrame, str]:
    """Read a selected CSV, zip with one matching file, or exact ZIP member.

    Ambiguous archives require ::member, to prevent unnoticed selection of a
    different universe or module from a DANE zip.
    """
    spec = str(source)
    path, sep, explicit = spec.partition('::')
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f'{kind}: {p} was not supplied')
    if p.suffix.lower() == '.zip':
        with zipfile.ZipFile(p) as z:
            if explicit:
                if explicit not in z.namelist():
                    raise ValueError(f'ZIP member {explicit!r} not present in {p}')
                chosen = explicit
            else:
                members = [m for m in z.namelist() if m.lower().endswith(('.csv', '.txt'))]
                if kind == 'occupied':
                    matches = [m for m in members if ('ocupad' in _norm(m).lower()) and 'no_ocupad' not in _norm(m).lower() and 'desocupad' not in _norm(m).lower()]
                elif kind == 'classification':
                    matches = [m for m in members if 'ciiu' in m.lower() or 'rama' in m.lower()]
                else:
                    matches = [m for m in members if 'caracteristica' in m.lower() or 'general' in m.lower()]
                if len(matches) != 1:
                    raise ValueError(f'Ambiguous {kind} member of {p}: {matches}; select using {MEMBER_FORMAT}')
                chosen = matches[0]
            payload = z.read(chosen)
            desc = f'{p.name}::{chosen}'
    elif not sep and p.suffix.lower() in ('.csv', '.txt'):
        payload, desc = p.read_bytes(), p.name
    else:
        raise ValueError(f'Unsupported path {spec}; expected CSV or ZIP[::member]')
    return _read_csv_bytes(payload, desc), hashlib.sha256(payload).hexdigest()


def _check_keys(frame: pd.DataFrame, context: str) -> pd.DataFrame:
    if not set(IDENTIFIERS).issubset(frame.columns):
        raise ValueError(f'{context}: missing person key columns {IDENTIFIERS}')
    df = frame.copy()
    for col in IDENTIFIERS:
        df[col] = df[col].astype(str).str.strip()
        if (df[col] == '').any():
            raise ValueError(f'{context}: blank person key {col}')
    if df.duplicated(list(IDENTIFIERS)).any():
        raise ValueError(f'{context}: duplicate person keys; join would inflate totals')
    return df


def _merge_columns(base: pd.DataFrame, addon: pd.DataFrame, wanted: tuple[str,...], context: str) -> pd.DataFrame:
    a = _check_keys(addon, context)
    present = [c for c in wanted if c in a.columns and c not in base.columns]
    if not present:
        return base
    out = base.merge(a[list(IDENTIFIERS)+present], on=list(IDENTIFIERS), how='left', validate='one_to_one', indicator=True)
    if (out['_merge'] != 'both').any():
        raise ValueError(f'{context}: left join missing person identifiers; cannot assign unknown weights or CIIU')
    return out.drop(columns='_merge')


def _division(code: str) -> int | None:
    s = str(code).strip()
    if not re.fullmatch(r'\d{1,4}(?:\.0+)?', s):
        return None
    s = s.split('.')[0]
    if len(s) > 2:
        s = s.zfill(4)[:2]
    try:
        d = int(s)
    except ValueError:
        return None
    return d if 1 <= d <= 99 else None


def _extract_divisions(df: pd.DataFrame) -> pd.Series:
    if 'RAMA2D_R4' in df:
        return df['RAMA2D_R4'].map(_division)
    if 'RAMA4D_R4' in df:
        return df['RAMA4D_R4'].map(_division)
    raise ValueError('RAMA2D_R4/RAMA4D_R4 missing: cannot identify B vs D+E')


def monthly_microdata_share(period: str, *, occupied: str | Path,
                            classification: str | Path | None = None,
                            characteristics: str | Path | None = None) -> dict:
    """Return a validated within-BDE monthly share from a single GEIH edition.

    The computed levels are survey-weighted but are NOT the official DANE
    monthly levels. The DANE monthly 13-group ANNEX supplies those levels.
    """
    year, month = map(int, period.split('-'))
    if not (2015 <= year <= 2026 and 1 <= month <= 12):
        raise ValueError(f'Period outside documented 2015–2026 CIIU4 GEIH contract: {period}')
    base, hash_occ = _read_table(occupied, 'occupied')
    base = _check_keys(base, 'Ocupados')
    # Reject an accidentally supplied file from another month when source has
    # an explicit numeric MES/ANIO, rather than relying on filename alone.
    if 'MES' in base.columns:
        vals=set(base['MES'].astype(str).str.strip())
        if all(v.isdigit() and 1 <= int(v) <= 12 for v in vals):
            if vals != {str(month)} and {int(v) for v in vals} != {month}:
                raise ValueError(f'{period}: Ocupados CSV belongs to a different MES: {vals}')
    for year_col in ('ANIO','ANO'):
        if year_col in base.columns:
            vals=set(base[year_col].astype(str).str.strip())
            if all(v.isdigit() for v in vals) and {int(v) for v in vals}!={year}:
                raise ValueError(f'{period}: Ocupados CSV belongs to another year: {vals}')
    hashes = {'occupied': hash_occ}
    if year <= 2019 and classification is None:
        raise ValueError('2015–2019: separate CIIU Rev4 classification file is mandatory')
    if classification is not None:
        aux, h = _read_table(classification, 'classification')
        # Avoid accepting an old or inconsistent CIIU module by positional order.
        if not any(c in aux for c in CLASS_COLS):
            raise ValueError('Classification file has no CIIU Rev4 RAMA2D_R4/RAMA4D_R4')
        base = _merge_columns(base, aux, CLASS_COLS, 'CIIU Rev4')
        hashes['classification'] = h
    if not any(c in base for c in WEIGHT_COLS):
        if characteristics is None:
            raise ValueError('Missing GEIH survey expansion weight: attach characteristics module')
        gen, h = _read_table(characteristics, 'characteristics')
        base = _merge_columns(base, gen, WEIGHT_COLS, 'Characteristics')
        hashes['characteristics'] = h
    weights = [c for c in WEIGHT_COLS if c in base]
    if len(weights) != 1:
        raise ValueError(f'Expected exactly one documented expansion weight (no silent fallback): {weights}')
    w = pd.to_numeric(base[weights[0]].str.replace(',', '.', regex=False), errors='coerce')
    if w.isna().any() or (w <= 0).any():
        raise ValueError('Invalid/missing person expansion weights: no zero or imputation')
    divisions = _extract_divisions(base)
    n_b = divisions.between(5, 9, inclusive='both')
    n_de = divisions.between(35,39,inclusive='both')
    if divisions.isna().mean() > 0.1:
        raise ValueError('More than 10% uncoded CIIU divisions; inspect source classification')
    b, de = float(w[n_b].sum()), float(w[n_de].sum())
    if b <= 0 or de <= 0:
        raise ValueError('Monthly mining or utilities branch has zero survey-weighted support; cannot split')
    # The sample weighted total is used as a quality indicator, not assumed
    # equal to the DANE publication before rounding/revisions.
    result = {'period':period, 'microdata_occupied_rows':len(base),
        'ciiu_uncoded_rows':int(divisions.isna().sum()),
        'weighted_mining_B':b, 'weighted_utilities_D_E':de,
        'weighted_all_occupied':float(w.sum()),
        'microdata_sample_B':int(n_b.sum()),'microdata_sample_D_E':int(n_de.sum()),
        'share_B_in_combined':b/(b+de),
        'share_D_E_in_combined':de/(b+de),
        'expansion_weight':weights[0], 'microdata_sha256':json.dumps(hashes,sort_keys=True),
        'classification_join': 'CIIU4_file_person_key' if classification is not None else 'in_occupied_module',
        'observation_status':'MICRODATA_WEIGHTED_SHARE_CALENDAR_MONTH',
        'temporal_support':'calendar_month', 'window_months':1,
    }
    return result


def _catalog_coverage():
    for year in range(1993,2027):
        for month in range(1,13):
            if year == 2026 and month > 8: break
            period=f'{year}-{month:02}'
            if year < 2001:
                status='NO_MONTHLY_GEIH; historical ENH/ECH evidence required'
            elif year < 2015:
                status='H11_LEGACY_ECH_GEIH_CIIU_MAPPING_NOT_VALIDATED'
            else:
                status='MONTHLY_OFFICIAL_13_GROUPS; B_DE_SPLIT_DEPENDS_ON_MONTH_MICRODATA'
            yield {'period':period,'sectorial_source_status':status,
                   'observed_direct_14_branches':False,
                   'sectoral_reconstruction_status':'NOT_PRODUCED'}


def run(*, observations_csv: Path, totals_csv: Path,
        output: Path, manifest_csv: Path | None = None,
        workbook: Path | None = None) -> dict:
    """Produce only genuinely supported 14-group monthly candidates.

    Optional manifest fields: period, occupied, classification, characteristics.
    Paths can be relative to the manifest directory. Never add artificial shares.
    """
    obs, totals, provenance = read_normalized_monthly(observations_csv, totals_csv, workbook)
    output=Path(output); output.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if manifest_csv is not None:
        mp=Path(manifest_csv); m=pd.read_csv(mp, dtype=str, keep_default_na=False)
        if not {'period','occupied'} <= set(m.columns):
            raise ValueError('Manifest must contain period, occupied')
        if m.period.duplicated().any():
            raise ValueError('Duplicate source periods in manifest')
        for r in m.to_dict('records'):
            period=str(r['period'])
            if period not in set(totals.period):
                raise ValueError(f'Microdata manifest month outside source monthly annex: {period}')
            def fix_path(v):
                v = str(v).strip()
                if not v: return None
                path, sep, mem = v.partition('::')
                path = Path(path)
                if not path.is_absolute(): path = mp.parent/path
                return str(path) + ('::' + mem if sep else '')
            manifest[period]={col:fix_path(r.get(col,'')) for col in ('occupied','classification','characteristics')}
    splits, audit = {}, []
    for period in sorted(totals.period):
        if period in manifest:
            inputs = manifest[period]
            if not inputs['occupied']:
                raise ValueError(f'Missing Ocupados file for manifest period {period}')
            result = monthly_microdata_share(period, **inputs)
            controls = totals.loc[totals.period==period].iloc[0]
            reported = float(controls.occupied_official_persons)
            published_combined = float(obs.loc[(obs.period==period)&(obs.sector_code=='B_D_E_COMBINED'),'employed_persons'].iloc[0])
            whole_error = abs(result['weighted_all_occupied']-reported)/reported
            combined_error = abs(result['weighted_mining_B']+result['weighted_utilities_D_E']-published_combined)/published_combined
            result['microdata_total_vs_published_relative_error']=whole_error
            result['microdata_combined_vs_published_relative_error']=combined_error
            if (result['microdata_occupied_rows'] < 100 or
                min(result['microdata_sample_B'],result['microdata_sample_D_E']) < 10):
                raise ValueError(f'{period}: INSUFFICIENT_GEIH_MICRODATA_SAMPLE; cannot claim a validated monthly B/D_E split')
            if whole_error > 0.05 or combined_error > 0.15:
                raise ValueError(f'{period}: GEIH_MICRODATA_DOMAIN_OR_VERSION_MISMATCH; '
                    f'national occupied diff {whole_error:.1%}, B_D_E diff {combined_error:.1%}')
            splits[period]=result
            status='ACCEPTED_MICRODATA_SPLIT_MONTHLY_ESTIMATE'
        else:
            result={}; status='PENDING_MICRODATA_NOT_SUPPLIED'
        audit.append({'period':period,'split_status':status,
                      'source_monthly_groups':13,'target_monthly_groups':14,
                      'source_is_direct_calendar_month':True,
                      '14_groups_officially_published':False,
                      **result})
    candidates=[]
    base_cols=['period','sector_code','employed_persons','observation_status','temporal_support','source_sha256']
    for period, subset in obs.groupby('period',sort=True):
        split=splits.get(period)
        if split is None:
            continue
        for entry in subset.to_dict('records'):
            if entry['sector_code'] != 'B_D_E_COMBINED':
                candidates.append({k:entry[k] for k in base_cols})
            else:
                for code,share_key in (('B','share_B_in_combined'),('D_E','share_D_E_in_combined')):
                    candidates.append({'period':period,'sector_code':code,
                        'employed_persons':float(entry['employed_persons'])*split[share_key],
                        'observation_status':'ESTIMATED_MONTHLY_FROM_OFFICIAL_BDE_TOTAL_AND_GEIH_MICRODATA_SHARE',
                        'temporal_support':'calendar_month',
                        'source_sha256':entry['source_sha256']})
    cf = pd.DataFrame(candidates,columns=base_cols)
    if len(cf):
        per=cf.groupby('period').employed_persons.sum()
        official=totals.set_index('period')
        gap=per + official.loc[per.index,'no_informa_persons']-official.loc[per.index,'occupied_official_persons']
        if gap.abs().max() > 10 or any(cf.groupby('period').sector_code.nunique()!=14):
            raise ValueError('Produced incomplete/inconsistent 14-group monthly candidate')
    else:
        gap=pd.Series(dtype=float)
    cf.to_csv(output/'10_candidatos_14_ramas_SOLO_MESES_CON_MICRODATOS.csv',index=False,float_format='%.10f')
    aud=pd.DataFrame(audit).fillna('')
    aud.to_csv(output/'10_auditoria_disponibilidad_desagregacion.csv',index=False,float_format='%.10f')
    cov=pd.DataFrame(_catalog_coverage())
    cov.loc[cov.period.isin(splits),'sectoral_reconstruction_status']='14_GROUP_ESTIMATE_FROM_OFFICIAL_MONTHLY_TOTAL_AND_WEIGHTED_MICRODATA'
    cov.to_csv(output/'10_matriz_cobertura_1993_2026.csv',index=False)
    summary={'month_count_official_13':len(totals),'month_count_validated_14_estimated':len(splits),
       'months_without_14_split':len(totals)-len(splits),'rows_14_candidates':len(cf),
       'max_monthly_closure_residual_persons':float(gap.abs().max()) if len(gap) else None,
       'source':'DANE original calendar-month 13 groups + within-month person-weighted GEIH CIIU4 split',
       'status':'PARTIAL_REQUIRES_MONTHLY_MICRODATA' if len(splits)<len(totals) else '14_MONTHLY_ESTIMATED_SPLIT_COMPLETE',
       'not_official_14_group_levels':True,
       'decision':'NO_SYNTHETIC_MONTHLY_SHARES; missing raw month leaves month unestimated; keep original 13-group official observations',
       'h10_source':provenance}
    (output/'10_puerta_microdatos_h10.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    return summary
