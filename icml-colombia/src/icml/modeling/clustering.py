"""Territorial clusters fitted only on training territories.

Each territory is summarized by a profile (medians of urban rates and
structure, plus growth) built with information up to a cutoff year. Two
families are used:

* a descriptive K-Means reference on the 22 labeled non-synthetic
  territories (not a model feature);
* fold-specific K-Means or Ward partitions, refitted in every fold and in
  the final fit, whose one-hot memberships are model features.

Held-out territories never influence the scaler, the partition or ``k``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

CLUSTER_PREFIX = "cluster_"


class ClusteringError(ValueError):
    """Raised when a valid partition cannot be fitted."""


@dataclass(frozen=True)
class ClusteringPolicy:
    """Profile definition and partition search settings."""

    profile_first_year: int
    profile_variables: Sequence[str]
    growth_variables: Sequence[str]
    reference_k_min: int
    reference_k_max: int
    reference_n_init: int
    reference_cut_year: int
    fold_max_k: int
    fold_kmeans_n_init: int
    singleton_penalty: float

    @property
    def cluster_columns(self) -> list[str]:
        """One-hot membership columns (fixed width)."""
        return [f"{CLUSTER_PREFIX}{j}" for j in range(self.fold_max_k)]


def territory_profiles(
    features: pd.DataFrame,
    policy: ClusteringPolicy,
    cut_year: int,
    territory_codes: Sequence[int],
) -> pd.DataFrame:
    """Return one profile row per territory, using data up to ``cut_year``.

    Raises
    ------
    ClusteringError
        If the window is empty or a territory has no profile.
    """
    sample = features[
        (features["year"] >= policy.profile_first_year)
        & (features["year"] <= cut_year)
    ]
    if sample.empty:
        raise ClusteringError("Empty profile window")
    profile = sample.groupby("dep_code")[
        list(policy.profile_variables)
    ].median()
    if set(profile.index) != set(territory_codes):
        raise ClusteringError("Incomplete clustering profile")
    first = sample.groupby("dep_code").first()
    last = sample.groupby("dep_code").last()
    for column in policy.growth_variables:
        profile[f"{column}_growth_log"] = np.log(
            last[column].clip(lower=1)
        ) - np.log(first[column].clip(lower=1))
    return profile.sort_index()


class TerritorialClustering:
    """Fit reference and fold-specific territorial partitions."""

    def __init__(
        self,
        policy: ClusteringPolicy,
        seed: int,
        territory_codes: Sequence[int],
        synthetic_code: int,
    ) -> None:
        """Store the policy and the territorial universe."""
        self._policy = policy
        self._seed = seed
        self._codes = sorted(territory_codes)
        self._synthetic = synthetic_code

    def reference(
        self, features: pd.DataFrame, training_codes: Sequence[int]
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
        """Descriptive K-Means with silhouette-chosen ``k`` (ties: smaller).

        Raises
        ------
        ClusteringError
            If there are too few training territories.
        """
        policy = self._policy
        codes = sorted(set(training_codes))
        cut = policy.reference_cut_year
        profiles = territory_profiles(features, policy, cut, self._codes)
        scaler = StandardScaler().fit(profiles.loc[codes])
        training = scaler.transform(profiles.loc[codes])
        trials = []
        for k in range(policy.reference_k_min, policy.reference_k_max + 1):
            if k >= len(codes):
                continue
            model = KMeans(
                n_clusters=k,
                random_state=self._seed,
                n_init=policy.reference_n_init,
            ).fit(training)
            silhouette = (
                silhouette_score(training, model.labels_)
                if len(set(model.labels_)) > 1
                else -1.0
            )
            trials.append((k, float(silhouette), model))
        if not trials:
            raise ClusteringError("Too few training territories")
        k, silhouette, model = sorted(trials, key=lambda t: (-t[1], t[0]))[0]
        labels = model.predict(scaler.transform(profiles))
        assignment = pd.DataFrame(
            {
                "dep_code": profiles.index.astype(int),
                "cluster_id": labels.astype(int),
                "cluster_fit_cutoff": cut,
                "cluster_training_membership": [
                    int(c in codes) for c in profiles.index
                ],
            }
        )
        candidates = pd.DataFrame(
            {"k": [t[0] for t in trials], "silhouette": [t[1] for t in trials]}
        )
        return (
            assignment,
            candidates,
            {
                "chosen_k": int(k),
                "silhouette": float(silhouette),
                "fit_cutoff_year": int(cut),
            },
        )

    def fold(
        self,
        features: pd.DataFrame,
        method: str,
        training_codes: Sequence[int],
        cut_year: int,
    ) -> pd.DataFrame:
        """Fit a K-Means or Ward partition on training territories.

        ``k`` maximizes the silhouette minus a penalty per singleton
        cluster; held-out territories are assigned to the nearest centroid
        (Ward) or by the K-Means predictor.

        Raises
        ------
        ClusteringError
            On an unknown method, the synthetic signal in training, or no
            valid partition.
        """
        policy = self._policy
        codes_train = np.array(
            sorted({int(c) for c in training_codes}), dtype=int
        )
        if self._synthetic in codes_train:
            raise ClusteringError("Synthetic signal not allowed in fitting")
        profiles = territory_profiles(features, policy, cut_year, self._codes)
        codes = profiles.index.to_numpy(dtype=int)
        scaler = StandardScaler().fit(
            profiles.loc[codes_train].to_numpy(dtype=float)
        )
        matrix = scaler.transform(profiles.to_numpy(dtype=float))
        train_index = np.flatnonzero(np.isin(codes, codes_train))
        training = matrix[train_index]
        winners = []
        for k in range(2, min(policy.fold_max_k, len(train_index) - 1) + 1):
            if method == "kmeans":
                model: Any = KMeans(
                    n_clusters=k,
                    random_state=self._seed,
                    n_init=policy.fold_kmeans_n_init,
                )
            elif method == "ward":
                model = AgglomerativeClustering(n_clusters=k, linkage="ward")
            else:
                raise ClusteringError(f"Unknown clustering method: {method}")
            labels = model.fit_predict(training)
            if len(np.unique(labels)) < 2:
                continue
            sizes = np.bincount(labels, minlength=k)
            silhouette = float(silhouette_score(training, labels))
            winners.append(
                (
                    silhouette
                    - policy.singleton_penalty * float(np.sum(sizes == 1)),
                    -k,
                    model,
                    labels,
                    k,
                )
            )
        if not winners:
            raise ClusteringError(f"No valid {method} partition")
        _, _, model, labels, k = max(winners, key=lambda w: (w[0], w[1]))
        if method == "kmeans":
            assigned = model.predict(matrix)
        else:
            centers = np.array(
                [training[labels == j].mean(axis=0) for j in range(k)]
            )
            assigned = np.argmin(
                ((matrix[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2),
                axis=1,
            )
            assigned[train_index] = labels
        onehot = np.zeros((len(codes), policy.fold_max_k))
        onehot[np.arange(len(codes)), assigned] = 1.0
        result = pd.DataFrame(onehot, columns=policy.cluster_columns)
        result.insert(0, "dep_code", codes)
        result["cluster_id"] = assigned.astype(int)
        result["fit_member"] = np.isin(codes, codes_train)
        result["cluster_method"] = method
        result["cut_year"] = cut_year
        result["k"] = k
        return result
