"""Build the RC1 golden catalog from a legacy ICML 2.0 RC2 tree.

This is a one-off migration tool. It records, for every artifact on the
canonical RC1 path, its legacy location, its SHA-256 and the columns that
identify a row. The resulting TOML is versioned in ``configs/golden``.

Usage::

    python tools/legacy/build_rc1_catalog.py --legacy-root <Proyecto> \
        --output configs/golden/rc1_catalog.toml
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Columns tried, in order, to identify rows of a table.
UNIT_KEY_CANDIDATES = ("dep_code", "city_code", "codigo", "territorio")
TIME_KEY_CANDIDATES = ("periodo", "period", "date", "fecha", "mes", "year")


@dataclass(frozen=True)
class Entry:
    """One catalog entry before hashing."""

    artifact_id: str
    stage: str
    role: str
    legacy_path: str
    source_class: str = ""
    note: str = ""


N01 = "fases/01_nacional"
N_EXP = f"{N01}/experimentos"
C02 = "fases/02_ciudades"
C_EXP = f"{C02}/experimentos/05_retropolacion_nacional_1993"
D03 = "fases/03_departamentos"
D_V03 = f"{D03}/experimentos/2026_10_31_B1_v03"
D_V04 = f"{D03}/experimentos/2026_10_31_B1_v04_revision"
I04 = "fases/04_integracion/experimentos"
M05 = "fases/05_modelado"
R06 = "fases/06_cierre_jerarquico"

ENTRIES: tuple[Entry, ...] = (
    # --- Sources -------------------------------------------------------
    Entry(
        "source.national_enh_annual",
        "sources",
        "source",
        f"{N01}/data/historico/source_enh_annual.csv",
        "dane_compiled",
    ),
    Entry(
        "source.national_geih_annual",
        "sources",
        "source",
        f"{N01}/data/historico/official_geih_annual.csv",
        "dane_compiled",
    ),
    Entry(
        "source.national_monthly_indicators",
        "sources",
        "source",
        f"{N01}/data/historico/indicadores_mensuales_1993_2003.csv",
        "legacy_derived",
        "Contains *_spliced columns produced by the original notebooks.",
    ),
    Entry(
        "source.national_methodology",
        "sources",
        "source",
        f"{N01}/config/metodologia_nacional.json",
        "frozen_decision",
    ),
    Entry(
        "source.geih_monthly_annex_2026_08",
        "sources",
        "source",
        f"{C02}/estudios/04_donantes_agregados_respaldo/fuentes/"
        "Anexo GEIH Agosto 2026.xlsx",
        "dane_raw",
    ),
    Entry(
        "source.geih_departments_annex_2025",
        "sources",
        "source",
        f"{D03}/fuentes/Anexo_GEIH_Departamentos_2025.xls",
        "dane_raw",
    ),
    Entry(
        "source.population_projections",
        "sources",
        "source",
        f"{D03}/fuentes/proyecciones_poblacion_original.csv",
        "dane_compiled",
    ),
    Entry(
        "source.urban_historical_signals",
        "sources",
        "source",
        f"{C02}/datos/senales_historicas_23_y_donantes.csv",
        "legacy_derived",
        "Byte-identical to legacy hito11 legacy_pea_restored.csv.",
    ),
    Entry(
        "source.urban_window_proxies_2026_08",
        "sources",
        "source",
        f"{C02}/datos/proxies_anuales_ventanas_2026_08.csv",
        "legacy_derived",
        "Producer script not included in RC2.",
    ),
    Entry(
        "source.urban_window_proxies_2026_06",
        "sources",
        "source",
        f"{C02}/datos/proxies_anuales_ventanas_2026_06.csv",
        "legacy_derived",
        "Producer script not included in RC2.",
    ),
    Entry(
        "source.urban_donor_reference",
        "sources",
        "source",
        f"{C02}/datos/donantes_congelados_referencia.csv",
        "frozen_decision",
    ),
    Entry(
        "source.cundinamarca_frozen_donor",
        "sources",
        "source",
        f"{C02}/config/cundinamarca_25_donante_congelado.json",
        "frozen_decision",
    ),
    # --- National --------------------------------------------------------
    Entry(
        "national.disaggregated_monthly",
        "national.disaggregation",
        "stage_output",
        f"{N_EXP}/03_con_visualizacion_integrada/series_mensuales.csv",
    ),
    Entry(
        "national.disaggregated_annual",
        "national.disaggregation",
        "stage_output",
        f"{N_EXP}/03_con_visualizacion_integrada/anclas_anuales.csv",
    ),
    Entry(
        "national.combined_with_provenance",
        "national.disaggregation",
        "stage_output",
        f"{N_EXP}/03_con_visualizacion_integrada/exports/visualizacion/"
        "06_tablas/serie_combinada_con_procedencia.csv",
        note="Consumed downstream from a visualization folder in RC1.",
    ),
    Entry(
        "national.reconciled_monthly",
        "national.reconciliation",
        "stage_output",
        f"{N_EXP}/04_conciliacion_contable_063/"
        "series_mensuales_conciliadas.csv",
    ),
    Entry(
        "national.reconciled_annual",
        "national.reconciliation",
        "stage_output",
        f"{N_EXP}/04_conciliacion_contable_063/anclas_conciliadas.csv",
    ),
    Entry(
        "national.seasonal_monthly",
        "national.seasonality",
        "stage_output",
        f"{N_EXP}/08_estacionalidad_063_v04_componentes/"
        "nacional_1993_2003_estacional_conciliado.csv",
    ),
    # --- Urban -----------------------------------------------------------
    Entry(
        "urban.donor_catalog",
        "urban.donor_selection",
        "stage_output",
        f"{C02}/results/catalogo_pareto_nueve_propuesto.csv",
    ),
    Entry(
        "urban.closed_annual_panel",
        "urban.closure",
        "stage_output",
        f"{C02}/results/cierre/panel_ciudades_cerrado_2007_2026.csv",
    ),
    Entry(
        "urban.cities_monthly_1993_2020",
        "urban.retropolation",
        "stage_output",
        f"{C_EXP}/ciudades_32_mensual_1993_2020.csv",
    ),
    Entry(
        "urban.unreconciled_signals",
        "urban.retropolation",
        "stage_output",
        f"{C_EXP}/seis_indicadores_sin_conciliar_1993_2020.csv",
    ),
    Entry(
        "urban.splice_factors_2007",
        "urban.retropolation",
        "stage_output",
        f"{C_EXP}/factores_empalme_2007.csv",
    ),
    Entry(
        "urban.recent_references",
        "urban.retropolation",
        "stage_output",
        f"{C_EXP}/referencias_urbanas_2021_2026_sin_alterar.csv",
    ),
    Entry(
        "urban.cundinamarca_monthly",
        "urban.synthetic_cundinamarca",
        "stage_output",
        f"{C_EXP}/cundinamarca_25_urbana_sintetica_mensual_1993_2024.csv",
    ),
    Entry(
        "urban.cundinamarca_splice",
        "urban.synthetic_cundinamarca",
        "stage_output",
        f"{C_EXP}/cundinamarca_25_empalme_nacional_2007.csv",
    ),
    Entry(
        "urban.cundinamarca_unreconciled",
        "urban.synthetic_cundinamarca",
        "stage_output",
        f"{C_EXP}/cundinamarca_25_senales_sin_conciliar.csv",
    ),
    Entry(
        "urban.signals_33_1993_2020",
        "urban.synthetic_cundinamarca",
        "stage_output",
        f"{C_EXP}/senales_urbanas_33_incluye_cundinamarca_sintetica_"
        "1993_2020.csv",
    ),
    Entry(
        "urban.donor_alternatives",
        "urban.donor_selection",
        "stage_output",
        f"{C02}/results/evaluacion_207_alternativas.csv",
    ),
    Entry(
        "urban.donor_rule_validation",
        "urban.donor_selection",
        "stage_output",
        f"{C02}/results/validacion_23_ciudades_6_reglas.csv",
        note="Six rules; the pipeline keeps the guarded rule only.",
    ),
    Entry(
        "urban.closure_audit",
        "urban.closure",
        "stage_output",
        f"{C02}/results/cierre/auditoria_9_ciudades.csv",
    ),
    Entry(
        "urban.anchor_audit",
        "urban.retropolation",
        "stage_output",
        f"{C_EXP}/auditoria_anclas_2007_2020.csv",
    ),
    Entry(
        "urban.seam_audit",
        "urban.retropolation",
        "stage_output",
        f"{C_EXP}/auditoria_puente_2006_2007.csv",
    ),
    Entry(
        "urban.retropolation_backtest",
        "urban.retropolation",
        "stage_output",
        f"{C_EXP}/validacion_retrospectiva_23_ciudades.csv",
    ),
    Entry(
        "urban.cundinamarca_annual",
        "urban.synthetic_cundinamarca",
        "stage_output",
        f"{C_EXP}/cundinamarca_25_anual_2007_2024.csv",
    ),
    Entry(
        "urban.cundinamarca_calibration",
        "urban.synthetic_cundinamarca",
        "stage_output",
        f"{C_EXP}/cundinamarca_25_calibracion_bogota_2021_2024.csv",
    ),
    Entry(
        "urban.cundinamarca_official",
        "urban.synthetic_cundinamarca",
        "stage_output",
        f"{C_EXP}/cundinamarca_25_anclas_oficiales_inalteradas.csv",
    ),
    # --- Departmental ----------------------------------------------------
    Entry(
        "departmental.official_anchors",
        "departmental.reconstruction",
        "stage_output",
        f"{D_V03}/fuentes/anclas_laborales_23_originales.csv",
    ),
    Entry(
        "departmental.reconciled_anchors",
        "departmental.reconstruction",
        "stage_output",
        f"{D_V03}/outputs/anclas_laborales_23_conciliadas.csv",
    ),
    Entry(
        "departmental.annual_projections",
        "departmental.reconstruction",
        "stage_output",
        f"{D_V03}/fuentes/proyeccion_poblacional_33_anual.csv",
    ),
    Entry(
        "departmental.monthly_v03",
        "departmental.reconstruction",
        "stage_output",
        f"{D_V03}/outputs/departamentos_23_mensual_1993_2025.csv",
    ),
    Entry(
        "departmental.chow_lin_diagnostics",
        "departmental.reconstruction",
        "stage_output",
        f"{D_V03}/auditoria/diagnostico_chow_lin.csv",
    ),
    Entry(
        "departmental.monthly_revised",
        "departmental.population_revision",
        "stage_output",
        f"{D_V04}/outputs/departamentos_23_mensual_1993_2025_revisado.csv",
    ),
    Entry(
        "departmental.anchor_corrections",
        "departmental.reconstruction",
        "stage_output",
        f"{D_V03}/auditoria/correcciones_anclas.csv",
    ),
    Entry(
        "departmental.population_vs_projection",
        "departmental.reconstruction",
        "stage_output",
        f"{D_V03}/auditoria/poblacion_geih_vs_proyeccion.csv",
    ),
    Entry(
        "departmental.population_calibration",
        "departmental.population_revision",
        "stage_output",
        f"{D_V04}/auditoria/calibracion_poblacion_y_puentes.csv",
    ),
    Entry(
        "departmental.population_backtest",
        "departmental.population_revision",
        "stage_output",
        f"{D_V04}/auditoria/validacion_retrospectiva_senales_poblacion.csv",
    ),
    Entry(
        "departmental.link_audit",
        "departmental.population_revision",
        "stage_output",
        f"{D_V04}/auditoria/auditoria_empalme_2006_2007.csv",
    ),
    Entry(
        "departmental.rho_sensitivity",
        "departmental.population_revision",
        "stage_output",
        f"{D_V04}/auditoria/cundinamarca_inactivos_rho_sensibilidad.csv",
    ),
    Entry(
        "departmental.rho_profile",
        "departmental.population_revision",
        "stage_output",
        f"{D_V04}/auditoria/cundinamarca_inactivos_perfil_rho.csv",
    ),
    # --- Integration -----------------------------------------------------
    Entry(
        "integration.national_monthly",
        "integration.propagation",
        "stage_output",
        f"{I04}/01_propagacion_estacional_1993_2000/outputs/"
        "nacional_mensual_1993_2026_08.csv",
    ),
    Entry(
        "integration.urban_signals_1993_2020",
        "integration.propagation",
        "stage_output",
        f"{I04}/01_propagacion_estacional_1993_2000/outputs/"
        "senales_urbanas_33_mensual_1993_2020.csv",
    ),
    Entry(
        "integration.departmental_monthly",
        "integration.propagation",
        "stage_output",
        f"{I04}/01_propagacion_estacional_1993_2000/outputs/"
        "departamentos_23_mensual_1993_2025.csv",
    ),
    Entry(
        "integration.urban_signals_full",
        "integration.recent_urban",
        "stage_output",
        f"{I04}/02_panel_urbano_33_2026_08/outputs/"
        "senales_urbanas_33_mensual_1993_2026_08.csv",
    ),
    Entry(
        "integration.predictor_base",
        "integration.recent_urban",
        "stage_output",
        f"{I04}/02_panel_urbano_33_2026_08/outputs/"
        "base_predictora_33_1993_2026_08_CANDIDATA.csv",
    ),
    Entry(
        "integration.urban_signals_strict",
        "integration.urban_regularization",
        "stage_output",
        f"{I04}/03_regularizacion_urbana_33_2026_08/outputs/"
        "senales_urbanas_33_mensual_1993_2026_08_ESTRICTAS_CANDIDATO.csv",
    ),
    Entry(
        "integration.predictor_base_strict",
        "integration.urban_regularization",
        "stage_output",
        f"{I04}/03_regularizacion_urbana_33_2026_08/outputs/"
        "base_predictora_33_1993_2026_08_ESTRICTA_CANDIDATA.csv",
    ),
    Entry(
        "integration.urban_signals_filtered",
        "integration.urban_quality_filter",
        "stage_output",
        f"{I04}/04_filtro_calidad_urbana_33_2026_08/outputs/"
        "senales_urbanas_33_1993_2026_08_FILTRO_CALIDAD_CANDIDATA.csv",
    ),
    Entry(
        "integration.predictor_base_filtered",
        "integration.urban_quality_filter",
        "stage_output",
        f"{I04}/04_filtro_calidad_urbana_33_2026_08/outputs/"
        "base_predictora_33_1993_2026_08_FILTRO_CALIDAD_CANDIDATA.csv",
    ),
    Entry(
        "integration.urban_propagation_changes",
        "integration.propagation",
        "stage_output",
        f"{I04}/01_propagacion_estacional_1993_2000/auditoria/"
        "cambios_urbanos_por_unidad.csv",
    ),
    Entry(
        "integration.departmental_propagation_changes",
        "integration.propagation",
        "stage_output",
        f"{I04}/01_propagacion_estacional_1993_2000/auditoria/"
        "cambios_departamentales_por_unidad.csv",
    ),
    Entry(
        "integration.signal_transfer",
        "integration.propagation",
        "stage_output",
        f"{I04}/01_propagacion_estacional_1993_2000/auditoria/"
        "transferencia_seis_senales.csv",
    ),
    Entry(
        "integration.urban_latent_segment",
        "integration.recent_urban",
        "stage_output",
        f"{I04}/02_panel_urbano_33_2026_08/outputs/"
        "tramo_inferido_33_2021_2026_08.csv",
    ),
    Entry(
        "integration.window_control",
        "integration.recent_urban",
        "stage_output",
        f"{I04}/02_panel_urbano_33_2026_08/auditoria/"
        "control_ventanas_por_ciudad.csv",
    ),
    Entry(
        "integration.window_comparison",
        "integration.recent_urban",
        "stage_output",
        f"{I04}/02_panel_urbano_33_2026_08/auditoria/"
        "ventanas_oficiales_vs_reconstruidas.csv",
    ),
    Entry(
        "integration.synthetic_anchor_trace",
        "integration.recent_urban",
        "stage_output",
        f"{I04}/02_panel_urbano_33_2026_08/auditoria/"
        "cundinamarca_anclas_propias.csv",
    ),
    Entry(
        "integration.quality_filter_decisions",
        "integration.urban_quality_filter",
        "stage_output",
        f"{I04}/04_filtro_calidad_urbana_33_2026_08/auditoria/"
        "decision_calidad_33_senales.csv",
    ),
    Entry(
        "integration.quality_filter_windows",
        "integration.urban_quality_filter",
        "stage_output",
        f"{I04}/04_filtro_calidad_urbana_33_2026_08/auditoria/"
        "reproduccion_detallada_57_ventanas_32_ciudades.csv",
    ),
    # --- Modeling --------------------------------------------------------
    Entry(
        "modeling.features_filtered",
        "modeling.feature_preparation",
        "stage_output",
        f"{M05}/hito_02_preparacion/outputs/"
        "features_laborales_33_1993_2026_08.csv",
    ),
    Entry(
        "modeling.features_strict",
        "modeling.feature_preparation",
        "stage_output",
        f"{M05}/hito_02_preparacion/outputs/"
        "features_laborales_33_1993_2026_08_ESTRICTA.csv",
    ),
    Entry(
        "modeling.targets",
        "modeling.feature_preparation",
        "stage_output",
        f"{M05}/hito_02_preparacion/outputs/"
        "objetivos_laborales_departamentales_33_1993_2026_08.csv",
    ),
    Entry(
        "modeling.cv_folds",
        "modeling.feature_preparation",
        "stage_output",
        f"{M05}/hito_02_preparacion/cv/particiones_y_procedencia.json",
    ),
    Entry(
        "modeling.oof_predictions",
        "modeling.training",
        "stage_output",
        f"{M05}/hito_03_entrenamiento/auditoria/predicciones_oof_15_folds.csv",
    ),
    Entry(
        "modeling.ward_predictions",
        "modeling.training",
        "stage_output",
        f"{M05}/hito_03_entrenamiento/outputs/"
        "predicciones_departamentales_33_1993_2026_08_EXPERIMENTAL.csv",
    ),
    Entry(
        "modeling.final_clusters",
        "modeling.training",
        "stage_output",
        f"{M05}/hito_03_entrenamiento/models/"
        "agrupaciones_finales_reentrenadas.csv",
    ),
    Entry(
        "modeling.test_targets",
        "modeling.selection",
        "source",
        f"{M05}/hito_04_seleccion_y_postajuste/inputs/objetivos_test.csv",
        "legacy_derived",
        "Producer not traced in RC2.",
    ),
    Entry(
        "modeling.population_projection",
        "modeling.selection",
        "source",
        f"{M05}/hito_04_seleccion_y_postajuste/inputs/"
        "poblacion_proyeccion.csv",
        "legacy_derived",
        "Producer not traced in RC2.",
    ),
    Entry(
        "modeling.hybrid_panel",
        "modeling.selection",
        "stage_output",
        f"{M05}/hito_04_seleccion_y_postajuste/outputs/"
        "panel_departamental_33_1993_2026_08_CANDIDATO.csv",
    ),
    Entry(
        "modeling.ward_panel",
        "modeling.selection",
        "stage_output",
        f"{M05}/hito_04_seleccion_y_postajuste/outputs/"
        "panel_alternativo_xgb_ward_33.csv",
    ),
    Entry(
        "modeling.reference_clusters",
        "modeling.feature_preparation",
        "stage_output",
        f"{M05}/hito_02_preparacion/outputs/"
        "clusters_referencia_exploratoria.csv",
    ),
    Entry(
        "modeling.reference_k_candidates",
        "modeling.feature_preparation",
        "stage_output",
        f"{M05}/hito_02_preparacion/auditoria/seleccion_k_referencia.csv",
    ),
    Entry(
        "modeling.strict_vs_filtered",
        "modeling.feature_preparation",
        "stage_output",
        f"{M05}/hito_02_preparacion/auditoria/"
        "comparacion_estricta_vs_filtrada.csv",
    ),
    Entry(
        "modeling.cv_metrics",
        "modeling.training",
        "stage_output",
        f"{M05}/hito_03_entrenamiento/auditoria/comparacion_metricas.csv",
    ),
    Entry(
        "modeling.cv_worst",
        "modeling.training",
        "stage_output",
        f"{M05}/hito_03_entrenamiento/auditoria/"
        "errores_por_territorio_fold.csv",
    ),
    Entry(
        "modeling.model_scores",
        "modeling.training",
        "stage_output",
        f"{M05}/hito_03_entrenamiento/auditoria/decision_modelo.csv",
    ),
    Entry(
        "modeling.fold_clusters",
        "modeling.training",
        "stage_output",
        f"{M05}/hito_03_entrenamiento/auditoria/"
        "agrupaciones_reentrenadas_por_fold.csv",
    ),
    Entry(
        "modeling.selection_comparison",
        "modeling.selection",
        "stage_output",
        f"{M05}/hito_04_seleccion_y_postajuste/auditoria/"
        "comparacion_108_postcierre.csv",
    ),
    Entry(
        "modeling.selection_decision",
        "modeling.selection",
        "stage_output",
        f"{M05}/hito_04_seleccion_y_postajuste/auditoria/"
        "decision_postcierre_comun.csv",
    ),
    Entry(
        "modeling.selection_paired_errors",
        "modeling.selection",
        "stage_output",
        f"{M05}/hito_04_seleccion_y_postajuste/auditoria/"
        "errores_pareados_departamento.csv",
    ),
    Entry(
        "modeling.selection_annual",
        "modeling.selection",
        "stage_output",
        f"{M05}/hito_04_seleccion_y_postajuste/auditoria/"
        "evaluacion_anual_completa.csv",
    ),
    Entry(
        "modeling.panel_sensitivity",
        "modeling.selection",
        "stage_output",
        f"{M05}/hito_04_seleccion_y_postajuste/auditoria/"
        "sensibilidad_panel_hibrido_vs_ward.csv",
    ),
    # --- Reconciliation --------------------------------------------------
    Entry(
        "reconciliation.ward_reconciled",
        "reconciliation.hierarchical",
        "stage_output",
        f"{R06}/outputs/panel_33_conciliado_ward_1993_2026_08.csv",
    ),
    Entry(
        "reconciliation.hybrid_reconciled",
        "reconciliation.hierarchical",
        "stage_output",
        f"{R06}/outputs/panel_33_conciliado_hibrido_1993_2026_08.csv",
    ),
    Entry(
        "reconciliation.ward_national_check",
        "reconciliation.hierarchical",
        "stage_output",
        f"{R06}/auditoria/conciliacion_nacional_6_magnitudes_ward.csv",
    ),
    Entry(
        "reconciliation.ward_anchor_check",
        "reconciliation.hierarchical",
        "stage_output",
        f"{R06}/auditoria/anclas_437_comparacion_ward.csv",
    ),
    Entry(
        "reconciliation.ward_smoothness",
        "reconciliation.hierarchical",
        "stage_output",
        f"{R06}/auditoria/diagnostico_suavidad_ward.csv",
    ),
    Entry(
        "reconciliation.hybrid_national_check",
        "reconciliation.hierarchical",
        "stage_output",
        f"{R06}/auditoria/conciliacion_nacional_6_magnitudes_hibrido.csv",
    ),
    Entry(
        "reconciliation.hybrid_anchor_check",
        "reconciliation.hierarchical",
        "stage_output",
        f"{R06}/auditoria/anclas_437_comparacion_hibrido.csv",
    ),
    Entry(
        "reconciliation.hybrid_smoothness",
        "reconciliation.hierarchical",
        "stage_output",
        f"{R06}/auditoria/diagnostico_suavidad_hibrido.csv",
    ),
    Entry(
        "product.national",
        "reconciliation.pet_linearization",
        "final_product",
        f"{R06}/outputs/nacional_pet_lineal_1993_2026_08.csv",
    ),
    Entry(
        "product.departmental",
        "reconciliation.pet_linearization",
        "final_product",
        f"{R06}/outputs/panel_33_ward_pet_lineal_1993_2026_08.csv",
    ),
    Entry(
        "product.urban_signals",
        "integration.urban_quality_filter",
        "final_product",
        f"{I04}/04_filtro_calidad_urbana_33_2026_08/outputs/"
        "senales_urbanas_33_1993_2026_08_FILTRO_CALIDAD_CANDIDATA.csv",
        note="RC1 urban product (copied as ciudades_rc1.csv).",
    ),
)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def infer_keys(path: Path) -> list[str]:
    """Infer the smallest unique key among common unit/time columns."""
    if path.suffix.lower() != ".csv":
        return []
    columns = list(pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns)
    units = [c for c in UNIT_KEY_CANDIDATES if c in columns]
    times = [c for c in TIME_KEY_CANDIDATES if c in columns]
    candidates = [[*units[:1], t] for t in times] + [units[:1]]
    frame = pd.read_csv(
        path,
        encoding="utf-8-sig",
        usecols=sorted({c for k in candidates for c in k}),
    )
    for key in candidates:
        if key and not frame.duplicated(subset=key).any():
            return key
    return []


def toml_string(value: str) -> str:
    """Quote a string for TOML."""
    return json.dumps(value, ensure_ascii=False)


def build(legacy_root: Path) -> str:
    """Return the catalog as TOML text."""
    lines = [
        "# RC1 golden catalog. Generated by "
        "tools/legacy/build_rc1_catalog.py; do not edit by hand.",
        "schema_version = 1",
        'reference = "rc1"',
        "",
    ]
    for entry in ENTRIES:
        path = legacy_root / entry.legacy_path
        if not path.is_file():
            raise FileNotFoundError(path)
        keys = ", ".join(toml_string(k) for k in infer_keys(path))
        lines += [
            "[[artifact]]",
            f"id = {toml_string(entry.artifact_id)}",
            f"stage = {toml_string(entry.stage)}",
            f"role = {toml_string(entry.role)}",
            f"legacy_path = {toml_string(entry.legacy_path)}",
            f"keys = [{keys}]",
            f"sha256 = {toml_string(sha256_file(path))}",
        ]
        if entry.source_class:
            lines.append(f"source_class = {toml_string(entry.source_class)}")
        if entry.note:
            lines.append(f"note = {toml_string(entry.note)}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build(args.legacy_root.resolve()), encoding="utf-8")


if __name__ == "__main__":
    main()
