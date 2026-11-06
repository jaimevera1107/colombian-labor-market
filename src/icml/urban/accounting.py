"""Six-signal accounting projection used by the urban stage.

Six urban signals (employed, unemployed, inactive, labor force, working
age, population) depend on four free non-negative components: employed,
unemployed, inactive and the population outside working age. Signals are
projected onto that subspace by least squares on *relative* errors, with
weights fixed by a reference vector. Because the weights are constant
within a block, the projection preserves the mean of already coherent
anchors.
"""

from __future__ import annotations

import numpy as np

URBAN_SIGNALS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
    "population",
)
SIGNAL_COMPONENTS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "outside_working_age",
)
# Rows: URBAN_SIGNALS; columns: SIGNAL_COMPONENTS.
SIGNAL_MATRIX = np.array(
    [
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [1, 1, 0, 0],
        [1, 1, 1, 0],
        [1, 1, 1, 1],
    ],
    dtype=float,
)
_NEGATIVE_TOLERANCE = 1e-7


class AccountingProjectionError(ValueError):
    """Raised when coherent non-negative signals cannot be obtained."""


def project_signals(values: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Project signal rows onto the identity-consistent subspace.

    Parameters
    ----------
    values : numpy.ndarray
        Array of shape ``(n, 6)`` in :data:`URBAN_SIGNALS` order.
    reference : numpy.ndarray
        Positive vector of shape ``(6,)`` defining relative weights.

    Returns
    -------
    numpy.ndarray
        Coherent signals with the same shape as ``values``.

    Raises
    ------
    AccountingProjectionError
        On malformed or non-positive inputs, or if a component would be
        negative. Values are never clipped.
    """
    signals = np.asarray(values, dtype=float)
    weights_reference = np.asarray(reference, dtype=float)
    if (
        signals.shape[-1] != len(URBAN_SIGNALS)
        or weights_reference.shape != (len(URBAN_SIGNALS),)
        or not np.isfinite(signals).all()
        or not np.isfinite(weights_reference).all()
        or (weights_reference <= 0).any()
    ):
        raise AccountingProjectionError(
            "Signals must be finite with a positive reference vector"
        )
    weights = 1.0 / weights_reference
    weighted_matrix = SIGNAL_MATRIX * weights[:, None]
    components = np.linalg.lstsq(
        weighted_matrix, (signals * weights).T, rcond=None
    )[0].T
    if np.min(components) < -_NEGATIVE_TOLERANCE:
        raise AccountingProjectionError(
            f"Projection needs a negative component: {np.min(components)}"
        )
    result = components @ SIGNAL_MATRIX.T
    if not (
        np.isfinite(result).all() and (result >= -_NEGATIVE_TOLERANCE).all()
    ):
        raise AccountingProjectionError("Inadmissible projected signals")
    return np.asarray(result)
