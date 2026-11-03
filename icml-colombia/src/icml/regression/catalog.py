"""Golden catalog: the RC1 artifacts every migrated stage must reproduce."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

SUPPORTED_SCHEMA_VERSION = 1


class ArtifactRole(StrEnum):
    """Role of an artifact in the RC1 lineage."""

    SOURCE = "source"
    STAGE_OUTPUT = "stage_output"
    FINAL_PRODUCT = "final_product"


@dataclass(frozen=True)
class GoldenArtifact:
    """One RC1 artifact with its expected content hash.

    Attributes
    ----------
    artifact_id : str
        Dotted identifier, stable across the migration.
    stage : str
        Pipeline stage that produced the artifact in RC1.
    role : ArtifactRole
        Source, intermediate stage output or final product.
    legacy_path : str
        POSIX path relative to the legacy RC2 project root.
    keys : tuple[str, ...]
        Row-identifying columns; empty means positional comparison.
    sha256 : str
        Expected SHA-256 of the RC1 file.
    source_class : str
        For sources: ``dane_raw``, ``dane_compiled``, ``legacy_derived``
        or ``frozen_decision``.
    note : str
        Free-text remark.
    """

    artifact_id: str
    stage: str
    role: ArtifactRole
    legacy_path: str
    keys: tuple[str, ...]
    sha256: str
    source_class: str = ""
    note: str = ""

    @property
    def is_tabular(self) -> bool:
        """Return whether the artifact is a CSV table."""
        return PurePosixPath(self.legacy_path).suffix.lower() == ".csv"


@dataclass(frozen=True)
class GoldenCatalog:
    """Collection of golden artifacts indexed by id."""

    reference: str
    artifacts: tuple[GoldenArtifact, ...]

    def get(self, artifact_id: str) -> GoldenArtifact:
        """Return an artifact by id.

        Raises
        ------
        KeyError
            If the id is not in the catalog.
        """
        for artifact in self.artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact
        raise KeyError(f"Unknown golden artifact: {artifact_id}")

    def by_stage(self, stage: str) -> tuple[GoldenArtifact, ...]:
        """Return the artifacts produced by a stage."""
        return tuple(a for a in self.artifacts if a.stage == stage)


def load_catalog(path: Path) -> GoldenCatalog:
    """Load and validate a golden catalog TOML file.

    Raises
    ------
    ValueError
        If the schema version is unsupported or ids are duplicated.
    """
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    version = payload.get("schema_version")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"Unsupported catalog schema version: {version}")
    artifacts = tuple(
        GoldenArtifact(
            artifact_id=item["id"],
            stage=item["stage"],
            role=ArtifactRole(item["role"]),
            legacy_path=item["legacy_path"],
            keys=tuple(item.get("keys", ())),
            sha256=item["sha256"],
            source_class=item.get("source_class", ""),
            note=item.get("note", ""),
        )
        for item in payload.get("artifact", [])
    )
    ids = [a.artifact_id for a in artifacts]
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        raise ValueError(f"Duplicated artifact ids in catalog: {duplicated}")
    return GoldenCatalog(
        reference=str(payload["reference"]), artifacts=artifacts
    )
