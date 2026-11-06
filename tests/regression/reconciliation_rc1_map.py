"""Mapping of reconciliation outputs and products to RC1 golden tables."""

from __future__ import annotations

from .equivalence import Equivalence
from .modeling_rc1_map import PANEL, PANEL_REFERENCE_ONLY

SPANISH = {
    "employed": "ocupados",
    "unemployed": "desocupados",
    "inactive": "inactivos",
    "labor_force": "pea",
    "working_age": "pet",
    "labor_population_reconciled": "poblacion_laboral_conciliada",
}
CLOSURE_COLUMNS = {
    "working_age_pre_calibration": "pet_original_precalibracion",
    "demographic_population_original": "poblacion_demografica_original",
    "labor_population_reconciled": "poblacion_laboral_conciliada",
    "smoothed_working_age": "pet_suavizada_con_ancla",
    "panel_population_original": "poblacion_laboral_original_del_panel",
    "working_age_adjustment_persons": "ajuste_pet_personas",
    "working_age_adjustment_pct": "ajuste_pet_pct",
    "labor_population_adjustment_pct": "ajuste_poblacion_laboral_pct",
    "employment_rate_final": "tasa_ocupacion_final",
    "unemployment_rate_final": "tasa_desempleo_final",
    "participation_rate_final": "tasa_participacion_final",
    "working_age_population_rate_final": "tasa_pet_poblacion_final",
    "hierarchical_provenance": "procedencia_jerarquica",
}
RECONCILED = {**PANEL, **CLOSURE_COLUMNS}
PRODUCT_DEPARTMENTAL = {
    **RECONCILED,
    "working_age_version": "version_metodologica_pet",
}
NATIONAL_CHECK = {"period": "periodo"} | {
    f"{prefix}_{k}": f"{legacy}_{v}"
    for k, v in SPANISH.items()
    for prefix, legacy in (
        ("national", "nacional"),
        ("departments", "departamentos"),
        ("residual", "residuo"),
    )
}
ANCHOR_CHECK = {
    "dep_code": "dep_code",
    "year": "year",
    **{k: v for k, v in SPANISH.items()},
    "employed_source": "employed",
    "unemployed_source": "unemployed",
    "inactive_source": "inactive",
    "labor_force_source": "pea_fuente",
    "working_age_source": "pet_fuente",
    "population": "population",
    **{f"error_{k}": f"error_{v}" for k, v in SPANISH.items()},
}
SMOOTHNESS = {
    "dep_code": "dep_code",
    "quantity": "variable",
    "max_curvature_pct": "tasa_curvatura_max_pct",
    "p99_curvature_pct": "tasa_curvatura_p99_pct",
    "max_curvature_before_pct": "curvatura_max_antes_pct",
    "months_curvature_above_2_pct": "tramos_curvatura_mayor_2_pct",
    "max_monthly_jump_pct": "salto_mensual_max_pct",
    "median_monthly_change_pct": "cambio_mensual_relativo_mediano_pct",
    "max_adjustment_vs_pre_pct": "ajuste_max_vs_pre_pct",
    "max_curvature_period": "max_mes_curvatura",
}
NATIONAL = {
    "period": "periodo",
    "origin": "origin",
    "employed": "employed",
    "labor_force": "pea",
    "working_age": "pet",
    "population": "population",
    "inactive": "inactive",
    "unemployed": "unemployed",
}

# Outputs that depend on the model panels, checked through decoupling.
PANEL_EQUIVALENCES: dict[str, tuple[str, Equivalence]] = {
    "reconciliation.ward_reconciled": (
        "reference",
        Equivalence(
            "reference_reconciled",
            ("dep_code", "periodo"),
            RECONCILED,
            reference_only=PANEL_REFERENCE_ONLY,
        ),
    ),
    "reconciliation.hybrid_reconciled": (
        "selected",
        Equivalence(
            "selected_reconciled",
            ("dep_code", "periodo"),
            RECONCILED,
            reference_only=PANEL_REFERENCE_ONLY,
        ),
    ),
    **{
        f"reconciliation.{golden}_{kind}": (
            name,
            Equivalence(f"{name}_{kind}", keys, columns),
        )
        for golden, name in (("ward", "reference"), ("hybrid", "selected"))
        for kind, keys, columns in (
            ("national_check", ("periodo",), NATIONAL_CHECK),
            ("anchor_check", ("dep_code", "year"), ANCHOR_CHECK),
            ("smoothness", ("dep_code", "variable"), SMOOTHNESS),
        )
    },
}
PRODUCT_DEPARTMENTAL_EQUIVALENCE = Equivalence(
    "departmental",
    ("dep_code", "periodo"),
    PRODUCT_DEPARTMENTAL,
    reference_only=PANEL_REFERENCE_ONLY,
)
NATIONAL_EQUIVALENCE = Equivalence("national", ("periodo",), NATIONAL)
