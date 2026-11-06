# Informe de trazabilidad y oportunidades de mejora — ICML 2.0

2026-11-03 · versión 2.4.0. Complementa el [Marco general de procesamiento](MARCO_GENERAL_PROCESAMIENTO.md).

## Alcance de la verificación

Se examinó el repositorio consolidado (`icml-colombia` 2.4.0: 133 módulos en 18 subpaquetes, unas 33.600 líneas de código fuente, contando archivos `.py` sin `__init__`; 92 archivos de prueba; 15 configuraciones) junto con las corridas ejecutadas durante su construcción. Las cifras de módulos y líneas de la versión anterior de este informe (142, 20 y 39.000) no se pudieron reproducir con ningún método de conteo, así que se reemplazan por las medidas. Las principales evidencias de ejecución son:

- la recalculación total adoptada (`2026-11-03_064801_corte-2026-08_total`), con la entrega verificada (36 de 36 comprobaciones);
- las tres rutinas de uso (`consolidar --desde-cero --hasta 2026-07`, `actualizar` y `graficos`) ejecutadas de punta a punta en una copia limpia, con las evidencias de `docs/production/ACTUALIZACION_MENSUAL.md`;
- la recalculación revertida (restauración apagada y empalme de la PET encendido), idéntica byte a byte en los ocho productos a la vintage de 2.3.0;
- la vintage de julio de 2026;
- la suite completa con referencias Golden: 801 pruebas pasan, 2 omitidas (una de ellas, de microdatos que viven fuera del árbol de fuentes).

La equivalencia con la vintage congelada con **todos** los cambios metodológicos apagados se verificó en 2.3.0 y no se repitió en 2.4.0.

Estados: **A** implementado y verificado (código más prueba o corrida); **B** implementado parcialmente o verificado solo de forma indirecta; **C** documentado sin evidencia suficiente; **D** recomendación, no implementado. Los números de línea se omiten porque cambian con cada edición.

## A. Matriz de trazabilidad

| Proceso | Componente (archivo · función) | Evidencia | Estado | Observaciones |
| --- | --- | --- | --- | --- |
| Detección de anexos y corte | `ingestion/discovery.py` · `discover`, `detect_cutoff`; `ingestion/validation.py` · `verify_annex` | `test_ingestion_discovery.py` (con libros reales) | A | El nombre clasifica y el contenido decide; ignora archivos temporales de Excel |
| Regla de dos anexos | `operations/source_pair.py` · `check_monthly_sources`; `detect_cutoff` | `test_h22_source_pair.py`, `test_recalculation_runner.py` | A | Mes con un solo anexo queda pendiente |
| Plan y compuertas del recálculo | `recalculation/plan.py` · `plan_recalculation`; `gates.py`; `policy.py` · `AnchorPolicy`; `runner.py` · `recalculate` | `test_recalculation.py`, `test_recalculation_runner.py`; simulacros reales | A | Total exige confirmación |
| Preparación de los nueve extractores | `operations/h31_prepare_all.py` · `run`; `excel_sources.py`; `h31_sources.py`; `h32_urban_annex.py` | `test_excel_source_preparation_h29.py`, `test_h31_excel_lineage.py`, `test_h32_urban_annex.py`; informe integral | B | El orquestador `run` no tiene prueba propia; sus extractores sí |
| Vista de fuentes laborales | `operations/h34_prepared_sources.py` · `stage_labor_source_view` | `test_h34_prepared_sources.py` | A | Manifiesto con hashes |
| Cadena laboral | `pipeline/chain.py` · `run_all`, `STAGES`; `*/pipeline.py` de cada etapa | Pruebas por etapa y `test_rc1_golden.py`; 8 de 8 productos idénticos byte a byte | A | `run_all` se valida por regresión y corridas, sin prueba unitaria propia |
| Conciliación jerárquica y linealización de la PET | `reconciliation/hierarchical.py`, `linearization.py`, `solvers.py` | `test_reconciliation_stage.py`, `test_reconciliation_solvers.py` | A | Tolerancias de 1e-3 personas |
| Representatividad (universo GEIH) | `reconciliation/representativeness.py` | `test_representativeness.py` | A | Factor 1 en 1993-2000, 0 en 2001-2013 para 9 territorios |
| Puerta de calidad laboral | `quality/gate.py`, `consolidated.py` | `test_quality_gate.py`, `test_three_bases.py` | A | Identidades a 1e-5 personas |
| Reconstrucción laboral 1993-2000 (PET lineal y componentes) | `pipeline/labor_reconstruction.py` · `reconstruct_labor_products` | `test_labor_reconstruction.py` (41); corrida adoptada; PET recta exacta y residuos menores a 4e-9 | A | Los componentes son generados, no observados; las medias anuales de la ENH dejan de ser anclas |
| Empalme laboral de la PET de 2.3.0 | `pipeline/labor_base_splice.py` · `splice_labor_products` | `test_labor_base_splice.py` (12) | D | Reemplazado en 2.4.0; se conserva para reproducir 2.3.0 |
| Regeneración de H5/H6 | `operations/h35_regenerate_informality.py` · `run` | `test_h35_regeneration_gates.py`, `test_h35_semantic_comparison.py`; corridas | B | La ventana estricta `strict_from` no tiene prueba propia |
| Cierre de informalidad H9 | `informality/finalize_block.py` · `run`, `_calibrate_full` | `test_informality_finalization.py`, `test_informality_quality_gate.py`; corridas | A | Los controles de evidencia científica independiente fallan por diseño y no bloquean |
| Refresco del puente censal | `finalize_block.py` · `_refresh_bridge_levels` | Corridas de julio y agosto | B | Sin prueba unitaria propia |
| Empalme de informalidad | `informality/regime_splice.py` · `splice_regime`, `estimate_break` | `test_regime_splice.py`; corrida adoptada | A | Quiebre nacional de 2,46 pp |
| Sectorial H16/H17 | `sectoral_predictive/h16_integracion.py`; `sectoral_integral.py` · `validate_bundle`, `export_experimental` | `test_h17_sectoral_integral.py` y pruebas H10 a H13; auditoría cruzada | A | Producto experimental |
| Auditoría cruzada y comparación con la referencia | `operations/integral.py` · `audit_products`, `compare_candidate` | `test_integral_h24.py`, `test_h27_product_equivalence.py`; corridas | A | 1e-3 personas, 1e-8 en participaciones |
| Injerto de años anclados | `recalculation/graft.py` · `graft_frozen_years`, `assert_frozen_unchanged` | `test_recalculation.py`, `test_replay_and_annex.py`; ensayo julio a agosto | A | Cero celdas congeladas cambiadas |
| Entrega por universo | `delivery/spec.py`; `builder.py` · `build_delivery` | `test_delivery.py` | A | Estado de cobertura GEIH incluido |
| Verificación de la entrega | `delivery/verify.py` · `verify_delivery`, `coverage_report` | `coverage_report` probado; `verify_delivery` solo sobre entregas reales (36 de 36) | B | Sin prueba unitaria de `verify_delivery` |
| Archivos sencillos | `delivery/simple.py` · `build_simple` | `test_delivery.py` | A | Fecha real en XLSX |
| Corte único | `domain/cutoff.py`; guardia de literales | `test_cutoff.py`, `test_no_cutoff_literals.py` | A | Variable `ICML_CUTOFF` solo para meses anteriores |
| Vintage de un corte anterior | `tools/release/build_vintage_root.py` | Vintage de julio: 8 productos y auditoría cruzada | B | Herramienta manual, fuera de `recalcular` |
| Regresión RC1 | `regression/catalog.py`, `compare.py`, `golden.py` | 102 referencias; suite de 704 pruebas | A | Requiere `ICML_GOLDEN_DIR` (en el repositorio: `legacy/validacion/rc1_original`) |
| Gráficos de una entrega (herramienta opcional) | `tools/plots/graficar_entrega.py` · `build_all`, `plot_dashboard` | `test_plots_tool.py` (17) e inspección visual de los 87 gráficos | A | Solo lee; no cambia cifras |
| Integridad de una copia del repositorio | `tools/release/verify_checkout.py`; `SHA256SUMS` | `test_verify_checkout.py` | A | Detecta archivos faltantes o alterados |
| Meses posteriores a la vintage congelada | Bloqueo en `runner.py` | Prueba de bloqueo en `test_recalculation_runner.py` | D | Falta la regla de extensión de los parámetros congelados |
| Leyendas de las entregas (LEEME) | Escritas al empaquetar, no por `build_delivery` | Revisión manual | B | Pueden desfasarse de la entrega |

## B. Brechas y riesgos

La brecha de mayor impacto es operativa: el sistema no puede producir un mes posterior a 2026-08. Las demás afectan la verificación o la gobernanza, no las cifras vigentes.

| # | Brecha o riesgo | Tipo | Prioridad | Efecto |
| --- | --- | --- | --- | --- |
| 1 | No hay regla para extender a meses nuevos los priors del modelo de informalidad ni el puente censal. El archivo de pesos del modelo (`weights.pt`) no está en el repositorio, solo sus priors; el código sabe guardarlo y recargarlo | Falla comprobada | Alta | Septiembre de 2026 no se puede calcular aunque lleguen los dos anexos |
| 2 | Tres piezas sin prueba unitaria propia: el refresco del puente censal, la ventana estricta de H5/H6 y `verify_delivery` | Falla comprobada | Media | Una regresión en ellas solo se detectaría en una corrida completa |
| 3 | Las referencias RC1, la vintage vigente y las entregas viajan ahora dentro del repositorio (unos 600 MB). Queda la dependencia de que el repositorio remoto se mantenga | Riesgo potencial | Baja | Mitigado por `SHA256SUMS` y por las copias locales |
| 4 | El corte se fija al importar el paquete mediante la variable `ICML_CUTOFF`, y la vintage de un mes anterior requiere una herramienta aparte | Riesgo potencial | Media | Un proceso con la variable mal puesta mezclaría calendarios; hoy lo impiden los guardias de forma |
| 5 | Los LEEME de las entregas se escriben al empaquetar, no los genera el constructor | Falla comprobada | Baja | Pueden desfasarse de la entrega real (ya ocurrió una vez y se corrigió) |
| 6 | En una vintage anterior, las observaciones de informalidad conservan la etiqueta de procedencia "Agosto 2026" | Falla comprobada | Baja | Cosmético; las cifras son correctas |
| 7 | Tolerancias heterogéneas: 1e-4 en anclas departamentales, 1e-3 en conciliación y auditoría, 1e-5 en calidad, 1,1 personas frente a la referencia publicada | Riesgo potencial | Baja | No son contradictorias, pero no hay una política única documentada |
| 8 | La versión de torch con que se generaron los priors originales no está registrada (2.15.0 es la fijada para verificar), y la advertencia de múltiples óptimos de rho (0,989 local frente a 0,898 global) no está medida | Requiere confirmación | Media | Afecta la reproducción de los priors, no su reutilización |
| 9 | Empalmes de 2001-01: error de unos 0,9 pp en la proporción PET (alrededor de 1,4 % en los niveles de 1993-2000); 8 ciudades pequeñas con residuo mayor a 0,5 pp medido por ventanas; persiste un salto de empleo de +2,8 % | Limitación metodológica documentada | Media | Incertidumbre de la historia reconstruida |
| 10 | Validación científica independiente de H9 no aprobada; la publicación no está autorizada por el propio sistema | Gobernanza | Alta | Los resultados no son publicables como oficiales |
| 11 | El fijado de dependencias cubre Python 3.12, mientras el paquete declara compatibilidad con 3.11 a 3.13 | Riesgo potencial | Baja | Reproducción no garantizada fuera de 3.12 |
| 12 | Dos pruebas de microdatos sectoriales se omiten porque su insumo está fuera del árbol | Falla comprobada | Baja | La división B / D_E con microdatos no se verifica en la suite |
| 13 | El flujo principal no descarta filas (las claves duplicadas o incompletas detienen la ejecución), pero no se auditó cada extractor de Excel fila por fila | Requiere confirmación | Media | Una exclusión silenciosa dentro de un extractor no se descartaría |
| 14 | (Resuelta) El repositorio se publica bajo licencia MIT (`LICENSE`) | Gobernanza | Baja | Ninguno |

## C. Recomendaciones

Las dos primeras habilitan la operación mensual y la gobernanza; el resto endurece la verificación. Ninguna está implementada.

| Prioridad | Recomendación | Resuelve | Justificación |
| --- | --- | --- | --- |
| 1 | Definir y aprobar la regla de extensión a meses nuevos. Opciones: recuperar los pesos originales del modelo de informalidad (`weights.pt`, del checkpoint 2.2.12) y aplicarlos al mes nuevo, o reentrenarlo con semilla fija y verificar que reproduce los priors congelados; para el puente censal, arrastrar los factores del último mes. Validar con una retroprueba de julio a agosto | Brecha 1 | Sin ella no hay actualización mensual después de agosto de 2026. Es una decisión metodológica |
| 2 | (Resuelta) Licencia MIT declarada | Brecha 14 | Ya aplicada |
| 3 | Agregar pruebas unitarias para el refresco del puente censal, la ventana estricta de H5/H6 y `verify_delivery` | Brecha 2 | Son controles críticos que hoy solo se ejercitan en corridas de 10 minutos |
| 4 | Generar los LEEME de las entregas desde el constructor, con corte, fecha, versión y métodos activos | Brecha 5 | Elimina el paso manual que ya produjo un desfase |
| 5 | Registrar la versión de torch, las semillas y la configuración de entrenamiento de los priors, y medir la advertencia de múltiples óptimos | Brecha 8 | Permite reproducir los parámetros congelados, no solo reutilizarlos |
| 6 | Pasar el corte como parámetro explícito de cada ejecución y llevar la reconstrucción de cortes anteriores dentro de `recalcular` | Brecha 4 | Evita depender de una variable de entorno y de una herramienta aparte |
| 7 | Documentar una política única de tolerancias por tipo de magnitud | Brecha 7 | Facilita auditorías y cambios coherentes |
| 8 | Auditar fila por fila los nueve extractores y declarar cualquier exclusión | Brecha 13 | Confirma que no hay pérdidas silenciosas en la preparación |
| 9 | Corregir las etiquetas de procedencia por vintage, incluir un insumo mínimo para las pruebas de microdatos y fijar dependencias para 3.11 y 3.13 o restringir la compatibilidad a 3.12 | Brechas 6, 11 y 12 | Cierra detalles de exactitud y cobertura de pruebas |
