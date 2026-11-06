"""H30: read-only lineage audit for urban Pareto and historical Excel evidence.

Checks selected donor decisions against the reviewed RC2 Pareto study without
changing the chosen model, and separates exactly matched historic auxiliaries
from reconstructed series that belong to a different vintage.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from icml.domain.cutoff import FROZEN_CUTOFF
from icml.operations.xlsx_cached import sheets

STUDY_DONORS = {81:63, 85:50, 86:63, 88:27, 91:17, 94:5, 95:44, 97:63, 99:68}
INDICATORS = (
    'exchange_rate', 'producer_price_index', 'consumer_price_index',
    'inflation_rate', 'industrial_production_index', 'real_value_unit_uvr',
)
NATIONAL_LABOR = {
    'population': ('D', 'population_spliced'),
    'pet': ('E', 'pet_spliced'),
    'pea': ('F', 'pea_spliced'),
    'employed': ('G', 'employed_spliced'),
}


def _records(path: Path) -> list[dict[str,str]]:
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def _month(serial: object) -> str:
    return (datetime(1899, 12, 30) + timedelta(days=float(serial))).strftime('%Y-%m')


def _file_evidence(path: Path) -> dict[str,Any]:
    return {'relative_name':path.name,'sha256':sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}


def _xlsx_rows(path:Path, name:str) -> list[dict[str,object]]:
    found=list(sheets(path, names={name}))
    if len(found)!=1:
        raise ValueError(f'Expected exactly one sheet {name!r} in {path.name}')
    return [r for idx,r in sorted(found[0][1].items()) if idx>1]


def audit(root: Path) -> dict[str,Any]:
    """Validate archived decisions and independent Excel sources, without writes."""
    import pandas as pd
    from icml.urban.pipeline import load_urban_config
    from icml.urban.inputs import load_urban_sources
    from icml.urban.donors import ParetoDonorSelector
    from icml.domain.territories import load_urban_domains, UrbanDomainKind

    root=Path(root).resolve()
    cfg=load_urban_config(root/'configs/rc1/urban.toml')
    p=cfg.sources
    hist=pd.read_csv(root/p.historical_signals)
    proxies=pd.read_csv(root/p.window_proxies)
    refs=pd.read_csv(root/p.reference_donors)
    names={x.dane_code:x.name for x in load_urban_domains() if x.kind is UrbanDomainKind.OBSERVED_CITY}
    sources=load_urban_sources(
        hist,proxies,city_codes=sorted(names),
        excluded_codes=cfg.donors.excluded_codes,
        selection_years=cfg.donors.selection_years,
        published_unit_persons=cfg.donors.published_unit_persons,
    )
    selection=ParetoDonorSelector(sources,cfg.donors,names).run(
        dict(zip(refs.dep_code,refs.donor_code,strict=True))
    )
    actual=dict(zip(selection.catalog.recipient_code.astype(int),
                    selection.catalog.selected_donor_code.astype(int),strict=True))
    from icml.urban.frozen_donors import verify_frozen
    verify_frozen(root/p.frozen_selection, proxies, cfg.donors,
                  root/p.historical_signals, root/p.reference_donors, actual)
    donors_pass=(actual==STUDY_DONORS and len(selection.alternatives)==207
                 and len(selection.backtest)==23)
    frozen=json.loads((root/p.synthetic_donor).read_text(encoding='utf-8'))
    synthetic_ok=(cfg.synthetic.recipient_code==25 and cfg.synthetic.donor_code==11
                  and frozen.get('source_sha256')==sha256((root/p.historical_signals).read_bytes()).hexdigest())
    evidence_dir=root/'datos/2_procesamiento/auditoria_historica_h30'
    manifest=json.loads((evidence_dir/'MANIFEST.json').read_text(encoding='utf-8'))
    manifest_matches=all(
        (evidence_dir/x['name']).exists()
        and sha256((evidence_dir/x['name']).read_bytes()).hexdigest()==x['sha256']
        for x in manifest['files']
    )
    excels={x['name']:evidence_dir/x['name'] for x in manifest['files']}
    base=root/'datos/2_procesamiento/fuentes_preparadas/nacional/indicadores_mensuales_1993_2003.csv'
    past={x['date'][:7]:x for x in _records(base)}
    external=next(v for k,v in excels.items() if k.startswith('Indicadores Económicos'))
    observed={_month(r['A']):r for r in _xlsx_rows(external,'Datos') if 'A' in r}
    comparisons=[]
    for idx,field in enumerate(INDICATORS,2):
        letter=chr(64+idx)
        both=[(float(row[field]),float(observed[month][letter])) for month,row in past.items()
              if month in observed and letter in observed[month]]
        mismatch=sum(abs(a-b)>1e-8 for a,b in both)
        comparisons.append({'variable':field,'compared':len(both),'mismatches':mismatch,
                            'max_abs_difference':max((abs(a-b) for a,b in both),default=None)})
    economic_match=(len(past)==132 and all(x['compared']==132 and x['mismatches']==0 for x in comparisons))

    population=next(v for k,v in excels.items() if k.startswith('Departamental and National'))
    poprows=_xlsx_rows(population,'Sheet1')
    popref={ (r['dep_code'].zfill(2),int(r['year']),r['area_type']):float(r['population'])
            for r in _records(root/'datos/2_procesamiento/fuentes_preparadas/departamental/proyecciones_poblacion_original.csv')}
    n_matches=0;n_mismatches=0;missing=0
    year_range=[]
    for r in poprows:
        if not all(x in r for x in ('A','C','D','E')):continue
        key=(str(r['A']).zfill(2),int(r['C']),str(r['D']))
        year_range.append(int(r['C']))
        if key not in popref:missing+=1
        elif abs(float(r['E'])-popref[key])>0:n_mismatches+=1
        else:n_matches+=1
    population_match=(n_matches==4752 and n_mismatches==missing==0)

    labor=next(v for k,v in excels.items() if k.startswith('Reconstruction National'))
    comparison_by_quantity={k:{'matched':0,'different':0,'max_abs_difference':0.} for k in NATIONAL_LABOR}
    for r in _xlsx_rows(labor,'Sheet1'):
        if 'A' not in r:continue
        month=_month(r['A'])
        if month not in past:continue
        for quantity,(col,field) in NATIONAL_LABOR.items():
            if col not in r:continue
            entry=comparison_by_quantity[quantity]
            entry['matched']+=1
            diff=abs(float(r[col])-float(past[month][field]))
            entry['different']+=int(diff>1e-5)
            entry['max_abs_difference']=max(entry['max_abs_difference'],diff)
    labor_is_alternative=any(v['different'] for v in comparison_by_quantity.values())
    return {
        'status':'PASS' if all((donors_pass,synthetic_ok,manifest_matches,economic_match,population_match,labor_is_alternative)) else 'FAIL',
        'cutoff':FROZEN_CUTOFF,'operation':'historical read-only audit; no model recomputation',
        'pareto':{'status':'PASS' if donors_pass else 'FAIL','n_alternatives':len(selection.alternatives),
                  'n_backtest_cities':len(selection.backtest),
                  'expected_donor_codes':STUDY_DONORS,'actual_donor_codes':actual,
                  'synthetic_cundinamarca_pass':synthetic_ok, 'monthly_frozen_policy_guard':'PASS',
                  'frozen_source_inputs':[_file_evidence(root/getattr(p,k)) for k in
                    ('historical_signals','window_proxies','reference_donors','synthetic_donor')]},
        'excel_sources_integrity':manifest_matches,
        'external_economic_1993_2003':{'status':'EXACT' if economic_match else 'DIFFERENT',
                                       'columns':comparisons,'other_columns_not_attributable_to_this_excel':
                                       ['vacancies','employed_spliced','inactive_spliced','pea_spliced','pet_spliced','population_spliced','unemployed_spliced']},
        'population':{'status':'EXACT' if population_match else 'DIFFERENT',
                      'rows_exact':n_matches,'rows_mismatched':n_mismatches,'rows_missing':missing,
                      'actual_years':[min(year_range),max(year_range)]},
        'labor_reconstruction':{'status':'ALTERNATIVE_VINTAGE_NOT_DROP_IN_REPLACEMENT' if labor_is_alternative else 'MATCH',
                                'by_quantity':comparison_by_quantity},
        'sectoral_history':{'status':'EVIDENCE_ONLY','file':next(k for k in excels if k.startswith('Ind_empleo')),
                            'warning':'Do not reinterpret historical annual shares as monthly official observations'},
        'reproduction_claim':'Validates the original donor decisions and historical workbook overlaps; does not regenerate the old urban GEIH history from Excel.',
    }
