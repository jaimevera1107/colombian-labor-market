"""Geographic-temporal cross-validation folds.

Labeled non-synthetic territories are split into groups with a seeded
permutation. Each fold holds out one group for a future window, trains on
the other groups up to the cutoff, and drops the last training year as an
embargo: annualized 12-month windows would otherwise overlap the test.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


class FoldError(ValueError):
    """Raised when folds would leak information."""


@dataclass(frozen=True)
class FoldPolicy:
    """Grouping, windows and embargo of the folds."""

    n_groups: int
    windows: Sequence[Sequence[int]]
    embargo_years: int


def make_folds(
    targets: pd.DataFrame,
    policy: FoldPolicy,
    seed: int,
    first_year: int,
    synthetic_code: int,
) -> list[dict[str, Any]]:
    """Return fold specifications.

    Raises
    ------
    FoldError
        On any overlap of territories or years between train and test.
    """
    train = targets[targets["eligible_training"]]
    codes = np.array(sorted(set(train["dep_code"]) - {synthetic_code}))
    groups = np.array_split(
        np.random.default_rng(seed).permutation(codes), policy.n_groups
    )
    folds = []
    for position, held in enumerate(groups):
        held_out = set(held.tolist())
        for cut, end in policy.windows:
            training = train[
                train["dep_code"].isin(set(codes) - held_out)
                & (train["year"] <= cut)
                & (train["year"] >= first_year)
            ]
            test = train[
                train["dep_code"].isin(held_out)
                & (train["year"] > cut)
                & (train["year"] <= end)
            ]
            if (
                set(training["dep_code"]) & set(test["dep_code"])
                or training["year"].max() >= test["year"].min()
            ):
                raise FoldError("Cross-validation leakage")
            last_train = cut - policy.embargo_years
            training = training[training["year"] <= last_train]
            if training["year"].max() >= test["year"].min() - 1:
                raise FoldError("Embargo failed")
            folds.append(
                {
                    "fold_id": f"G{position + 1}_T{cut}_{end}",
                    "training_codes": sorted(set(training["dep_code"])),
                    "test_codes": sorted(held_out),
                    "train_year_min": first_year,
                    "train_year_max": last_train,
                    "test_year_min": cut + 1,
                    "test_year_max": end,
                    "embargo_months": 12 * policy.embargo_years,
                    "n_train_rows": int(len(training)),
                    "n_test_rows": int(len(test)),
                }
            )
    return folds
