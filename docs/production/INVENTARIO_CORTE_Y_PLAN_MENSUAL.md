# Corte 2026-08: inventario, estado del refactor y plan para un mes nuevo

Documento de trabajo posterior a H36. Describe qué se verificó, qué se
cambió y qué falta, separando hechos medidos de decisiones pendientes.

## 1. Qué se cambió (refactor puro)

El cierre de agosto de 2026 estaba incrustado en el código de dos formas:

* **Fechas**: el literal `2026-08` en 24 módulos (51 líneas).
* **Formas de panel derivadas del calendario**: `404` meses, `13332`
  (33 x 404), `808` (2 x 404) y `199980` (13332 x 15), en 16 módulos
  (72 apariciones). Una primera versión de este inventario contó solo las
  fechas y subestimó el problema; las formas no aparecen al buscar `2026-08`.

Ahora todo vive en `icml.domain.cutoff`: `FIRST_MONTH`, `FROZEN_CUTOFF`,
`INFORMALITY_NEW_FIRST_MONTH`, `SECTORAL_FIRST_MONTH`, helpers de calendario
(`month_periods`, `month_labels`, `month_starts`, `expected_month_count`,
`next_month`, `trailing_window_label`) y las formas `N_MONTHS`, `ROWS_33`,
`ROWS_NATIONAL`. Los valores por defecto son los de la vintage congelada,
de modo que el comportamiento no cambia. De las 72 formas, 65 estaban en
código y se migraron; 7 estaban dentro de mensajes de texto y se dejaron.

Evidencia de que no cambió (misma máquina, mismo entorno fijado):

* `run-integral --mode recompute` antes y después: mismo estado, auditoría
  cruzada `PASS`, y los 8 productos idénticos byte a byte (SHA-256).
* `tests/unit/test_cutoff.py`: los helpers y constantes reproducen las
  expresiones y literales originales.
* `tests/unit/test_no_cutoff_literals.py`: trinquete que impide que
  reaparezcan fechas o formas de panel fuera de este módulo; las formas se
  detectan por *tokens*, no por texto, y se comprobó que falla ante un
  `404` nuevo en código y que ignora uno dentro de un mensaje.

Límite: la identidad byte a byte se midió entre corridas en la misma
máquina. No demuestra reproducibilidad entre sistemas operativos o CPU.

## 2. Fechas que permanecen (14 apariciones, justificadas)

| Categoría | Dónde | Apariciones |
|---|---|---|
| Definición de la constante y su documentación | `domain/cutoff.py` | 3 |
| Ayuda de la CLI | `cli.py` | 2 |
| Docstrings | `integral.py`, `sectoral_monthly.py`, `h31_sources.py` | 3 |
| Identidad de archivos o roles de fuentes congeladas | `h34_prepared_sources.py`, `h31_sources.py`, `excel_sources.py` | 6 |
| Meses explícitos de comparación de revisiones | `h22.py` | 1 |

## 3. Lo que NO está resuelto

Centralizar el valor no equivale a parametrizarlo. Los helpers y las
formas son constantes de la vintage congelada, evaluadas al importar el
módulo. Hay que convertirlas en parámetros `cutoff` recibidos desde la
política de vintage. Calendarios fijados así hoy:

* `informality/urban_backcast.py`: `MONTHS`, `NEW_MONTHS`.
* `informality/finalize_block.py`: `MONTHS`.
* `informality/postclosure_evaluation.py`: `PERIODS`.
* `informality/quality_gate.py`: `CALENDAR`, `PERIOD_START`, `PERIOD_END`.
* `operations/integral.py`: `PERIOD_END`; `operations/h22.py`: `LAST_FROZEN`.

Hay además reglas que son metodológicas, no de calendario, y por eso no
se tocaron:

* `operations/h31_sources.extract_window_proxies`: contrato "congelado en
  2026-08" (para 2026 usa las ventanas disponibles hasta agosto).
* Años de anclas anuales sectoriales: `range(2015, 2026)` en
  `sectoral_predictive/h15_predictor.py` y `operations/excel_sources.py`.
* Política sobre parámetros congelados (puente CNPV, priors MLP de H9,
  características sectoriales) al incorporar un mes nuevo.

## 4. Estado de las etapas frente a un mes nuevo

| Componente | Estado medido |
|---|---|
| Laboral (nacional → calidad) | Parametrizado por configuración (`last_month`, `n_windows`); vintages y injerto ya implementados y probados (`pipeline/vintage.py`, `test_incremental_update.py`) |
| Informalidad H5/H6/H9 | Calendario fijo por constantes de módulo (sección 3) |
| Sectorial H16 | Contratos de ventanas y años de anclas fijos (sección 3) |
| Recepción de fuentes (`h22`, `h23`) | Implementada; declara `SOURCE_INTAKE_ONLY` y bloquea el cómputo |

## 5. Bloqueo de datos para septiembre de 2026

La regla de dos anexos (`REGLA_DOS_ANEXOS_ICML.md`) exige, para el mes
objetivo `M`, el GEIH de `M` **y** el anexo de Empleo Informal y Seguridad
Social cuyo trimestre móvil termine en `M`. Para septiembre, el segundo
(julio–septiembre) figura como pendiente, con publicación esperada hacia
mediados de noviembre de 2026 (fecha orientativa, no verificada). Hasta
entonces, un mes nuevo real no puede procesarse sin violar la regla.

## 6. Plan propuesto

1. Convertir las constantes de la sección 3 en parámetros `cutoff`
   recibidos desde la política de vintage, con el valor congelado como
   defecto. Aceptación: ocho productos idénticos byte a byte.
2. Ensayo con julio de 2026, cuyas dos fuentes (GEIH de julio y Seguridad
   Social mayo–julio) están en `insumos/`. Aceptación: la vintage de julio
   se reproduce y la actualización a agosto no altera celdas finales.
3. Política de parámetros congelados: decidida, ver
   `DECISION_PARAMETROS_CONGELADOS.md`.
4. Con el par de septiembre publicado, ejecutar la primera actualización
   real y registrar sus evidencias.
