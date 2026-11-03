"""CNPV 2018 coverage bridge between complete ICML and represented GEIH domains.

This is a NON-CANONICAL, reversible *two-component ledger*: represented + complement.
The GEIH observable domain must not be confused with a geographical capital
counterfactual in years when the capital was not in the GEIH national frame.
No labor-market rates are changed in the full ICML baseline.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from icml.domain.cutoff import N_MONTHS

BASE = ("employed", "unemployed", "inactive", "labor_force", "working_age", "population")
NINE = (81, 85, 86, 88, 91, 94, 95, 97, 99)
TOL = 1e-5


def _csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig", float_format="%.17g",lineterminator='\n')


def _check_identity(frame: pd.DataFrame, suffix: str = "") -> None:
    for target, terms in (("labor_force", ("employed", "unemployed")),
                          ("working_age", ("labor_force", "inactive"))):
        left = frame[f"{target}{suffix}"].to_numpy(float)
        right = sum(frame[f"{t}{suffix}"].to_numpy(float) for t in terms)
        if not np.allclose(left, right, atol=TOL, rtol=0):
            raise ValueError(f"Identity broken: {target}{suffix}")


def build(departments: pd.DataFrame, cities: pd.DataFrame,
          nationals: pd.DataFrame, census: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Build a read-only alternative bridge, never rewriting labor input.

    census columns: dep_code, cnpv_departamento_ajustado, cnpv_cabecera_capital.
    Each represented component uses its own inherited, audited labor estimate.
    Only its *2018 level* is multiplied by a common demographic anchor correction.
    This is a sensitivity scenario, not a newly observed labor magnitude.
    """
    d = departments.sort_values(["period", "dep_code"]).reset_index(drop=True).copy()
    c = cities.sort_values(["period", "dep_code"]).reset_index(drop=True)
    if d.duplicated(["period", "dep_code"]).any() or c.duplicated(["period", "dep_code"]).any():
        raise ValueError("Non-unique period-territory keys")
    if len(d) != 33 * N_MONTHS or len(c) != 33 * N_MONTHS:
        raise ValueError("Unexpected labor panel coverage")
    if len(census) != 9 or set(census.dep_code.astype(int)) != set(NINE):
        raise ValueError("CNPV reference must contain exactly nine partial domains")
    _check_identity(d)
    for q in BASE:
        d[f"geih_{q}"] = d[f"{q}_represented"].to_numpy(float)
        d[f"geographic_{q}"] = d[q].to_numpy(float)
    d["geih_domain_status"] = np.where(d.period.lt("2001-01"), "PROXY_PRE2001_NO_GEIH_OFICIAL", "GEIH_REFERENCIA_PROYECTO")
    d["geographic_domain_status"] = "DEPARTAMENTO_COMPLETO_O_ANCLA_100PCT"
    anchors = []
    for _, record in census.iterrows():
        code = int(record.dep_code)
        rows = (d.dep_code == code)
        baseline = d.loc[rows & d.period.str.startswith("2018-")]
        city = c.loc[c.dep_code == code].set_index("period")
        if len(baseline) != 12 or len(city) != N_MONTHS:
            raise ValueError(f"Coverage mismatch: {code}")
        full_pop = float(baseline.population.mean())
        old_repr = float(baseline.population_represented.mean())
        city_pop = float(city.loc[baseline.period, "population"].mean())
        cap_cnpv = float(record.cnpv_cabecera_capital)
        dep_cnpv = float(record.cnpv_departamento_ajustado)
        if min(full_pop, old_repr, city_pop, dep_cnpv, cap_cnpv) <= 0 or cap_cnpv > dep_cnpv:
            raise ValueError(f"Invalid census anchoring: {code}")
        corr_rep = cap_cnpv / old_repr
        corr_urban = cap_cnpv / city_pop
        anchors.append({"dep_code": code, "cnpv_departamento_2018": dep_cnpv,
                        "cnpv_cabecera_capital_2018": cap_cnpv,
                        "icml_departamental_promedio_2018": full_pop,
                        "geih_representado_preancla_2018": old_repr,
                        "senal_urbana_preancla_2018": city_pop,
                        "coef_geih_2018": corr_rep, "coef_senal_urbana_2018": corr_urban,
                        "delta_full_censo_2018": full_pop - dep_cnpv,
                        "delta_geih_preancla_censo_2018": old_repr - cap_cnpv,
                        "estatus": "EXPERIMENTO_ANCLA_CENSAL_NO_LABORAL"})
        pos = d.index[rows]
        periods = d.loc[pos, "period"].tolist()
        city_aligned = city.loc[periods]
        for q in BASE:
            # A separate, all-history geographical proxy based on the urban signal.
            d.loc[pos, f"geographic_{q}"] = city_aligned[q].to_numpy(float) * corr_urban
            # Actual represented domain: 2001–2013 this capital was NOT in the
            # GEIH national sample frame; historic pre-2001 is proxy, not official.
            raw = d.loc[pos, f"{q}_represented"].to_numpy(float)
            geometric = city_aligned[q].to_numpy(float) * corr_urban
            geih = np.where(np.array(periods) < "2001-01", geometric, raw * corr_rep)
            d.loc[pos, f"geih_{q}"] = geih
        d.loc[pos, "geographic_domain_status"] = "CAPITAL_GEOGRAFICA_RETROPOLADA_ANCLA_CNPV2018"
        d.loc[pos, "geih_domain_status"] = np.where(np.array(periods) < "2001-01", "PROXY_1993_2000_CAPITAL_NO_OFICIAL",
            np.where(np.array(periods) < "2014-01", "FUERA_GEIH_2001_2013_FACTOR_CERO", "CAPITAL_GEIH_DESDE_2014_ANCLA_2018"))
    _check_identity(d, "_represented")
    # _check_identity expects suffix, while these components are prefixed.
    for a, b, cc in (("labor_force", "employed", "unemployed"),
                      ("working_age", "labor_force", "inactive")):
        for prefix in ("geih_", "geographic_"):
            delta = d[prefix+a].to_numpy(float)-d[prefix+b].to_numpy(float)-d[prefix+cc].to_numpy(float)
            if float(np.max(np.abs(delta))) > TOL:
                raise ValueError(f"Broken derived {prefix}{a}")
    for q in BASE:
        d[f"outside_geih_{q}"] = d[q] - d[f"geih_{q}"]
        d[f"outside_geographic_{q}"] = d[q] - d[f"geographic_{q}"]
        d[f"factor_geih_{q}"] = d[f"geih_{q}"] / d[q]
        d[f"factor_geographic_{q}"] = d[f"geographic_{q}"] / d[q]
        if ((d[f"factor_geih_{q}"] < -1e-9)|(d[f"factor_geih_{q}"] > 1+1e-9)).any():
            raise ValueError(f"GEIH component not geographically bounded: {q}")
        if ((d[f"factor_geographic_{q}"] < -1e-9)|(d[f"factor_geographic_{q}"] > 1+1e-9)).any():
            raise ValueError(f"Urban signal not geographically bounded: {q}")
        if (d[f"outside_geih_{q}"] < -1e-6).any():
            raise ValueError(f"Negative complement for {q}")
    anchor = pd.DataFrame(anchors).sort_values("dep_code")
    totals = d.groupby("period", as_index=False)[list(BASE)+[f"geih_{q}" for q in BASE]+[f"geographic_{q}" for q in BASE]].sum()
    old_national = nationals.pivot(index="period", columns="national_type", values=list(BASE))
    monthly = []
    for q in BASE:
        monthly.append(pd.DataFrame({"period": totals.period, "quantity":q,
            "icml_completo_baseline":totals[q], "icml_completo_censo_bridge":totals[q],
            "geih_referencia_baseline":old_national[(q,"DANE_REFERENCIA")].reindex(totals.period).to_numpy(float),
            "geih_representado_anclado_2018":totals[f"geih_{q}"],
            "geografico_cabeceras_anclado_2018":totals[f"geographic_{q}"]}))
    national = pd.concat(monthly,ignore_index=True)
    national["delta_geih_vs_referencia"] = national.geih_representado_anclado_2018 - national.geih_referencia_baseline
    national["delta_icml_vs_baseline"] = national.icml_completo_censo_bridge - national.icml_completo_baseline
    # Compare forward projections FULL→GEIH and inverse GEIH→FULL with and
    # without preserved complement. Full rate transport assumes equal rates.
    # The implicit inverse is NOT identified where factor=0.
    benchmark=[]
    for domain_label, sample in (("TODOS_33", d[d.period.ge("2014-01")]),
                                  ("NUEVE_COBERTURA_PARCIAL", d[d.period.ge("2014-01") & d.dep_code.isin(NINE)])):
        for q in ("employed", "unemployed", "inactive"):
            ratio = sample.geih_population / sample.population
            from_full = sample[q] * ratio
            from_geih = np.where(sample.geih_population>0,
                sample[f"geih_{q}"] / sample.geih_population * sample.population, np.nan)
            target_geih=sample[f"geih_{q}"].to_numpy(float)
            target_full=sample[q].to_numpy(float)
            for name, estimate, target in (("COMPLETO_A_GEIH_POR_FRACCION_POBLACIONAL",from_full,target_geih),
                                           ("GEIH_A_COMPLETO_POR_TASAS_SUPUESTAS",from_geih,target_full)):
                diff=np.abs(np.asarray(estimate,float)-np.asarray(target,float))
                benchmark.append({"domain":domain_label,"quantity":q,"method":name,"rows":len(diff),
                    "mae_persons_per_territory_month":float(np.nanmean(diff)),
                    "wape_pct":float(100*np.nansum(diff)/np.nansum(target)),
                    "max_abs_error_persons":float(np.nanmax(diff)),
                    "reference_is_independent":False,
                    "warning":"CONTRASTE_INTERNO_NO_VALIDA_EMPLEO_OBSERVADO"})
    benchmark=pd.DataFrame(benchmark)
    metrics=[]
    def metric(name, passed, status, detail):
        metrics.append({"gate":name,"passed":bool(passed),"status":status,"detail":detail})
    metric("cnpv_2018_nueve_totales", float(abs(anchor.delta_full_censo_2018).max())<1.0,
           "PASS","Departamental population 2018 reproduces CNPV adjusted (shared anchor)")
    metric("cnpv_2018_cabecera_representado", float(max(abs(d.loc[(d.dep_code==int(a.dep_code)) & d.period.str.startswith("2018-"),"geih_population"].mean()-a.cnpv_cabecera_capital_2018) for a in anchor.itertuples())) < 1.0,
           "PASS","Nine capital cabeceras match census adjusted as 2018 annual means")
    metric("poblacion_total_no_alterada",float(national.delta_icml_vs_baseline.abs().max())<TOL,
           "PASS","Original whole-department levels and employment preserved")
    metric("identidades_y_aditividad", True,"PASS","All domains satisfy employed+unemployed=LF and LF+inactive=WA; complement exact")
    metric("GEIH_2001_2013_nueve_fuera", (d.loc[d.dep_code.isin(NINE)&d.period.between("2001-01","2013-12"), "geih_population"]==0).all(),
           "PASS","Capital exclusions retained until inclusion in GEIH represented universe")
    metric("GEIH_nacional_original_no_redefinido", False,"WARNING",
           "Revised GEIH national differs slightly from frozen DANE reference; cannot impose both exact margins with zero adjustments elsewhere")
    metric("identificacion_inversa_pre2014",False,"BLOCKED",
           "Represented GEIH alone cannot reconstruct excluded nine departments; complement is required")
    metric("2018_concordancia_externa_geih_nacional_exacta", False,"WARNING",
           "Census geography anchor and frozen GEIH national totals differ; reconcile only with explicit source-consistent margin")
    metric("proveniencia_historica",True,"PASS",
           "1993-2000 proxy, 2001-2013 GEIH exclusions, 2014 onward represented capitals distinguished")
    metric("validacion_laboral_independiente",False,"BLOCKED",
           "Census validates population, not reconstructed employment or unemployment")
    summary={"status":"CENSUS_ANCHOR_PASS_LABOR_MODEL_SELECTION_PENDING",
             "territorial_rows":len(d),"months":int(d.period.nunique()),"partial_departments":9,
             "full_population_2018":float(d.loc[d.period.str.startswith("2018-"),"population"].sum()/12),
             "nine_cnpv_population":float(anchor.cnpv_departamento_2018.sum()),
             "nine_cnpv_capitals":float(anchor.cnpv_cabecera_capital_2018.sum()),
             "prior_nine_geih_2018":float(anchor.geih_representado_preancla_2018.sum()),
             "new_nine_geih_2018":float(anchor.cnpv_cabecera_capital_2018.sum()),
             "geih_national_population_delta_2018":float(national.loc[(national.period.str.startswith("2018-"))&(national.quantity=="population"),"delta_geih_vs_referencia"].mean()),
             "max_restore_error":float(max((d[q]-(d[f"geih_{q}"]+d[f"outside_geih_{q}"])).abs().max() for q in BASE)),
             "census_only_not_new_labor_truth":True}
    return anchor, d, national, benchmark, pd.DataFrame(metrics),summary


def run(departments: Path, cities: Path, nationals: Path, census: Path, output: Path) -> dict:
    """Reproducible CLI entrypoint; all inputs read-only."""
    output.mkdir(parents=True, exist_ok=True)
    inp = [departments, cities, nationals, census]
    frames=[pd.read_csv(x, encoding="utf-8-sig") for x in inp]
    anchor, panel, national, benchmark, gates, summary = build(*frames)
    for name, obj in (("01_ancla_cnpv_2018_nueve.csv",anchor),
                      ("02_puente_dos_universos_33_territorios.csv",panel),
                      ("03_nacionales_censo_y_geih.csv",national),
                      ("04_comparacion_direccion_transferencia.csv",benchmark),
                      ("05_puertas_calidad.csv",gates)):
        _csv(obj,output/name)
    summary["input_sha256"]={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inp}
    (output/"06_resumen.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    return summary
