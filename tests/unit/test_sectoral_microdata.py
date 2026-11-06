"""Synthetic fixtures prove mechanics; never pass these off as DANE observations."""
import csv
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from icml.sectoral.microdata import monthly_microdata_share, run, _division


def _write(path, rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return path


def _base():
    return [dict(DIRECTORIO='001',SECUENCIA_P='1',ORDEN='1'),
            dict(DIRECTORIO='002',SECUENCIA_P='1',ORDEN='1'),
            dict(DIRECTORIO='003',SECUENCIA_P='1',ORDEN='1')]


def test_CIIU_mapping():
    assert _division('0501') == 5 and _division('05')==5
    assert _division('3510') == 35
    assert _division('3900')==39
    assert _division('AABB') is None


def test_2018_join_and_weights(tmp_path):
    occ=_write(tmp_path/'Ocupados.csv',_base())
    aux=_write(tmp_path/'Rama_CIIU4.csv',[dict(**r,RAMA2D_R4=v) for r,v in zip(_base(),['05','35','08'])])
    gen=_write(tmp_path/'Caracteristicas.csv',[dict(**r,FEX_C18=v) for r,v in zip(_base(),['2','3','2'])])
    r=monthly_microdata_share('2018-04',occupied=occ, classification=aux, characteristics=gen)
    assert r['share_B_in_combined']==pytest.approx(4/7)
    assert r['classification_join']=='CIIU4_file_person_key'
    assert r['weighted_utilities_D_E']==pytest.approx(3)
    assert r['microdata_occupied_rows']==3


def test_2026_inline_zip_member(tmp_path):
    csv_file=_write(tmp_path/'Ocupados.csv',[dict(**r,RAMA4D_R4=v,FEX_C18='2') for r,v in zip(_base(),['0510','3510','3910'])])
    z=tmp_path/'agosto_2026.zip'
    with zipfile.ZipFile(z,'w') as f:
        f.write(csv_file,'datos/Ocupados.csv')
        f.writestr('datos/No Ocupados.csv','other\n1\n')
    r=monthly_microdata_share('2026-08',occupied=str(z)+'::datos/Ocupados.csv')
    assert r['share_B_in_combined']==pytest.approx(1/3)
    assert r['classification_join']=='in_occupied_module'


def test_old_separate_classification_is_required(tmp_path):
    occ=_write(tmp_path/'occ.csv',[dict(**r,FEX_C18='1') for r in _base()])
    with pytest.raises(ValueError,match='mandatory'):
        monthly_microdata_share('2018-04',occupied=occ)


def test_wrong_month_ciiu_key_rejected(tmp_path):
    occ=_write(tmp_path/'occ.csv',[dict(**r,FEX_C18='1') for r in _base()])
    aux=_write(tmp_path/'aux.csv',[dict(**r,RAMA2D_R4='05') for r in _base()[:2]])
    with pytest.raises(ValueError,match='missing person identifiers'):
        monthly_microdata_share('2018-04',occupied=occ,classification=aux)


def test_duplicates_rejected(tmp_path):
    occ=_write(tmp_path/'occ.csv',[dict(**r,RAMA2D_R4='05',FEX_C18='1') for r in _base()[:1]*2])
    with pytest.raises(ValueError,match='duplicate'):
        monthly_microdata_share('2025-06',occupied=occ)


def test_no_microdata_does_not_generate_split(tmp_path):
    # Actual normalized DANE snapshot from prior artifact, not synthetic shares.
    root=Path(__file__).resolve().parents[2]
    path=root/'sectoral'/'hito10_mensual_v001'
    if not path.exists():pytest.skip('integration snapshot is outside source tree')
    result=run(observations_csv=path/'10_observaciones_oficiales_mensuales_13_grupos.csv',
        totals_csv=path/'10_totales_oficiales_mensuales.csv',output=tmp_path)
    assert result['month_count_validated_14_estimated']==0
    assert result['months_without_14_split']==140
    assert len(pd.read_csv(tmp_path/'10_matriz_cobertura_1993_2026.csv'))==404


def test_single_supported_month_without_inventing_others(tmp_path):
    root=Path(__file__).resolve().parents[2]
    path=root/'sectoral'/'hito10_mensual_v001'
    if not path.exists():pytest.skip('integration snapshot is outside source tree')
    prev=pd.read_csv(path/'10_totales_oficiales_mensuales.csv')
    old=pd.read_csv(path/'10_observaciones_oficiales_mensuales_13_grupos.csv')
    official=float(prev.loc[prev.period=='2026-08','occupied_official_persons'].iloc[0])
    combined=float(old.loc[(old.period=='2026-08')&(old.sector_code=='B_D_E_COMBINED'),'employed_persons'].iloc[0])
    rows=[]
    for j in range(300):
        code='05' if j<50 else '35' if j<150 else '10'
        weight=combined/150 if j<150 else (official-combined)/150
        rows.append({'DIRECTORIO':f'{j:06}', 'SECUENCIA_P':'1','ORDEN':'1',
            'RAMA2D_R4':code, 'FEX_C18':f'{weight:.12f}'})
    occupied=_write(tmp_path/'occ.csv',rows)
    mf=_write(tmp_path/'manifest.csv',[{'period':'2026-08','occupied':occupied.name}])
    result=run(observations_csv=path/'10_observaciones_oficiales_mensuales_13_grupos.csv',
        totals_csv=path/'10_totales_oficiales_mensuales.csv',output=tmp_path/'out',manifest_csv=mf)
    assert result['month_count_validated_14_estimated']==1
    split=pd.read_csv(tmp_path/'out'/'10_candidatos_14_ramas_SOLO_MESES_CON_MICRODATOS.csv')
    assert split.sector_code.nunique()==14 and len(split)==14
    b=float(split.loc[split.sector_code=='B','employed_persons'].iloc[0]);de=float(split.loc[split.sector_code=='D_E','employed_persons'].iloc[0])
    assert b==pytest.approx(combined/3) and b+de==pytest.approx(combined)
    assert 'ESTIMATED' in split.loc[split.sector_code=='B','observation_status'].iloc[0]
