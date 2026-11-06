"""Gates of an anchored recalculation: refuse changes that touch frozen years."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from icml.recalculation.policy import AnchorPolicy


def check_frozen_observations(
    previous: pd.DataFrame,
    current: pd.DataFrame,
    policy: AnchorPolicy,
    *,
    keys: Sequence[str],
    value: str,
    tolerance: float = 1e-9,
) -> dict:
    """Compare two releases of the same official figures on frozen years.

    A figure of a frozen year that was **revised**, **removed** or **added**
    between consecutive releases changes what the source says about that year.
    An anchored recalculation must not absorb it silently: the report lists
    the cells and the status is ``BLOCKED``. Added figures matter because
    DANE sometimes fills a window that an earlier release left empty (for
    example the national window Dec 2022 - Feb 2023 of the informality annex,
    absent in April 2026 and present in August 2026).

    Parameters
    ----------
    previous, current : pandas.DataFrame
        Tidy tables with ``period``, the ``keys`` and the ``value`` column.
    policy : AnchorPolicy
    keys : Sequence[str]
        Columns identifying an observation, including ``period``.
    value : str
        Numeric column to compare.
    tolerance : float
        Absolute tolerance.

    Returns
    -------
    dict
        ``status`` is ``PASS`` or ``BLOCKED``; ``revisions`` lists up to 50
        offending cells and ``n_revisions`` counts them all.
    """
    pre = previous[previous["period"].map(policy.is_frozen)]
    cur = current[current["period"].map(policy.is_frozen)]
    merged = pre.merge(cur, on=list(keys), how="outer", suffixes=("_prev", "_curr"), indicator=True)
    both = merged[merged["_merge"] == "both"]
    diff = (
        pd.to_numeric(both[f"{value}_prev"]) - pd.to_numeric(both[f"{value}_curr"])
    ).abs()
    revised = both[diff > tolerance]
    removed = merged[merged["_merge"] == "left_only"]
    added = merged[merged["_merge"] == "right_only"]
    cells = pd.concat([revised, removed, added])
    return {
        "check": "frozen_observations_unrevised",
        "frozen_through_year": policy.last_anchor_year,
        "n_revisions": int(len(revised)),
        "n_frozen_observations_removed": int(len(removed)),
        "n_added_in_frozen_years": int(len(added)),
        "added_in_frozen_years": int(len(added)),
        "n_changes": int(len(cells)),
        "revisions": cells.head(50).drop(columns="_merge").to_dict("records"),
        "status": "BLOCKED" if len(cells) else "PASS",
    }


def check_frozen_parameters(
    previous_hashes: Mapping[str, str], current_hashes: Mapping[str, str]
) -> dict:
    """Frozen parameters (CNPV bridge, MLP priors...) must not change."""
    changed = sorted(
        path
        for path in set(previous_hashes) | set(current_hashes)
        if previous_hashes.get(path) != current_hashes.get(path)
    )
    return {
        "check": "frozen_parameters_unchanged",
        "changed": changed,
        "status": "BLOCKED" if changed else "PASS",
    }


def fingerprint(files: Sequence[Path], root: Path) -> dict[str, str]:
    """Return ``{relative path: sha256}`` for the given files."""
    from icml.delivery.builder import sha256_file

    return {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(files)}
