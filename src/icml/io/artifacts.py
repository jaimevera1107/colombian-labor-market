"""Artifact store: explicit, hash-tracked data exchange between stages.

Stages never copy files into each other's folders. A stage declares the
artifacts it reads and writes; the store resolves them under a single run
root and records their hashes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pandas as pd

from icml.io.hashing import sha256_file
from icml.io.tables import (
    DEFAULT_CSV_FORMAT,
    CsvFormat,
    read_table,
    write_table,
)

_ARTIFACT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


@dataclass(frozen=True)
class ArtifactSpec:
    """Declaration of a tabular artifact.

    Attributes
    ----------
    artifact_id : str
        Dotted identifier, e.g. ``"national.reconciled_monthly"``.
    relative_path : str
        POSIX path relative to the store root.
    keys : tuple[str, ...]
        Columns that uniquely identify a row.
    description : str
        Short human-readable description.
    """

    artifact_id: str
    relative_path: str
    keys: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        """Validate identifier and path."""
        if not _ARTIFACT_ID_PATTERN.fullmatch(self.artifact_id):
            raise ValueError(f"Invalid artifact id: {self.artifact_id!r}")
        posix = PurePosixPath(self.relative_path)
        if posix.is_absolute() or ".." in posix.parts:
            raise ValueError(
                f"Artifact path must be relative and inside the store: "
                f"{self.relative_path!r}"
            )


@dataclass(frozen=True)
class ArtifactRecord:
    """Immutable record of a materialized artifact."""

    artifact_id: str
    relative_path: str
    sha256: str
    n_rows: int
    n_columns: int


@dataclass
class ArtifactStore:
    """Resolve, read and write artifacts below a root folder.

    Attributes
    ----------
    root : pathlib.Path
        Root folder of a run (or of a frozen source set).
    csv_format : CsvFormat
        Serialization used for every write.
    """

    root: Path
    csv_format: CsvFormat = DEFAULT_CSV_FORMAT
    _records: dict[str, ArtifactRecord] = field(default_factory=dict)

    def resolve(self, spec: ArtifactSpec) -> Path:
        """Return the absolute path of an artifact."""
        return self.root.joinpath(*PurePosixPath(spec.relative_path).parts)

    def read(
        self,
        spec: ArtifactSpec,
        *,
        dtypes: Mapping[str, str] | None = None,
    ) -> pd.DataFrame:
        """Read an artifact and record its hash as a consumed input."""
        path = self.resolve(spec)
        frame = read_table(path, dtypes=dtypes)
        self._validate_keys(spec, frame)
        self._records[spec.artifact_id] = self._record(spec, path, frame)
        return frame

    def write(self, spec: ArtifactSpec, frame: pd.DataFrame) -> ArtifactRecord:
        """Write an artifact once; artifacts are immutable within a run.

        Raises
        ------
        FileExistsError
            If the artifact already exists.
        ValueError
            If the declared keys are missing or not unique.
        """
        self._validate_keys(spec, frame)
        path = write_table(
            frame, self.resolve(spec), csv_format=self.csv_format
        )
        record = self._record(spec, path, frame)
        self._records[spec.artifact_id] = record
        return record

    @property
    def records(self) -> tuple[ArtifactRecord, ...]:
        """Return every artifact read or written, ordered by id."""
        return tuple(self._records[k] for k in sorted(self._records))

    @staticmethod
    def _validate_keys(spec: ArtifactSpec, frame: pd.DataFrame) -> None:
        if not spec.keys:
            return
        missing = [key for key in spec.keys if key not in frame.columns]
        if missing:
            raise ValueError(
                f"{spec.artifact_id}: missing key columns {missing}"
            )
        duplicated = int(frame.duplicated(subset=list(spec.keys)).sum())
        if duplicated:
            raise ValueError(
                f"{spec.artifact_id}: {duplicated} duplicated key rows"
            )

    @staticmethod
    def _record(
        spec: ArtifactSpec, path: Path, frame: pd.DataFrame
    ) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=spec.artifact_id,
            relative_path=spec.relative_path,
            sha256=sha256_file(path),
            n_rows=int(frame.shape[0]),
            n_columns=int(frame.shape[1]),
        )
