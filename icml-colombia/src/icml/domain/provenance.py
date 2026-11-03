"""Provenance of every estimated value.

Each value in an ICML product carries a provenance category. RC1 used
free-text labels; they are mapped here to a closed set of categories plus
a provisional flag, loaded from package data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from icml.domain._resources import read_reference_table

_LABELS_FILE = "provenance_labels.csv"


class ProvenanceCategory(StrEnum):
    """Closed set of provenance categories."""

    OBSERVED = "observed"
    ANCHORED_RECONSTRUCTION = "anchored_reconstruction"
    UNANCHORED_RECONSTRUCTION = "unanchored_reconstruction"
    LATENT_FROM_WINDOWS = "latent_from_windows"
    DONOR_ESTIMATE = "donor_estimate"
    SYNTHETIC = "synthetic"
    PREDICTED = "predicted"


@dataclass(frozen=True)
class Provenance:
    """Provenance attached to a value."""

    category: ProvenanceCategory
    is_provisional: bool
    description: str


@cache
def legacy_provenance_map() -> Mapping[str, Provenance]:
    """Return the mapping from RC1 origin labels to provenance."""
    table = read_reference_table(_LABELS_FILE)
    mapping: dict[str, Provenance] = {}
    for row in table:
        label = str(row["legacy_label"])
        if label in mapping:
            raise ValueError(f"Duplicated legacy provenance label: {label}")
        mapping[label] = Provenance(
            category=ProvenanceCategory(row["category"]),
            is_provisional=str(row["is_provisional"]).strip().lower()
            == "true",
            description=str(row["description"]),
        )
    return mapping


def resolve_legacy_labels(labels: Iterable[str]) -> dict[str, Provenance]:
    """Resolve RC1 origin labels, failing on any unknown label.

    Raises
    ------
    KeyError
        If at least one label has no registered provenance. Unknown labels
        are never mapped to a default category.
    """
    mapping = legacy_provenance_map()
    unique_labels = sorted(set(labels))
    unknown = [label for label in unique_labels if label not in mapping]
    if unknown:
        raise KeyError(f"Unregistered provenance labels: {unknown}")
    return {label: mapping[label] for label in unique_labels}
