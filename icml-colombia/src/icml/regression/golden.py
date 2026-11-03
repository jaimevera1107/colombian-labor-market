"""Capture and verification of the RC1 golden reference set.

The golden set is a copy of the catalogued RC1 artifacts, kept outside the
repository (it is published as a release asset) and checked by SHA-256.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pandas as pd

from icml.io.hashing import sha256_file
from icml.io.tables import read_table
from icml.regression.catalog import GoldenArtifact, GoldenCatalog

GOLDEN_MANIFEST_NAME = "golden_manifest.json"


@dataclass(frozen=True)
class IntegrityIssue:
    """A golden artifact that is missing or has an unexpected hash."""

    artifact_id: str
    path: str
    problem: str


def _artifact_path(root: Path, artifact: GoldenArtifact) -> Path:
    return root.joinpath(*PurePosixPath(artifact.legacy_path).parts)


def check_integrity(
    root: Path, catalog: GoldenCatalog
) -> tuple[IntegrityIssue, ...]:
    """Check that every catalogued artifact exists with the expected hash.

    Works both on the legacy RC2 tree and on a captured golden folder,
    since both use the same relative layout.
    """
    issues: list[IntegrityIssue] = []
    for artifact in catalog.artifacts:
        path = _artifact_path(root, artifact)
        if not path.is_file():
            issues.append(
                IntegrityIssue(artifact.artifact_id, str(path), "missing")
            )
        elif sha256_file(path) != artifact.sha256:
            issues.append(
                IntegrityIssue(
                    artifact.artifact_id, str(path), "sha256 mismatch"
                )
            )
    return tuple(issues)


def capture_golden(
    legacy_root: Path, catalog: GoldenCatalog, destination: Path
) -> Path:
    """Copy the catalogued RC1 artifacts into a golden folder.

    Raises
    ------
    FileExistsError
        If the destination already holds a golden manifest.
    RuntimeError
        If the legacy tree does not match the catalog hashes.
    """
    manifest_path = destination / GOLDEN_MANIFEST_NAME
    if manifest_path.exists():
        raise FileExistsError(f"Golden set already captured: {destination}")
    issues = check_integrity(legacy_root, catalog)
    if issues:
        details = "; ".join(f"{i.artifact_id}: {i.problem}" for i in issues)
        raise RuntimeError(f"Legacy tree does not match catalog: {details}")
    for artifact in catalog.artifacts:
        target = _artifact_path(destination, artifact)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_artifact_path(legacy_root, artifact), target)
    manifest = {
        "reference": catalog.reference,
        "artifacts": {a.artifact_id: a.sha256 for a in catalog.artifacts},
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def load_golden_table(root: Path, artifact: GoldenArtifact) -> pd.DataFrame:
    """Read a tabular golden artifact.

    Raises
    ------
    ValueError
        If the artifact is not a CSV table.
    """
    if not artifact.is_tabular:
        raise ValueError(f"{artifact.artifact_id} is not a CSV table")
    return read_table(_artifact_path(root, artifact))
