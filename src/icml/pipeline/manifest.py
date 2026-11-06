"""Run manifests: what was executed, with which inputs, code and outputs."""

from __future__ import annotations

import json
import platform
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from icml import __version__
from icml.io.artifacts import ArtifactRecord

_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")

# Packages whose versions can change numerical results.
TRACKED_PACKAGES: tuple[str, ...] = (
    "numpy",
    "pandas",
    "scipy",
    "scikit-learn",
    "statsmodels",
    "xgboost",
    "tempdisagg",
)


def validate_run_id(run_id: str) -> str:
    """Validate a run identifier (letters, digits, ``_`` and ``-``).

    Raises
    ------
    ValueError
        If the identifier is empty, too long or has invalid characters.
    """
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"Invalid run id: {run_id!r}")
    return run_id


def capture_environment(
    packages: Iterable[str] = TRACKED_PACKAGES,
) -> dict[str, str]:
    """Return Python and package versions relevant to reproducibility."""
    environment = {"python": platform.python_version()}
    for name in packages:
        try:
            environment[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            environment[name] = "not-installed"
    return environment


@dataclass(frozen=True)
class RunManifest:
    """Complete description of a pipeline run.

    Attributes
    ----------
    run_id : str
        Unique identifier of the run.
    stage : str
        Stage or command that produced the run.
    created_at : str
        UTC timestamp in ISO 8601 format.
    package_version : str
        Version of the ``icml`` package.
    config_sha256 : str
        Hash of the configuration used.
    inputs : tuple[ArtifactRecord, ...]
        Artifacts consumed.
    outputs : tuple[ArtifactRecord, ...]
        Artifacts produced.
    environment : dict[str, str]
        Interpreter and package versions.
    """

    run_id: str
    stage: str
    config_sha256: str
    inputs: tuple[ArtifactRecord, ...]
    outputs: tuple[ArtifactRecord, ...]
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    package_version: str = __version__
    environment: dict[str, str] = field(default_factory=capture_environment)

    def __post_init__(self) -> None:
        """Validate the run identifier."""
        validate_run_id(self.run_id)

    def to_json(self) -> str:
        """Serialize deterministically (sorted keys, UTF-8)."""
        return (
            json.dumps(
                asdict(self), ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n"
        )

    def write(self, path: Path) -> Path:
        """Write the manifest; existing manifests are never overwritten.

        Raises
        ------
        FileExistsError
            If the destination already exists.
        """
        if path.exists():
            raise FileExistsError(f"Manifest already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path


def records_from_sequence(
    records: Sequence[ArtifactRecord],
) -> tuple[ArtifactRecord, ...]:
    """Return records sorted by artifact id for stable manifests."""
    return tuple(sorted(records, key=lambda record: record.artifact_id))
