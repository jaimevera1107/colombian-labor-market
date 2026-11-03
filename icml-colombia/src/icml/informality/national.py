"""Hito 5: national informality source contract and monthly latent candidate.

The DANE publication consists of *three-month rolling averages*. A latent
monthly path is a modeled estimate even when it reproduces those windows.
The historical national non-pension proxy is never concatenated with the
new GEIH definition of informality.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from icml.config import build_dataclass, load_toml, section
from icml.io.artifacts import ArtifactRecord, ArtifactSpec, ArtifactStore
from icml.io.hashing import sha256_file
from icml.domain.cutoff import N_MONTHS

NEW = "new_geih_employment_based"
OLD_NAT = "old_non_pension_proxy_NOT_equivalent_to_new_informality"
OLD_CITY = "old_small_firm_size"
QUALITY_NATIONALS = ArtifactSpec("quality.nacionales", "products/nacionales.csv", keys=("national_type", "period"))
SOURCE = ArtifactSpec(
    "informality.source_observations", "informality_source_observations.csv",
    keys=("source", "domain", "concept", "period_end"),
)
OUTPUTS = {
    "source_inventory": ArtifactSpec("informality.source_inventory", "audit/source_inventory.csv"),
    "national_windows": ArtifactSpec("informality.national_windows", "sources/national_windows.csv", keys=("definition", "domain", "period_end")),
    "source_domain_closure": ArtifactSpec("informality.source_domain_closure", "audit/source_domain_closure.csv", keys=("definition", "period_end")),
    "labor_alignment": ArtifactSpec("informality.labor_alignment", "audit/labor_alignment.csv", keys=("definition", "period_end")),
    "definition_overlap": ArtifactSpec("informality.definition_overlap", "audit/definition_overlap.csv", keys=("domain", "period_end")),
    "monthly_latent": ArtifactSpec("informality.monthly_latent", "candidates/national_informality_monthly_2021_2026.csv", keys=("period",)),
    "window_reproduction": ArtifactSpec("informality.window_reproduction", "audit/window_reproduction.csv", keys=("period_end",)),
}

@dataclass(frozen=True)
class InformalityNationalPolicy:
    """Controlled source and numerical contract for Hito 5."""
    snapshot_sha256: str
    expected_observations: int
    expected_new_national_windows: int
    expected_possible_missing_zeros: int
    source_identity_tolerance_persons: float
    benchmark_window_tolerance_persons: float
    latent_window_tolerance_persons: float
    reference_type: str

    def __post_init__(self) -> None:
        if len(self.snapshot_sha256) != 64 or self.expected_observations < 1:
            raise ValueError("Invalid frozen snapshot configuration")
        if min(self.source_identity_tolerance_persons,
               self.benchmark_window_tolerance_persons,
               self.latent_window_tolerance_persons) < 0:
            raise ValueError("Negative tolerance")


def load_informality_config(path: Path) -> InformalityNationalPolicy:
    """Read strict, frozen Hito 5 parameters."""
    return build_dataclass(InformalityNationalPolicy, section(load_toml(path), "informality"), context="informality")


def check_source(df: pd.DataFrame, policy: InformalityNationalPolicy) -> None:
    """Verify vintage, rolling window, provenance and source identities."""
    required = set(["source", "definition", "domain", "concept", "period_start", "period_end",
                    "reference_type", "occupied_thousands", "formal_thousands", "informal_thousands",
                    "informality_rate", "value_status", "eligible_for_training"])
    if not required.issubset(df.columns):
        raise ValueError(f"Informality source columns missing: {sorted(required-set(df.columns))}")
    if len(df) != policy.expected_observations:
        raise ValueError(f"Unexpected source observations: {len(df)}")
    if df.duplicated(["source", "domain", "concept", "period_end"]).any():
        raise ValueError("Duplicate informality source windows")
    if not df.reference_type.eq(policy.reference_type).all():
        raise ValueError("Source windows are not rolling three-month means")
    start = pd.to_datetime(df.period_start)
    end = pd.to_datetime(df.period_end)
    if not ((start + pd.DateOffset(months=2)) == end).all():
        raise ValueError("Wrong three-month rolling window boundaries")
    levels = df[["occupied_thousands", "formal_thousands", "informal_thousands"]].apply(pd.to_numeric)
    if not np.isfinite(levels.to_numpy()).all() or (levels < 0).any().any():
        raise ValueError("Invalid source levels")
    err = (levels.occupied_thousands - levels.formal_thousands - levels.informal_thousands).abs().max() * 1000
    if err > policy.source_identity_tolerance_persons:
        raise ValueError(f"Official source rounded identity exceeded: {err} persons")
    sentinel = levels.occupied_thousands.eq(0)
    if int(sentinel.sum()) != policy.expected_possible_missing_zeros:
        raise ValueError("Changed number of possible missing-zero sentinels")
    if (df.loc[sentinel, "eligible_for_training"].astype(str).str.lower() == "true").any():
        raise ValueError("2020 sentinel marked eligible for training")
    rate = levels.informal_thousands.div(levels.occupied_thousands.where(~sentinel))
    if np.nanmax(np.abs(rate.to_numpy() - df.informality_rate.to_numpy(dtype=float))) > 1e-9:
        raise ValueError("Source informality rate disagrees with counts")
    new_nat = df[(df.domain == "national") & (df.definition == NEW)]
    if len(new_nat) != policy.expected_new_national_windows:
        raise ValueError("Incomplete national new-definition reference")


def _dane_and_icml(nacionales: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if set(nacionales.national_type.unique()) != {"DANE_REFERENCIA", "ICML_COMPLETO"}:
        raise ValueError("Expected exactly the two national series")
    if nacionales.duplicated(["national_type", "period"]).any():
        raise ValueError("Duplicate national period")
    n = nacionales.copy()
    n["period"] = pd.to_datetime(n.period)
    if n[["period", "employed"]].isna().any().any() or (n.employed <= 0).any():
        raise ValueError("Missing/nonpositive frozen employment")
    n1 = n[n.national_type == "DANE_REFERENCIA"].set_index("period").sort_index()
    n2 = n[n.national_type == "ICML_COMPLETO"].set_index("period").sort_index()
    if not n1.index.equals(n2.index):
        raise ValueError("National calendars differ")
    if len(n1) != N_MONTHS:
        raise ValueError("Unexpected frozen national calendar")
    return n1,n2


def _rolling_comparison(old_new: pd.DataFrame, dane: pd.DataFrame, icml: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in old_new.itertuples(index=False):
        dates = pd.date_range(r.period_start,r.period_end,freq="MS")
        if not set(dates).issubset(dane.index):
            raise ValueError(f"Missing national employment window {r.period_end}")
        d = float(dane.loc[dates,"employed"].mean())
        i = float(icml.loc[dates,"employed"].mean())
        a = float(r.occupied_thousands)*1000
        rows.append({"definition":r.definition,"period_start":r.period_start,
                     "period_end":r.period_end, "reference_type":r.reference_type,
                     "annex_employed_persons":a, "dane_labor_employed_persons":d,
                     "icml_complete_employed_persons":i,
                     "delta_dane_persons":a-d,
                     "delta_dane_pct":(a/d-1)*100,
                     "delta_icml_pct":(a/i-1)*100,
                     "informality_rate_annex":r.informality_rate,
                     "informality_is_comparable_with_new":r.definition == NEW,
                     "definition_warning":"NON_PENSION_PROXY_NOT_CURRENT_INFORMALITY" if r.definition==OLD_NAT else "CURRENT_GEIH_DEFINITION"})
    return pd.DataFrame(rows).sort_values(["definition","period_end"]).reset_index(drop=True)


def _exact_min_curvature(three_month_mean: np.ndarray) -> np.ndarray:
    """Invert overlapping 3-month means; select minimum second difference.

    Rolling averages alone leave two unidentified degrees of freedom.
    The curvature criterion supplies these; the path is NOT observed.
    """
    m = len(three_month_mean)
    A = np.zeros((m,m+2),dtype=float)
    for k in range(m):
        A[k,k:k+3] = 1.0/3.0
    x0 = np.linalg.lstsq(A,three_month_mean,rcond=None)[0]
    # Two-dimensional null space, computed without a heavy optimizer.
    # This null structure follows x[k+2] = -x[k] - x[k+1].
    z = np.zeros((m+2,2),dtype=float)
    z[0] = [1,0]; z[1] = [0,1]
    for k in range(m):z[k+2] = -z[k]-z[k+1]
    second = np.diff(np.eye(m+2),n=2,axis=0)
    theta = np.linalg.lstsq(second@z,-second@x0,rcond=None)[0]
    return x0 + z@theta


def _monthly_latent(new_nat: pd.DataFrame, dane: pd.DataFrame,
                    policy: InformalityNationalPolicy) -> tuple[pd.DataFrame,pd.DataFrame]:
    dat = new_nat.sort_values("period_start").reset_index(drop=True)
    starts = pd.to_datetime(dat.period_start)
    if not starts.equals(pd.Series(pd.date_range(starts.iloc[0], periods=len(dat),freq="MS"))):
        raise ValueError("Nonconsecutive official moving windows")
    dates = pd.date_range(starts.iloc[0],periods=len(dat)+2,freq="MS")
    if not set(dates).issubset(dane.index):
        raise ValueError("Latent calendar outside frozen national employment")
    informal = _exact_min_curvature(dat.informal_thousands.to_numpy(dtype=float)*1000)
    employed = dane.loc[dates,"employed"].to_numpy(dtype=float)
    formal = employed-informal
    if not np.isfinite(informal).all() or (informal < 0).any() or (formal < 0).any():
        raise ValueError("Latent informal/formal amounts violate bounds; a constrained solver is necessary")
    monthly = pd.DataFrame({"period":dates.strftime("%Y-%m"),
        "informal_persons_latent":informal,"formal_persons_latent":formal,
        "employed_persons_fixed_dane":employed,
        "informality_rate_latent":informal/employed,
        "definition":NEW, "universe":"DANE_REFERENCIA",
        "reference_type":"latent_monthly_rolling3_min_second_difference",
        "is_official_monthly_observation":False,
        "eligible_for_icml_complete_without_bridge":False})
    out=[]
    for j,r in dat.iterrows():
        sub=monthly.iloc[j:j+3]
        informal_pred=float(sub.informal_persons_latent.mean())
        formal_pred=float(sub.formal_persons_latent.mean())
        occ_pred=float(sub.employed_persons_fixed_dane.mean())
        out.append({"period_start":r.period_start,"period_end":r.period_end,
            "source_informal_persons":r.informal_thousands*1000,
            "recovered_informal_persons":informal_pred,
            "informal_residual_persons":informal_pred-r.informal_thousands*1000,
            "source_formal_persons":r.formal_thousands*1000,
            "recovered_formal_persons":formal_pred,
            "formal_residual_persons":formal_pred-r.formal_thousands*1000,
            "source_employed_persons":r.occupied_thousands*1000,
            "recovered_employed_persons":occ_pred,
            "employed_residual_persons":occ_pred-r.occupied_thousands*1000})
    audit=pd.DataFrame(out)
    if audit.informal_residual_persons.abs().max()>policy.latent_window_tolerance_persons:
        raise ValueError("Latent reconstruction did not preserve official informal windows")
    if audit.formal_residual_persons.abs().max()>policy.benchmark_window_tolerance_persons:
        raise ValueError("Fixed DANE denominator cannot reproduce official formal windows")
    return monthly,audit


@dataclass(frozen=True)
class InformalityResult:
    """Contract compatible with existing stage manifests."""
    outputs: tuple[ArtifactRecord,...]
    inputs: tuple[ArtifactRecord,...]
    diagnostics: dict[str,Any]


class InformalityNationalPipeline:
    """Audit old/new source concepts and create a recent-only latent candidate."""

    def __init__(self, policy: InformalityNationalPolicy):
        self.policy = policy

    def run(self,sources:Path,quality:ArtifactStore,output:ArtifactStore)->InformalityResult:
        """Create immutable artifacts without changing the labor market."""
        source_path=sources / SOURCE.relative_path
        if sha256_file(source_path)!=self.policy.snapshot_sha256:
            raise ValueError("Changed informality source snapshot: create new vintage/config")
        incoming=ArtifactStore(sources)
        raw=incoming.read(SOURCE)
        check_source(raw,self.policy)
        n=quality.read(QUALITY_NATIONALS)
        dane,icml=_dane_and_icml(n)
        national=raw[raw.domain.isin(["national","urban_cabeceras","rural"])].copy()
        national= national.sort_values(["definition","domain","period_end"]).reset_index(drop=True)
        inventory=(raw.groupby(["source","definition","domain"],dropna=False)
          .agg(observations=("period_end","size"),concepts=("concept","nunique"),
               first_period_start=("period_start","min"),last_period_end=("period_end","max"),
               possible_missing_zero=("value_status",lambda s:int(s.eq("ZERO_SENTINEL_POSSIBLE_MISSING").sum())))
          .reset_index())
        old_nat=national[(national.domain=="national")&(national.definition==OLD_NAT)]
        new_nat=national[(national.domain=="national")&(national.definition==NEW)]
        aligned=_rolling_comparison(pd.concat([old_nat,new_nat]),dane,icml)
        current=aligned[aligned.definition==NEW]
        if current.delta_dane_persons.abs().max()>self.policy.benchmark_window_tolerance_persons:
            raise ValueError("Latest DANE employment source is not consistent with frozen labor benchmark")
        # The national total and its two disjoint domains need not sum
        # exactly (sampling/rounding); publish the residual instead.
        piv=national.pivot(index=["definition","period_end"],columns="domain",values="occupied_thousands")
        piv=piv.dropna(subset=["national","urban_cabeceras","rural"])
        domain=(piv.reset_index()[["definition","period_end"]].copy())
        domain["occupied_domain_residual_persons"]=(piv.national-piv.urban_cabeceras-piv.rural).to_numpy()*1000
        monthly,reproduction=_monthly_latent(new_nat,dane,self.policy)
        old_overlay=old_nat.merge(new_nat,on="period_end",suffixes=("_old","_new"),how="inner")
        overlap=pd.DataFrame({"domain":"national", "period_end":old_overlay.period_end,
             "old_definition":OLD_NAT, "new_definition":NEW,
             "old_rate_non_pension_proxy":old_overlay.informality_rate_old,
             "new_rate_informality":old_overlay.informality_rate_new,
             "difference_new_minus_old_pp":100*(old_overlay.informality_rate_new-old_overlay.informality_rate_old),
             "comparable_estimands":False})
        results={"source_inventory":inventory,"national_windows":national,"source_domain_closure":domain,
                 "labor_alignment":aligned,"definition_overlap":overlap,
                 "monthly_latent":monthly,"window_reproduction":reproduction}
        records=tuple(output.write(OUTPUTS[k],v) for k,v in results.items())
        stats={"status":"HITO5_NATIONAL_RECENT_LATENT_CANDIDATE_NOT_ICML_PUBLISHED",
               "source_rows":len(raw),"zero_possible_missing":int(raw.value_status.eq("ZERO_SENTINEL_POSSIBLE_MISSING").sum()),
               "new_national_rolling_windows":len(new_nat),"recent_monthly_latent_months":len(monthly),
               "max_alignment_dane_persons":float(current.delta_dane_persons.abs().max()),
               "median_alignment_icml_pct":float(current.delta_icml_pct.median()),
               "max_informal_window_residual_persons":float(reproduction.informal_residual_persons.abs().max()),
               "max_formal_window_residual_persons":float(reproduction.formal_residual_persons.abs().max()),
               "overlap_national_pp":overlap.difference_new_minus_old_pp.tolist(),
               "uncovered_historic_months":"1993-01 to 2020-12 (pending compatible-definition bridge)",
               "labor_market_bases_modified":False,
               "policy":asdict(self.policy)}
        target=output.root/'audit/summary.json';target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(stats,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return InformalityResult(records,tuple(incoming.records+quality.records),stats)
