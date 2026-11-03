"""Nationally anchored informal/formal allocation after departmental prediction.

Reconciles the *shares* learnt by the MLP to ICML and DANE universes without
modifying any frozen employed totals. Adaptation of legacy InformalityProcessor:
its independent informal/formal scaling may violate departmental identity.

Experimental until national rate definitions and departmental transfer pass G0-G6.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import root
from scipy.special import expit, logit


class InfeasibleClosure(ValueError):
    """A national target cannot be reconciled with the fixed employment panel."""


def calibrate_month(
    rates: np.ndarray,
    employed: np.ndarray,
    factor: np.ndarray,
    icml_target_informals: float,
    dane_target_informals: float | None = None,
    *,
    tolerance_people: float = 1e-4,
) -> dict[str, np.ndarray | float | str]:
    """Minimum-Bernoulli-KL adjustment to one or two national count targets.

    Rates are an uncalibrated prior; adjusted rates are logistic offsets in
    1 and represented-employment factor. Constraints are in *persons*.
    Before 2001 the DANE reference is historical/reconstructed and its
    factor=1 is only a default: it must NOT be imposed as a second target.
    """
    p = np.asarray(rates, dtype=float)
    e = np.asarray(employed, dtype=float)
    f = np.asarray(factor, dtype=float)
    if p.ndim != 1 or e.shape != p.shape or f.shape != p.shape or not len(p):
        raise ValueError("Rates, employed and factor must be nonempty equal-length vectors")
    if not all(np.isfinite(x).all() for x in (p, e, f)):
        raise ValueError("Non-finite input")
    if np.any(e <= 0) or np.any(f < 0) or np.any(f > 1) or np.any((p < 0) | (p > 1)):
        raise ValueError("Invalid employed, coverage factor or rates")
    total = float(e.sum())
    if not (np.isfinite(icml_target_informals) and 0 < icml_target_informals < total):
        raise InfeasibleClosure("ICML informal target outside frozen national employment")
    represented_employed = float(e @ f)
    two = dane_target_informals is not None
    if two:
        if not (np.isfinite(dane_target_informals) and 0 < dane_target_informals < represented_employed):
            raise InfeasibleClosure("DANE informal target outside represented employment")
        if np.ptp(f) <= 1e-12:
            raise InfeasibleClosure("DANE factor constant: target is not an independent constraint")
    w = e / total
    eta = logit(np.clip(p, 1e-8, 1 - 1e-8))
    t_icml = icml_target_informals / total
    if two:
        t_rep = float(dane_target_informals) / total
        def equations(z):
            s = expit(eta + z[0] + z[1] * f)
            return np.array([w @ s - t_icml, (w * f) @ s - t_rep])
        def jac(z):
            s = expit(eta + z[0] + z[1] * f)
            v = w * s * (1 - s)
            return np.array([[v.sum(), v @ f], [v @ f, v @ (f * f)]])
        res = root(equations, np.zeros(2), jac=jac, method="hybr", options={"xtol": 1e-12})
        coeff = np.asarray(res.x, dtype=float)
        adjusted = expit(eta + coeff[0] + coeff[1] * f)
        residual = np.array([float(e @ adjusted - icml_target_informals),
                            float((e * f) @ adjusted - dane_target_informals)])
        if not np.isfinite(coeff).all() or np.max(abs(residual)) > tolerance_people:
            raise InfeasibleClosure(f"Two-margin closure failed; person residuals {residual.tolist()}")
    else:
        lo, hi = -80., 80.
        for _ in range(100):
            mid = (lo + hi) / 2
            if float(w @ expit(eta + mid)) < t_icml:
                lo = mid
            else:
                hi = mid
        coeff = np.array([(lo + hi) / 2, 0.])
        adjusted = expit(eta + coeff[0])
        residual = np.array([float(e @ adjusted - icml_target_informals)])
        if abs(residual[0]) > tolerance_people:
            raise InfeasibleClosure(f"Single-margin closure failed: {residual[0]}")
    informal = e * adjusted
    formal = e - informal
    return {
        "calibrated_rate": adjusted,
        "informal": informal,
        "formal": formal,
        "shift_intercept": float(coeff[0]),
        "shift_factor": float(coeff[1]),
        "residual_icml_people": float(residual[0]),
        "residual_dane_people": float(residual[1]) if two else float("nan"),
        "constraint_mode": "ICML_AND_DANE_REPRESENTED" if two else "ICML_ONLY_HISTORICAL",
    }


def original_independent_allocation(
    rates: np.ndarray, employed: np.ndarray, national_informal: float,
    national_formal: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Exact algebra of original InformalityProcessor, for diagnostic only."""
    r = np.asarray(rates, float)
    e = np.asarray(employed, float)
    a, b = r * e, (1 - r) * e
    return a / a.sum() * national_informal, b / b.sum() * national_formal


def apply_to_panel(department: pd.DataFrame, prior: pd.DataFrame,
                   nationals: pd.DataFrame, *, rate_col: str,
                   label: str, allow_missing_months: bool = False
                   ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconcile prior predictions without changes to frozen labor or targets."""
    cols = ["dep_code", "period", "employed", "factor_employed"]
    d = department[cols].merge(
        prior[["dep_code", "period", rate_col]], on=["dep_code", "period"],
        validate="one_to_one", how="left")
    d["dep_code"] = d["dep_code"].astype(int)
    if d.duplicated(["dep_code", "period"]).any():
        raise ValueError("Duplicated department-month")
    n = nationals.pivot(index="period", columns="national_type",
                        values=["informal_estimated", "employed_frozen", "informality_rate_estimated"])
    output, audit = [], []
    for month, grp in d.groupby("period", sort=True):
        if len(grp) != 33: raise ValueError(f"Missing territories {month}: {len(grp)}")
        if grp[rate_col].isna().any():
            if allow_missing_months and grp[rate_col].isna().all():
                audit.append({"period":month,"candidate":label,"status":"BLOCKED_MISSING_PREDICTIONS"})
                continue
            raise ValueError(f"Partial missing predictions in {month}")
        if month not in n.index: raise ValueError(f"No national target: {month}")
        icml = float(n.loc[month, ("informal_estimated", "ICML_COMPLETO")])
        dane = float(n.loc[month, ("informal_estimated", "DANE_REFERENCIA")])
        actual_icml = float(grp.employed.sum())
        ref_icml = float(n.loc[month, ("employed_frozen", "ICML_COMPLETO")])
        if abs(actual_icml - ref_icml) > 0.001:
            raise ValueError(f"Frozen ICML mismatch {month}")
        current_rep = float((grp.employed*grp.factor_employed).sum())
        ref_rep = float(n.loc[month, ("employed_frozen", "DANE_REFERENCIA")])
        use_dane = month >= "2001-01"
        if use_dane and abs(current_rep-ref_rep) > 0.001:
            raise ValueError(f"Frozen DANE represented mismatch {month}")
        r = grp[rate_col].to_numpy(float)
        e = grp.employed.to_numpy(float)
        f = grp.factor_employed.to_numpy(float)
        result=calibrate_month(r,e,f,icml,dane if use_dane else None)
        legacy_inf,legacy_form=original_independent_allocation(
            r,e,icml,ref_icml-icml)
        out=grp[["dep_code","period","employed","factor_employed"]].copy()
        out["rate_prior"]=r
        out["rate_calibrated"]=result["calibrated_rate"]
        out["informal"]=result["informal"]
        out["formal"]=result["formal"]
        out["informal_represented"]=out.informal*out.factor_employed
        out["formal_represented"]=out.formal*out.factor_employed
        out["candidate"]=label
        out["calibration_status"]="COUNTERFACTUAL_NOT_PUBLISHED"
        output.append(out)
        audit.append({"period":month,"candidate":label,
            "status":result["constraint_mode"],
            "raw_icml_gap_pp":100*(float(np.average(r,weights=e))-icml/ref_icml),
            "raw_dane_gap_pp":100*(float(np.average(r,weights=e*f))-dane/ref_rep) if use_dane else float("nan"),
            "mean_abs_change_pp":100*float(np.average(abs(result["calibrated_rate"]-r), weights=e)),
            "max_abs_change_pp":100*float(np.max(abs(result["calibrated_rate"]-r))),
            "residual_icml_people":result["residual_icml_people"],
            "residual_dane_people":result["residual_dane_people"],
            "max_local_identity_residual":float(np.max(abs(result["informal"]+result["formal"]-e))),
            "legacy_max_local_identity_residual":float(np.max(abs(legacy_inf+legacy_form-e))),
            "shift_intercept":result["shift_intercept"],
            "shift_factor":result["shift_factor"],
            "national_rates_same_assumption":bool(abs(
                icml/ref_icml - dane/ref_rep) < 1e-10) if use_dane else True,
            "target_provenance":"RECONSTRUCTED_EXPERIMENTAL_NOT_INDEPENDENT",
        })
    return pd.concat(output,ignore_index=True) if output else pd.DataFrame(), pd.DataFrame(audit)


def run(department_path: Path, prior_path: Path, national_path: Path,
        output_dir: Path, *,rate_col: str,label: str,
        allow_missing_months: bool=False) -> dict:
    """Read-only comparator; never alters previous datasets or published series."""
    department_path,prior_path,national_path,output_dir = map(Path,
         (department_path,prior_path,national_path,output_dir))
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("Immutable output directory already populated")
    d = pd.read_csv(department_path)
    p = pd.read_csv(prior_path)
    n = pd.read_csv(national_path)
    calibrated, audit = apply_to_panel(d,p,n,rate_col=rate_col,label=label,
                                      allow_missing_months=allow_missing_months)
    output_dir.mkdir(parents=True,exist_ok=True)
    calibrated.to_csv(output_dir/"08_department_informality_CALIBRATION_EXPERIMENTAL.csv",
                      index=False,float_format="%.12g")
    audit.to_csv(output_dir/"08_national_closure_audit.csv",index=False,float_format="%.12g")
    summary = {
       "status":"COUNTERFACTUAL_NOT_CANONICAL",
       "method":"legacy_share_allocation_adapted_to_bounded_dual_margin_kl",
       "candidate":label,
       "processed_months":len(calibrated.period.unique()) if len(calibrated) else 0,
       "blocked_months":int((audit.status=="BLOCKED_MISSING_PREDICTIONS").sum()),
       "max_local_identity_residual":float(audit.max_local_identity_residual.max()),
       "max_legacy_local_identity_residual":float(audit.legacy_max_local_identity_residual.max()),
       "max_abs_icml_residual_people":float(audit.residual_icml_people.abs().max()),
       "max_abs_dane_residual_people":float(audit.residual_dane_people.abs().max()),
       "max_rate_change_pp":float(audit.max_abs_change_pp.max()),
       "source_sha256":{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in
             (department_path,prior_path,national_path)},
    }
    (output_dir/"08_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf8")
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output_dir.iterdir() if p.is_file()}
    (output_dir/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf8")
    return summary
