"""Mapping of departmental package outputs to their RC1 golden tables."""

from __future__ import annotations

from .equivalence import Equivalence

QUANTITIES = {"labor_force": "pea", "working_age": "pet"}
LEVELS = {
    q: q for q in ("employed", "unemployed", "inactive", "population")
} | QUANTITIES
ANNUAL = {
    "dep_code": "dep_code",
    "department": "department",
    "year": "year",
    **LEVELS,
}
MONTHLY = {
    "dep_code": "dep_code",
    "department": "department",
    "period": "periodo",
    "year": "year",
    "origin": "origin",
    **LEVELS,
}

EQUIVALENCES: dict[str, Equivalence] = {
    "departmental.official_anchors": Equivalence(
        "official_anchors", ("dep_code", "year"), ANNUAL
    ),
    "departmental.reconciled_anchors": Equivalence(
        "closed_anchors", ("dep_code", "year"), ANNUAL
    ),
    "departmental.anchor_corrections": Equivalence(
        "anchor_corrections",
        ("dep_code", "year", "variable"),
        {
            "dep_code": "dep_code",
            "year": "year",
            "quantity": "variable",
            "official_value": "observed_source",
            "closed_value": "reconciled_anchor",
            "change_persons": "change_persons",
            "relative_change_pct": "relative_change_pct",
        },
    ),
    "departmental.annual_projections": Equivalence(
        "annual_projections",
        ("dep_code", "year"),
        {
            "dep_code": "dep_code",
            "dep_name": "dep_name",
            "year": "year",
            "population_demographic_projection": (
                "population_demographic_projection"
            ),
        },
    ),
    "departmental.population_vs_projection": Equivalence(
        "population_vs_projection",
        ("dep_code", "year"),
        {
            "dep_code": "dep_code",
            "department": "department",
            "year": "year",
            "population": "population",
            "population_demographic_projection": (
                "population_demographic_projection"
            ),
            "gap_persons": "gap_persons",
            "gap_pct": "gap_pct",
        },
        reference_only=("decision",),
    ),
    "departmental.monthly_v03": Equivalence(
        "monthly_initial", ("dep_code", "periodo"), MONTHLY
    ),
    "departmental.chow_lin_diagnostics": Equivalence(
        "chow_lin_diagnostics",
        ("dep_code", "variable"),
        {
            "dep_code": "dep_code",
            "department": "department",
            "quantity": "variable",
            "method": "method",
            "national_indicator": "national_indicator",
            "rho": "rho",
            "rho_at_bound": "rho_at_bound",
            "warnings": "warnings",
            "max_annual_anchor_error_persons": (
                "max_annual_anchor_error_persons"
            ),
            "link_ratio": "link_ratio_2007",
            "negative_month_count": "negative_month_count",
            "min_value_persons": "min_value_persons",
        },
    ),
    "departmental.monthly_revised": Equivalence(
        "monthly_revised", ("dep_code", "periodo"), MONTHLY
    ),
    "departmental.population_calibration": Equivalence(
        "population_calibration",
        ("dep_code",),
        {
            "dep_code": "dep_code",
            "department": "department",
            "scale_factor": "scale_2007_geih_to_demography",
            "max_annual_target_error_persons": (
                "max_annual_target_error_persons"
            ),
            "seam_change_pct_new": "pct_dec2006_jan2007_new",
            "seam_change_pct_old": "pct_dec2006_jan2007_old",
        },
    ),
    "departmental.population_backtest": Equivalence(
        "population_backtest",
        ("dep_code", "method"),
        {
            "dep_code": "dep_code",
            "department": "department",
            "method": "method",
            "holdout_wape_pct": "holdout_wape_pct",
            "calibration_factor": "k_calibration",
        },
        reference_only=("test_2007_2012", "train_2013_2017"),
    ),
    "departmental.link_audit": Equivalence(
        "link_audit",
        ("dep_code", "variable"),
        {
            "dep_code": "dep_code",
            "department": "department",
            "quantity": "variable",
            "link_log_change_pct": "link_log_change_pct",
            "national_log_change_pct": "national_log_change_pct",
            "residual_to_national_pct_log": "residual_to_national_pct_log",
            "empirical_low_abs_log_pct": "empirical_p95_abs_log_pct",
            "empirical_high_abs_log_pct": "empirical_p99_abs_log_pct",
            "above_high_quantile": "above_p99",
            "above_large_change": "above_20pct_simple",
        },
    ),
    "departmental.rho_sensitivity": Equivalence(
        "rho_sensitivity",
        ("periodo",),
        {
            "period": "periodo",
            "global_rho_value": "inactivos_rho_global",
            "competing_rho_value": "inactivos_rho_competidor",
            "difference_pct": "diff_pct",
        },
    ),
    "departmental.rho_profile": Equivalence(
        "rho_profile",
        (),  # floats are not reliable join keys: compare by position
        {"rho": "rho", "negative_loglik": "negative_loglik"},
    ),
}

VALUE_MAPS: dict[str, dict[str, dict[str, str]]] = {
    "departmental.anchor_corrections": {"variable": QUANTITIES},
    "departmental.population_backtest": {
        "method": {
            "national": "Nacional",
            "departmental_projection": "Proyeccion_departamental",
        }
    },
}
