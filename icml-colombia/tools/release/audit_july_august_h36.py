"""H36: deterministic source audit for the two consecutive DANE annex vintages.

Research audit only. No model estimates, no frozen output changes or publication.
Run from an editable ICML install or set PYTHONPATH=icml-colombia/src.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from icml.operations.h22 import inspect_annex
from icml.operations.h35_social_annex import inspect_social_annex


def hash_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            d.update(block)
    return d.hexdigest()


def run(root: Path, output: Path) -> dict:
    from icml.ingestion.discovery import INFORMALITY, LABOR, annex_for
    ingesta = root / 'datos/1_ingesta'
    paths = {
        month: {'geih': annex_for(ingesta, LABOR, month).path,
                'social': annex_for(ingesta, INFORMALITY, month).path}
        for month in ('2026-07', '2026-08')
    }
    report = {'release':'H36','final_month':'2026-08',
              'archive_is_official_statistics':False,
              'historical_publication_allowed':False,
              'months':{}, 'revisions':[], 'status':'NOT_CHECKED'}
    observations=[]
    try:
        for month, sources in paths.items():
            geih = inspect_annex(sources['geih'], [month]); social = inspect_social_annex(sources['social'],month)
            report['months'][month] = {
                'geih':{'path':str(sources['geih'].relative_to(root)),
                        'sha256':hash_file(sources['geih']), 'status':'PASS',
                        'observations':geih},
                'informality_social':{'path':str(sources['social'].relative_to(root)),
                                      'sha256':hash_file(sources['social']),
                                      'status':social['status'],
                                      'three_month_window_start':social['three_month_window_start'],
                                      'observations':social['observations'],
                                      'social_security_rolling':social['social_security_rolling']},
            }
            for row in geih:
                observations.append({'month':month,'source':'GEIH','domain':row['domain'],
                                     'reference_type':'observed_monthly',
                                     'employed_thousands':row['employed_thousands'],
                                     'unemployment_rate_pct':row['unemployment_rate_pct'],
                                     'informality_rate_pct':'', 'social_pension_thousands':''})
            for row in social['observations']:
                observations.append({'month':month,'source':'INFORMALITY',
                                     'domain':row['domain'],'reference_type':row['reference_type'],
                                     'employed_thousands':row['occupied_thousands'],
                                     'unemployment_rate_pct':'',
                                     'informality_rate_pct':row['informality_rate']*100,
                                     'social_pension_thousands':''})
            socialsec=social['social_security_rolling']
            observations.append({'month':month,'source':'SEGURIDAD_SOCIAL',
                                 'domain':'national','reference_type':'rolling_three_months',
                                 'employed_thousands':socialsec['occupied_thousands'],
                                 'unemployment_rate_pct':'','informality_rate_pct':'',
                                 'social_pension_thousands':socialsec['pension_contributors_thousands']})
        july_in_august=inspect_annex(paths['2026-08']['geih'], ['2026-07'])
        july_original=report['months']['2026-07']['geih']['observations']
        changes=[]
        for old,new in zip(july_original,july_in_august,strict=True):
            assert old['period']==new['period'] and old['domain']==new['domain']
            for key,ov in old.items():
                nv=new[key]
                if isinstance(ov,(float,int)) and abs(ov-nv)>1e-9:
                    changes.append({'domain':old['domain'],'field':key,'july_release':ov,
                                    'august_release_lookback':nv,'delta':nv-ov})
        report['revisions']=changes
        report['july_geih_prior_vintage_revisions_found']=bool(changes)
        report['status']='PASS_SOURCES_AND_JULY_REVISION_CHECK'
    except Exception as exc:
        report['status']='BLOCKED_SOURCE_VALIDATION'
        report['error']={'type':type(exc).__name__,'message':str(exc)}
    output.mkdir(parents=True,exist_ok=True)
    (output/'H36_AUDITORIA_FUENTES_JULIO_AGOSTO.json').write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if observations:
        keys=['month','source','domain','reference_type','employed_thousands',
              'unemployment_rate_pct','informality_rate_pct','social_pension_thousands']
        with (output/'H36_OBSERVACIONES_OFICIALES_JULIO_AGOSTO.csv').open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(observations)
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    result=run(args.root,args.output)
    print(json.dumps({'status':result['status'],'july_geih_revisions':len(result['revisions'])},indent=2))
    if not result['status'].startswith('PASS'):
        raise SystemExit(1)
