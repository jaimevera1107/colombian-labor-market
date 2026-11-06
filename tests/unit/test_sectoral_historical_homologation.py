"""H11 crosswalk source preservation, calendar semantics and accounting invariants."""
from __future__ import annotations

import csv
from pathlib import Path
import numpy as np
import pytest

from icml.sectoral.historical_homologation import (
    GROUPS, SECTORS, load_inputs, monthlyize, reconcile, run,
    individual_internal_bounds, read_csv,
)

ROOT=Path(__file__).resolve().parents[2] / "datos" / "2_procesamiento" / "sectorial_h11"
IN=ROOT/'inputs'
PATHS=(IN/'dane_4_ramas_anuales_vintages.csv',
       IN/'h11_link_2001_07_FULL.csv',
       IN/'totales_icml_1993_2001.csv',
       IN/'11_crosswalk_ENH_4_grupos_a_15_ramas_CIIU4.csv')


def inputs():
    return load_inputs(*PATHS)


def test_complete_mapping_and_all_fifteen_categories():
    ar,link,totals,months,mapping,rows=inputs()
    assert ar.shape == (9,5)
    assert len(rows)==15 and set(mapping)==set(SECTORS)
    assert mapping['NO_INFO']=='SIN_CLASIFICAR'
    assert {s for s,g in mapping.items() if g=='Otros'}=={'B','D_E','F'}
    assert {s for s,g in mapping.items() if g=='Comercio'}=={'G','I'}
    assert {s for s,g in mapping.items() if g=='Servicios'}=={'H','J','K','L','M_N','O_P_Q','R_S_T_U'}
    assert len(totals)==204 and months[0]=='1993-01' and months[-1]=='2001-07'


@pytest.mark.parametrize('mode',['september','annual_mean'])
def test_dane_latent_anchor_at_right_temporal_support(mode):
    ar,*_=inputs()
    latent=monthlyize(ar,mode=mode)
    assert np.max(np.abs(latent.sum(axis=1)-1))<1e-10
    for y in range(1993,2001):
        i=(y-1993)*12
        obtained=latent[i+8] if mode=='september' else latent[i:i+12].mean(axis=0)
        assert np.max(np.abs(obtained-ar[y-1993]))<1e-11


def test_no_info_not_productive_and_link_immutable():
    ar,link,totals,months,mapping,*_=inputs()
    latent=monthlyize(ar)
    groups, shares,_=reconcile(latent,link,mapping)
    unknown=shares[:,SECTORS.index('NO_INFO')]
    assert np.max(np.abs(unknown-link['NO_INFO']))<1e-14
    assert np.max(np.abs(shares[-1]-np.array([link[k] for k in SECTORS])))<1e-11
    assert np.max(np.abs(shares.sum(axis=1)-1))<1e-11
    assert np.max(np.abs(groups.sum(axis=1)-(1-link['NO_INFO'])))<1e-11


def test_within_group_conditional_fraction_constant_at_baseline():
    ar,link,totals,months,mapping,*_=inputs()
    groups,shares,_=reconcile(monthlyize(ar),link,mapping)
    for j,g in enumerate(GROUPS):
        for i,s in enumerate(SECTORS):
            if mapping[s]==g:
                assert np.max(np.abs(shares[:,i]/groups[:,j]-link[s]/groups[-1,j]))<1e-11


def test_source_values_represent_trend_not_scale():
    ar,link,*_=inputs()
    _,shares,_=reconcile(monthlyize(ar),link,inputs()[4])
    assert abs(shares[-1,SECTORS.index('A')]-link['A'])<1e-11
    assert abs(shares[8,SECTORS.index('A')]-ar[0,0])>1e-4


def test_holdout_without_leakage_and_soft_boundary():
    ar,link,*_=inputs()
    latent=monthlyize(ar,'september',holdout=1997)
    altered=ar.copy(); altered[4,:]=[.25,.13,.22,.33,.07]
    assert np.max(np.abs(monthlyize(altered,'september',holdout=1997)-latent))<1e-11
    assert np.max(np.abs(monthlyize(ar,hard_2001=True)-monthlyize(ar,hard_2001=False)))>1e-7


def test_internal_sensitivity_is_not_confidence_interval():
    ar,link,totals,months,mapping,*_=inputs()
    latent=monthlyize(ar)
    g,base,_=reconcile(latent,link,mapping)
    limits=individual_internal_bounds(g,link,mapping)
    assert np.max(np.abs(limits[-1,:,0]-base[-1]))<1e-11
    assert np.max(np.abs(limits[-1,:,1]-base[-1]))<1e-11
    assert np.min(limits[:,:,0]-base)>-0.03
    assert np.all(limits[:,:,0]<=base+1e-12) and np.all(limits[:,:,1]>=base-1e-12)
    assert np.max(limits[:,:,1]-limits[:,:,0])>0.01
    for factor in (1.25,1/1.25):
        _,stressed,_=reconcile(latent,link,mapping,odds_factor=factor)
        assert np.max(np.abs(stressed.sum(axis=1)-1))<1e-11
        assert np.max(np.abs(stressed[-1]-base[-1]))<1e-11


def test_main_and_sensitivity_outputs_accounting_and_universes(tmp_path):
    q=run(dane_csv=PATHS[0],link_csv=PATHS[1],totals_csv=PATHS[2],mapping_csv=PATHS[3],output=tmp_path)
    assert q['months']==102 and q['rows']==9180 and q['branches']==15
    assert q['max_closure_error_persons']<1e-6 and q['max_simplex_error']<1e-10
    assert q['immutable_H11_after_2001_06']
    rows=read_csv(tmp_path/'11_retropolacion_1993_2001_HOMOLOGADA_EXPERIMENTAL.csv')
    assert '2001-07' not in {r['period'] for r in rows}
    d={}
    for r in rows:
        key=(r['period'],r['method'],r['sector_code'])
        d.setdefault(key,[]).append(float(r['sector_share']))
    assert len(d)==102*3*15
    assert all(len(v)==2 and abs(v[0]-v[1])<1e-14 for v in d.values())
    assert all(r['is_directly_observed']=='False' for r in rows)


def test_crosswalk_rejects_duplicates_or_no_info_as_economic(tmp_path):
    records=read_csv(PATHS[3]); records[0]['sector_code']='NO_INFO'
    malformed=tmp_path/'bad_map.csv'
    with malformed.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    with pytest.raises(ValueError,match='15 H11 sector codes'):
        load_inputs(*PATHS[:3],malformed)
    records=read_csv(PATHS[3]); records[-1]['dane_group']='Otros'
    with malformed.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    with pytest.raises(ValueError,match='NO_INFO'):
        load_inputs(*PATHS[:3],malformed)
