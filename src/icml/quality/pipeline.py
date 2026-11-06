"""Independent, hash-recorded quality stage downstream of reconciliation."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from icml.config import build_dataclass, load_toml, section
from icml.io.artifacts import ArtifactRecord, ArtifactSpec, ArtifactStore
from icml.quality.gate import QualityPolicy, audit_products, unify_territories
from icml.quality.consolidated import build_three_bases
from icml.reconciliation.pipeline import OUTPUTS as RECONCILIATION_OUTPUTS


def load_quality_config(path: Path) -> QualityPolicy:
    """Strict read of the quality policy.

    The last anchored year is not repeated here: it is read from the
    ``departmental.toml`` beside this file (``[departmental.annex] last_year``),
    so the annual annex update moves it in one place only.
    """
    policy = build_dataclass(QualityPolicy, section(load_toml(path), "quality"), context="quality")
    departmental = Path(path).with_name("departmental.toml")
    if policy.last_anchor_year is None and departmental.is_file():
        annex = load_toml(departmental).get("departmental", {}).get("annex", {})
        if "last_year" in annex:
            policy = replace(policy, last_anchor_year=int(annex["last_year"]))
    return policy


OUTPUTS = {
    "ciudades": ArtifactSpec("quality.ciudades", "products/ciudades.csv", keys=("city_code", "period")),
    "departamentos": ArtifactSpec("quality.departamentos", "products/departamentos.csv", keys=("dep_code", "period")),
    "nacionales": ArtifactSpec("quality.nacionales", "products/nacionales.csv", keys=("national_type", "period")),
    "reference_alignment": ArtifactSpec("quality.reference_alignment","audit/reference_alignment.csv",keys=("period","quantity")),
    "territories": ArtifactSpec("quality.identities_territories","audit/identities_territories.csv",keys=("dep_code","period")),
    "urban": ArtifactSpec("quality.identities_urban","audit/identities_urban.csv",keys=("city_code","period")),
    "extreme_changes": ArtifactSpec("quality.extreme_changes","audit/extreme_changes.csv"),
    "structural_breaks": ArtifactSpec("quality.structural_breaks","audit/structural_breaks.csv"),
    "demographic_jumps": ArtifactSpec("quality.demographic_jumps","audit/demographic_jumps.csv"),
    "annual_linearity": ArtifactSpec("quality.annual_linearity","audit/annual_linearity.csv",keys=("entity","year","product","quantity")),
    "official_deviation_check": ArtifactSpec("quality.official_deviation_check","audit/official_deviation_check.csv",keys=("dep_code","year","quantity")),
    "official_accuracy_summary": ArtifactSpec("quality.official_accuracy_summary","audit/official_accuracy_summary.csv",keys=("reference_type","quantity")),
}


@dataclass(frozen=True)
class QualityRunResult:
    """Manifest compatible output of the final gate."""
    outputs: tuple[ArtifactRecord, ...]
    inputs: tuple[ArtifactRecord, ...]
    diagnostics: dict[str,Any]


class QualityPipeline:
    """Consume immutable 2.1.0 products and publish three complete bases."""

    def __init__(self, policy: QualityPolicy):
        self.policy = policy

    def run(self, upstream: ArtifactStore, output: ArtifactStore) -> QualityRunResult:
        """Publish a candidate and audit, never silently approve hard failures."""
        deps = upstream.read(RECONCILIATION_OUTPUTS["departmental_factors"])
        nat = upstream.read(RECONCILIATION_OUTPUTS["national_icml"])
        urban = upstream.read(RECONCILIATION_OUTPUTS["urban_signals"])
        official = upstream.read(RECONCILIATION_OUTPUTS["official_deviation"])
        bases = build_three_bases(deps,urban,nat,self.policy)
        unified = unify_territories(bases["departamentos"],nat)
        diagnostics,summary = audit_products(unified,bases["ciudades"],nat,self.policy,official)
        records = [output.write(OUTPUTS[key],bases[key]) for key in ("ciudades","departamentos","nacionales")]
        for key,frame in diagnostics.items():
            records.append(output.write(OUTPUTS[key],frame))
        folder = output.root / "audit"
        folder.mkdir(parents=True,exist_ok=True)
        (folder / "summary.json").write_text(json.dumps({"policy":asdict(self.policy),**summary},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        return QualityRunResult(tuple(records),upstream.records,summary)
