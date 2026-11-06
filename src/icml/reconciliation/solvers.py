"""Sparse quadratic programs and proportional fitting used by the closure.

Every smoother minimizes a distance to a baseline plus a second-difference
(curvature) penalty under exact linear constraints, solved through the
KKT system with a sparse direct solver.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import spsolve

_ANCHOR_CHECK = 1e-5
MONTHS_PER_YEAR = 12


class SolverError(ValueError):
    """Raised when constraints are infeasible or not satisfied."""


def second_difference(n: int) -> sparse.csr_matrix:
    """Return the ``(n - 2) x n`` second-difference operator."""
    return sparse.diags(
        [np.ones(n - 2), -2 * np.ones(n - 2), np.ones(n - 2)],
        [0, 1, 2],
        shape=(n - 2, n),
        format="csr",
    )


def smooth_with_annual_means(
    values: np.ndarray,
    years: np.ndarray,
    annual: Mapping[int, float],
    strength: float,
) -> np.ndarray:
    """Minimize ``||z - x||^2 + strength ||D2 z||^2`` with exact year means.

    Raises
    ------
    SolverError
        If an anchored year does not have twelve months or a mean is lost.
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    curvature = second_difference(n)
    system = (
        sparse.eye(n, format="csr") + strength * (curvature.T @ curvature)
    ).tocsc()
    if not annual:
        return np.asarray(spsolve(system, x))
    anchored = sorted(annual)
    rows, columns, weights = [], [], []
    for position, year in enumerate(anchored):
        months = np.flatnonzero(years == year)
        if len(months) != MONTHS_PER_YEAR:
            raise SolverError(f"Incomplete anchored year {year}")
        rows.extend([position] * len(months))
        columns.extend(months.tolist())
        weights.extend([1 / MONTHS_PER_YEAR] * len(months))
    means = sparse.csr_matrix(
        (weights, (rows, columns)), shape=(len(anchored), n)
    )
    targets = np.array([annual[y] for y in anchored])
    kkt = sparse.bmat([[system, means.T], [means, None]], format="csc")
    solution = spsolve(kkt, np.r_[x, targets])[:n]
    if np.max(np.abs(means @ solution - targets)) >= _ANCHOR_CHECK:
        raise SolverError("Annual means not preserved")
    return np.asarray(solution)


def joint_smoother(
    baseline: np.ndarray,
    codes: Sequence[int],
    years: np.ndarray,
    national: np.ndarray,
    anchors: pd.DataFrame,
    strength: float,
    anchor_values: Sequence[float],
    national_tolerance: float,
) -> np.ndarray:
    """Smooth all territories jointly with exact national monthly totals.

    Minimizes relative deviation plus relative curvature for every
    territory, subject to the national total of each month and to the
    annual mean of every anchored territory-year (``anchor_values`` in the
    order of ``anchors``). National breaks are thus spread over all
    territories instead of the unanchored ones only.

    Raises
    ------
    SolverError
        If the national totals are not reproduced.
    """
    n_months, n_units = baseline.shape
    scales = np.median(baseline, axis=0)
    national_scale = float(np.median(national))
    curvature = second_difference(n_months)
    block = sparse.eye(n_months, format="csr") + strength * (
        curvature.T @ curvature
    )
    quadratic = sparse.block_diag([block] * n_units, format="csc")
    normalized = (baseline / scales).T.reshape(-1)
    position = {code: j for j, code in enumerate(codes)}
    rows, columns, weights, rhs = [], [], [], []
    for month in range(n_months):
        for unit in range(n_units):
            rows.append(month)
            columns.append(unit * n_months + month)
            weights.append(scales[unit] / national_scale)
        rhs.append(national[month] / national_scale)
    for record, value in zip(anchors.itertuples(), anchor_values, strict=True):
        row = len(rhs)
        unit = position[int(record.dep_code)]
        months = np.flatnonzero(years == int(record.year))
        if len(months) != MONTHS_PER_YEAR:
            raise SolverError("Incomplete anchored year")
        for month_index in months:
            rows.append(row)
            columns.append(unit * n_months + int(month_index))
            weights.append(1 / MONTHS_PER_YEAR)
        rhs.append(float(value) / scales[unit])
    constraints = sparse.csr_matrix(
        (weights, (rows, columns)), shape=(len(rhs), n_units * n_months)
    )
    kkt = sparse.bmat(
        [[quadratic, constraints.T], [constraints, None]], format="csc"
    )
    solution = spsolve(kkt, np.r_[normalized, np.asarray(rhs)])
    result = (
        solution[: n_units * n_months].reshape(n_units, n_months).T
        * scales[None, :]
    )
    gap = float(np.max(np.abs(result.sum(axis=1) - national)))
    if gap > national_tolerance:
        raise SolverError(f"Joint smoothing misses national totals: {gap}")
    return np.asarray(result)


def proportional_fit(
    seed: np.ndarray,
    row_totals: np.ndarray,
    column_totals: np.ndarray,
    *,
    max_iterations: int,
    tolerance: float,
    check_every: int,
    floor: float,
) -> np.ndarray:
    """KL projection of a positive table onto exact margins (IPFP).

    Raises
    ------
    SolverError
        On non-positive or incompatible margins, or no convergence.
    """
    if np.any(row_totals <= 0) or np.any(column_totals <= 0):
        raise SolverError("Non-positive residual margins")
    if abs(row_totals.sum() - column_totals.sum()) > 1e-4:
        raise SolverError("Margins do not add up")
    table = np.maximum(seed, floor).astype(float).copy()
    for iteration in range(max_iterations):
        table *= (row_totals / table.sum(axis=1))[:, None]
        table *= (column_totals / table.sum(axis=0))[None, :]
        if (
            iteration % check_every == 0
            and max(
                abs(table.sum(axis=0) - column_totals).max(),
                abs(table.sum(axis=1) - row_totals).max(),
            )
            < tolerance
        ):
            break
    table *= (row_totals / table.sum(axis=1))[:, None]
    if (
        max(
            abs(table.sum(axis=0) - column_totals).max(),
            abs(table.sum(axis=1) - row_totals).max(),
        )
        > 1e-5
    ):
        raise SolverError("Proportional fitting did not converge")
    return np.asarray(table)
