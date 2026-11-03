"""Read-only post-calibration validation of ICML informal employment candidates.

This measures accounting, intervention, stability and candidate disagreement.
It does NOT infer departmental predictive accuracy from exact national closure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from icml.domain.cutoff import month_periods
from scipy.stats import spearmanr

from icml.informality.national_closure import calibrate_month

CANDIDATES = ("urban_direct", "mlp_residual_92", "mlp_shared19")
PERIODS = month_periods()
TOLERANCE_PEOPLE = 0.1  # exported CSVs use finite decimal precision


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _corr(x: np.ndarray, y: np.ndarray) -> float:
    if np.ptp(x) < 1e-12 or np.ptp(y) < 1e-12:
        return float("nan")
    return float(spearmanr(x, y).statistic)


def _summary(df: pd.DataFrame) -> dict:
    vals = df.to_numpy(dtype=float)
    vals = vals[np.isfinite(vals)]
    return {"count": int(len(vals)), "mean": float(vals.mean()) if len(vals) else None,
            "median": float(np.median(vals)) if len(vals) else None,
            "p95": float(np.quantile(vals, .95)) if len(vals) else None,
            "max": float(vals.max()) if len(vals) else None}


def _validate(frame: pd.DataFrame, labor: pd.DataFrame, national: pd.DataFrame,
              candidate: str) -> pd.DataFrame:
    required = {"dep_code", "period", "rate_prior", "rate_calibrated", "informal", "formal",
                "employed", "factor_employed", "informal_represented", "formal_represented"}
    if required - set(frame.columns):
        raise ValueError(f"{candidate}: missing fields: {required - set(frame.columns)}")
    if frame[["dep_code", "period"]].duplicated().any():
        raise ValueError(f"{candidate}: duplicated territory-month")
    if frame[list(required - {"period", "dep_code"})].isna().any().any():
        raise ValueError(f"{candidate}: missing accounting values")
    frame = frame.copy()
    frame["period"] = frame.period.astype(str)
    actual_periods = sorted(frame.period.unique())
    if candidate == "urban_direct":
        expected = {str(x) for x in PERIODS}
    else:
        expected = {str(x) for x in PERIODS if x.year != 2020}
    if set(actual_periods) != expected:
        raise ValueError(f"{candidate}: unexpected missing / extra periods")
    if (frame.groupby("period").dep_code.nunique() != 33).any():
        raise ValueError(f"{candidate}: incomplete departments")
    m = frame.merge(labor[["dep_code", "period", "employed", "factor_employed"]],
                    on=["dep_code", "period"], how="left", validate="one_to_one", suffixes=("", "_reference"))
    for name in ("employed", "factor_employed"):
        if m[f"{name}_reference"].isna().any() or not np.allclose(
                m[name], m[f"{name}_reference"], atol=TOLERANCE_PEOPLE if name == "employed" else 1e-9, rtol=0):
            raise ValueError(f"{candidate}: frozen {name} altered")
    if not ((m[["rate_prior", "rate_calibrated"]].to_numpy() >= 0).all()
            and (m[["rate_prior", "rate_calibrated"]].to_numpy() <= 1).all()):
        raise ValueError(f"{candidate}: impossible rate")
    if (m.employed < 0).any() or (m.informal < 0).any() or (m.formal < 0).any():
        raise ValueError(f"{candidate}: negative count")
    if np.max(np.abs(m.informal + m.formal - m.employed)) > TOLERANCE_PEOPLE:
        raise ValueError(f"{candidate}: local labor identity violation")
    if np.max(np.abs(m.informal - m.employed * m.rate_calibrated)) > TOLERANCE_PEOPLE:
        raise ValueError(f"{candidate}: calibrated rate/count mismatch")
    if np.max(np.abs(m.informal_represented - m.informal * m.factor_employed)) > TOLERANCE_PEOPLE:
        raise ValueError(f"{candidate}: represented informal count mismatch")
    targets = national.pivot(index="period", columns="national_type", values="informal_estimated")
    for period, g in m.groupby("period"):
        if abs(g.informal.sum() - targets.at[period, "ICML_COMPLETO"]) > TOLERANCE_PEOPLE:
            raise ValueError(f"{candidate} {period}: ICML national mismatch")
        if period >= "2001-01" and abs(g.informal_represented.sum() - targets.at[period, "DANE_REFERENCIA"]) > TOLERANCE_PEOPLE:
            raise ValueError(f"{candidate} {period}: DANE national mismatch")
    return m


def run(closure_root: Path, labor_path: Path, national_path: Path,
        output: Path, *, sensitivity_pp: float = 1.0) -> dict:
    """Inspect existing calibrated candidates without fitting models or changing history."""
    closure_root, labor_path, national_path, output = map(Path,
                        (closure_root, labor_path, national_path, output))
    if not (0 < sensitivity_pp <= 2):
        raise ValueError("sensitivity_pp must be in (0, 2]")
    if output.exists():
        raise FileExistsError("Output path already exists; evaluations are immutable")
    labor = pd.read_csv(labor_path)
    labor["period"] = labor.period.astype(str)
    nationals = pd.read_csv(national_path)
    nationals["period"] = nationals.period.astype(str)
    if (labor[["dep_code", "period"]].duplicated().any() or
            nationals[["national_type", "period"]].duplicated().any()):
        raise ValueError("Duplicated frozen key")
    targets = nationals.set_index(["period", "national_type"])
    frames = {}
    gate_rows = []
    interventions = []
    time_flags = []
    per_month = []
    dual_margin = []
    for name in CANDIDATES:
        root = closure_root / name
        csv = root / "08_department_informality_CALIBRATION_EXPERIMENTAL.csv"
        frame = _validate(pd.read_csv(csv), labor, nationals, name)
        frames[name] = frame
        for period, g in frame.groupby("period", sort=True):
            g = g.sort_values("dep_code")
            before, after, e, f = (g.rate_prior.to_numpy(float),
                  g.rate_calibrated.to_numpy(float), g.employed.to_numpy(float),
                  g.factor_employed.to_numpy(float))
            delta = 100 * (after - before)
            if period >= "2001-01":
                # Counterfactual single ICML margin. This isolates the extra
                # territorial intervention from the DANE represented margin.
                icml_t = float(targets.at[(period, "ICML_COMPLETO"), "informal_estimated"])
                dane_t = float(targets.at[(period, "DANE_REFERENCIA"), "informal_estimated"])
                single = calibrate_month(before, e, f, icml_t)["calibrated_rate"]
                represented_e = float(np.dot(e, f))
                single_dane_gap_pp = 100*(float(np.dot(e*f, single))-dane_t)/represented_e
                single_top = set(g.iloc[np.argsort(single)[-5:]].dep_code)
                dual_top = set(g.iloc[np.argsort(after)[-5:]].dep_code)
                dual_margin.append({"candidate":name,"period":period,
                    "single_margin_dane_gap_pp":single_dane_gap_pp,
                    "additional_mean_abs_change_pp":100*float(np.average(np.abs(after-single),weights=e)),
                    "additional_max_change_pp":100*float(np.max(np.abs(after-single))),
                    "spearman_single_vs_double":_corr(single,after),
                    "top5_overlap_single_vs_double":len(single_top&dual_top)})
            raw_rank = set(g.iloc[np.argsort(before)[-5:]].dep_code)
            post_rank = set(g.iloc[np.argsort(after)[-5:]].dep_code)
            per_month.append({"candidate": name, "period": period,
              "spearman_rank_pre_post": _corr(before, after),
              "top5_overlap": len(raw_rank & post_rank),
              "weighted_abs_intervention_pp": float(np.average(np.abs(delta), weights=e)),
              "max_intervention_pp": float(np.max(np.abs(delta))),
              "p95_intervention_pp": float(np.quantile(np.abs(delta), .95)),
              "mean_calibrated_rate_pct": 100*float(np.average(after, weights=e)),
              "factor_zero_departments": int((f == 0).sum()),
              "factor_partial_departments": int(((f > 0)&(f < 1)).sum()),
              "factor_one_departments": int((f == 1).sum())})
            for _,r in g.iterrows():
                interventions.append({"candidate":name, "dep_code":int(r.dep_code),
                  "period":period, "factor_employed":float(r.factor_employed),
                  "abs_intervention_pp":100*abs(float(r.rate_calibrated-r.rate_prior)),
                  "signed_intervention_pp":100*float(r.rate_calibrated-r.rate_prior)})
        for code, g in frame.groupby("dep_code", sort=True):
            g = g.sort_values("period")
            dates = pd.PeriodIndex(g.period, freq="M")
            consecutive = np.r_[False, np.diff(dates.asi8) == 1]
            before = 100*g.rate_prior.to_numpy(float)
            after = 100*g.rate_calibrated.to_numpy(float)
            for i in np.where(consecutive)[0]:
                jump_pre = float(before[i] - before[i-1]); jump_post=float(after[i]-after[i-1])
                if abs(jump_pre)>5 or abs(jump_post)>5:
                    time_flags.append({"candidate":name,"dep_code":int(code),"period":str(dates[i]),
                        "prior_jump_pp":jump_pre,"post_jump_pp":jump_post,
                        "added_alert_by_closure":bool(abs(jump_post)>5 and abs(jump_pre)<=5),
                        "definition_boundary":bool(str(dates[i]) == "2021-01")})
        gate_rows.extend([
            {"candidate":name,"gate":"G1_COMPLETENESS","status":"PASS" if name=="urban_direct" else "BLOCKED_2020",
                "details":f"{frame.period.nunique()} months × 33 territories"},
            {"candidate":name,"gate":"G2_FIXED_LABOR_IDENTITIES","status":"PASS", "details":"All frozen employed and exact counts conserved"},
            {"candidate":name,"gate":"G3_NATIONAL_ACCOUNTING","status":"PASS","details":"All independent domain constraints within 0.1 person"},
            {"candidate":name,"gate":"G4_TEMPORAL_AND_RANK_STABILITY","status":"REVIEW","details":"See temporal and ranking diagnostics"},
            {"candidate":name,"gate":"G5_SPATIAL_PREDICTIVE_VALIDITY","status":"NOT_VERIFIABLE","details":"No independent departmental informal outcomes"},
            {"candidate":name,"gate":"G6_TARGET_DEFINITION","status":"BLOCKED","details":"Both national targets use an inferred common rate; bridge unvalidated"},
        ])
    # Pairwise differences can be computed only where ALL candidates have predictions.
    comparison = []
    common = set.intersection(*[set(x.period.unique()) for x in frames.values()])
    for period in sorted(common):
        vals = {name:frames[name].loc[frames[name].period.eq(period)].sort_values("dep_code").rate_calibrated.to_numpy(float)
                for name in CANDIDATES}
        for i,left in enumerate(CANDIDATES):
            for right in CANDIDATES[i+1:]:
                difference = 100*np.abs(vals[left]-vals[right])
                comparison.append({"period":period,"left":left,"right":right,
                    "mean_abs_difference_pp":float(difference.mean()),
                    "max_abs_difference_pp":float(difference.max()),
                    "spearman_rank_between_models":_corr(vals[left],vals[right])})
    # Test conditional sensitivity to the national rate: same +/- change in
    # BOTH national rates, not a new independent DANE observation.
    sensitivity=[]
    sample_periods = [f"{year}-{month:02d}" for year in (1998,2007,2013,2019,2022,2025,2026)
                        for month in (1,4,7,10) if f"{year}-{month:02d}" in common]
    for name,frame in frames.items():
        for period in sample_periods:
            g=frame.loc[frame.period.eq(period)].sort_values("dep_code")
            r=g.rate_prior.to_numpy(float);e=g.employed.to_numpy(float);f=g.factor_employed.to_numpy(float)
            base=g.rate_calibrated.to_numpy(float)
            for direction in (-1,1):
                delta=direction*sensitivity_pp/100
                icml_employed=float(targets.at[(period,"ICML_COMPLETO"),"employed_frozen"])
                dane_employed=float(targets.at[(period,"DANE_REFERENCIA"),"employed_frozen"])
                t_icml=float(targets.at[(period,"ICML_COMPLETO"),"informal_estimated"])+delta*icml_employed
                t_dane=(float(targets.at[(period,"DANE_REFERENCIA"),"informal_estimated"])+delta*dane_employed)
                altered=calibrate_month(r,e,f,t_icml,
                         t_dane if period >= "2001-01" else None)["calibrated_rate"]
                drift=100*abs(np.asarray(altered)-base)
                sensitivity.append({"candidate":name,"period":period,"national_rate_perturbation_pp":direction*sensitivity_pp,
                    "mean_abs_department_change_pp":float(np.average(drift,weights=e)),
                    "max_abs_department_change_pp":float(drift.max())})
    out=output
    out.mkdir(parents=True)
    tables = {
        "09_quality_gates.csv":pd.DataFrame(gate_rows),
        "09_monthly_intervention_and_rank.csv":pd.DataFrame(per_month),
        "09_department_interventions.csv":pd.DataFrame(interventions),
        "09_temporal_flags.csv":pd.DataFrame(time_flags),
        "09_pairwise_postclosure.csv":pd.DataFrame(comparison),
        "09_national_target_sensitivity.csv":pd.DataFrame(sensitivity),
        "09_dual_margin_incremental_effect.csv":pd.DataFrame(dual_margin),
    }
    for filename,df in tables.items():
        df.to_csv(out/filename,index=False,float_format="%.12g")
    fmonth=tables["09_monthly_intervention_and_rank.csv"]
    yearly = fmonth.copy()
    yearly["year"] = yearly.period.str[:4].astype(int)
    yearly = yearly.groupby(["candidate","year"], as_index=False).agg(
        months=("period","size"), mean_intervention_pp=("weighted_abs_intervention_pp","mean"),
        maximum_intervention_pp=("max_intervention_pp","max"),
        minimum_rank_spearman=("spearman_rank_pre_post","min"))
    yearly.to_csv(out/"09_annual_summary.csv",index=False,float_format="%.12g")
    fddual=tables["09_dual_margin_incremental_effect.csv"]
    fdiff=tables["09_pairwise_postclosure.csv"]
    summary={"protocol":"icml-2.2.8-postclosure-readonly",
       "status":"EXPERIMENTAL_NOT_CERTIFIED",
       "national_closure_not_predictive_accuracy":True,
       "same_national_rate_across_universes":True,
       "n_common_months":len(common),
       "n_2020_missing_months_mlp":12,
       "candidates":{},"postclosure_pair_differences":{},
       "sensitivity_scenario_pp":sensitivity_pp,
       "limitation":"Monthly urban outcomes are latent, no independent departmental informal labels or real vintage evaluation.",
       "source_sha256":{
           "frozen_departments":_sha256(labor_path),
           "national_informal_targets":_sha256(national_path),
           **{f"calibrated_{name}":_sha256(closure_root/name/
               "08_department_informality_CALIBRATION_EXPERIMENTAL.csv")
               for name in CANDIDATES}}}
    for name in CANDIDATES:
        a=fmonth[fmonth.candidate.eq(name)]
        t=tables["09_temporal_flags.csv"]
        t=t[t.candidate.eq(name)]
        summary["candidates"][name]={
            "n_months":len(a),"intervention_pp":_summary(a.weighted_abs_intervention_pp),
            "max_local_shift_pp":float(a.max_intervention_pp.max()),
            "min_pre_post_rank_spearman":float(a.spearman_rank_pre_post.min()),
            "top5_unchanged_fraction":float(np.mean(a.top5_overlap.eq(5))),
            "monthly_gt5pp_flags_either":len(t),
            "monthly_gt5pp_flags_added_by_closure":int(t.added_alert_by_closure.sum()),
            "monthly_gt10pp_post":int((t.post_jump_pp.abs()>10).sum()),
            "second_margin_incremental_pp":_summary(
                fddual.loc[fddual.candidate.eq(name),"additional_mean_abs_change_pp"]),
            "second_margin_min_rank_spearman":float(
                fddual.loc[fddual.candidate.eq(name),"spearman_single_vs_double"].min())}
    for (left,right),g in fdiff.groupby(["left","right"]):
        summary["postclosure_pair_differences"][f"{left}__vs__{right}"]={
            "mean_abs_pp":float(g.mean_abs_difference_pp.mean()),
            "max_abs_pp":float(g.max_abs_difference_pp.max()),
            "mean_spearman":float(g.spearman_rank_between_models.mean())}
    # The existing held-out urban results are separate evidence; they are
    # NOT post-closure departmental truth, nor a model-selection certificate.
    (out/"09_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    manifest={p.name:_sha256(p) for p in sorted(out.glob("09_*")) if p.name!="09_manifest.json"}
    (out/"09_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return summary
