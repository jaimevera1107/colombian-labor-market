"""Structural contract shared by every stage result."""

from __future__ import annotations

from typing import Any, Protocol

from icml.io.artifacts import ArtifactRecord


class StageResult(Protocol):
    """What a stage returns: artifacts consumed, produced, diagnostics."""

    @property
    def outputs(self) -> tuple[ArtifactRecord, ...]:
        """Artifacts written by the stage."""

    @property
    def inputs(self) -> tuple[ArtifactRecord, ...]:
        """Artifacts read by the stage."""

    @property
    def diagnostics(self) -> dict[str, Any]:
        """Stage diagnostics (also written to ``diagnostics.json``)."""
