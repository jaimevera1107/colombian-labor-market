"""Check that the period a workbook declares matches the one its name claims."""

from __future__ import annotations

from pathlib import Path

from icml.ingestion.discovery import INFORMALITY, LABOR, Annex


class AnnexPeriodMismatch(ValueError):
    """The workbook declares a different period than its file name."""


def declared_period(annex: Annex, configs: Path) -> str:
    """Return the last month the workbook actually contains.

    Reads it with the same readers the calculation uses, so the period is the
    one that would enter the models, whatever the file is called.
    """
    from icml.recalculation.annex_checks import informality_observations, national_observations

    if annex.kind == LABOR:
        observations = national_observations(annex.path, Path(configs) / "national.toml")
    elif annex.kind == INFORMALITY:
        observations = informality_observations(annex.path)
    else:
        raise ValueError(f"Declared period is only defined for monthly annexes, not {annex.kind}")
    return str(observations["period"].max())


def verify_annex(annex: Annex, configs: Path) -> dict:
    """Raise ``AnnexPeriodMismatch`` unless name and content agree."""
    declared = declared_period(annex, configs)
    if declared != annex.period:
        raise AnnexPeriodMismatch(
            f"{annex.path.name}: the name says {annex.period} but the workbook "
            f"declares {declared}. Rename the file or replace it."
        )
    return {"kind": annex.kind, "period": annex.period, "path": str(annex.path), "declared": declared}
