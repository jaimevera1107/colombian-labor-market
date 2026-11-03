"""Ingesta auditable de informalidad, sin empalmar definiciones no comparables.

Lee matrices de la fuente original desde ``legacy_biff.sheets`` o artifact_tool.
Cada registro corresponde a un TRIMESTRE MÓVIL (tres meses), nunca a un mes puntual.
No fusiona definiciones 2007–2021 y 2021+ ni calibra a departamentos.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .legacy_biff import sheets as legacy_sheets

MONTHS=pd.date_range('2007-01-01','2026-12-01',freq='MS')


def _label(x):
    import unicodedata
    s=''.join(c for c in unicodedata.normalize('NFKD',str(x).lower()) if not unicodedata.combining(c))
    return ' '.join(s.strip().split())


def _triple(rows, pos, idx, first_col, n, name, level, definition, source):
    """Bloque ocupados/formales/informales; emite sólo períodos completos."""
    block=rows[pos:pos+3]
    if len(block)<3: raise ValueError(f'Bloque incompleto: {name}')
    d=[]
    for k in range(n):
        v=[r[first_col+k] if first_col+k<len(r) else None for r in block]
        if not all(isinstance(x,(int,float)) and np.isfinite(x) for x in v):
            raise ValueError(f'Falta cifra en {source}: {name}, ventana {k}, {v}')
        occ,form,inf=map(float,v)
        if min(occ,form,inf)<0 or abs(occ-form-inf)>max(0.002,occ*1e-7):
            raise ValueError(f'Sin cierre ocupados=formales+informales: {name} {k} {v}')
        start=pd.Timestamp(idx)+pd.DateOffset(months=k)
        end=start+pd.DateOffset(months=2)
        d.append({'source':source,'definition':definition,'domain':level,'concept':name,
                  'period_start':start.strftime('%Y-%m-%d'), 'period_end':end.strftime('%Y-%m-%d'),
                  'reference_type':'rolling_3_month_mean','occupied_thousands':occ,
                  'formal_thousands':form,'informal_thousands':inf,'informality_rate':inf/occ if occ>0 else np.nan})
    return d


def _count_numeric(row,offset):
    k=0
    while offset+k<len(row) and isinstance(row[offset+k],(int,float)) and np.isfinite(row[offset+k]):k+=1
    return k


def extract_new(cities,national):
    """GEIH nueva: desde enero-marzo 2021; 25 bloques de ciudades y 3 de agregado nacional."""
    out=[]
    for i,r in enumerate(cities):
        if len(r)<3 or _label(r[1])!='poblacion ocupada':continue
        if i+2>=len(cities) or _label(cities[i+1][1])!='formal' or _label(cities[i+2][1])!='informal':
            raise ValueError(f'Se alteró estructura de ciudades GEIH en fila {i+1}')
        n=_count_numeric(r,2)
        if n<48:raise ValueError('Cobertura de ciudad reciente insuficiente')
        out.extend(_triple(cities,i,'2021-01-01',2,n,str(r[0]).strip(),'city',
                           'new_geih_employment_based', 'GEIH Informalidad Agosto 2026/Ciudades'))
    # Tres bloques nacionales: TOTAL / CABECERAS / RURAL; buscan secuencias, no offsets fijos.
    domain='unknown'; found=set()
    for i,r in enumerate(national):
        if len(r)==0:continue
        tag=_label(r[0]);
        if tag=='total nacional':domain='national'
        elif tag=='cabeceras':domain='urban_cabeceras'
        elif tag in ('centros poblados y rural disperso','centro poblado y rural disperso'):domain='rural'
        if tag!='poblacion ocupada':continue
        if domain in found or domain=='unknown':raise ValueError('Bloque nacional duplicado/no identificado')
        if _label(national[i+1][0])!='formal' or _label(national[i+2][0])!='informal':
            raise ValueError(f'Se alteró estructura nacional GEIH en fila {i+1}')
        n=_count_numeric(r,1)
        if n<48:raise ValueError('Cobertura nacional insuficiente')
        out.extend(_triple(national,i,'2021-01-01',1,n,domain,domain,
                           'new_geih_employment_based','GEIH Informalidad Agosto 2026/Total nacional'))
        found.add(domain)
    if found!={'national','urban_cabeceras','rural'}:raise ValueError(f'Dominios nacionales faltantes: {found}')
    df=pd.DataFrame(out)
    if df.loc[df.domain.eq('city'),'concept'].nunique()!=25:raise ValueError('Se esperan 23 ciudades y dos agregados urbanos')
    return df


def extract_old(old_cities,old_social):
    """Método antiguo basado en tamaño de empresa; agregado nacional proxy por pensiones.

    No implica que empleo no pensionado == empleo informal en la metodología nueva.
    """
    out=[]
    for i,r in enumerate(old_cities):
        if _label(r[0])!='ocupados' or i+2>=len(old_cities):continue
        if _label(old_cities[i+1][0])!='formales' or _label(old_cities[i+2][0])!='informales':continue
        name=None
        for j in range(max(i-4,0),i):
            val=str(old_cities[j][0]).strip()
            if val and (str(old_cities[j][1]).strip()=='2007' or val in ('Total 13 ciudades y AM','Total 13 áreas')):name=val
        if not name:raise ValueError(f'No se identificó ciudad vieja fila {i}')
        n=_count_numeric(r,1)
        if n<140:raise ValueError('Serie antigua ciudad incompleta')
        out.extend(_triple(old_cities,i,'2007-01-01',1,n,name,'city',
                           'old_small_firm_size', 'GEIH Informalidad Marzo 2021/Ciudades'))
    if len({x['concept'] for x in out})<20:raise ValueError('Muy pocas ciudades de metodología antigua')
    # SOLO sección de valores absolutos, nunca porcentajes subsecuentes.
    search={'total nacional':'national','cabeceras':'urban_cabeceras','centro poblado y rural disperso':'rural'}
    found=set()
    for i,r in enumerate(old_social):
        key=_label(r[0])
        if key not in search or search[key] in found: continue
        domain=search[key]; block=old_social[i+1:i+17]
        occ=next((rr for rr in block if _label(rr[0])=='total ocupados'),None)
        pens=next((rr for rr in block if _label(rr[0])=='pensiones'),None)
        if occ is None or pens is None:raise ValueError(f'No hay total y pensiones: {domain}')
        n=min(_count_numeric(occ,1),_count_numeric(pens,1))
        if n<140:raise ValueError('Serie pensiones antigua incompleta')
        for k in range(n):
            o=float(occ[k+1]);f=float(pens[k+1]);v=o-f
            if min(o,f,v)<0:raise ValueError('Empleo no pensionado negativo')
            s=pd.Timestamp('2007-01-01')+pd.DateOffset(months=k)
            e=s+pd.DateOffset(months=2)
            out.append({'source':'GEIH Informalidad Marzo 2021/Seguridad social T. nal',
                        'definition':'old_non_pension_proxy_NOT_equivalent_to_new_informality',
                        'domain':domain,'concept':domain,'period_start':s.strftime('%Y-%m-%d'),
                        'period_end':e.strftime('%Y-%m-%d'),'reference_type':'rolling_3_month_mean',
                        'occupied_thousands':o,'formal_thousands':f,'informal_thousands':v,
                        'informality_rate':v/o if o else np.nan})
        found.add(domain)
    if found!=set(search.values()):raise ValueError(f'Faltan bloques nacionales antiguos: {found}')
    return pd.DataFrame(out)


def run(old_path,new_path,output):
    output=Path(output)
    if output.exists():raise FileExistsError(f'Vintage inmutable: {output}')
    old=legacy_sheets(old_path)
    # Lector compatible con Windows y sin depender de artifact_tool.
    def mat(name, rng):
        nrows=120 if name=='Ciudades' else 45
        cells=pd.read_excel(new_path,sheet_name=name,header=None,nrows=nrows)
        return cells.astype(object).where(cells.notna(),None).values.tolist()
    reader_backend='pandas_openpyxl'
    new=extract_new(mat('Ciudades','A1:CU120'),mat('Total nacional','A1:CU45'))
    prev=extract_old(old['Ciudades'],old['Seguridad social T. nal'])
    data=pd.concat([prev,new],ignore_index=True)
    if data.duplicated(['source','domain','concept','period_end']).any():raise ValueError('Duplicados en fuente')
    data=data.sort_values(['source','domain','concept','period_end']).reset_index(drop=True)
    data['value_status']=np.where(data.occupied_thousands.eq(0), 'ZERO_SENTINEL_POSSIBLE_MISSING', 'USABLE_OBSERVATION')
    data['eligible_for_training']=data.value_status.eq('USABLE_OBSERVATION')
    output.mkdir(parents=True)
    data.to_csv(output/'informality_source_observations.csv',index=False)
    overlap=methodology_overlap_diagnostics(data)
    overlap.to_csv(output/'methodology_overlap_2021.csv',index=False)
    coverage=data.groupby(['source','definition','domain']).agg(observations=('period_end','size'),
       concepts=('concept','nunique'),earliest=('period_start','min'),latest=('period_end','max')).reset_index()
    coverage.to_csv(output/'source_coverage.csv',index=False)
    report={'status':'OFFICIAL_ROLLING_3MO_OBSERVATIONS_NO_BRIDGE_NO_DEPARTMENT_MODEL',
            'new_input_reader':reader_backend,'n_observations':len(data),'old_observations':len(prev),'new_observations':len(new),
            'n_duplicates':0,'overlap_observations':len(overlap),
            'zero_sentinel_possible_missing':int((~data.eligible_for_training).sum()),
            'valid_observations':int(data.eligible_for_training.sum()),
            'overlap_national_differences_pp':overlap.loc[overlap.domain.eq('national'),'difference_informality_pp'].round(3).tolist(),
            'max_employment_identity_error_thousands':float((data.occupied_thousands-data.formal_thousands-data.informal_thousands).abs().max()),
            'warning':'Old size-of-enterprise and nonpensioned proxy are NOT same estimand as new GEIH informal employment.',
            'input_sha256':{Path(f).name:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in (old_path,new_path)}}
    (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--old',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.old,a.new,a.output),indent=2,ensure_ascii=False))


# Los nombres antiguos difieren de los nuevos; el mapeo se usa SOLO para diagnosticar
# el empalme temporal, nunca para asumir que los estimandos son comparables.
_CITY_TO_CANONICAL={
    'total 13 areas':'13_ciudades', '13 ciudades y a.m.':'13_ciudades',
    '23 ciudades y areas':'23_ciudades', '23 ciudades y a.m.':'23_ciudades',
}

def canonical_city(name):
    s=_label(name).replace(' a.m.','').replace(' a.m','').replace(' d.c.','')
    s=_CITY_TO_CANONICAL.get(_label(name),s)
    return {'medellin':'medellin','cali':'cali','barranquilla':'barranquilla',
            'bucaramanga':'bucaramanga','manizales':'manizales','pereira':'pereira',
            'cucuta':'cucuta','monteria':'monteria','popayan':'popayan',
            'santa marta':'santa marta','bogota':'bogota'}.get(s,s)


def methodology_overlap_diagnostics(data):
    """Brecha 2021 entre fuentes, NUNCA puente automático ni validación de igualdad."""
    d=data.copy()
    d['match_key']=np.where(d.domain.eq('city'),d.concept.map(canonical_city),d.domain)
    old=d[d.definition.ne('new_geih_employment_based')]
    new=d[d.definition.eq('new_geih_employment_based')]
    keys=['domain','match_key','period_end']
    if old.duplicated(keys).any() or new.duplicated(keys).any():
        raise ValueError('Correspondencias de informalidad duplicadas')
    pairs=old.merge(new,on=keys,how='inner',validate='one_to_one',suffixes=('_old','_new'))
    if len(pairs)==0:raise ValueError('No hay solapamiento temporal entre definiciones')
    pairs['difference_informality_pp']=(pairs.informality_rate_new-pairs.informality_rate_old)*100
    pairs['ratio_occupied_new_over_old']=pairs.occupied_thousands_new/pairs.occupied_thousands_old
    return pairs[['domain','match_key','period_end','concept_old','concept_new',
                  'definition_old','definition_new','informality_rate_old','informality_rate_new',
                  'difference_informality_pp','ratio_occupied_new_over_old']]

if __name__=='__main__':main()
