"""Audited 1993–2001 H11 sector mapping from DANE ENH four broad trends.

Experimental: NONE of these 15 sectors are monthly observed prior to 2001.
Four DANE published groups + arithmetic residual constrain broad trajectories.
NO_INFO is independent of productive residual and stays at H11-link share.
Shares of modern subgroups stay at 2001-07 H11 proportions (unidentified).
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu

GROUPS = ("Agricultura", "Industria", "Comercio", "Servicios", "Otros")
SOURCE_COLS = ("agriculture", "industry", "commerce", "services", "other")
SECTORS = ("A", "B", "C", "D_E", "F", "G", "H", "I", "J", "K", "L", "M_N", "O_P_Q", "R_S_T_U", "NO_INFO")
TYPES = ("ICML_COMPLETO", "GEIH_REPRESENTADO_CNPV2018")
STATUS = "RETROPOLACION_HISTORICA_EXPERIMENTAL_CIIU_APROX"


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, records, fields=None):
    if not records:
        raise ValueError(f"empty output: {path}")
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_inputs(dane_csv, link_csv, totals_csv, mapping_csv, vintage="1958-2011"):
    mapping_rows = read_csv(mapping_csv)
    codes = [r["sector_code"] for r in mapping_rows]
    if len(mapping_rows) != 15 or set(codes) != set(SECTORS) or len(set(codes)) != 15:
        raise ValueError("Mapping must contain 15 H11 sector codes exactly once")
    mapping = {r["sector_code"]:r["dane_group"] for r in mapping_rows}
    if mapping["NO_INFO"] != "SIN_CLASIFICAR" or any(v=="SIN_CLASIFICAR" for k,v in mapping.items() if k!="NO_INFO"):
        raise ValueError("NO_INFO must be the sole unclassified entry")
    if set(mapping.values()) != set(GROUPS) | {"SIN_CLASIFICAR"}:
        raise ValueError("Mapping must cover five groups and separate unknown")
    if any(not any(g==val for g in mapping.values()) for val in GROUPS):
        raise ValueError("Every historic group must have modern members")
    data_rows = [r for r in read_csv(dane_csv) if r["vintage"]==vintage and 1993 <= int(r["year"]) <= 2001]
    if len(data_rows) != 9 or len({r["year"] for r in data_rows}) != 9:
        raise ValueError("DANE 1993–2001 must have nine unique annual observations")
    data_rows.sort(key=lambda r:int(r["year"]))
    if [int(r["year"]) for r in data_rows] != list(range(1993,2002)):
        raise ValueError("Incomplete DANE years")
    ar = np.array([[float(r[c])/100 for c in SOURCE_COLS] for r in data_rows])
    if not np.isfinite(ar).all() or np.any(ar<=0) or not np.allclose(ar.sum(axis=1),1,atol=1e-11):
        raise ValueError("Invalid DANE published shares/residual")
    link_rows = read_csv(link_csv)
    if len(link_rows)!=15 or len(set(r["sector_code"] for r in link_rows))!=15:
        raise ValueError("H11 link must contain 15 distinct sectors")
    if set(r["sector_code"] for r in link_rows) != set(SECTORS):
        raise ValueError("H11 sector codes mismatch")
    if any(r["period"]!="2001-07" or r["national_type"]!="ICML_COMPLETO" or r["scenario"]!="FULL_2015_BRIDGE" for r in link_rows):
        raise ValueError("Incorrect H11 link vintage, universe or scenario")
    link = {r["sector_code"]:float(r["sector_share"]) for r in link_rows}
    if not np.isfinite(list(link.values())).all() or min(link.values()) <= 0 or abs(sum(link.values())-1)>1e-9:
        raise ValueError("Invalid H11 link composition")
    totals_rows = read_csv(totals_csv)
    months = [f"{y:04d}-{m:02d}" for y in range(1993,2002) for m in range(1,13) if y<2001 or m<=7]
    expected = {(m,t) for m in months[:-1] for t in TYPES}
    keys = [(r["period"], r["national_type"]) for r in totals_rows]
    if len(keys)!=len(expected) or set(keys)!=expected or len(set(keys))!=len(keys):
        raise ValueError("Incomplete, duplicate or unexpected ICML occupation totals")
    totals = {(r["period"],r["national_type"]):float(r["employed"]) for r in totals_rows}
    if not np.isfinite(list(totals.values())).all() or min(totals.values())<=0:
        raise ValueError("Invalid ICML occupied levels")
    return ar, link, totals, months, mapping, mapping_rows


def monthlyize(ar, mode="september", lam=2.0, hard_2001=True, holdout=None):
    """H11-compatible quadratic monthly inverse with exact latent ENH anchors.

    2001 ECH anchored to July is a **comparison convention**, NOT a July observation.
    """
    if mode not in ("september", "annual_mean") or lam<=0:
        raise ValueError("Invalid method or lambda")
    if holdout is not None and holdout not in range(1993,2001):
        raise ValueError("Invalid holdout year")
    n=103
    years=[y for y in range(1993,2002) if y!=holdout]
    xp=np.array([(y-1993)*12+6 for y in years])
    prior = np.column_stack([np.interp(np.arange(n),xp,[ar[y-1993,j] for y in years]) for j in range(5)])
    D=sparse.diags([-np.ones(n-1), np.ones(n-1)],[0,1],shape=(n-1,n),format="csc")
    Q=sparse.eye(n,format="csc")+lam*(D.T@D).tocsc()
    conditions=[]; values=[]
    for y in range(1993,2001):
        if y==holdout:
            continue
        b=np.zeros(n)
        idx=(y-1993)*12
        if mode=="september":b[idx+8]=1.0
        else:b[idx:idx+12]=1/12
        conditions.append(b); values.append(ar[y-1993])
    if hard_2001:
        b=np.zeros(n);b[-1]=1.0
        conditions.append(b); values.append(ar[-1])
    B=sparse.csc_matrix(np.array(conditions))
    K=sparse.bmat([[Q,B.T],[B,None]],format="csc")
    rhs=np.vstack([prior,np.array(values)])
    latent=splu(K).solve(rhs)[:n]
    if not np.isfinite(latent).all() or latent.min()<=0 or np.max(np.abs(latent.sum(axis=1)-1))>1e-10:
        raise ValueError("Monthlyization violated composition simplex")
    if np.max(np.abs(B@latent-np.array(values)))>1e-10:
        raise ValueError("Monthlyization failed to respect latent constraints")
    return latent


def reconcile(latent, link, mapping, odds_factor=1.0):
    """Ratio-splice H11 group shares, keep NO_INFO independent and close shares.

    odds_factor: extreme stress scenario for within-group weights, applied with
    alternating signs to sector codes. Not an observed source or best estimate.
    """
    if odds_factor<=0:
        raise ValueError("Positive odds factor required")
    group_link=np.array([sum(link[s] for s in SECTORS if mapping[s]==g) for g in GROUPS])
    if (group_link<=0).any():raise ValueError("Empty group in H11 link")
    no_info=float(link["NO_INFO"])
    # Ratio transfer from source: source levels never replace H11 levels.
    raw=latent/latent[-1,:]*group_link[None,:]
    group_final=raw/raw.sum(axis=1,keepdims=True)*(1-no_info)
    if not np.allclose(group_final[-1],group_link,atol=1e-10):
        raise ValueError("Original H11 link not preserved")
    shares=np.zeros((len(latent),len(SECTORS)))
    horizon=np.linspace(1,0,len(latent))  # zero deviation at 2001-07
    for j,g in enumerate(GROUPS):
        subset=[i for i,s in enumerate(SECTORS) if mapping[s]==g]
        base=np.array([link[SECTORS[i]]/group_link[j] for i in subset])
        # Deliberate stress only: perturb the odds within a group by +/- factor
        # backward, and re-close the subgroup shares every month.
        signs=np.array([1 if k%2==0 else -1 for k in range(len(subset))])
        scores=base[None,:] * np.exp(np.log(odds_factor)*horizon[:,None]*signs[None,:])
        internal=scores/scores.sum(axis=1,keepdims=True)
        shares[:,subset]=internal*group_final[:,j,None]
    shares[:,SECTORS.index("NO_INFO")]=no_info
    if not np.isfinite(shares).all() or shares.min() < 0 or np.max(np.abs(shares.sum(axis=1)-1))>1e-11:
        raise ValueError("Final sector closure failed")
    if not np.allclose(shares[-1,:],[link[s] for s in SECTORS],atol=1e-11):
        raise ValueError("H11 July link altered")
    return group_final,shares,raw


def individual_internal_bounds(group_final, link, mapping, odds=1.25):
    """Non-simultaneous bounds for each unidentified H11 subgroup member.

    Relative odds of each individual member vs all other members of the same
    historic group may vary +/-25% at Jan 1993; taper to no change in July 2001.
    These are assumption bounds, NOT probabilistic confidence intervals.
    """
    n=len(group_final)
    horizon=np.linspace(1,0,n)
    result=np.zeros((n,len(SECTORS),2))
    for j,g in enumerate(GROUPS):
        members=[i for i,s in enumerate(SECTORS) if mapping[s]==g]
        base_mass=sum(link[SECTORS[i]] for i in members)
        for i in members:
            w=link[SECTORS[i]]/base_mass
            low_odds=odds**(-horizon)
            high_odds=odds**horizon
            result[:,i,0]=group_final[:,j]*(w*low_odds)/(1-w+w*low_odds)
            result[:,i,1]=group_final[:,j]*(w*high_odds)/(1-w+w*high_odds)
    result[:,SECTORS.index("NO_INFO"),:]=link["NO_INFO"]
    return result


def run(*, dane_csv, link_csv, totals_csv, mapping_csv, output, vintage="1958-2011", lam=2.0):
    """Calculate an experimental H11 extension; never mutate H11 anchor files."""
    paths=[Path(p) for p in (dane_csv,link_csv,totals_csv,mapping_csv)]
    hashes={p.name:sha256(p) for p in paths}
    ar,link,totals,months,mapping,mapping_rows=load_inputs(*paths,vintage=vintage)
    month_items=months[:-1]
    sep=monthlyize(ar,"september",lam,hard_2001=True)
    mean=monthlyize(ar,"annual_mean",lam,hard_2001=True)
    soft=monthlyize(ar,"september",lam,hard_2001=False)
    scenarios={"ENH_SEP_PRINCIPAL":sep,"MEDIA_ANUAL_SENSIBILIDAD":mean,"ECH2001_FLEXIBLE_SENSIBILIDAD":soft}
    rec={k:reconcile(v,link,mapping) for k,v in scenarios.items()}
    groups,shares,raw=rec["ENH_SEP_PRINCIPAL"]
    lohi=individual_internal_bounds(groups,link,mapping)
    # Concurrent extreme profile stress scenarios are clearly distinguished
    # from marginal, independent +/-25% assumption bounds.
    stress_up=reconcile(sep,link,mapping,odds_factor=1.25)[1]
    stress_down=reconcile(sep,link,mapping,odds_factor=1/1.25)[1]
    assert np.max(np.abs(stress_up.sum(axis=1)-1))<1e-11
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    results=[]; close=[]; bygroup=[]; sensitivity=[]; anchors=[]; bounds=[]
    for name,(g,s,preraw) in rec.items():
        for i,period in enumerate(month_items):
            for group_j,group in enumerate(GROUPS):
                bygroup.append({"period":period,"scenario":name,"source_group":group,"latent_aux_share":float(scenarios[name][i,group_j]),"final_icml_share":float(g[i,group_j]),"h11_link_share":sum(link[c] for c in SECTORS if mapping[c]==group),"historical_source_frequency":"SEPTIEMBRE_ENH" if name!="MEDIA_ANUAL_SENSIBILIDAD" else "SUPUESTO_MEDIA_ANUAL","historical_category_status":"DANE_FOUR_PUBLISHED" if group!="Otros" else "ARITHMETIC_RESIDUAL"})
            for ty in TYPES:
                total=totals[(period,ty)]
                for k,code in enumerate(SECTORS):
                    results.append({"period":period,"national_type":ty,"scenario":"FULL_2015_BRIDGE","method":name,"sector_code":code,"dane_group":mapping[code],"sector_share":float(s[i,k]),"employed_sector_persons":float(s[i,k]*total),"employed_total_persons":total,"historical_status":STATUS,"source_support":"DANE_ENH_SEPTEMBER_1993_2000+ECH_2001_CONVENTIONAL_PROXY","internal_allocation":"H11_2001_07_CONSTANT_SHARE" if code!="NO_INFO" else "FIXED_H11_NO_INFO","is_directly_observed":False})
                close.append({"period":period,"national_type":ty,"method":name,"occupied_icml":total,"sum_sectors":float(np.sum(s[i,:]*total)),"closure_error_persons":float(np.sum(s[i,:]*total)-total),"simplex_error":float(s[i].sum()-1),"no_info_share":float(s[i,SECTORS.index("NO_INFO")]),"sum_5_source_group_shares":float(g[i].sum()),"pre_close_group_sum":float(preraw[i].sum())})
    for i,period in enumerate(month_items):
        for k,code in enumerate(SECTORS):
            sensitivity.append({"period":period,"sector_code":code,"group":mapping[code],"main_share":float(shares[i,k]),"annual_mean_minus_main_pp":float((rec['MEDIA_ANUAL_SENSIBILIDAD'][1][i,k]-shares[i,k])*100),"soft_2001_minus_main_pp":float((rec['ECH2001_FLEXIBLE_SENSIBILIDAD'][1][i,k]-shares[i,k])*100),"internal_up_minus_main_pp":float((stress_up[i,k]-shares[i,k])*100),"internal_down_minus_main_pp":float((stress_down[i,k]-shares[i,k])*100)})
            bounds.append({"period":period,"sector_code":code,"group":mapping[code],"central_share":float(shares[i,k]),"lower_share_ASSUMPTION":float(lohi[i,k,0]),"upper_share_ASSUMPTION":float(lohi[i,k,1]),"band_type":"MARGINAL_NON_SIMULTANEOUS_25PCT_INTERNAL_ODDS"})
    for yi,y in enumerate(range(1993,2001)):
        for j,g in enumerate(GROUPS):
            a=float(ar[yi,j]);idx=yi*12+8
            anchors.append({"year":y,"month":"September","source_group":g,"dane_percent":a*100,"latent_september_percent":sep[idx,j]*100,"final_ICML_group_percent":groups[idx,j]*100,"source_minus_latent_pp":(a-sep[idx,j])*100,"source_minus_final_pp":(a-groups[idx,j])*100,"source_type":"ENH_SEPTIEMBRE" if g!="Otros" else "OTHER_RESIDUAL_NOT_DANE_PUBLISHED"})
    write_csv(output/"11_homologacion_historica_15_ramas.csv",mapping_rows)
    write_csv(output/"11_retropolacion_1993_2001_HOMOLOGADA_EXPERIMENTAL.csv",results)
    write_csv(output/"11_auditoria_cierre_y_no_info.csv",close)
    write_csv(output/"11_auditoria_5_agregados.csv",bygroup)
    write_csv(output/"11_auditoria_anclas_septiembre.csv",anchors)
    write_csv(output/"11_sensibilidad_temporal_e_interna.csv",sensitivity)
    write_csv(output/"11_cotas_supuestos_reparto_interno.csv",bounds)
    maxerr=max(abs(r['closure_error_persons']) for r in close)
    maxsum=max(abs(r['simplex_error']) for r in close)
    maxtemp=max(abs(r['annual_mean_minus_main_pp']) for r in sensitivity)
    maxsoft=max(abs(r['soft_2001_minus_main_pp']) for r in sensitivity)
    maxinternal=max(max(abs(r['internal_up_minus_main_pp']),abs(r['internal_down_minus_main_pp'])) for r in sensitivity)
    maxbound=max((r['upper_share_ASSUMPTION']-r['lower_share_ASSUMPTION'])*100 for r in bounds)
    noinfo_2001=link['NO_INFO']
    maxdifferenceprior=None
    q={"publication_gate":"BLOCKED_EXPERIMENTAL_HISTORICAL_HOMOLOGATION", "decision":"Use functional crosswalk and labelled backcast for 1993–2001, NOT directly observed sector months", "source":"DANE 1991–2000 ENH September, 2001 ECH annual not July, residual arithmetic", "source_vintage":vintage,"monthlyization":"H11-constrained quadratic lambda=2.0; primary ENH September, mean/soft-border sensitivity", "mapping":"CIIU3 conceptual buckets -> 15 modern H11 sectors; NO_INFO excluded from productive residual", "allocation":"Within broad groups constant H11 July-2001 proportions; no identification of individual subgroup movements", "other_group":"100% minus DANE four groups; derived, not official fifth DANE sector", "no_info":"Held fixed at H11 July-2001 share (explicit assumption), not a productive industry", "2001_ECH_caveat":"2001 ECH annual vector conditionally assigned to July as a modeling proxy, not a DANE July observation", "rows":len(results),"months":len(month_items),"branches":len(SECTORS),"universes":list(TYPES),"main_and_sensitivity_scenarios":list(scenarios),"max_closure_error_persons":maxerr,"max_simplex_error":maxsum,"max_annual_mean_vs_main_pp":maxtemp,"max_soft_link_vs_main_pp":maxsoft,"max_internal_stress_vs_main_pp":maxinternal,"max_internal_individual_bounds_width_pp":maxbound,"no_info_share_percent":noinfo_2001*100,"max_source_vs_final_enh_pp":max(abs(r['source_minus_final_pp']) for r in anchors if r['source_group']!='Otros'),"max_source_vs_aux_enh_pp":max(abs(r['source_minus_latent_pp']) for r in anchors if r['source_group']!='Otros'),"immutable_H11_after_2001_06":True,"input_sha256":hashes,"statistical_limitations":["ENH September observations, not 1993–2000 observed monthly data","2001 ECH does not identify July","DANE group names not exact CIIU4 crosswalk","4 anchors + arithmetic residual cannot determine 15 historical series","Fixed within-group shares are an assumption","Internal +/-25% odds bands are sensitivity, not confidence intervals","Strict reconciliation closes accounts, not empirical estimation error"]}
    (output/"11_puerta_homologacion_historica.json").write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding="utf-8")
    if maxerr>1e-6 or maxsum>1e-10:
        raise RuntimeError("H11 accounting closure failed")
    return q
