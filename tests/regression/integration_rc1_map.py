"""Mapping of integration package outputs to their RC1 golden tables."""

from __future__ import annotations

from .equivalence import Equivalence, RelaxedRows

QUANTITIES = {"labor_force": "pea", "working_age": "pet"}
LEVELS = {
    q: q for q in ("employed", "unemployed", "inactive", "population")
} | QUANTITIES
CITY_PANEL = {
    "city_code": "city_code",
    "city_name": "city_name",
    "period": "periodo",
    "origin": "origin",
    "unit_type": "tipo_unidad",
    **LEVELS,
}
PREDICTORS = {
    **CITY_PANEL,
    "year": "year",
    "population_demographic_projection": ("population_demographic_projection"),
    "unemployment_rate_signal": "td_senal_urbana",
    "employment_rate_signal": "to_senal_urbana",
    "participation_rate_signal": "tgp_senal_urbana",
    "target_with_annual_anchor": ("objetivo_depto_con_ancla_anual_disponible"),
    "is_synthetic_signal": "es_senal_urbana_sintetica",
}
CITY_KEYS = ("city_code", "periodo")
# Flexible cities of the quality filter: their optimum is ill-conditioned
# (a 2e-13 change in the windows moves months by up to 5e-4 persons).
FLEXIBLE_CODES = (91, 94, 97)
FLEXIBLE_REASON = (
    "Soft-constrained QP with a flat optimum; RC1 consumed "
    "CSV-rounded windows (2e-13 persons)."
)


def _relaxed(
    columns: tuple[str, ...], derived: tuple[str, ...] = ()
) -> RelaxedRows:
    return RelaxedRows(
        "city_code", FLEXIBLE_CODES, columns, FLEXIBLE_REASON, derived
    )


FILTERED_LEVELS = ("unemployed", "pea", "pet")
FILTERED_RATES = ("td_senal_urbana", "to_senal_urbana", "tgp_senal_urbana")

EQUIVALENCES: dict[str, Equivalence] = {
    "integration.national_monthly": Equivalence(
        "national_monthly",
        ("periodo",),
        {"period": "periodo", "origin": "origin", **LEVELS},
    ),
    "integration.urban_signals_1993_2020": Equivalence(
        "urban_signals_1993_2020", CITY_KEYS, CITY_PANEL
    ),
    "integration.departmental_monthly": Equivalence(
        "departmental_monthly",
        ("dep_code", "periodo"),
        {
            "dep_code": "dep_code",
            "department": "department",
            "period": "periodo",
            "year": "year",
            "origin": "origin",
            **LEVELS,
        },
    ),
    "integration.urban_propagation_changes": Equivalence(
        "urban_propagation_changes",
        ("code",),
        {
            "city_code": "code",
            "city_name": "name",
            "unit": "tipo",
            "max_monthly_change_pct": "max_cambio_mensual_pct",
            "trace_error_persons": "error_trazabilidad_raw_personas",
            "max_change_persons": "max_cambio_personas",
        },
    ),
    "integration.departmental_propagation_changes": Equivalence(
        "departmental_propagation_changes",
        ("code",),
        {
            "dep_code": "code",
            "department": "name",
            "max_component_change_pct": "max_cambio_3_componentes_pct",
            "max_change_persons": "max_cambio_personas",
        },
    ),
    "integration.signal_transfer": Equivalence(
        "signal_transfer",
        ("city_code", "variable"),
        {
            "city_code": "city_code",
            "quantity": "variable",
            "frozen_factor": "factor_congelado",
            "max_monthly_change_pct": "max_cambio_mensual_pct",
        },
        reference_only=("max_error_senal_antes_de_cierre_personas",),
    ),
    "integration.urban_signals_full": Equivalence(
        "urban_signals_full", CITY_KEYS, CITY_PANEL
    ),
    "integration.urban_latent_segment": Equivalence(
        "urban_latent_segment", CITY_KEYS, CITY_PANEL
    ),
    "integration.predictor_base": Equivalence(
        "predictor_base", CITY_KEYS, PREDICTORS
    ),
    "integration.window_control": Equivalence(
        "window_control",
        ("city_code", "variable"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "quantity": "variable",
            "max_window_error_persons": "max_error_ventanas_personas",
            "published_labor_force_identity": "error_interno_oficial_pea",
            "published_working_age_identity": "error_interno_oficial_pet",
            "seam_log_pct": "puente_dic20_ene21_log_pct",
            "first_year_ratio_to_national": "q03_relativo_vs_nacional",
            "prior_wape_pct": "ajuste_prior_wape_pct",
            "lower_bound_active": "limite_positivo_activo",
        },
    ),
    "integration.window_comparison": Equivalence(
        "window_comparison",
        ("city_code", "window_end", "variable"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "window_end": "window_end",
            "quantity": "variable",
            "published_mean": "dane_media_12m",
            "estimated_mean": "estimado_media_12m",
            "difference_persons": "diferencia_personas",
        },
    ),
    "integration.synthetic_anchor_trace": Equivalence(
        "synthetic_anchor_trace",
        ("year", "variable"),
        {
            "city_code": "city_code",
            "year": "year",
            "quantity": "variable",
            "departmental_anchor": "ancla_departamental",
            "synthetic_mean": "media_sintetica",
            "difference_persons": "diferencia_personas",
        },
    ),
    "integration.urban_signals_strict": Equivalence(
        "urban_signals_strict", CITY_KEYS, CITY_PANEL
    ),
    "integration.predictor_base_strict": Equivalence(
        "predictor_base_strict", CITY_KEYS, PREDICTORS
    ),
    "integration.urban_signals_filtered": Equivalence(
        "urban_signals_filtered",
        CITY_KEYS,
        CITY_PANEL,
        relaxed=_relaxed(FILTERED_LEVELS),
    ),
    "integration.predictor_base_filtered": Equivalence(
        "predictor_base_filtered",
        CITY_KEYS,
        PREDICTORS,
        relaxed=_relaxed(FILTERED_LEVELS + FILTERED_RATES),
    ),
    "product.urban_signals": Equivalence(
        "urban_signals_filtered",
        CITY_KEYS,
        CITY_PANEL,
        relaxed=_relaxed(FILTERED_LEVELS),
    ),
    "integration.quality_filter_decisions": Equivalence(
        "quality_filter_decisions",
        ("city_code",),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "rule": "politica",
            "max_window_error_pct": "ventana_error_max_pct",
            "max_bidirectional_ratio": "variacion_mensual_bidireccional_max",
            "max_change_persons": "cambio_contra_original_personas_max",
        },
        reference_only=(
            "max_aumento_mensual_pct",
            "ventanas_n",
            "tipo_unidad",
        ),
        relaxed=_relaxed(
            (
                "ventana_error_max_pct",
                "variacion_mensual_bidireccional_max",
                "cambio_contra_original_personas_max",
            )
        ),
    ),
    "integration.quality_filter_windows": Equivalence(
        "quality_filter_windows",
        ("city_code", "fin_ventana"),
        {
            "city_code": "city_code",
            "city_name": "city_name",
            "window_end": "fin_ventana",
            "published_mean": "ventana_oficial",
            "filtered_mean": "ventana_ajustada",
            "difference_persons": "diferencia_personas",
            "relative_error_pct": "error_relativo_pct",
            "rule": "politica",
        },
        relaxed=_relaxed(
            ("ventana_ajustada",),
            derived=("diferencia_personas", "error_relativo_pct"),
        ),
    ),
}

RULES = {
    "unchanged": "SIN_AJUSTE",
    "strict_exact_windows": "ESTRICTA_VENTANAS_EXACTAS",
    "flexible_bounded_tolerance": "FLEXIBLE_TOLERANCIA_CONTROLADA",
    "synthetic_unchanged": "SINTETICA_INALTERADA",
}
VALUE_MAPS: dict[str, dict[str, dict[str, str]]] = {
    "integration.urban_propagation_changes": {
        "tipo": {"city": "CIUDAD", "synthetic": "URBANA_SINTETICA"}
    },
    "integration.signal_transfer": {"variable": QUANTITIES},
    "integration.window_control": {"variable": QUANTITIES},
    "integration.window_comparison": {"variable": QUANTITIES},
    "integration.synthetic_anchor_trace": {"variable": QUANTITIES},
    "integration.quality_filter_decisions": {"politica": RULES},
    "integration.quality_filter_windows": {"politica": RULES},
}
