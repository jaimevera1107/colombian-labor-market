"""Rebuild historic urban signals from DANE's 23-city rolling-quarter annex.

The derived ``*_geih`` series are annual *medians of published overlapping
three-month windows*, 2007--2026, expressed in thousands of persons. They
are not independent observations of calendar-year employment. The earlier
legacy donor-signal mapping is distinct from the H30 selected Pareto donors.
"""
from __future__ import annotations

import csv
from pathlib import Path
from statistics import median
import math
import unicodedata

from icml.domain.cutoff import LAST_MONTH, LAST_YEAR
from icml.domain.territories import UrbanDomainKind, load_urban_domains
from icml.operations.h31_sources import (
    _col,
    _map_data,
    _norm,
    _records,
    extract_window_proxies,
)

GEIH_METRICS = {
    'population_geih': ('Población total', 10),
    'pet_geih': ('Población en edad de trabajar (PET)', 11),
    'pea_geih': ('Fuerza de trabajo', 12),
    'employed_geih': ('Población ocupada', 13),
    'unemployed_geih': ('Población desocupada', 14),
    'inactive_geih': ('Población fuera de la fuerza de trabajo', 15),
}
PROXY_METRICS = ('employed','inactive','pea','pet','population','unemployed')
FIELDS = ('dep_code','year','dep_code_similar', *PROXY_METRICS,
          'Region', *GEIH_METRICS)


def _annual_columns(year: int) -> list[str]:
    if not 2007 <= year <= LAST_YEAR:
        raise ValueError(f'Year outside recorded GEIH annex: {year}')
    first = 2 if year == 2007 else 12 + (year - 2008) * 12
    count = 10 if year == 2007 else (LAST_MONTH if year == LAST_YEAR else 12)
    return [_col(j) for j in range(first, first + count)]


def _legacy_donor_map(path: Path) -> dict[int,int]:
    """Transfer the historical snapshot's donor mapping, NOT H30 Pareto picks."""
    pairs = {}
    for item in _records(path):
        d = int(item['dep_code']); donor = int(item['donor_code'])
        if d in pairs:
            raise ValueError(f'Duplicate historical donor mapping for {d}')
        pairs[d] = donor
    if len(pairs) != 33:
        raise ValueError(f'Expected 33 historical domain mappings, got {len(pairs)}')
    return pairs


def _normalize_label(value: object) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).casefold().split())


def _extract_area(cells: dict, area: str) -> dict[str,dict[str,float]]:
    headers = [r for r,line in cells.items()
               if _normalize_label(line.get('A')) == 'cundinamarca']
    if len(headers) != 1:
        raise ValueError(f'Expected one Cundinamarca block in {area}; found {len(headers)}')
    header=headers[0]
    if _normalize_label(cells.get(header+1,{}).get('A')) != 'concepto':
        raise ValueError(f'Missing Concepto header in {area}')
    years={}
    for col,value in cells.get(header+2,{}).items():
        if col != 'A' and isinstance(value,(int,float)) and float(value).is_integer():
            yr=int(value)
            if 2021 <= yr <= 2024:
                if str(yr) in years:raise ValueError(f'Duplicate {yr} in {area}')
                years[str(yr)]=col
    if set(years) != {'2021','2022','2023','2024'}:
        raise ValueError(f'Incomplete years in {area}')
    labels={
        'population':'poblacion total',
        'pet':'poblacion en edad de trabajar (pet)',
        'pea':'fuerza de trabajo',
        'employed':'poblacion ocupada',
        'unemployed':'poblacion desocupada',
        'inactive':'poblacion fuera de la fuerza de trabajo',
    }
    lines={}
    for rowid in range(header+3,header+17):
        line=cells.get(rowid,{})
        label=_normalize_label(line.get('A'))
        for metric,expected in labels.items():
            if label == expected:
                if metric in lines:raise ValueError(f'Duplicate {metric} in {area}')
                lines[metric]=line
    if set(lines) != set(labels):
        raise ValueError(f'Missing {set(labels)-set(lines)} in {area}')
    anchors={}
    for year,col in sorted(years.items()):
        item={}
        for metric,line in lines.items():
            value=line.get(col)
            if not isinstance(value,(float,int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'Invalid {metric}/{year} in {area}')
            item[metric]=float(round(float(value)*1000))
        if abs(item['pea']-item['employed']-item['unemployed']) > 2:
            raise ValueError(f'Labor force identity failed in {area}/{year}')
        if abs(item['pet']-item['pea']-item['inactive']) > 2:
            raise ValueError(f'PET identity failed in {area}/{year}')
        if item['pet'] > item['population']:
            raise ValueError(f'PET > population in {area}/{year}')
        anchors[year]=item
    return anchors


def extract_cundinamarca_area_breakdown(department_annex: Path) -> dict[str,dict[str,dict[str,float]]]:
    """Read all 3 published DANE department domains and audit their identity.

    The historical synthetic model uses TOTAL as its level anchor; CABECERAS
    and RESTO are separately observed domains, NOT implicit urban model output.
    """
    sheets={'total':'Departamentos anual',
            'cabeceras':'Departamento anual Cabeceras',
            'resto':'Departamento anual CentrosP'}
    parts={key:_extract_area(_map_data(department_annex,tab),key)
           for key,tab in sheets.items()}
    for year in ('2021','2022','2023','2024'):
        for metric in ('population','pet','pea','employed','unemployed','inactive'):
            diff=(parts['total'][year][metric]-parts['cabeceras'][year][metric]
                  -parts['resto'][year][metric])
            if abs(diff)>2:
                raise ValueError(f'DANE Cundinamarca area decomposition mismatch {year}/{metric}: {diff}')
    return parts


def extract_cundinamarca_department_anchors(department_annex: Path) -> dict[str,dict[str,float]]:
    """Official department-level anchors for the frozen historical model."""
    return extract_cundinamarca_area_breakdown(department_annex)['total']


def extract_urban_historical_annex(
    annex: Path, historical_donor_mapping: Path, department_annex: Path
) -> list[dict]:
    """Rebuild all 660 archived urban donor-signal rows from a DANE XLSX.

    For 2007--2020 the 32-city proxies do not exist and remain empty. For
    2021--2026 those six fields come from *a different* 12-month rolling
    window annex, via the already validated H31 extractor. Cundinamarca has no published 32-city row: 2021--2024 use official
    departmental anchors from the annual DANE workbook. Their use as
    an urban model proxy is synthetic; the source quantities are not.
    2025--2026 remain blank under the frozen calibration policy.
    """
    cells = _map_data(annex, 'Total 23 ciudades A.M. Trim')
    domains = {int(x.dane_code): x.name for x in load_urban_domains()
               if x.kind is UrbanDomainKind.OBSERVED_CITY}
    if len(domains) != 32:
        raise ValueError('Expected 32 observed city names in domain registry')
    names = {_norm(name): code for code,name in domains.items()}
    historical = {}
    for start, line in sorted(cells.items()):
        name = line.get('A')
        code = names.get(_norm(name))
        if code is None:
            continue
        if code in historical:
            raise ValueError(f'Duplicate 23-city header {name!r}')
        blocks = {}
        for metric,(label,offset) in GEIH_METRICS.items():
            values = cells.get(start + offset, {})
            if _norm(values.get('A')) != _norm(label):
                raise ValueError(f'Unexpected concept for {name}: {metric} at {start+offset}')
            blocks[metric] = values
        historical[code] = (name, blocks)
    if len(historical) != 23:
        raise ValueError(f'Expected 23 city blocks; found {len(historical)}')

    donors = _legacy_donor_map(historical_donor_mapping)
    if set(donors.values()) != set(historical):
        raise ValueError('Legacy mapping does not cover precisely the 23 annex cities')
    proxies = {(int(x['dep_code']),int(x['year'])):x
               for x in extract_window_proxies(annex)}
    if len(proxies) != 32 * (LAST_YEAR - 2020):
        raise ValueError(f'Expected {32 * (LAST_YEAR - 2020)} published 32-city proxy rows')
    official_anchors=extract_cundinamarca_department_anchors(department_annex)
    result = []
    for domain, donor in sorted(donors.items()):
        name, data = historical[donor]
        for year in range(2007, LAST_YEAR + 1):
            row = {'dep_code':domain,'year':year,
                   'dep_code_similar':donor}
            selected = proxies.get((domain,year)) if year>=2021 else None
            if domain==25 and 2021 <= year <= 2024:
                selected = official_anchors[str(year)]
            for metric in PROXY_METRICS:
                row[metric] = None if selected is None else float(selected[metric])
            row['Region'] = name
            columns = _annual_columns(year)
            for metric, values in data.items():
                nums = [values.get(c) for c in columns]
                if len(nums) != len(columns) or not all(
                    isinstance(v, (int,float)) and v >= 0 for v in nums
                ):
                    raise ValueError(f'Missing source cells for {name}, {year}, {metric}')
                row[metric] = float(median(nums))
            result.append(row)
    expected_signals = 33 * (LAST_YEAR - 2006)
    if len(result) != expected_signals:
        raise ValueError(f'Expected {expected_signals} domain-year signals; found {len(result)}')
    return result


def compare_historical_annex(actual: list[dict], frozen: list[dict]) -> dict:
    """Compare every field, including donor IDs and missing 32-city proxies."""
    def index(rows):
        out={}
        for r in rows:
            k=(int(r['dep_code']),int(r['year']))
            if k in out:
                raise ValueError(f'Duplicate {k}')
            out[k]=r
        return out
    src=index(actual); ref=index(frozen)
    missing=sorted(ref.keys()-src.keys())
    extra=sorted(src.keys()-ref.keys())
    max_geih=0.0;max_proxy=0.0;bad=[]
    for key in src.keys() & ref.keys():
        x,y=src[key],ref[key]
        if int(x['dep_code_similar']) != int(y['dep_code_similar']) or x['Region']!=y['Region']:
            bad.append({'key':key,'field':'legacy_mapping'})
        for metric in (*GEIH_METRICS,*PROXY_METRICS):
            a=x[metric];b=y[metric]
            aa=None if a is None or str(a).strip() in ('','nan') else float(a)
            bb=None if b is None or str(b).strip() in ('','nan') else float(b)
            if aa is None or bb is None:
                if aa is not None or bb is not None:
                    bad.append({'key':key,'field':metric,'reason':'missingness'})
                continue
            diff=abs(aa-bb)
            if metric in GEIH_METRICS:
                max_geih=max(max_geih,diff)
                tolerance=0.000051 # 0.051 person (original stored in thousands)
            else:
                max_proxy=max(max_proxy,diff)
                tolerance=0.051 # frozen proxy rounded to 0.1 person
            if diff>tolerance:
                bad.append({'key':key,'field':metric,'difference':diff})
    return {'status':'PASS' if not(missing or extra or bad) else 'BLOCKED',
            'rows':len(actual),'years':f'2007-{LAST_YEAR}','annex_city_count':23,
            'recipient_domain_count':33,'max_geih_abs_thousands':max_geih,
            'max_proxy_abs_persons':max_proxy,
            'missing_keys':len(missing),'extra_keys':len(extra),
            'violations':len(bad),'examples':bad[:10],
            'method':'annual_median_of_published_rolling_3_month_windows',
            'status_note':'Donor mapping in the source-signal table is not the H30 selected Pareto mapping.'}


def write_csv(path: Path, records: list[dict]) -> None:
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader();w.writerows(records)
