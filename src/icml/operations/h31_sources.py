"""H31: independently rebuild three historical CSV inputs from DANE Excel.

The primary workbook is the frozen 2026-08 GEIH labor annex. This module
never changes the historical source hashes or the selected donor methodology.
The historical urban city signals can also be reconstructed from the
published 23-city rolling-quarter sheet, audited by H32.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from icml.domain.cutoff import ACTIVE_CUTOFF, LAST_YEAR, vintage_suffix
from icml.domain.periods import MonthlyPeriod

from icml.operations.xlsx_cached import sheets

METRICS = {
    'population': 'Población total',
    'pet': 'Población en edad de trabajar (PET)',
    'pea': 'Fuerza de trabajo',
    'employed': 'Población ocupada',
    'unemployed': 'Población desocupada',
    'inactive': 'Población fuera de la fuerza de trabajo',
}
MACRO = {
    'exchange_rate': 'B',
    'producer_price_index': 'C',
    'consumer_price_index': 'D',
    'inflation_rate': 'E',
    'industrial_production_index': 'F',
    'real_value_unit_uvr': 'G',
    'vacancies': 'H',
}
NATIONAL = {
    'population': 'population_geih',
    'working_age': 'pet_geih',
    'labor_force': 'pea_geih',
    'employed': 'employed_geih',
    'unemployed': 'unemployed_geih',
    'inactive': 'inactive_geih',
}


def _sha(path: Path) -> str:
    with Path(path).open('rb') as f:
        h = hashlib.sha256()
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
        return h.hexdigest()


def _col(number: int) -> str:
    if number < 1:
        raise ValueError('Excel column must be positive')
    out = ''
    while number:
        number, n = divmod(number - 1, 26)
        out = chr(65 + n) + out
    return out


def _records(path: Path) -> list[dict[str, str]]:
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def _norm(s: object) -> str:
    return ' '.join(str(s).split()).casefold()


def _map_data(path: Path, tab: str) -> dict[int,dict[str,object]]:
    result = list(sheets(path, names=[tab]))
    if len(result) != 1:
        raise ValueError(f'Missing {tab!r} in {path.name}')
    return result[0][1]


def extract_window_proxies(path: Path, cutoff: str = ACTIVE_CUTOFF) -> list[dict]:
    """Average the published trailing-12m windows ending within each year.

    2021 has one available 12-month window; for 2022 up to the year before
    the cutoff use 12, and the cutoff year uses as many windows as months
    elapsed (eight for an August cutoff, seven for a July one). The result is
    *not* a calendar-year sample average of monthly employment
    observations. An annex that does not carry the windows of the requested
    month is rejected instead of silently padded.
    """
    period = MonthlyPeriod.parse(cutoff)
    if period.year < 2022:
        raise ValueError(f'Window proxies need a cutoff from 2022 on, got {cutoff}')
    last_year = period.year
    cells = _map_data(path, 'Año_móvil_32_ciudades')
    from icml.domain.territories import load_urban_domains, UrbanDomainKind
    names = {x.name: x.dane_code for x in load_urban_domains()
             if x.kind is UrbanDomainKind.OBSERVED_CITY}
    if len(names) != 32:
        raise ValueError('Expected 32 official urban domains')
    out = []
    seen = set()
    for header, row in sorted(cells.items()):
        if _norm(row.get('A')) != 'año móvil':
            continue
        city = cells.get(header - 1, {}).get('A')
        if city not in names or city in seen:
            raise ValueError(f'Unexpected or duplicated GEIH city {city!r}')
        seen.add(city)
        data = {}
        for j in range(header + 1, header + 17):
            line = cells.get(j, {})
            key = _norm(line.get('A'))
            for metric, label in METRICS.items():
                if key == _norm(label):
                    if metric in data:
                        raise ValueError(f'Duplicated concept {metric} for {city}')
                    data[metric] = line
        if set(data) != set(METRICS):
            raise ValueError(f'Missing city labor concepts {city}: {set(METRICS)-set(data)}')
        # B: Ene-Dic 2021; C:N end 2022; O:Z end 2023; ...; AY:BF 2026.
        for year in range(2021, last_year + 1):
            start = 2 if year == 2021 else 3 + 12 * (year - 2022)
            length = 1 if year == 2021 else (period.month if year == last_year else 12)
            values = {'dep_code':str(names[city]), 'city':city, 'year':str(year)}
            for metric in ('employed','inactive','pea','pet','population','unemployed'):
                numbers = [data[metric].get(_col(k)) for k in range(start, start+length)]
                if any(not isinstance(v, (float,int)) or not math.isfinite(v) or v <= 0 for v in numbers):
                    raise ValueError(f'Invalid/missing year-móvil values {city} {year} {metric}')
                values[metric] = (sum(numbers) / length) * 1000.0
            out.append(values)
    expected_rows = 32 * (last_year - 2020)
    if seen != set(names) or len(out) != expected_rows:
        raise ValueError(f'Expected {expected_rows} city-years, found {len(out)}')
    out.sort(key=lambda x: (int(x['dep_code']),int(x['year'])))
    return out


def extract_macro(path: Path) -> list[dict]:
    """Reconstruct all seven economic and vacancy columns from one Excel."""
    cells = _map_data(path, 'Datos')
    result = []
    for n, row in sorted(cells.items()):
        if n <= 1 or not isinstance(row.get('A'), (int,float)):
            continue
        date = datetime(1899,12,30) + timedelta(days=float(row['A']))
        if not (date.year >= 1993 and date.year <= 2003):
            continue
        item = {'date':date.strftime('%Y-%m-%d'), 'year':str(date.year), 'month':str(date.month)}
        for metric, column in MACRO.items():
            value = row.get(column)
            if not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError(f'Missing macro {metric} at {date}')
            item[metric] = float(value)
        result.append(item)
    result.sort(key=lambda x:x['date'])
    if len(result)!=132 or [(x['year'],x['month']) for x in result] != [
            (str(y),str(m)) for y in range(1993,2004) for m in range(1,13)]:
        raise ValueError('External macro series is not contiguous 1993-2003')
    return result


def extract_geih_annual(annex: Path, config: Path) -> list[dict]:
    """Reproduce annual averages of GEIH monthly published quantities."""
    from icml.national.pipeline import load_national_config
    from icml.national.geih_annex import GeihAnnexReader
    cfg=load_national_config(config)
    df=GeihAnnexReader(cfg.geih_annex).read_national_monthly(annex)
    df['year'] = df['period'].str[:4].astype(int)
    means=df.groupby('year',sort=True).mean(numeric_only=True).reset_index()
    out=[]
    for row in means.to_dict('records'):
        out.append({'year':str(row['year']),**{field:float(row[key])
                    for key,field in NATIONAL.items()}})
    if len(out)!=LAST_YEAR-2000 or [int(x['year']) for x in out]!=list(range(2001,LAST_YEAR+1)):
        raise ValueError(f'GEIH annual reference must cover 2001-{LAST_YEAR}')
    return out


def compare_numeric(actual:list[dict], frozen:list[dict], keys:tuple[str,...],
                    fields:tuple[str,...], tolerance:float) -> dict:
    """Fail-closed key and quantity comparison; no row-order assumptions."""
    def map_keys(rows):
        lookup={}
        for x in rows:
            key=tuple(str(x[k]) for k in keys)
            if key in lookup:raise ValueError(f'Duplicate key {key}')
            lookup[key]=x
        return lookup
    a=map_keys(actual);b=map_keys(frozen)
    missing=set(b)-set(a);extra=set(a)-set(b)
    max_abs=0.0;bad=0
    for key in a.keys() & b.keys():
        for fld in fields:
            d=abs(float(a[key][fld])-float(b[key][fld]))
            if not math.isfinite(d):raise ValueError('Nonfinite comparison')
            max_abs=max(max_abs,d)
            bad+=d>tolerance
    return {'expected':len(b),'actual':len(a),'missing_keys':len(missing),
            'extra_keys':len(extra),'numeric_violations':bad,
            'tolerance':tolerance,'max_abs_difference':max_abs,
            'equivalent':not (missing or extra or bad) and len(a)==len(b)}


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def run(root: Path, output: Path) -> dict:
    """New immutable stage: no new model fit, no publication, no source edits."""
    root=Path(root).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    if root==output or root in output.parents:raise ValueError('Output must be outside original checkpoint')
    catalog=json.loads((root/'datos/2_procesamiento/catalogos/catalogo_fuentes.json').read_text(encoding='utf-8'))
    annex_rel=catalog['sources']['national.geih_monthly_annex']
    annex=root/annex_rel['path']
    if _sha(annex)!=annex_rel['sha256']:
        raise ValueError('Official GEIH annex differs from frozen source catalog')
    evidence=root/'datos/2_procesamiento/auditoria_historica_h30'
    archived=json.loads((evidence/'MANIFEST.json').read_text(encoding='utf-8'))
    macro_file=next(x for x in archived['files'] if x['name'].startswith('Indicadores Económicos'))
    econ=evidence/macro_file['name']
    if _sha(econ)!=macro_file['sha256']:
        raise ValueError('Economic Excel differs from frozen evidence')
    old_national=root/'datos/2_procesamiento/fuentes_preparadas/nacional'
    old_urban=root/'datos/2_procesamiento/fuentes_preparadas/urbano'
    actual={
        'annual':extract_geih_annual(annex,root/'configs/rc1/national.toml'),
        'macro':extract_macro(econ),
        'proxies':extract_window_proxies(annex),
    }
    frozen={
        'annual':_records(old_national/'official_geih_annual.csv'),
        'macro':_records(old_national/'indicadores_mensuales_1993_2003.csv'),
        'proxies':_records(old_urban/f'proxies_anuales_ventanas_{vintage_suffix()}.csv'),
    }
    comparisons={
        'annual':compare_numeric(actual['annual'],frozen['annual'],('year',),tuple(NATIONAL.values()), 0.0001),
        'macro':compare_numeric(actual['macro'],frozen['macro'],('date','year','month'),tuple(MACRO),1e-10),
        'proxies':compare_numeric(actual['proxies'],frozen['proxies'],('dep_code','city','year'),tuple(METRICS),1e-6),
    }
    historical=old_urban/'senales_historicas_23_y_donantes.csv'
    historic_meta=catalog['sources']['urban.historical_signals']
    if _sha(historical)!=historic_meta['sha256']:
        raise ValueError('Historical urban processed snapshot was altered')
    historical_rows=_records(historical)
    if len(historical_rows)!=33*(LAST_YEAR-2006):
        raise ValueError('Unexpected historical urban snapshot coverage')
    from icml.operations.h32_urban_annex import (
        extract_urban_historical_annex, compare_historical_annex, write_csv as write_h32_csv
    )
    departmental_annual = root/catalog['sources']['departmental.annex']['path']
    if _sha(departmental_annual)!=catalog['sources']['departmental.annex']['sha256']:
        raise ValueError('Departmental annual Excel differs from frozen source catalog')
    historical_rebuilt=extract_urban_historical_annex(
        annex, old_urban/'donantes_congelados_referencia.csv',
        root/catalog['sources']['departmental.annex']['path'])
    historical_audit=compare_historical_annex(historical_rebuilt,historical_rows)
    if historical_audit['status']!='PASS':
        raise ValueError(f'Historical city annex reconstruction differs: {historical_audit}')
    status='PASS' if all(x['equivalent'] for x in comparisons.values()) else 'BLOCKED'
    summary={
        'status':status, 'reference_month':ACTIVE_CUTOFF, 'published':False,
        'source_sha256':{'geih_annex':_sha(annex),'external_indicators_excel':_sha(econ),
                         'departmental_annual_annex':_sha(departmental_annual)},
        'comparisons':comparisons,
        'urban_historical_2007_2026':{
            'status':'REGENERATED_FROM_23_CITIES_ROLLING_QUARTERS_AND_32_CITY_PROXIES',
            'rows':len(historical_rows),'frozen_sha256':_sha(historical),
            'comparison':historical_audit,
            'note':'2007-2026 GEIH historical signals are annual medians of rolling quarter windows. 2021-2026 32-city proxies come from rolling 12-month windows. Cundinamarca 2021-2024 is extracted from 24 official departmental Excel quantities, used as synthetic urban-model calibration, not observed city GEIH. Historical source donor map is NOT H30 Pareto.'},
        'national_spliced_columns':{
            'status':'FROZEN_LEGACY_DERIVED_NOT_REGENERATED',
            'columns':[k for k in frozen['macro'][0] if k.endswith('_spliced')],
            'note':'These columns are unrelated to the 7 economic series and differ from the present reconstruction vintage. National disaggregation only uses external regressors declared in national.toml.'},
        'outputs':'derived Excel source staging, NEVER replaces frozen CSV or model outputs',
    }
    if status!='PASS':
        raise ValueError(f'Source comparison failed: {comparisons}')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.icml_h31_',dir=output.parent,ignore_cleanup_errors=True) as tmp:
        stage=Path(tmp)
        write_h32_csv(stage/'senales_historicas_23_y_donantes.csv',historical_rebuilt)
        _write_csv(stage/f'proxies_anuales_ventanas_{vintage_suffix()}.csv',actual['proxies'])
        _write_csv(stage/'official_geih_annual.csv',actual['annual'])
        _write_csv(stage/'indicadores_externos_1993_2003.csv',actual['macro'])
        (stage/'H31_AUDITORIA.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # os.rename fails on Windows if the target exists or across devices; shutil.move is cross-platform.
        import shutil as _shutil
        _shutil.move(str(stage), str(output))
    return summary
