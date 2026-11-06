"""Mapping of urban package outputs to their RC1 golden counterparts.

Each entry renames candidate columns to RC1 names, optionally filters the
reference rows and restricts the comparison to the columns the package
reproduces. Columns of RC1 that belong to archived exploratory studies are
listed explicitly in ``reference_only`` so that nothing is dropped silently.
"""

from __future__ import annotations

from .equivalence import Equivalence

QUANTITIES = {"labor_force": "pea", "working_age": "pet"}


CATALOG_COLUMNS = {
    "recipient_code": "receptor",
    "recipient_name": "ciudad",
    "reference_donor_code": "donante_vigente",
    "reference_donor_name": "nombre_vigente",
    "selected_donor_code": "donante_sugerido",
    "selected_donor_name": "nombre_sugerido",
    "backup_1_code": "respaldo_1",
    "backup_1_name": "respaldo_1_nombre",
    "backup_2_code": "respaldo_2",
    "backup_2_name": "respaldo_2_nombre",
    "frontier_size": "tamano_frontera",
    "reference_in_frontier": "donante_vigente_en_frontera",
    "selected_dominates_reference": "sugerido_domina_vigente_5_criterios",
    "score_minimax_reference": "score_minimax_vigente",
    "score_minimax_selected": "score_minimax_sugerido",
    "holdout_error_reference": "error_2025_vigente",
    "holdout_error_selected": "error_2025_sugerido",
    "seam_error_reference": "continuidad_vigente",
    "seam_error_selected": "continuidad_sugerido",
    "max_working_age_share_selected": "max_pet_pob_sugerido",
    "positive_selected": "no_negativos",
    "selection_status": "tipo_guardia",
}
ALTERNATIVE_COLUMNS = {
    "recipient_code": "receptor",
    "donor_code": "donante",
    "growth_occ": "growth_occ",
    "growth_pop": "growth_pop",
    "rate": "rate",
    "scale": "scale",
    "ratio_stability": "ratio_stability",
    "population_ratio": "razon_poblacion",
    "pareto_efficient": "pareto_eficiente",
    "max_regret": "max_regret",
    "weighted_regret": "regret_ponderado",
    "score_minimax": "score_minimax",
    "score_distance": "score_distancia",
    "score_incumbent_rule": "score_factor_estable",
    "holdout_error_mean": "error_2025_medio",
    "holdout_error_max": "error_2025_max",
    "seam_error_mean": "puente_2021_medio",
    "seam_error_max": "puente_2021_max",
    "complete": "sin_vacios",
    "positive": "no_negatividad",
    "working_age_below_population": "pet_menor_poblacion",
    "max_working_age_share": "max_pet_pob",
    "is_reference_donor": "es_vigente",
    **{
        f"{f}_norm": f"{f}_norm"
        for f in (
            "growth_occ",
            "growth_pop",
            "rate",
            "scale",
            "ratio_stability",
        )
    },
    **{
        f"regret_{f}": f"regret_{f}"
        for f in (
            "growth_occ",
            "growth_pop",
            "rate",
            "scale",
            "ratio_stability",
        )
    },
    **{
        f"holdout_error_{c}": f"error_2025_{c}"
        for c in ("employed", "unemployed", "inactive", "population")
    },
}
MONTHLY_CITY_COLUMNS = {"period": "periodo", **QUANTITIES}

EQUIVALENCES: dict[str, Equivalence] = {
    "urban.donor_catalog": Equivalence(
        "donor_catalog",
        ("receptor",),
        CATALOG_COLUMNS,
        reference_only=("decision",),
    ),
    "urban.donor_alternatives": Equivalence(
        "donor_alternatives",
        ("receptor", "donante"),
        ALTERNATIVE_COLUMNS,
        reference_only=(
            "receptor_nombre",
            "donante_nombre",
            "score_tendencia",
            "score_equilibrado",
            "score_poblacion",
            "score_estructura",
            "score_media",
        ),
    ),
    "urban.donor_rule_validation": Equivalence(
        "donor_backtest",
        ("receptor",),
        {
            "city_code": "receptor",
            "city_name": "ciudad",
            "donor_code": "donante",
            "donor_name": "nombre_donante",
            "wape_balanced": "wape_balanceado",
            "wape_max_quantity": "wape_max_variable",
            "wape_employed": "wape_employed",
            "wape_unemployed": "wape_unemployed",
            "wape_working_age": "wape_pet",
            "wape_population": "wape_population",
            "holdout_error_mean": "error_2025_medio",
            "seam_error_mean": "puente_2021_medio",
        },
        reference_filter=("regla", "pareto_con_guardia"),
        reference_only=("regla",),
    ),
    "urban.closed_annual_panel": Equivalence(
        "recipient_annual_panel",
        ("receptor", "year"),
        {
            "recipient_code": "receptor",
            "recipient_name": "ciudad",
            "donor_code": "donante",
            "year": "year",
            "origin": "origin",
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "population": "population",
            **QUANTITIES,
        },
    ),
    "urban.closure_audit": Equivalence(
        "recipient_closure_audit",
        ("receptor",),
        {
            "recipient_code": "receptor",
            "recipient_name": "ciudad",
            "donor_code": "donante",
            "seam_before": "bridge_before",
            "seam_after": "bridge_after",
            "max_delta_log": "maximum_delta_log",
            "max_extra_growth_log": "max_additional_growth_log",
            "coherent": "coherent",
            "target_met": "threshold_met",
            "untouched_before_ramp": "untouched_pre_2015",
            "holdout_error_log": "control_2025_log",
            "holdout_warning": "control_2025_warning",
        },
        reference_only=("deltas_log", "control_2025_decision", "decision"),
    ),
    "urban.cities_monthly_1993_2020": Equivalence(
        "cities_monthly",
        ("city_code", "periodo"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "origin": "origin",
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "population": "population",
            **MONTHLY_CITY_COLUMNS,
        },
    ),
    "urban.unreconciled_signals": Equivalence(
        "cities_unreconciled",
        ("city_code", "periodo"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "origin": "origin",
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "population": "population",
            **MONTHLY_CITY_COLUMNS,
        },
    ),
    "urban.splice_factors_2007": Equivalence(
        "splice_factors",
        ("city_code", "variable"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "quantity": "variable",
            "link_year": "link_year",
            "link_factor": "link_factor",
            "city_anchor": "city_2007_anchor",
            "national_mean": "national_2007_mean",
        },
        reference_only=("indicator", "link_method", "indicator_transform"),
    ),
    "urban.anchor_audit": Equivalence(
        "anchor_audit",
        ("city_code", "year", "variable"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "year": "year",
            "quantity": "variable",
            "source": "source",
            "source_value": "source_value",
            "reconciled_value": "reconciled_value",
            "delta": "delta",
            "relative_delta": "relative_delta",
        },
    ),
    "urban.seam_audit": Equivalence(
        "seam_audit",
        ("city_code", "variable"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "quantity": "variable",
            "seam_log": "gap_2006_2007_log",
            "national_seam_log": "national_gap_log",
            "seam_extra_log": "gap_extra_log",
            "max_relative_closure_before_anchor": "relative_close_max_pre2007",
            "max_signal_ratio_error_before_anchor": (
                "ratio_relative_signal_pre2007_max"
            ),
        },
    ),
    "urban.retropolation_backtest": Equivalence(
        "retropolation_backtest",
        ("city_code", "calibration_year", "variable"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "calibration_year": "calibration_year",
            "hidden_start": "hidden_start",
            "hidden_end": "hidden_end",
            "quantity": "variable",
            "wape_pct": "wape_pct",
            "max_ape_pct": "max_ape_pct",
        },
    ),
    "urban.recent_references": Equivalence(
        "recent_references",
        ("dep_code", "year"),
        {
            "city_code": "dep_code",
            "city_name": "city",
            "year": "year",
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "population": "population",
            **QUANTITIES,
        },
    ),
    "urban.cundinamarca_monthly": Equivalence(
        "synthetic_monthly",
        ("periodo",),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "unit_type": "tipo_unidad",
            "origin": "origin",
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "population": "population",
            **MONTHLY_CITY_COLUMNS,
        },
    ),
    "urban.cundinamarca_unreconciled": Equivalence(
        "synthetic_unreconciled",
        ("periodo",),
        {
            "city_code": "city_code",
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "population": "population",
            **MONTHLY_CITY_COLUMNS,
        },
    ),
    "urban.cundinamarca_splice": Equivalence(
        "synthetic_links",
        ("variable",),
        {"quantity": "variable", "ratio": "ratio", "link_year": "link_year"},
        reference_only=("indicator",),
    ),
    "urban.cundinamarca_annual": Equivalence(
        "synthetic_annual",
        ("year",),
        {
            "year": "year",
            "origin": "origin",
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "population": "population",
            **QUANTITIES,
            **{
                f"raw_{q}": f"raw_{q}"
                for q in ("employed", "unemployed", "inactive", "population")
            },
            "raw_labor_force": "raw_pea",
            "raw_working_age": "raw_pet",
        },
    ),
    "urban.cundinamarca_calibration": Equivalence(
        "synthetic_calibration",
        ("variable",),
        {
            "quantity": "variable",
            "donor_code": "donor_code",
            "donor_name": "donor_name",
            "recipient_code": "target_code",
            "recipient_name": "target_name",
            "calibration_start": "calibration_start",
            "calibration_end": "calibration_end",
            "ratio": "ratio",
            "donor_mean": "donor_average_2021_2024",
            "recipient_official_mean": (
                "cundinamarca_official_average_2021_2024"
            ),
            "max_ratio_variation_pct": "max_calibration_ratio_variation_pct",
        },
    ),
    "urban.cundinamarca_official": Equivalence(
        "synthetic_official_anchors",
        ("year",),
        {
            "year": "year",
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "population": "population",
            **QUANTITIES,
        },
    ),
    "urban.signals_33_1993_2020": Equivalence(
        "signals_33",
        ("city_code", "periodo"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "origin": "origin",
            "unit_type": "tipo_unidad",
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "population": "population",
            **MONTHLY_CITY_COLUMNS,
        },
    ),
}

# Values that RC1 wrote as Spanish labels and the package writes in English.
VALUE_MAPS: dict[str, dict[str, dict[str, str]]] = {
    "urban.donor_catalog": {
        "tipo_guardia": {
            "pareto_with_guards": "PARETO_CON_CONTROLES",
            "exception_keeps_incumbent": "EXCEPCION_CONSERVA_REFERENCIA",
        }
    },
    "urban.cundinamarca_splice": {"variable": QUANTITIES},
    # RC1 named the same synthetic unit differently in this one table.
    "urban.cundinamarca_calibration": {
        "variable": QUANTITIES,
        "target_name": {
            "Cundinamarca — señal urbana sintética": (
                "Cundinamarca — señal sintética"
            )
        },
    },
    "urban.splice_factors_2007": {"variable": QUANTITIES},
    "urban.anchor_audit": {"variable": QUANTITIES},
    "urban.seam_audit": {"variable": QUANTITIES},
    "urban.retropolation_backtest": {"variable": QUANTITIES},
}
