"""Mapping of modeling package outputs to their RC1 golden tables."""

from __future__ import annotations

from .equivalence import Equivalence, RelaxedRows

QUANTITIES = {"labor_force": "pea", "working_age": "pet"}
SPANISH_LEVELS = {
    "employed": "ocupados",
    "unemployed": "desocupados",
    "labor_force": "pea",
    "working_age": "pet",
    "inactive": "inactivos",
}
FLEXIBLE_CODES = (91, 94, 97)
HYBRID = "hibrido_urbano_to_tgp_xgb_td_pet"
POPULATION = {
    "population_demographic_projection": "population_demographic_projection"
}
FLEXIBLE_REASON = (
    "Inherited from the integration quality filter: the "
    "flexible-city optimum is ill-conditioned."
)


def token_map(
    columns: list[str], renames: dict[str, str] | None = None
) -> dict[str, str]:
    """Map package columns to RC1 names by vocabulary tokens."""
    exact = {"period": "periodo", **(renames or {})}
    mapping = {}
    for column in columns:
        if column in exact:
            mapping[column] = exact[column]
            continue
        legacy = column
        for new, old in QUANTITIES.items():
            legacy = legacy.replace(new, old)
        mapping[column] = legacy
    return mapping


FEATURE_COLUMNS = [
    "dep_code",
    "urban_unit_name",
    "period",
    "urban_origin",
    "urban_unit_type",
    "year",
    "population_demographic_projection",
    "unemployment_rate_signal",
    "employment_rate_signal",
    "participation_rate_signal",
    "month",
    "date",
    "is_synthetic_urban_signal",
    "urban_signal_vintage_asof_available",
    *[
        f"urban_{q}"
        for q in (
            "employed",
            "unemployed",
            "inactive",
            "labor_force",
            "working_age",
            "population",
        )
    ],
    *[
        f"nat_{q}"
        for q in (
            "employed",
            "unemployed",
            "inactive",
            "labor_force",
            "working_age",
            "population",
        )
    ],
    "urban_to_department_mapping",
    "urban_unemployment_rate",
    "urban_employment_rate",
    "urban_participation_rate",
    "urban_inactivity_rate",
    "national_unemployment_rate",
    "national_employment_rate",
    "national_participation_rate",
    "urban_minus_national_unemployment_pp",
    "urban_minus_national_employment_pp",
    "urban_population_to_department_projection",
    "urban_employed_to_national",
    "urban_working_age_to_national",
    "log1p_department_population_projection",
    *[
        f"log1p_urban_{q}"
        for q in (
            "employed",
            "unemployed",
            "inactive",
            "working_age",
            "population",
        )
    ],
    *[
        f"urban_{q}_{s}"
        for q in ("employed", "unemployed", "population")
        for s in (
            "mom_pct",
            "lag1_warmup",
            "lag1",
            "yoy_pct",
            "lag12_warmup",
            "lag12",
        )
    ],
    "month_sin",
    "month_cos",
]
FEATURES = token_map(
    FEATURE_COLUMNS,
    {
        "urban_unit_type": "urban_type",
        "unemployment_rate_signal": "td_senal_urbana",
        "employment_rate_signal": "to_senal_urbana",
        "participation_rate_signal": "tgp_senal_urbana",
    },
)
TARGET_COLUMNS = [
    "dep_code",
    "period",
    "year",
    "month",
    "is_synthetic_urban_signal",
    "target_origin",
    *[
        f"target_{q}"
        for q in (
            "employed",
            "unemployed",
            "inactive",
            "labor_force",
            "working_age",
            "population",
        )
    ],
    "is_target_available",
    "target_status",
    "eligible_training",
    "eligible_unbiased_cundinamarca_validation",
    "target_ratio_employed_over_working_age",
    "target_ratio_unemployed_over_labor_force",
    "target_ratio_labor_force_over_working_age",
    "target_ratio_working_age_over_population",
]
OOF = {
    "fold_id": "fold_id",
    "dep_code": "dep_code",
    "period": "periodo",
    "model": "model",
    "variable": "variable",
    "actual": "actual",
    "pred": "pred",
    "coherent_to": "coherent_to",
    "coherent_td": "coherent_td",
    "coherent_tgp": "coherent_tgp",
    "coherent_pet_demog": "coherent_pet_demog",
    "post_pred": "post_pred",
    "raw_abs_pp": "raw_abs_pp",
    "post_abs_pp": "post_abs_pp",
}
PREDICTIONS = {
    "variant": "variant",
    "dep_code": "dep_code",
    "period": "periodo",
    "year": "year",
    "is_synthetic_urban_signal": "is_synthetic_urban_signal",
    "population_demographic_projection": "population_demographic_projection",
    "pet_demog": "pet_demog",
    "td": "td",
    "tgp": "tgp",
    "to": "to",
    "to_coherent": "to_coherent",
    "td_coherent": "td_coherent",
    "tgp_coherent": "tgp_coherent",
    "pet_demog_coherent": "pet_demog_coherent",
    "working_age": "pet_inferido",
    "labor_force": "pea_inferida",
    "unemployed": "desocupados_inferidos",
    "employed": "ocupados_inferidos",
    "inactive": "inactivos_inferidos",
    "prediction_status": "estado_prediccion",
    "target_available": "objetivo_departamental_disponible",
    "is_synthetic_signal": "senal_urbana_sintetica",
    "model": "modelo",
}
RATES = ("to", "td", "tgp", "pet_demog")
PANEL = {
    "dep_code": "dep_code",
    "period": "periodo",
    "year": "year",
    "population_demographic_projection": "population_demographic_projection",
    "is_synthetic_urban_signal": "is_synthetic_urban_signal",
    **{f"raw_{r}": f"crudo_{r}" for r in RATES},
    **{f"final_{r}": f"final_{r}" for r in RATES},
    **{f"delta_{r}_pp": f"delta_{r}_pp" for r in RATES},
    **SPANISH_LEVELS,
    "origin": "origen",
    **{
        f"predicted_pre_reference_{k}": f"predicho_pre_referencia_{v}"
        for k, v in SPANISH_LEVELS.items()
    },
    "bridge_pp": "puente_2026_pp",
    "is_synthetic_signal": "es_sintetica_urbana",
    "employment_rate": "tasa_ocupacion",
    "unemployment_rate": "tasa_desempleo",
    "participation_rate": "tasa_participacion",
    "working_age_population_rate": "tasa_pet_poblacion",
    "closure_cost_pp": "costo_postcierre_pp",
    "max_anchor_adjustment_persons": "ajuste_ancla_max_personas",
}
PANEL_REFERENCE_ONLY = tuple(f"{v}_ref" for v in SPANISH_LEVELS.values())
SUMMARY = {
    "model": "model",
    "postprocessing": "postajuste",
    "mae_annual_pp": "mae_anual_pp",
    "mape_levels_pct": "mape_cantidades_pct",
    "worst_territory_pp": "peor_territorio_pp",
    "mae_monthly_pp": "mae_mensual_pp",
    "intervention_pp": "intervencion_pp",
    "intervention_max_pp": "intervencion_max_pp",
    "roughness_pp": "roughness_pp",
    "group": "grupo",
    "sample": "muestra",
}
ANNUAL = {
    "model": "model",
    "postprocessing": "postajuste",
    "fold_id": "fold_id",
    "dep_code": "dep_code",
    "year": "year",
    **SPANISH_LEVELS,
    **{f"target_{k}": f"target_{v}" for k, v in SPANISH_LEVELS.items()},
    "population_demographic_projection": "population_demographic_projection",
    **{f"{p}_{r}": f"{p}_{r}" for p in ("pred", "ref") for r in RATES},
    **{f"abs_{r}_pp": f"abs_{r}_pp" for r in RATES},
    **{f"abs_{k}_pct": f"abs_{v}_pct" for k, v in SPANISH_LEVELS.items()},
}
SENSITIVITY = {
    "dep_code": "dep_code",
    "period": "periodo",
    **{f"{k}_selected": f"{v}_hibrido" for k, v in SPANISH_LEVELS.items()},
    **{f"{k}_reference": f"{v}_ward" for k, v in SPANISH_LEVELS.items()},
    **{
        f"difference_{k}_pct": f"diferencia_{v}_pct"
        for k, v in SPANISH_LEVELS.items()
    },
}


def _flexible(columns: tuple[str, ...]) -> RelaxedRows:
    return RelaxedRows("dep_code", FLEXIBLE_CODES, columns, FLEXIBLE_REASON)


FLEXIBLE_FEATURES = (
    "td_senal_urbana",
    "to_senal_urbana",
    "tgp_senal_urbana",
    "urban_unemployed",
    "urban_pea",
    "urban_pet",
    "urban_unemployment_rate",
    "urban_employment_rate",
    "urban_participation_rate",
    "urban_inactivity_rate",
    "urban_minus_national_unemployment_pp",
    "urban_minus_national_employment_pp",
    "urban_unemployed_lag1",
    "urban_unemployed_lag12",
    "log1p_urban_unemployed",
    "log1p_urban_pet",
    "urban_pet_to_national",
)
FLEXIBLE_DERIVED = (
    "urban_unemployed_mom_pct",
    "urban_unemployed_yoy_pct",
    "urban_minus_national_unemployment_pp",
    "urban_minus_national_employment_pp",
)


PANEL_DERIVED = tuple(f"delta_{r}_pp" for r in RATES)

EQUIVALENCES: dict[str, Equivalence] = {
    "modeling.features_filtered": Equivalence(
        "features_filtered",
        ("dep_code", "periodo"),
        FEATURES,
        relaxed=RelaxedRows(
            "dep_code",
            FLEXIBLE_CODES,
            FLEXIBLE_FEATURES,
            FLEXIBLE_REASON,
            FLEXIBLE_DERIVED,
        ),
    ),
    "modeling.features_strict": Equivalence(
        "features_strict", ("dep_code", "periodo"), FEATURES
    ),
    "modeling.targets": Equivalence(
        "targets", ("dep_code", "periodo"), token_map(TARGET_COLUMNS)
    ),
    "modeling.test_targets": Equivalence(
        "targets",
        ("dep_code", "periodo"),
        token_map(
            [
                "dep_code",
                "period",
                *[
                    f"target_{q}"
                    for q in (
                        "employed",
                        "unemployed",
                        "inactive",
                        "labor_force",
                        "working_age",
                    )
                ],
            ]
        ),
    ),
    "modeling.population_projection": Equivalence(
        "features_filtered",
        ("dep_code", "periodo"),
        {
            "dep_code": "dep_code",
            "period": "periodo",
            **POPULATION,
        },
    ),
    "modeling.reference_clusters": Equivalence(
        "reference_clusters",
        ("dep_code",),
        {
            c: c
            for c in (
                "dep_code",
                "cluster_id",
                "cluster_fit_cutoff",
                "cluster_training_membership",
            )
        },
    ),
    "modeling.reference_k_candidates": Equivalence(
        "reference_k_candidates",
        ("k",),
        {"k": "k", "silhouette": "silhouette"},
    ),
    "modeling.strict_vs_filtered": Equivalence(
        "strict_vs_filtered",
        ("dep_code",),
        {
            c: c
            for c in (
                "dep_code",
                "n_months_changed_unemployment",
                "max_abs_difference_unemployed",
                "max_abs_difference_employed",
            )
        },
        relaxed=_flexible(("max_abs_difference_unemployed",)),
    ),
    "modeling.oof_predictions": Equivalence(
        "oof_predictions",
        ("fold_id", "dep_code", "periodo", "model", "variable"),
        OOF,
    ),
    "modeling.cv_metrics": Equivalence(
        "cv_metrics",
        ("model", "variable"),
        {
            c: c
            for c in (
                "model",
                "variable",
                "mae_pp",
                "mae_post_pp",
                "median_abs_pp",
                "p90_abs_pp",
                "n",
                "worst_department_fold_mae_pp",
                "worst_department_fold_mae_post_pp",
            )
        },
    ),
    "modeling.cv_worst": Equivalence(
        "cv_worst",
        ("model", "variable", "fold_id", "dep_code"),
        {
            c: c
            for c in (
                "model",
                "variable",
                "fold_id",
                "dep_code",
                "raw_abs_pp",
                "post_abs_pp",
            )
        },
    ),
    "modeling.model_scores": Equivalence(
        "model_scores",
        ("model",),
        {c: c for c in ("model", "mae", "worst", "decision_score")},
    ),
    "modeling.fold_clusters": Equivalence(
        "fold_clusters",
        ("fold_id", "method", "dep_code"),
        {
            c: c
            for c in (
                "dep_code",
                "cluster_id",
                "k",
                "fit_member",
                "fold_id",
                "method",
            )
        },
    ),
    "modeling.ward_predictions": Equivalence(
        "full_predictions",
        ("variant", "dep_code", "periodo"),
        PREDICTIONS,
        reference_only=("poblacion_demografica_fijada", "release_status"),
        relaxed=_flexible(
            tuple(
                v
                for k, v in PREDICTIONS.items()
                if k not in ("variant", "dep_code", "period", "year", "model")
                and "status" not in k
                and "available" not in k
                and "synthetic" not in k
            )
        ),
    ),
    "modeling.final_clusters": Equivalence(
        "final_clusters",
        ("dep_code",),
        {
            c: c
            for c in (
                "dep_code",
                "cluster_id",
                "k",
                *[f"cluster_{j}" for j in range(5)],
            )
        },
    ),
    "modeling.selection_comparison": Equivalence(
        "selection_comparison", ("model", "postajuste", "muestra"), SUMMARY
    ),
    "modeling.selection_decision": Equivalence(
        "selection_decision",
        ("model",),
        {
            **SUMMARY,
            "reserve_mae_pp": "reserva_mae_pp",
            "reserve_worst_pp": "reserva_peor_pp",
            "eligible": "elegible",
            "pareto_frontier": "frontera_pareto",
        },
    ),
    "modeling.selection_paired_errors": Equivalence(
        "selection_paired_errors",
        ("fold_id", "dep_code"),
        {
            "fold_id": "fold_id",
            "dep_code": "dep_code",
            HYBRID: HYBRID,
            "urban_analog": "urban_analog",
            "xgb_none": "xgb_none",
            "xgb_ward": "xgb_ward",
            "hybrid_minus_reference_pp": "hibrido_menos_ward_pp",
        },
    ),
    "modeling.selection_annual": Equivalence(
        "selection_annual",
        ("model", "postajuste", "fold_id", "dep_code", "year"),
        ANNUAL,
    ),
    "modeling.hybrid_panel": Equivalence(
        "panel_selected",
        ("dep_code", "periodo"),
        PANEL,
        reference_only=PANEL_REFERENCE_ONLY,
        relaxed=RelaxedRows(
            "dep_code",
            FLEXIBLE_CODES,
            tuple(
                v
                for k, v in PANEL.items()
                if k not in ("dep_code", "period", "year", "origin")
                and "synthetic" not in k
                and v not in PANEL_DERIVED
            ),
            FLEXIBLE_REASON,
            PANEL_DERIVED,
        ),
    ),
    "modeling.ward_panel": Equivalence(
        "panel_reference",
        ("dep_code", "periodo"),
        PANEL,
        reference_only=PANEL_REFERENCE_ONLY,
        relaxed=RelaxedRows(
            "dep_code",
            FLEXIBLE_CODES,
            tuple(
                v
                for k, v in PANEL.items()
                if k not in ("dep_code", "period", "year", "origin")
                and "synthetic" not in k
                and v not in PANEL_DERIVED
            ),
            FLEXIBLE_REASON,
            PANEL_DERIVED,
        ),
    ),
    "modeling.panel_sensitivity": Equivalence(
        "panel_sensitivity",
        ("dep_code", "periodo"),
        SENSITIVITY,
        relaxed=_flexible(
            tuple(
                v
                for k, v in SENSITIVITY.items()
                if k not in ("dep_code", "period")
            )
        ),
    ),
}
VALUE_MAPS: dict[str, dict[str, dict[str, str]]] = {
    "modeling.ward_predictions": {
        "variant": {"filtered": "filtrada", "strict": "estricta"}
    },
    "modeling.selection_comparison": {
        "muestra": {"development": "desarrollo", "reserve": "reserva_G5"}
    },
    "modeling.selection_decision": {
        "muestra": {"development": "desarrollo", "reserve": "reserva_G5"}
    },
}
