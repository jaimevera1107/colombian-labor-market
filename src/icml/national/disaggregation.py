"""Annual splicing (ENH -> GEIH) and Chow-Lin temporal disaggregation.

Both steps use only the public API of ``tempdisagg`` (0.6.3 or later in the 0.6 series). Each labor
quantity is spliced and disaggregated independently, so the monthly result
does not satisfy the accounting identities; closing them is the job of
:mod:`icml.national.reconciliation`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any

import numpy as np
import pandas as pd
from tempdisagg import SeriesSplicer, TemporalDisaggregator

from icml.national.schema import (
    PERIOD_COLUMN,
    QUANTITY_COLUMNS,
    YEAR_COLUMN,
    source_token,
)

#: The public API this module uses exists from 0.6.3 and the 0.6 series.
#: Measured: 0.6.3 and 0.6.4 reproduce the frozen reference vintage (max
#: difference 0.013 persons). The equivalence gate of ``run-integral`` is
#: what protects the numbers when a newer release changes them.
MINIMUM_TEMPDISAGG_VERSION = (0, 6, 3)
SUPPORTED_TEMPDISAGG_SERIES = (0, 6)
# Methods that accept an autoregressive-parameter truncation.
_RHO_METHOD_PREFIXES = ("chow-lin", "litterman")
# Methods without a regression intercept.
_NO_INTERCEPT_METHODS = ("uniform", "denton", "denton-cholette")
# Annual means must be preserved to this absolute/relative precision.
_ANCHOR_ABSOLUTE_TOLERANCE = 1e-4
_ANCHOR_RELATIVE_TOLERANCE = 1e-9


class NationalSpecificationError(ValueError):
    """Raised when inputs or settings violate the national contract."""


@dataclass(frozen=True)
class SpliceSpec:
    """ENH-to-GEIH annual splice settings."""

    method: str
    overlap_periods: int

    def __post_init__(self) -> None:
        """Validate the overlap length."""
        if self.overlap_periods < 1:
            raise ValueError("overlap_periods must be at least 1")


@dataclass(frozen=True)
class DisaggregationSpec:
    """Temporal disaggregation settings.

    Attributes
    ----------
    method : str
        ``tempdisagg`` method name (e.g. ``"chow-lin-maxlog"``).
    include_intercept : bool
        Whether the regression includes an intercept.
    truncated_rho : float
        Lower truncation of the autoregressive parameter.
    indicators : Mapping[str, Sequence[str]]
        Monthly indicators used for each quantity.
    """

    method: str
    include_intercept: bool
    truncated_rho: float
    indicators: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Require explicit, non-empty indicators for every quantity."""
        if set(self.indicators) != set(QUANTITY_COLUMNS):
            raise ValueError(
                "indicators must be declared for the six labor quantities"
            )
        for quantity, names in self.indicators.items():
            if not names or len(set(names)) != len(names):
                raise ValueError(f"Empty or duplicated indicators: {quantity}")

    @property
    def all_indicators(self) -> tuple[str, ...]:
        """Return every indicator once, in declaration order."""
        ordered = (
            name for q in QUANTITY_COLUMNS for name in self.indicators[q]
        )
        return tuple(dict.fromkeys(ordered))


@dataclass(frozen=True)
class DisaggregationQualityPolicy:
    """Thresholds reported (not enforced) by the disaggregation gates."""

    max_annual_identity_error_persons: float
    max_monthly_identity_error_persons: float
    reject_rho_boundary: bool


@dataclass(frozen=True)
class DisaggregationResult:
    """Output of the national disaggregation stage.

    Attributes
    ----------
    annual : pandas.DataFrame
        Spliced annual anchors (``year`` plus six quantities).
    monthly : pandas.DataFrame
        Disaggregated monthly series (``period`` plus six quantities).
    splice_diagnostics : tuple[dict, ...]
        One record per quantity.
    fit_diagnostics : tuple[dict, ...]
        One record per quantity.
    gates : Mapping[str, bool]
        Quality gates; failing gates are reported, not raised, as in RC1.
    """

    annual: pd.DataFrame
    monthly: pd.DataFrame
    splice_diagnostics: tuple[dict[str, Any], ...]
    fit_diagnostics: tuple[dict[str, Any], ...]
    gates: Mapping[str, bool]


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for piece in version.split(".")[:3]:
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def require_tempdisagg_version() -> None:
    """Fail fast if the installed ``tempdisagg`` is outside the supported range (>=0.6.3, <0.7)."""
    found = metadata.version("tempdisagg")
    parsed = _version_tuple(found)
    if parsed[:2] != SUPPORTED_TEMPDISAGG_SERIES or parsed < MINIMUM_TEMPDISAGG_VERSION:
        raise NationalSpecificationError(
            "tempdisagg>=0.6.3,<0.7 required, "
            f"found {found}"
        )


def prepare_annual_source(frame: pd.DataFrame, suffix: str) -> pd.DataFrame:
    """Validate an annual source and index it by annual period.

    Parameters
    ----------
    frame : pandas.DataFrame
        Table with ``year`` and ``<quantity>_<suffix>`` columns.
    suffix : str
        Source suffix (``"enh"`` or ``"geih"``).

    Returns
    -------
    pandas.DataFrame
        Six quantity columns (canonical names) indexed by annual period.

    Raises
    ------
    NationalSpecificationError
        On missing columns, non-finite, negative or duplicated values.
    """
    columns = {f"{source_token(q)}_{suffix}": q for q in QUANTITY_COLUMNS}
    missing = sorted({YEAR_COLUMN, *columns} - set(frame.columns))
    if missing:
        raise NationalSpecificationError(
            f"Missing {suffix} columns: {missing}"
        )
    data = frame[[YEAR_COLUMN, *columns]].apply(pd.to_numeric, errors="raise")
    values = np.array(data, dtype=float)
    if not np.isfinite(values).all():
        raise NationalSpecificationError("Annual anchors must be finite")
    if (values[:, 1:] < 0).any():
        raise NationalSpecificationError("Negative annual quantity")
    years = data[YEAR_COLUMN]
    if not (years == years.round()).all() or years.duplicated().any():
        raise NationalSpecificationError("Years must be unique integers")
    data = data.assign(**{YEAR_COLUMN: years.astype(int)})
    data = data.sort_values(YEAR_COLUMN).set_index(YEAR_COLUMN)
    data = data.rename(columns=columns)
    data.index = pd.PeriodIndex(data.index.astype(str), freq="Y")
    return data


def prepare_monthly_indicators(
    frame: pd.DataFrame, names: Sequence[str]
) -> pd.DataFrame:
    """Validate monthly indicators and index them by monthly period.

    Raises
    ------
    NationalSpecificationError
        On missing, non-finite or duplicated values, gaps, or partial years
        (completion is not allowed).
    """
    required = ["year", "month", *names]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise NationalSpecificationError(f"Missing indicators: {missing}")
    data = frame[required].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(np.array(data, dtype=float)).all():
        raise NationalSpecificationError("Indicators must be finite")
    if data.duplicated(subset=["year", "month"]).any():
        raise NationalSpecificationError("Duplicated monthly periods")
    if not data["month"].between(1, 12).all():
        raise NationalSpecificationError("Month out of range")
    data = data.sort_values(["year", "month"])
    index = pd.PeriodIndex.from_fields(
        year=data["year"].astype(int),
        month=data["month"].astype(int),
        freq="M",
    )
    if not index.equals(pd.period_range(index[0], index[-1], freq="M")):
        raise NationalSpecificationError("Monthly indicators have gaps")
    if len(index) % 12:
        raise NationalSpecificationError("Indicators must cover full years")
    return pd.DataFrame(
        np.array(data[list(names)], dtype=float),
        index=index,
        columns=list(names),
    )


class AnnualSplicer:
    """Splice ENH annual history onto observed GEIH annual values."""

    def __init__(self, spec: SpliceSpec) -> None:
        """Create the underlying ``tempdisagg`` splicer."""
        self._splicer = SeriesSplicer(
            spec.method, overlap_periods=spec.overlap_periods
        )

    def splice(
        self, enh: pd.DataFrame, geih: pd.DataFrame
    ) -> tuple[pd.DataFrame, tuple[dict[str, Any], ...]]:
        """Return spliced annual anchors and per-quantity diagnostics.

        Raises
        ------
        NationalSpecificationError
            If an observed GEIH value is altered or years remain empty.
        """
        history = prepare_annual_source(enh, "enh")
        current = prepare_annual_source(geih, "geih")
        spliced: dict[str, pd.Series] = {}
        diagnostics: list[dict[str, Any]] = []
        for quantity in QUANTITY_COLUMNS:
            observed = current[quantity].rename(quantity)
            result = self._splicer.splice(
                history[quantity].rename(quantity), observed
            )
            if not np.array_equal(
                np.array(result.values.loc[current.index], dtype=float),  # noqa: PD011
                np.array(observed, dtype=float),
            ):
                raise NationalSpecificationError(
                    f"Observed GEIH anchor altered: {quantity}"
                )
            spliced[quantity] = result.values  # noqa: PD011
            diagnostics.append(
                {
                    "quantity": quantity,
                    "method": result.method.value,
                    "overlap": [str(p) for p in result.overlap_index],
                    "parameters": {
                        k: float(v) for k, v in result.link.items()
                    },
                    "historical_filled_periods": int(result.filled.sum()),
                }
            )
        annual = pd.DataFrame(spliced).sort_index()
        if annual.isna().any().any():
            raise NationalSpecificationError("Years without anchor")
        return annual, tuple(diagnostics)


class ChowLinDisaggregator:
    """Disaggregate annual means into months with a regression method."""

    def __init__(self, spec: DisaggregationSpec) -> None:
        """Store the specification."""
        self._spec = spec

    def disaggregate(
        self, annual: pd.Series, indicators: pd.DataFrame
    ) -> tuple[pd.Series, dict[str, Any]]:
        """Disaggregate one annual series.

        Raises
        ------
        NationalSpecificationError
            If annual means are not preserved, the output is not finite, or
            the library imputed periods or indicator values.
        """
        kwargs: dict[str, Any] = {"completion": False}
        if self._spec.method.startswith(_RHO_METHOD_PREFIXES):
            kwargs["truncated_rho"] = self._spec.truncated_rho
        if self._spec.method not in _NO_INTERCEPT_METHODS:
            kwargs["include_intercept"] = self._spec.include_intercept
        model = TemporalDisaggregator(
            self._spec.method, conversion="average", **kwargs
        )
        result = model.fit(annual, indicators)
        # ``result.values`` is the tempdisagg estimate series, not a pandas
        # ``.values`` array.
        estimates = result.values.sort_index().rename(annual.name)  # noqa: PD011
        if not estimates.index.equals(indicators.index):
            raise NationalSpecificationError("Output calendar mismatch")
        if not np.isfinite(np.array(estimates, dtype=float)).all():
            raise NationalSpecificationError("Non-finite estimates")
        back = estimates.groupby(estimates.index.asfreq("Y")).mean()
        errors = (back.reindex(annual.index) - annual).abs()
        bound = np.maximum(
            _ANCHOR_ABSOLUTE_TOLERANCE,
            np.array(annual, dtype=float) * _ANCHOR_RELATIVE_TOLERANCE,
        )
        if np.any(np.array(errors, dtype=float) > bound):
            raise NationalSpecificationError("Annual means not preserved")
        preprocessing = result.preprocessing
        if preprocessing.n_filled_values or len(preprocessing.added_periods):
            raise NationalSpecificationError("Library imputed inputs")
        warnings = list(result.diagnostics.warnings)
        diagnostics = {
            "quantity": str(annual.name),
            "method": result.method_name,
            "rho": None if result.rho is None else float(result.rho.value),
            "rho_boundary": any("RhoBoundaryWarning" in w for w in warnings),
            "aggregation_error": float(errors.max()),
            "regression_coefficients": (
                None
                if result.regression is None
                else {
                    k: float(v)
                    for k, v in result.regression.coefficients.items()
                }
            ),
            "warnings": warnings,
            "indicators": list(indicators.columns),
            "nonpositive_months": int((estimates <= 0).sum()),
        }
        return estimates, diagnostics


def _max_identity_gap(frame: pd.DataFrame) -> float:
    labor_force_gap = (
        (frame["labor_force"] - frame["employed"] - frame["unemployed"])
        .abs()
        .max()
    )
    working_age_gap = (
        (frame["working_age"] - frame["labor_force"] - frame["inactive"])
        .abs()
        .max()
    )
    return float(max(labor_force_gap, working_age_gap))


class NationalDisaggregation:
    """Composite stage: splice annual sources, then disaggregate monthly."""

    def __init__(
        self,
        splice_spec: SpliceSpec,
        disaggregation_spec: DisaggregationSpec,
        quality_policy: DisaggregationQualityPolicy,
    ) -> None:
        """Compose the splicer and the disaggregator."""
        self._splicer = AnnualSplicer(splice_spec)
        self._disaggregator = ChowLinDisaggregator(disaggregation_spec)
        self._spec = disaggregation_spec
        self._policy = quality_policy

    def run(
        self,
        enh_annual: pd.DataFrame,
        geih_annual: pd.DataFrame,
        monthly_indicators: pd.DataFrame,
    ) -> DisaggregationResult:
        """Run the stage on validated in-memory inputs."""
        require_tempdisagg_version()
        indicators = prepare_monthly_indicators(
            monthly_indicators, self._spec.all_indicators
        )
        spliced, splice_diagnostics = self._splicer.splice(
            enh_annual, geih_annual
        )
        years = indicators.index.asfreq("Y").unique()
        if not set(years).issubset(spliced.index):
            raise NationalSpecificationError("Missing annual anchors")
        annual = spliced.loc[years]

        monthly = pd.DataFrame(index=indicators.index)
        fit_diagnostics: list[dict[str, Any]] = []
        for quantity in QUANTITY_COLUMNS:
            names = list(self._spec.indicators[quantity])
            series, diagnostics = self._disaggregator.disaggregate(
                annual[quantity].rename(quantity), indicators[names]
            )
            monthly[quantity] = series
            fit_diagnostics.append(diagnostics)

        gates = {
            "annual_identities_close": _max_identity_gap(annual)
            <= self._policy.max_annual_identity_error_persons,
            "monthly_identities_close": _max_identity_gap(monthly)
            <= self._policy.max_monthly_identity_error_persons,
            "rho_not_on_boundary": not self._policy.reject_rho_boundary
            or not any(d["rho_boundary"] for d in fit_diagnostics),
            "all_positive": not any(
                d["nonpositive_months"] for d in fit_diagnostics
            ),
        }
        return DisaggregationResult(
            annual=_to_table(annual, YEAR_COLUMN, int),
            monthly=_to_table(monthly, PERIOD_COLUMN, str),
            splice_diagnostics=splice_diagnostics,
            fit_diagnostics=tuple(fit_diagnostics),
            gates=gates,
        )


def _to_table(
    frame: pd.DataFrame, key: str, cast: type[int] | type[str]
) -> pd.DataFrame:
    table = frame[list(QUANTITY_COLUMNS)].copy()
    table.insert(0, key, [cast(str(p)) for p in frame.index])
    return table.reset_index(drop=True)
