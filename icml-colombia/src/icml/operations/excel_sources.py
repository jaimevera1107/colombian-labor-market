"""Auditable regeneration of ICML derived inputs from original Excel files.

Output is always staged outside the frozen checkpoint. No model fitting, no
vintage promotion, and no automatic acceptance of a changed source.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import tempfile
from pathlib import Path

from .xlsx_cached import sheets

CATEGORIES = (
    'A', 'B', 'C', 'D+E', 'F', 'G', 'I', 'H', 'J', 'K', 'L',
    'M+N', 'O+P+Q', 'R+S+T+U',
)
AREA_TYPES = ('Cabecera', 'Centros Poblados y Rural Disperso', 'Total')


class SourceFormatError(ValueError):
    """The Excel source is not compatible with the approved extractor."""


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _file(root: Path, rel: str) -> Path:
    p = (root / rel).resolve()
    if root not in p.parents or not p.is_file():
        raise FileNotFoundError(f"Invalid or missing source: {rel}")
    if p.suffix.lower() != '.xlsx':
        raise SourceFormatError(f"Expected original .xlsx: {p}")
    return p


def _roles(root: Path) -> dict[str,Path]:
    """Resolve active files from one source manifest; verify original hashes."""
    catalog=root/'datos/2_procesamiento/catalogos/REGISTRO_EXCEL_ORIGINALES_H29.json'
    roles=json.loads(catalog.read_text(encoding='utf-8'))['active_roles']
    result={}
    for role, entry in roles.items():
        rel=entry['path']
        path=(root/rel).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError(f'Missing original source role {role}: {rel}')
        if path.suffix.lower()!='.xlsx' and role!='informality_old_archive':
            raise SourceFormatError(f'Only XLSX is an active input: {role}: {rel}')
        if _sha(path)!=entry['sha256']:
            raise SourceFormatError(f'Hash mismatch in original Excel role {role}')
        result[role]=path
    return result


def _unique(rows: list[dict], fields: tuple[str, ...]) -> None:
    seen = set()
    for row in rows:
        key = tuple(row[c] for c in fields)
        if key in seen:
            raise SourceFormatError(f'Duplicate record: {key}')
        seen.add(key)


def extract_demography(paths: list[Path]) -> list[dict]:
    """Combine the 3 DANE demographic Excel publications without imputation."""
    result = []
    for file in paths:
        found = False
        for name, data in sheets(file):
            if not name.startswith('Departamental_'):
                continue
            found = True
            for index, row in data.items():
                if row.get('D') not in AREA_TYPES:
                    continue
                try:
                    code = str(row['A']).zfill(2)
                    year = int(row['C'])
                    value = int(row['E'])
                    assert value >= 0 and len(code) == 2
                except (KeyError, ValueError, TypeError, AssertionError) as exc:
                    raise SourceFormatError(f'{file.name}: row {index}') from exc
                result.append(dict(dep_code=code, dep_name=str(row['B']).strip(),
                                   year=str(year), area_type=row['D'], population=str(value)))
        if not found:
            raise SourceFormatError(f'Missing demographic sheet in {file.name}')
    _unique(result, ('dep_code','year','area_type'))
    if len(result) != 4752 or {int(r['year']) for r in result} != set(range(1993,2051)):
        raise SourceFormatError('Demographic history differs from the frozen 1993–2050 scope')
    result.sort(key=lambda r:(r['dep_code'],int(r['year']),AREA_TYPES.index(r['area_type'])))
    return result


def extract_gdp(path: Path) -> list[dict]:
    """Extract the current-price GDP Cuadro 1; never use volume Cuadro 2."""
    try:
        _, data = next(sheets(path, names=['Cuadro 1']))
    except StopIteration as exc:
        raise SourceFormatError('GDP Cuadro 1 absent') from exc
    result = []
    heads = [(index, row['A'].split(':')[0].strip())
             for index,row in data.items() if isinstance(row.get('A'), str)
             and ': valor agregado según actividad económica' in row['A']]
    for index, name in heads:
        year_labels = data.get(index+5,{})
        years = {}
        for col,label in year_labels.items():
            if len(col)>1 or col in ('A','B','C'):continue
            found = re.search(r'20[0-2][0-9]',str(label))
            if found and 2005<=int(found.group())<=2024:
                years[col] = int(found.group())
        if len(years)!=20 or set(years.values()) != set(range(2005,2025)):
            raise SourceFormatError(f'Unexpected GDP year headers: {name}')
        for row_index in range(index+6,index+18):
            row=data.get(row_index,{})
            code=re.sub(r'\s*\+\s*','+',str(row.get('B','')).strip())
            if code not in ('A','B','C','D+E','F','G+H+I','J','K','L','M+N','O+P+Q','R+S+T'):
                raise SourceFormatError(f'Unexpected GDP group: {name} {row_index} {code}')
            for col,year in years.items():
                value=row.get(col)
                if not isinstance(value,(float,int)) or value<0:
                    raise SourceFormatError(f'GDP missing/negative: {name} {code} {year}')
                result.append(dict(department=name,year=str(year),gdp_code=code,
                                   value_billion_cop=repr(float(value))))
    _unique(result,('department','year','gdp_code'))
    if len(result)!=7920 or len(heads)!=33:
        raise SourceFormatError(f'Unexpected GDP coverage: {len(heads)} territories, {len(result)} values')
    result.sort(key=lambda r:(r['department'],r['gdp_code'],int(r['year'])))
    return result


def extract_official_sectors(path:Path) -> list[dict]:
    """Extract 14 GEIH sectors from the annual departmental sheet with cell refs."""
    try:
        _,data=next(sheets(path, names=['Ocu ramas anual  Dptos CIIU 4']))
    except StopIteration as exc:
        raise SourceFormatError('Ocu ramas anual  Dptos CIIU 4 sheet absent') from exc
    result=[];departments=[]
    for index,row in data.items():
        name=row.get('A')
        if not isinstance(name,str) or data.get(index+1,{}).get('A')!='Concepto':
            continue
        years={col:int(value) for col,value in data.get(index+2,{}).items()
               if isinstance(value,(float,int)) and 2015<=value<=2025}
        if set(years.values())!=set(range(2015,2026)):continue
        departments.append(name)
        for offset,code in enumerate(CATEGORIES):
            row_index=index+6+offset
            sector=data.get(row_index,{})
            if not isinstance(sector.get('A'),str) or not sector.get('A'):
                raise SourceFormatError(f'Missing sector name: {name} row {row_index}')
            for col,year in years.items():
                value=sector.get(col)
                if not isinstance(value,(float,int)) or value<0:
                    raise SourceFormatError(f'Missing/negative sector observation: {name} {code} {year}')
                column=0
                for letter in col:column=column*26+ord(letter)-64
                result.append(dict(department=name,year=str(year),sector_code=code,
                                   employed_thousands=repr(float(value)),
                                   source_row=str(row_index),source_col=str(column)))
    _unique(result,('department','year','sector_code'))
    if len(departments)!=23 or len(result)!=3542:
        raise SourceFormatError(f'Unexpected official-sector coverage: {len(departments)} departments, {len(result)} values')
    result.sort(key=lambda r:(r['department'],int(r['year']),CATEGORIES.index(r['sector_code'])))
    return result


def extract_enh_historical(path: Path) -> list[dict]:
    """Read the frozen ENH_Final 1991–2002 values (not official GEIH series)."""
    try:
        _, data = next(sheets(path, names=['ENH_Final']))
    except StopIteration as exc:
        raise SourceFormatError('ENH_Final sheet absent') from exc
    columns = ('population_enh','pet_enh','pea_enh','employed_enh',
               'unemployed_enh','inactive_enh')
    result = []
    for row in data.values():
        year = row.get('A')
        if not isinstance(year,(float,int)) or not 1991 <= year <= 2002:
            continue
        fields = {field: repr(float(row[col])) for field,col in zip(columns,'BCDEFG')}
        result.append({'year':str(int(year)),**fields})
    _unique(result,('year',))
    if len(result)!=12 or {int(r['year']) for r in result} != set(range(1991,2003)):
        raise SourceFormatError('ENH historical coverage changed')
    result.sort(key=lambda r:int(r['year']))
    return result


def _compare(rows: list[dict], baseline: Path, numeric: tuple[str,...]) -> dict:
    """Compare independent Excel extraction against frozen CSV by all key fields."""
    with baseline.open(encoding='utf-8-sig',newline='') as f:
        historical=list(csv.DictReader(f))
    fields=list(rows[0]); key_fields=[k for k in fields if k not in numeric]
    actual={tuple(r[k] for k in key_fields):r for r in rows}
    expected={tuple(r[k] for k in key_fields):r for r in historical}
    if len(actual)!=len(rows) or len(expected)!=len(historical):
        raise SourceFormatError(f'Duplicate keys when comparing {baseline}')
    missing=expected.keys()-actual.keys();extra=actual.keys()-expected.keys()
    max_abs=0.0;errors=0
    for k in expected.keys()&actual.keys():
        for field in numeric:
            d=abs(float(actual[k][field])-float(expected[k][field]))
            max_abs=max(max_abs,d)
            if d>1e-9:errors+=1
    return dict(rows=len(rows),baseline_rows=len(historical),missing_keys=len(missing),
                extra_keys=len(extra),numeric_differences_over_1e_9=errors,
                max_absolute_difference=max_abs,baseline_sha256=_sha(baseline),
                equivalent=(len(rows)==len(historical) and not missing and not extra and not errors))


def _write(path:Path,rows:list[dict]):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def run(root: Path, output:Path, verify:bool=True) -> dict:
    """Prepare three proven derived datasets from the unchanged Excel sources."""
    root=Path(root).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError(f'Never overwrite staged outputs: {output}')
    if root==output or root in output.parents:raise ValueError('Output must be outside checkpoint')
    roles=_roles(root)
    source_paths={
      'enh':[roles['enh_historical']],
      'population':[roles['population_1993_2004'], roles['population_2005_2019'],
                    roles['population_2020_2050']],
      'gdp':[roles['gdp_2005_2024']],
      'sectors':[roles['departments_2025']],
      'informality':[roles['informality_old_archive'],roles['informality_current']],
    }
    outputs={
      'enh':('source_enh_annual.csv',extract_enh_historical(source_paths['enh'][0]),
          root/'datos/2_procesamiento/fuentes_preparadas/nacional/source_enh_annual.csv',
          ('population_enh','pet_enh','pea_enh','employed_enh','unemployed_enh','inactive_enh')),
      'population':('proyecciones_poblacion_original.csv', extract_demography(source_paths['population']),
         root/'datos/2_procesamiento/fuentes_preparadas/departamental/proyecciones_poblacion_original.csv',('population',)),
      'gdp':('gdp_groups_2005_2024.csv',extract_gdp(source_paths['gdp'][0]),
         root/'datos/2_procesamiento/sectorial_h16/inputs/gdp_groups_2005_2024.csv',('value_billion_cop',)),
      'sectors':('official_sectors_2015_2025.csv',extract_official_sectors(source_paths['sectors'][0]),
         root/'datos/2_procesamiento/sectorial_h16/inputs/official_sectors_2015_2025.csv',('employed_thousands',)),
    }
    # Original pre-2021 .xls is a FROZEN legacy archive, not a user-maintained
    # monthly input. Current and future user-supplied annexes must be XLSX.
    old_source, new_source = source_paths['informality']
    if not old_source.is_file():
        raise FileNotFoundError(f'Missing archived historical reference: {old_source}')
    if _sha(old_source) != '451907808e5636044f69c401aea9a3924a2949cdd18cc30141685afc6b7bcfdb':
        raise SourceFormatError('Frozen March 2021 historical methodology anchor changed')
    from icml.informality.extract_annexes import run as extract_informality
    with tempfile.TemporaryDirectory(prefix='icml_h29_informality_') as tmp:
        extract_informality(old_source, new_source, Path(tmp)/'extracted')
        temporary = Path(tmp)/'extracted/informality_source_observations.csv'
        baseline = root/'datos/2_procesamiento/fuentes_preparadas/informalidad/informality_source_observations.csv'
        frozen_match = _sha(temporary) == _sha(baseline)
        observations = sum(1 for _ in temporary.open(encoding='utf-8')) - 1
        audits_informality = dict(rows=observations, baseline_sha256=_sha(baseline),
                                  generated_sha256=_sha(temporary), equivalent=frozen_match,
                                  compare_type='SHA256_BYTE_EXACT',
                                  input_methodology='legacy_pre_2021_plus_2021_2026_no_bridge')
        if not frozen_match:
            return dict(status='BLOCKED',components={'informality':audits_informality},
                        outputs_written=False)
        # Preserve exact official extraction from the existing approved extractor.
        informal_bytes = temporary.read_bytes()
    # All comparisons must pass before writing anything.
    audits={}
    for component,(filename,rows,baseline,numeric) in outputs.items():
        comparison=_compare(rows,baseline,numeric) if verify else {'equivalent': None,'status':'NOT_VERIFIED'}
        audits[component]=comparison
    audits['informality'] = audits_informality
    status='PASS' if all(v['equivalent'] is True for v in audits.values()) else 'BLOCKED'
    if verify and status!='PASS':
        return dict(status='BLOCKED',components=audits,outputs_written=False)
    output.mkdir(parents=True)
    for component,(filename,rows,baseline,numeric) in outputs.items():
        _write(output/filename,rows)
        audits[component]['output_sha256']=_sha(output/filename)
    (output/'informality_source_observations.csv').write_bytes(informal_bytes)
    info=dict(status=status,outputs_written=True,components=audits,
              source_sha256={component:{p.name:_sha(p) for p in paths}
                             for component,paths in source_paths.items()},
              policy='Staged derived files only. Never alters frozen inputs or models.')
    (output/'preparation_audit.json').write_text(json.dumps(info,indent=2,ensure_ascii=False),encoding='utf-8')
    return info


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.root,args.output,verify=True)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result['status']=='PASS' else 2


if __name__=='__main__':
    raise SystemExit(main())
