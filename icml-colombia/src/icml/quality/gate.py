"""Unify national and departmental territories and audit labor identities.

National code '00' is a *non-additive* aggregate. DANE values in its
represented columns are a published GEIH reference from 2001 onward;
in the reconstructed period they are an auxiliary model reference, NOT
an official national observation. No supplied input is modified.
"""
from __future__ import annotations

from dataclasses import dataclass

from icml.domain.territories import load_territories, territory_codes

import numpy as np
import pandas as pd

LEVELS = ("employed", "unemployed", "inactive", "labor_force", "working_age", "population")
RATES = ("unemployment_rate", "employment_rate", "participation_rate")
OFFICIAL_FROM = "2001-01"


class QualityContractError(ValueError):
    """Raised when the unified product cannot be built without loss."""


@dataclass(frozen=True)
class QualityPolicy:
    """Declared thresholds; statistical signals do not imply bad data."""

    extreme_growth_pct: float = 200.0
    structural_window_months: int = 12
    structural_unemployment_pp: float = 5.0
    structural_employment_pp: float = 4.0
    structural_participation_pp: float = 4.0
    accounting_tolerance_persons: float = 1e-5
    reference_tolerance_persons: float = 1.1
    reference_from: str = OFFICIAL_FROM


def _validate(frame: pd.DataFrame, keys: list[str], name: str) -> None:
    if frame.empty or any(key not in frame for key in keys):
        raise QualityContractError(f"{name}: missing keys or empty frame")
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise QualityContractError(f"{name}: null or duplicated keys")
    if any(q not in frame for q in LEVELS):
        if name == "national_icml":
            return
        raise QualityContractError(f"{name}: incomplete labor quantities")


def unify_territories(departments: pd.DataFrame, national: pd.DataFrame) -> pd.DataFrame:
    """Produce 33 departments plus one row '00' per month, without double count.

    The national represented values are taken from national_icml.dane_*. In
    pre-GEIH months they are *reconstructed references*, explicitly marked.
    The effective national factor is represented / whole-territory total
    from 2001 onward; pre-2001 factors are 1 by the reconstructed-universe rule.
    """
    _validate(departments, ["dep_code", "period"], "departmental_factors")
    _validate(national, ["period"], "national_icml")
    needed = [f"icml_{q}" for q in LEVELS] + [f"dane_{q}" for q in LEVELS]
    missing = [c for c in needed if c not in national]
    if missing:
        raise QualityContractError(f"national_icml missing {missing}")
    dep = departments.copy()
    if set(dep["dep_code"].astype(int).unique()) != set(territory_codes()):
        raise QualityContractError("Expected exactly the 33 canonical territories")
    periods = sorted(dep["period"].astype(str).unique())
    if periods != sorted(national["period"].astype(str).unique()):
        raise QualityContractError("National/territorial calendars differ")
    if not (dep.groupby("period").size() == 33).all():
        raise QualityContractError("Exactly 33 territories required per month")
    names = {t.dane_code: t.name for t in load_territories()}
    dep["territory_name"] = dep["dep_code"].astype(int).map(names)
    dep["dep_code"] = dep["dep_code"].map(lambda x: f"{int(x):02d}")
    dep["territory_id"] = "CO-" + dep["dep_code"]
    dep["territory_level"] = "DEPARTAMENTO"
    dep["is_aggregate"] = False
    dep["is_additive_member"] = True
    dep["reference_status"] = np.where(
        dep["period"] >= OFFICIAL_FROM, "GEIH_REFERENCIA", "HISTORICO_RECONSTRUIDO"
    )
    # National row follows the same quantities and representativeness contract.
    nat = pd.DataFrame({"period": national["period"].astype(str).to_numpy()})
    nat["dep_code"] = "00"
    nat["territory_id"] = "CO-00"
    nat["territory_name"] = "Colombia (ICML, 33 territorios)"
    nat["is_additive_member"] = False
    nat["year"] = nat["period"].str[:4].astype(int)
    nat["source"] = "NACIONAL_ICML_SUMA_33"
    nat["territory_level"] = "NACIONAL_ICML"
    nat["is_aggregate"] = True
    nat["reference_status"] = np.where(
        nat["period"] >= OFFICIAL_FROM, "GEIH_PUBLICADA", "HISTORICO_RECONSTRUIDO"
    )
    for q in LEVELS:
        nat[q] = national[f"icml_{q}"].to_numpy(dtype=float)
        nat[f"{q}_represented"] = np.where(
            nat["period"].lt(OFFICIAL_FROM),
            nat[q].to_numpy(dtype=float),
            national[f"dane_{q}"].to_numpy(dtype=float),
        )
        valid = nat["period"].ge(OFFICIAL_FROM).to_numpy() & (nat[q].to_numpy(dtype=float) > 0)
        nat[f"factor_{q}"] = np.divide(
            nat[f"{q}_represented"], nat[q],
            out=np.ones(len(nat), dtype=float), where=valid,
        )
    for q in ("employed", "unemployed", "inactive", "population"):
        nat[f"{q}_residual_share"] = 0.0  # not applicable for aggregate
    nat["unemployment_rate"] = nat["unemployed"] / nat["labor_force"]
    nat["employment_rate"] = nat["employed"] / nat["working_age"]
    nat["participation_rate"] = nat["labor_force"] / nat["working_age"]
    cols = list(dict.fromkeys([*dep.columns, *nat.columns]))
    unified = pd.concat(
        [dep.reindex(columns=cols), nat.reindex(columns=cols)], ignore_index=True
    ).sort_values(["period", "dep_code"], kind="stable").reset_index(drop=True)
    # National population coverage gap remains derived; not double counted.
    for q in LEVELS:
        unified[f"coverage_gap_{q}"] = (
            unified[q] - unified[f"{q}_represented"]
        )
    return unified


def identity_diagnostics(frame: pd.DataFrame, *, key: str) -> pd.DataFrame:
    """Row-level accounting residuals; not a sum across levels."""
    result = frame[[key, "period"]].copy()
    result["labor_force_residual"] = frame["labor_force"] - (
        frame["employed"] + frame["unemployed"]
    )
    result["working_age_residual"] = frame["working_age"] - (
        frame["labor_force"] + frame["inactive"]
    )
    result["population_residual"] = np.minimum(
        0.0, frame["population"] - frame["working_age"]
    )
    if all(f"{q}_represented" in frame for q in LEVELS):
        result["represented_labor_force_residual"] = (
            frame["labor_force_represented"]
            - frame["employed_represented"] - frame["unemployed_represented"]
        )
        result["represented_working_age_residual"] = (
            frame["working_age_represented"]
            - frame["labor_force_represented"] - frame["inactive_represented"]
        )
    else:
        result["represented_labor_force_residual"] = np.nan
        result["represented_working_age_residual"] = np.nan
    for q, numer, denom in (
        ("unemployment_rate", "unemployed", "labor_force"),
        ("employment_rate", "employed", "working_age"),
        ("participation_rate", "labor_force", "working_age"),
    ):
        if q in frame:
            result[f"{q}_residual"] = frame[q] - frame[numer] / frame[denom]
    return result


def extreme_changes(frame: pd.DataFrame, key: str, policy: QualityPolicy, kind: str) -> pd.DataFrame:
    """Flag threefold increases, symmetric threefold falls, and zero switches.

    No division by zero is ever classified as a finite percentage.
    """
    rows: list[pd.DataFrame] = []
    levels = ("employed", "unemployed", "inactive", "working_age", "population")
    data = frame.sort_values([key, "period"]).copy()
    for q in levels:
        for lag, comparison in ((1, "MoM"), (12, "YoY")):
            old = data.groupby(key)[q].shift(lag)
            new = data[q]
            ratio = new / old.where(old > 0, np.nan)
            threshold = 1 + policy.extreme_growth_pct / 100.0
            spike = (ratio >= threshold) | (ratio <= 1 / threshold)
            zero_switch = old.notna() & (((old == 0) & (new > 0)) | ((old > 0) & (new == 0)))
            mask = spike | zero_switch
            if not mask.any():
                continue
            tmp = data.loc[mask, [key, "period"]].copy()
            tmp["product"] = kind
            tmp["quantity"] = q
            tmp["comparison"] = comparison
            tmp["previous"] = old[mask].to_numpy()
            tmp["current"] = new[mask].to_numpy()
            tmp["change_pct"] = (100 * (ratio[mask] - 1)).to_numpy()
            tmp["rule"] = np.where(zero_switch[mask], "ZERO_TRANSITION", "SYMMETRIC_200_PCT")
            rows.append(tmp)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=[key, "period", "product", "quantity", "comparison", "previous", "current", "change_pct", "rule"]
    )


def structural_breaks(frame: pd.DataFrame, key: str, policy: QualityPolicy, kind: str) -> pd.DataFrame:
    """Screen persistent rate level shifts using two adjacent yearly windows.

    This is a *candidate break screen*, not a causality test. Consecutive
    flagged months for one episode are thinned to its largest absolute
    median shift in each 6-month segment.
    """
    rows = []
    w = policy.structural_window_months
    limits = {
        "unemployment_rate": policy.structural_unemployment_pp,
        "employment_rate": policy.structural_employment_pp,
        "participation_rate": policy.structural_participation_pp,
    }
    for entity, part in frame.sort_values("period").groupby(key, sort=True):
        part = part.sort_values("period").reset_index(drop=True)
        for q, limit in limits.items():
            if q in part:
                rate = part[q].to_numpy(dtype=float)
            else:
                numer, denom = {
                    "unemployment_rate": ("unemployed", "labor_force"),
                    "employment_rate": ("employed", "working_age"),
                    "participation_rate": ("labor_force", "working_age"),
                }[q]
                rate = (part[numer] / part[denom]).to_numpy(dtype=float)
            suspects = []
            for idx in range(w, len(rate) - w + 1):
                a, b = rate[idx-w:idx], rate[idx:idx+w]
                if not (np.isfinite(a).all() and np.isfinite(b).all()):
                    continue
                shift = 100 * (np.median(b) - np.median(a))
                if abs(shift) >= limit:
                    suspects.append((idx, shift))
            # Keep the strongest shift in a local cluster; not one event per month.
            clusters = []
            for item in suspects:
                if not clusters or item[0] - clusters[-1][-1][0] > 6:
                    clusters.append([item])
                else:
                    clusters[-1].append(item)
            for cluster in clusters:
                idx, shift = max(cluster, key=lambda x: abs(x[1]))
                period = str(part.at[idx, "period"])
                rows.append({
                    "entity": str(entity).zfill(2), "period": period,
                    "product": kind, "rate": q, "shift_pp": shift,
                    "window_months": w,
                    "known_context": (
                        "PANDEMIA_2020" if "2020-01" <= period <= "2020-12"
                        else "CAMBIO_MARCO_2021" if "2021-01" <= period <= "2021-12"
                        else "AMPLIACION_2014" if "2014-01" <= period <= "2014-06"
                        else "EMPALME_2001" if "2001-01" <= period <= "2001-06"
                        else "NO_PREASIGNADO"
                    ),
                })
    return pd.DataFrame(rows, columns=["entity", "period", "product", "rate", "shift_pp", "window_months", "known_context"])


def monthly_demographic_jumps(frame: pd.DataFrame, key: str, kind: str) -> pd.DataFrame:
    """Screen >1% changes in population / working_age, non-blocking."""
    data = frame.sort_values([key, "period"]).copy()
    records = []
    for q in ("population", "working_age"):
        previous = data.groupby(key)[q].shift(1)
        pct = 100 * (data[q] / previous - 1)
        mask = previous.gt(0) & pct.abs().gt(1.0)
        if mask.any():
            tmp = data.loc[mask, [key, "period"]].copy()
            tmp["product"] = kind
            tmp["quantity"] = q
            tmp["change_pct"] = pct[mask].to_numpy()
            records.append(tmp)
    return pd.concat(records, ignore_index=True) if records else pd.DataFrame(
        columns=[key,"period","product","quantity","change_pct"]
    )


def annual_linearity(frame: pd.DataFrame, key: str, kind: str) -> pd.DataFrame:
    """Test annual straight-line shape separately from closure and anchas.

    Nonlinearity is a diagnostic, not permission to overwrite official data.
    A flat year is explicitly identified because it creates January steps.
    """
    records = []
    base = frame.assign(year=frame["period"].astype(str).str[:4].astype(int))
    for (entity, year), part in base.groupby([key,"year"]):
        part = part.sort_values("period")
        if len(part) < 4:
            continue
        x = np.arange(len(part),dtype=float)
        for q in ("population","working_age"):
            values = part[q].to_numpy(dtype=float)
            slope, intercept = np.polyfit(x,values,1)
            fitted = slope*x+intercept
            residual = float(np.max(np.abs(values-fitted)))
            pct = 100 * residual / max(float(np.mean(values)),1.0)
            plateau = bool(np.max(values)-np.min(values) <= 1e-5)
            records.append({
                "entity":str(entity).zfill(2),"year":int(year),"product":kind,
                "quantity":q,"months":len(part),"slope_persons_per_month":float(slope),
                "max_linearity_residual_persons":residual,
                "max_linearity_residual_pct":pct,
                "annual_plateau":plateau,
                "shape_flag": (
                    "YEARLY_PLATEAU" if plateau
                    else "STRONG_NONLINEARITY" if pct > 2
                    else "MODERATE_NONLINEARITY" if pct > .5
                    else "NEAR_LINE"),
            })
    return pd.DataFrame(records)


def audit_products(
    unified: pd.DataFrame,
    urban: pd.DataFrame,
    reference: pd.DataFrame,
    policy: QualityPolicy = QualityPolicy(),
    official_deviation: pd.DataFrame | None = None,
) -> tuple[dict[str, pd.DataFrame], dict]:
    """Audit hard invariants and soft time-series warnings independently."""
    _validate(unified, ["dep_code", "period"], "unified")
    _validate(urban, ["city_code", "period"], "urban_signals")
    _validate(reference, ["period"], "national_icml")
    if unified.groupby("period").size().ne(34).any():
        raise QualityContractError("Unified panel must include 34 rows per month")
    if unified[unified["dep_code"] == "00"].shape[0] != reference.shape[0]:
        raise QualityContractError("Missing national 00 months")
    if (unified["is_aggregate"] != unified["dep_code"].eq("00")).any():
        raise QualityContractError("Invalid aggregate marking")
    if (unified["is_additive_member"] != unified["dep_code"].ne("00")).any():
        raise QualityContractError("Aggregate must be excluded from sums")
    if urban.groupby("period").size().ne(33).any():
        raise QualityContractError("Urban product must include 33 rows per month")
    periods = sorted(str(p) for p in reference["period"])
    required = list(pd.period_range(periods[0], periods[-1], freq="M").astype(str))
    if periods != required:
        raise QualityContractError("National months are not contiguous")
    if sorted(unified["period"].unique()) != periods or sorted(urban["period"].unique()) != periods:
        raise QualityContractError("Product calendars differ")
    diagnostics = {
        "territories": identity_diagnostics(unified, key="dep_code"),
        "urban": identity_diagnostics(urban, key="city_code"),
    }
    # Assess finite, positive magnitudes and meaningful rate bounds.
    hard = []
    for name, frame in (("territories", unified), ("urban", urban)):
        numeric = frame[list(LEVELS)].to_numpy(dtype=float)
        bad = ~np.isfinite(numeric) | (numeric < -policy.accounting_tolerance_persons)
        if bad.any():
            hard.append(f"{name}: {int(bad.sum())} invalid levels")
        if (frame["working_age"] > frame["population"] + policy.accounting_tolerance_persons).any():
            count = int((frame["working_age"] > frame["population"] + policy.accounting_tolerance_persons).sum())
            hard.append(f"{name}: {count} working-age > population")
        if (frame["labor_force"] <= 0).any() or (frame["working_age"] <= 0).any():
            hard.append(f"{name}: non-positive denominators")
        for col in ("labor_force_residual", "working_age_residual", "represented_labor_force_residual", "represented_working_age_residual"):
            resid = diagnostics[name][col]
            max_resid = float(resid.abs().max())
            # The GEIH source rounds its national LF (1 person) and WA
            # (0.1 persons). Use source tolerance for represented values;
            # never overwrite the DANE-provided reference to force closure.
            tol = (policy.reference_tolerance_persons if col.startswith("represented_")
                   else policy.accounting_tolerance_persons)
            if max_resid > tol:
                hard.append(f"{name}: {col} max {max_resid:.8f}")
        for q in RATES:
            rate = (
                frame[q] if q in frame else
                frame[{"unemployment_rate":"unemployed", "employment_rate":"employed", "participation_rate":"labor_force"}[q]] /
                frame[{"unemployment_rate":"labor_force", "employment_rate":"working_age", "participation_rate":"working_age"}[q]]
            )
            if rate.lt(-1e-10).any() or rate.gt(1+1e-10).any():
                hard.append(f"{name}: invalid {q}")
            if q in frame and diagnostics[name][f"{q}_residual"].abs().max() > 1e-10:
                hard.append(f"{name}: published rate inconsistent {q}")
    for q in LEVELS:
        col = f"factor_{q}"
        if (unified[col].isna().any()
            or unified[col].lt(-1e-10).any()
            or unified[col].gt(1+1e-10).any()):
            hard.append(f"factors: out of range {col}")
        if not unified.loc[unified["period"].lt(policy.reference_from), col].eq(1).all():
            hard.append(f"factors: pre-2001 historical {col} must be 1")
        if (unified[f"{q}_represented"] -
            unified[q] * unified[col]).abs().max() > policy.accounting_tolerance_persons:
            hard.append(f"factors: represented != factor * {q}")
    # 00 must be SUM of 33 complete territories, not the DANE series.
    sums = unified[unified.dep_code != "00"].groupby("period")[list(LEVELS)].sum()
    nation = unified[unified.dep_code == "00"].set_index("period")
    alignment = []
    dane = reference.set_index("period")
    for q in LEVELS:
        own = (sums[q] - nation[q]).abs()
        if own.max() > policy.accounting_tolerance_persons:
            hard.append(f"national 00 != sum 33 for {q}: {own.max():.8f}")
        represented_sum = unified[unified.dep_code != "00"].groupby("period")[f"{q}_represented"].sum()
        for period in sums.index:
            official_month = period >= policy.reference_from
            represented_err = represented_sum[period] - nation.at[period, f"{q}_represented"]
            cross_err = nation.at[period,f"{q}_represented"] - dane.at[period, f"dane_{q}"]
            alignment.append({"period":period,"quantity":q,"reference_status": "GEIH_PUBLICADA" if official_month else "HISTORICO_RECONSTRUIDO", "sum_33":sums.at[period,q],"national_00":nation.at[period,q],"sum_33_represented":represented_sum[period],"national_reference":nation.at[period,f"{q}_represented"], "delta_33_minus_00":sums.at[period,q]-nation.at[period,q], "delta_represented_minus_reference":represented_err, "delta_00_reference_minus_input":cross_err})
            if official_month and abs(represented_err) > policy.reference_tolerance_persons:
                hard.append(f"DANE coverage {period}/{q}: {represented_err:.8f}")
    diagnostics["reference_alignment"] = pd.DataFrame(alignment)
    if official_deviation is not None:
        od = official_deviation.copy()
        expected = 100 * (od["published"] / od["official"] - 1)
        delta = od["published"] - od["official"]
        err_pct = (expected - od["deviation_pct"]).abs()
        err_persons = (delta - od["deviation_persons"]).abs()
        if od["official"].le(0).any() or not np.isfinite(expected).all():
            hard.append("official deviations: invalid reference levels")
        if err_pct.max() > 1e-8 or err_persons.max() > policy.accounting_tolerance_persons:
            hard.append("official deviations: formulas inconsistent")
        diagnostics["official_deviation_check"] = od.assign(
            verified_deviation_pct=expected,
            difference_pct=err_pct,
            difference_persons=err_persons,
        )
        diagnostics["official_accuracy_summary"] = (
            od.groupby(["reference_type","quantity"])["deviation_pct"]
              .agg(n="size",median_abs_pct=lambda x: x.abs().median(),
                   p95_abs_pct=lambda x: x.abs().quantile(.95),
                   max_abs_pct=lambda x: x.abs().max())
              .reset_index()
        )
    dep = unified[unified.dep_code != "00"]
    entity_products = ((unified, "dep_code", "TERMINAL_UNIFICADO"), (urban, "city_code", "CIUDADES"))
    extreme_frames = [
        extreme_changes(frame, key, policy, name).rename(columns={key:"entity"})
        for frame, key, name in entity_products
    ]
    diagnostics["extreme_changes"] = pd.concat(
        [f for f in extreme_frames if not f.empty] or extreme_frames[:1],
        ignore_index=True,
    )
    diagnostics["structural_breaks"] = pd.concat(
        [structural_breaks(frame, key, policy, name) for frame, key, name in entity_products],
        ignore_index=True,
    )
    jump_frames = [
        monthly_demographic_jumps(frame,key,name).rename(columns={key:"entity"})
        for frame,key,name in entity_products
    ]
    diagnostics["demographic_jumps"] = pd.concat(
        [f for f in jump_frames if not f.empty] or jump_frames[:1],
        ignore_index=True,
    )
    diagnostics["annual_linearity"] = pd.concat([
        annual_linearity(unified,"dep_code","TERMINAL_UNIFICADO"),
        annual_linearity(urban,"city_code","CIUDADES"),
    ],ignore_index=True)
    if not diagnostics["demographic_jumps"].empty:
        jump = diagnostics["demographic_jumps"]
        annual = jump["period"].str.endswith("-01") & jump["period"].lt("2001-01")
        jump["classification"] = np.where(
            annual & jump["quantity"].eq("population") & jump["product"].eq("TERMINAL_UNIFICADO"),
            "ESCALON_ANUAL_PROYECCION_REVISAR", "IRREGULARIDAD_DEMOGRAFICA_REVISAR"
        )
    if not diagnostics["extreme_changes"].empty:
        diagnostics["extreme_changes"]["review_status"] = "PENDIENTE_INSPECCION"
    if not diagnostics["structural_breaks"].empty:
        screen = diagnostics["structural_breaks"]
        screen["review_status"] = np.where(
            screen["known_context"].eq("NO_PREASIGNADO"),
            "PENDIENTE_EXPLICACION", "CONTEXTO_CONOCIDO_SIN_VERIFICAR"
        )
    # These are warnings by default; never alter observed or predicted cells.
    linearity = diagnostics["annual_linearity"]
    severe_linearity = linearity["shape_flag"].eq("STRONG_NONLINEARITY")
    annual_plateaus = linearity["annual_plateau"] & linearity["quantity"].eq("population")
    methodological_warnings = int(severe_linearity.sum() + annual_plateaus.sum())
    summary = {
        "status": ("BLOQUEADO" if hard else
                   "REQUIERE_REVISION_METODOLOGICA" if methodological_warnings else
                   "APTO_CON_ALERTAS_POR_REVISAR" if any(len(diagnostics[k]) for k in ("extreme_changes", "structural_breaks", "demographic_jumps")) else "APTO"),
        "hard_failures": list(dict.fromkeys(hard)),
        "rows": {"unified":len(unified),"departmental":len(dep),"national":len(nation),"urban":len(urban)},
        "period_range": [str(min(reference.period)),str(max(reference.period))],
        "alerts": {k:len(diagnostics[k]) for k in ("extreme_changes", "structural_breaks", "demographic_jumps")},
        "linearity": {
            "population_flat_years":int(annual_plateaus.sum()),
            "population_flat_years_since_2001_territories":int((annual_plateaus & linearity["product"].eq("TERMINAL_UNIFICADO") & linearity["year"].ge(2001)).sum()),
            "strong_non_linearity_years_over_2pct":int(severe_linearity.sum()),
            "max_working_age_deviation_from_annual_line_pct":float(linearity.loc[linearity.quantity=="working_age","max_linearity_residual_pct"].max()),
            "shape_definition":"Maximum residual from per-year least-squares straight line divided by annual average; >2% is a screen, not an automatic correction.",
        },
        "official_deviation_max_pct": (
            {str(k):float(v) for k,v in official_deviation.groupby("quantity")["deviation_pct"].apply(lambda x:x.abs().max()).items()}
            if official_deviation is not None else {}
        ),
        "max_identity_residual_persons": {
            k: float(v[["labor_force_residual","working_age_residual"]].abs().max().max()) for k,v in diagnostics.items() if k in ("territories","urban")
        },
        "max_represented_reference_residual_since_2001_persons": float(
            diagnostics["reference_alignment"].loc[lambda x: x.period>=policy.reference_from,"delta_represented_minus_reference"].abs().max()
        ),
        "note": "Structural breaks and large changes are screening signals; independent investigation is required before certification.",
    }
    return diagnostics,summary
