## 2.6.0 — Reference vintage refrozen, equivalence gate enforced, months after the frozen cutoff (methodological review, phase 2)

Published deliveries at the August 2026 cutoff do not change: a recompute reproduces the eight products byte for byte. What changes is the reference, the gates and what the system can do after August.

- **Reference vintage refrozen from one recompute** (`tools/refreeze_reference.py`, `docs/production/REFERENCE_VINTAGE.md`). Five of the eight frozen products were one commit behind the code (`92a9465` changed the GEIH factors of the nine partial territories after the last freeze) and the sectoral predictor bundle had been trained on the labor base before 2.4.0. All eight products, the H9 closure and its lineage, the sectoral bundle and both hash catalogs now come from a single `run-integral --mode recompute`. Sectoral predictor on the current labor base: LOGO 2015-2024 MAE 1.1583 → 1.1598 pp, 2025 held out 1.2673 → 1.2680 pp.
- **The equivalence gate closes.** At the frozen cutoff the `WITH_SPLICES` state requires `eight_product_equivalence_passed`; a mismatch is `RECOMPUTED_BUT_CROSS_AUDIT_OR_REFERENCE_EQUIVALENCE_FAILED` with `reference_equivalence = FROZEN_VINTAGE_MISMATCH_REFREEZE_REQUIRED`. Before, the flag was written in every delivery's `INFORME_RECALCULO_INTEGRAL.json` as `false` and ignored. The CLI accepts the same clean states as the service.
- **Months after the frozen vintage are processed** (`docs/production/EXTENSION_BEYOND_FROZEN_CUTOFF.md`). `build_vintage_root` extends the frozen parameter panels with explicit, tagged rules: informality priors and national sectoral composition take the same month of the previous year (`EXTENDED_SEASONAL_PERSISTENCE`), the census bridge carries its last month (`EXTENDED_LAST_MONTH_PERSISTENCE`); the tags reach `prior_provenance` and `source_status` and the manifest's `frozen_parameters_extension`. Verified with unit tests and a September smoke test on the extended panels; the first real month after August is the first end-to-end run.
- The cross audit now asserts that the GEIH-represented domain of informality equals the labor product's row by row (it used to differ because the products came from different vintages); the resume-mode audit is no longer `xfail`.

## 2.5.0 — Software design refactor (no methodological change)

Numbers are unchanged. Equivalence check: a full `rebuild --through 2026-07` followed by `update`, run on 2.4.0 (`main`, commit 92a9465) and on this version from the same clean clone, produced **64 of 64 delivery CSV files and 8 of 8 published-base CSV files byte-identical**, and 32 of 32 simple-file `.xlsx` identical except for the creation timestamp that openpyxl writes in `docProps/core.xml`. The only differences are in `MANIFEST.json` / `INFORME_RECALCULO_INTEGRAL.json`: run id, timestamps, software version, the absolute path of the clone, the sort order of a list of absolute paths (`configs/` now sorts before `datos/`), and the fingerprint of `informalidad_cierre_h9/manifest.json`, which this version deliberately resynchronizes. Everything below is layout, naming and language.

- **One project at the root.** `icml-colombia/` is gone: `src/`, `tests/`, `tools/`, `configs/`, `docs/`, `requirements/` and `pyproject.toml` live at the root; one `README`, one `LICENSE`, one CI workflow. Distribution name `icml`.
- **Modules named by function, not by milestone.** `sectoral_*.py` and `sectoral_predictive/` → `icml.sectoral`; `census_bridge.py` → `icml.census.bridge`; `operations/hNN_*.py` → `frozen_products`, `geih_intake`, `monthly_cycle`, `certification`, `excel_staging`, `excel_historical_sources`, `urban_annex`, `prepared_sources`, `informality_lineage`, `informality_regeneration`, `social_annex`, `historical_lineage`, `monthly_staging`.
- **One CLI, in English.** `icml.cli` is a package with one module per command group and a handler per parser. Everyday commands: `status`, `rebuild`, `update`, `plots`, `verify`, `checksums` (`estado`, `consolidar --desde-cero`, `actualizar`, `graficos`, `verificar`); flags `--through`, `--yes`, `--dry-run`, `--no-simple`, `--folder`, `--only`, `--universe`, `--departments`, `--force`. `rebuild` always starts over and asks for confirmation when a base is published (`--yes` answers it). Expert commands: `recalc`, `delivery build|simple|verify`, `run`, `<stage> run`, `informality`, `sectoral`, `census-bridge`, `operations`, `golden`.
- `icml.recalculation.service` holds the orchestration that used to live in the console module; `icml.layout` centralizes the shared paths; `icml.plots` (delivery dashboards, audit charts) replaces `tools/plots/` with a function API.
- **Integrity.** `catalogo_fuentes.json` and the H9 manifest are resynchronized with the frozen products regenerated after 2.4.0 (commits 0a6f316..92a9465 had changed the CSVs without updating the hashes). `SHA256SUMS` now lists exactly the versioned files (517): `icml checksums` skips the folders the pipeline generates. The resume-mode audit of the integral run is `xfail`: the frozen sectoral stage predates the current labor vintage (methodological review pending).
- **Removed:** `tools/legacy/`, the one-time migration and release scripts, `scripts/production/`, `docs/historico/`, two unreachable informality modules, the nested `.github/` workflows.
- **Language.** Code, CLI, installers (`install.sh`/`install.bat`), README, TESTING and the operational docs are English. Persisted values (plan statuses, mode names, folder suffixes, delivery columns), the text inside the figures and the methodological write-ups stay in Spanish.
- Tests: 640 passed, 138 skipped (RC1 golden references not in the repository), 1 xfailed.

## 2.4.0 — PET lineal y componentes de 1993-2000 restaurados (cambio metodológico)

Restaura dos propiedades de la reconstrucción histórica que se perdieron al migrar las etapas, según la estimación
nacional original (`1 - Estimación Nacional.ipynb`). **Reescribe la historia anterior a 2001-01** de las tres bases, de
la informalidad y del sectorial. Desde 2001-01 los productos nacionales no cambian; los territorios solo cambian en su PET,
población e inactivos (suavizado). La vintage se recalcula en
modo total.

- **PET lineal** (`pipeline/labor_reconstruction.py`, `configs/rc1/labor_reconstruction.toml`): recta exacta de su nivel
  inicial al valor oficial de 2001-01, en el nacional, los 33 departamentos y las 33 ciudades. Antes (ADR-006) se
  desviaba hasta 3,65 % de una recta y cambiaba de sentido 6 veces.
- **Componentes de las tasas**: la historia recupera la dinámica de la etapa GEIH (STL del irregular oficial, ruido
  determinístico a escala 0,45 y patrón estacional 2001-2018). Desempleo del ICML, Δ mensual 1993-1999: 0,26 → 1,21 pp.
- **Población lineal antes de 2001**, como en el notebook, en el nacional, los departamentos y las ciudades.
- **PET y población de los territorios, suavizadas después de 2001** (`smooth_territories`): la PET departamental tenía serrucho
  (mediana de 153 cambios de sentido) y ahora es lisa como la nacional (2). Curvatura mínima que conserva las medias anuales; los
  departamentos siguen sumando el nacional oficial. Ocupados, desocupados y fuerza de trabajo no cambian: los inactivos absorben.
- **Identidades exactas.** El notebook dejaba `PEA − (ocupados + desocupados)` desviada hasta 357 mil personas; aquí PEA
  es la suma e inactivos el resto (residuo menor a 4e-9).
- **Reemplaza al empalme de la PET de 2.3.0** (`labor_base_splice.toml` queda en `enabled = false`). Son excluyentes:
  la corrida falla si ambos están activos.
- El empalme de la informalidad de 2.3.0 sigue vigente.
- Licencia MIT (`LICENSE`, `pyproject.toml`).
- **Comandos sencillos en español** (`icml estado`, `consolidar`, `actualizar`, `graficos`, `verificar`) y atajos `icml.sh` /
  `icml.bat`. `consolidar --desde-cero` fuerza recomenzar todo (pide confirmar); `actualizar` agrega solo el mes nuevo y lo dice;
  `--hasta AAAA-MM` trabaja hasta un mes anterior ignorando los anexos posteriores. `docs`: README raíz, secciones 1 a 3.
- La raíz de un corte anterior (`recalculation/vintage_root.py`) pasó de herramienta a función de la librería; `run_recalculation`
  es la única ruta de recálculo. La huella de entradas del manifiesto excluye los anexos posteriores al corte (si no, consolidar hasta
  julio con agosto ya copiado hacía que la actualización de agosto se viera "sin cambios"). `vigente.json` guarda el corte.
  Un `NEW_VINTAGE` de otro corte ya cuenta como limpio. Pruebas: `test_cli_amigable.py` (28).
- Pruebas: `test_labor_reconstruction.py` (41) y `test_adopted_splices.py` actualizada. Nota: `docs/production/RECONSTRUCCION_LABORAL.md`.

## 2.3.0.dev0 — Empalme de la costura de 2001-01 (cambio metodológico)

Primer cambio **metodológico** posterior al refactor de equivalencia. **Reescribe la historia de 1993-2000**
de las tres bases, de la informalidad y del sectorial, por lo que la vintage se recalcula en modo total.

- **Informalidad** (`regime_splice.toml`): hasta 2000-12 la tasa es una retropolación sin ancla oficial y desde
  2001-01 está anclada al DANE; la tasa nacional saltaba 2,8 pp en un mes (y en las 33 ciudades y 29 de 33
  departamentos). Se desplaza el tramo inobservado con una constante estimada por regresión con salto y pendiente
  común (24 meses a cada lado); cada serie tiene su quiebre y los departamentos se recalibran al objetivo nacional.
  Quiebre nacional 2,46 pp. Paso de un mes: 2,78 pp pasa a 0,32 pp.
- **Laboral** (`labor_base_splice.toml`): el quiebre real está en la proporción PET/población (+1,6 pp en un mes,
  27 veces lo normal), no en las tasas (TO, TGP y TD no tienen quiebre; su estimador sería engañoso en el giro del
  ciclo de 2000-2001). Se empalma solo esa proporción y los niveles se reconstruyen con las tasas intactas: todos los
  niveles salvo la población se multiplican por un mismo factor, así que toda identidad y toda tasa se conservan.
  Departamentos con quiebre propio; el nacional ICML es la suma de los departamentos corregidos; la referencia DANE
  anterior a 2001 tiene el suyo; las ciudades usan un quiebre común (su tramo 1993-2000 es una retropolación nacional).
  Salto de ocupados en 2001-01: +5,19 % pasa a +2,80 %; de informales, +9,55 % pasa a +3,28 %.
- **Desde 2001-01 los ocho productos son idénticos** a la vintage anterior, texto por texto.
- La entrega registra los empalmes en `MANIFEST.json` (`inputs_note`). `recalcular` acepta el estado
  `RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES` solo si un empalme está realmente activo.
- La comparación estricta de H5/H6 con lo congelado se exige desde el mes del quiebre (`strict_from`).
- Con `enabled = false` en ambos archivos se reproduce la vintage congelada de agosto de 2026, byte a byte.
- Sin cambios en los parámetros congelados (puente CNPV, priors del MLP, características H16).
- Consolidación del repositorio: README de la raíz y del paquete reescritos, `datos/README.md`, índice de documentación
  (`docs/README.md`), guías de hitos superados en `docs/historico/`, instaladores con versiones fijadas, `.gitignore` de
  proyecto, restos de la entrega H36 en `legacy/` y documento `docs/MARCO_GENERAL_PROCESAMIENTO.md`.
- Repositorio listo para publicar con **todo** dentro (código, datos, referencias RC1, vintage vigente, entrega y bitácora;
  600 MB, sin Git LFS): `.gitignore` mínimo, `.gitattributes` que impide convertir saltos de línea (los hashes de los datos
  dependen de los bytes), flujo de pruebas en GitHub Actions, `SHA256SUMS` y `tools/release/verify_checkout.py` para comprobar
  que una copia está completa e intacta, guía `docs/production/PUBLICACION_EN_GITHUB.md` y las dos versiones completas de
  la documentación metodológica (`docs/MARCO_GENERAL_PROCESAMIENTO.md`, `docs/INFORME_TRAZABILIDAD.md`).
- Herramienta opcional de gráficos (`tools/plots/graficar_entrega.py`): tableros del nacional y de cada departamento en los dos
  universos y comparativos de las tasas (nacional censo contra GEIH, los 33 departamentos, mapas de calor anuales, ranking y
  dispersión). Solo lee una entrega; no cambia cifras. Las imágenes de la entrega vigente van en `datos/3_salida/`.
- README de la raíz convertido en guía de uso mensual. La ingesta solo cuenta libros de datos: las notas y los
  archivos de bloqueo de Excel (`~$…`) ya no cuentan como insumos ni como anexos.

## 2.2.28.dev0 — H27 reproducibilidad integral (2026-11-02)

- Se recuperaron 102 referencias Golden RC1 del RC2 como **datos de prueba**, verificadas por SHA-256 (101 rutas únicas); se conserva el catálogo previo sin reescribirlo.
- Se corrigió el directorio de salida laboral en `run-integral --mode recompute` para auditar ocho productos recalculados.
- Se actualizaron siete pruebas de insumos a las rutas centralizadas del H26.
- Versionado y procedimientos de regresión en Python 3.12, con separación explícita de integridad vs equivalencia numérica.
- Sin modificaciones de los modelos y las ocho bases congeladas.

## 2.2.24.dev0 — H22b: obligatoriedad de dos fuentes sincrónicas

- Corrige la política de actualización: el ICML **nunca** puede ejecutar la reconstrucción integral de un nuevo mes solo con GEIH. Requiere además el anexo oficial de Empleo Informal y Seguridad Social cuyo trimestre móvil **termine en el mismo mes**.
- Agrega `operations check-monthly-sources` para bloquear faltantes y períodos incompatibles, sin permitir publicar y sin confundir declaración de metadatos con inspección real del XLSX.
- La recepción GEIH continúa permitida en `staging` como auditoría aislada, pero deja explícito que **no autoriza** nueva estimación, cierre ni vintage.
- Septiembre 2026: GEIH septiembre + Seguridad Social julio–septiembre. Hasta contar con ambos, se conserva agosto 2026; prohibida la mezcla con junio–agosto.
- No altera modelos, predicciones, datos originales, productos congelados ni referencias RC1.

## 2.2.23.dev0 — H22: GEIH monthly-source intake (NOT a September model update)

- New read-only `operations intake-geih` GEIH monthly XLSX receipt, checksums, two observed domains, overlap revision alarms, published-rate checks, immutable staging.
- Source discovery September 2026 and blocking status if original XLSX not locally available.
- No changes to the eight frozen products or any of the selected model parameters.
- September 2026 model output and July–September informality remain pending.

## 2.2.22.dev0 — H21, auditoría técnica no destructiva

- `icml operations certify`: valida catálogo RC1 (102 referencias / 101 rutas), disponibilidad e integridad de Golden externos, versiones del lock Python 3.12 y hashes de los ocho productos H20.
- Bloquea la certificación ante cualquier ausencia; no recrea referencias históricas ni cambia los productos congelados.
- Nueva batería de pruebas de casos negativos, evidencia de compilación de wheel y prueba aislada del CLI.
- No hay reentrenamiento, no hay nuevas observaciones del DANE, y los Golden originales no están disponibles en este paquete.

## 2.2.20.dev0 — H19, cierre operativo (sin reestimación)

- Nuevo `icml operations preflight`: comprueba integridad H18, tres bases laborales, informalidad y disponibilidad golden.
- Nuevo `icml operations stage-update`: preparación con política de vintages, rechazo explícito de cambios históricos protegidos, validación de entidades y prueba de identidades. No publica una nueva versión.
- Batería completa disponible: 314 PASS, 137 SKIP (sin golden externo). Prueba de una actualización sintética y bloqueo de cambios en historial definitivo.
- Matriz sectorial H16, bases canónicas y modelos congelados no modificados.
- La certificación de distribución estable permanece bloqueada hasta Python 3.12 y entorno numérico bloqueado, golden externo y actualización con fuente real.

## 2.2.19.dev0 — H17 Integración integral de investigación sectorial (no canónica)

- Integra en el paquete ICML los comandos y módulos H11–H13 previamente aislados.
- Incorpora motor H15–H16 (ensamble, composición y conciliación) bajo `icml.sectoral_predictive`.
- Incluye los insumos, resultados y auditorías congelados H11–H16 en `research/sectoral/`.
- Añade `icml sectoral validate-panel` (solo lectura, SHA-256, dimensiones y márgenes).
- Añade `icml sectoral predict-monthly` (salida independiente obligatoria, nunca escribe sobre fuentes).
- No altera series laborales canónicas, resultados de informalidad, ni atribuye oficialidad a estimaciones territoriales.
- Mantiene bloqueada la puerta de publicación sectorial hasta validación externa y evaluación histórica.

## 2.2.18.dev0 — Hito 11 experimental

- Deconvolución positiva de ventanas móviles, anclas mensuales 2015, CV contra baseline, transparencia de residuos y puertas bloqueantes.
- Conserva series previas y dominios; no se publican mensualidades no observadas como oficiales.

## 2.2.17.dev0 — H10 empalme CIIU Rev3 / Rev4 por anexo marzo 2015 (experimental)

- Incorpora anexo oficial de marzo 2015 y 163 ventanas trimestrales CIIU Rev3 2001–2015 en el pipeline sin convertirlas en mensualidades observadas.
- Implementa correspondencia explícita a 14 ramas CIIU Rev4 candidatas por trimestre y puente composicional en 2015 Q1 con 3 escenarios (sin corrección, parcial, completa).
- Mantiene el universo ICML completo como rector y transfiere una sola composición estimada al GEIH representado usando ocupados de la misma ventana; categoría `No informa` conservada por separado.
- Puerta SHA de fuente, identidades por ventana, incompatibilidades de clasificación, cobertura 1993–2026, anomalías de origen, sensibilidad y reproducibilidad.
- No microdatos, no suavizamiento de los 140 meses directos, no estimaciones sectoriales mensuales históricas publicadas como oficiales.

## 2.2.16.dev0 — H10 histórico por anexos (experimental)

- Retira microdatos del alcance metodológico activo (conservados solo por trazabilidad).
- Añade inventario oficial de 70 publicaciones 2007–2014 y contrato de anclas numéricas verificables.
- Bloquea la promoción de trimestres móviles a meses observados; valida SHA y revisión de fuente.
- Incorpora una copia de archivo histórico diciembre 2015 de las fuentes originales, sin afirmar que esté tabulado.
- No genera valores sectoriales 2007–2014 sin los XLS fuente.

## 2.2.15.dev0 — H10 microdatos CIIU Rev4 (experimental)

- Importador mensual de GEIH Ocupados y clasificación CIIU externa 2015–2019, interna 2020+.
- Desagregación condicionada de B/D_E, manteniendo el nivel publicado BDE y conservando los 13 grupos oficiales.
- Nuevas puertas de factores, dominio, unión por persona, muestra suficiente, fuente y mensualidad.
- No se publican ramas faltantes sin microdatos.

## 2.2.14.dev0 — H10 fuentes sectoriales verdaderamente mensuales

- Identificada y extraída la serie mensual oficial 2015–2026 del anexo DANE (140 meses, 13 grupos + No informa); sin suavizamiento ni falsa desagregación.
- Auditado el uso incorrecto de 138 ventanas móviles como meses individuales (MAE 1,285 %, abril 2020 18,22 %).
- Confirmada la coincidencia mensual sectorial con DANE_REFERENCIA, no con universo ICML completo.
- Implementado RAS con márgenes factibles y conservación simultánea; bloqueada la publicación de 14 ramas sin evidencia mensual separada para B y D_E.

## [2.2.13.dev0] — 2026-11-01
- Hito 9: tres bases mensuales completas de informalidad, anualizaciones y incertidumbre de 2020.
- Una MLP residual por definición, cierre KL del universo completo y dominio GEIH derivado con ancla CNPV 2018.
- Puertas de completitud, 6 identidades laborales por universo, reproducibilidad y alerta de evidencia no identificada.
- Conserva íntegros los insumos laborales congelados y los productos 2.2.12 anteriores.

## [2.2.12.dev0] — 2026-11-01
- Experimento de transferencia censal del MLP original y cierre nacional desde un solo universo.
- Reentrenamiento determinista para comprobar que 2018 no altera las etiquetas DANE urbanas originales.
- Pruebas de identidad, dominios excluidos, sensibilidad y cierre sin cambiar bases laborales.

## 2.2.11.dev0 — Census coverage bridge (experimental)

- Canonical full 2018 census population verified; nine capital cabeceras census anchor added.
- Reversible component ledger for 33 departments × 404 months; 2014 GEIH inclusion and 1993–2000 historical proxy statuses.
- Optional post-quality stage `census_bridge`, CLI `census-bridge`, gates and transfer-direction benchmark.
- No canonical labor or informal employment series altered, no models retrained.

## 2.2.9.dev0 — Frontera de calibraciones restringidas (experimental)

- Agrega `icml.informality.constrained_frontier` y `icml informality compare-calibrators`.
- Compara KL original, L2 por ocupados, L2 por varianza y L2 temporal (intensidades 1 y 4).
- Preserva ocupados, factores, nacional ICML y nacional representado DANE; antes de 2001 un solo margen.
- Evalúa distorsión, máximos, discontinuidades, rangos y conservación de jerarquías.
- No altera productos canónicos y no declara precisión departamental demostrada.

## [2.2.7.dev0] — National calibration following the original informality estimator

- Re-examined notebook `InformalityProcessor`: national totals allocate predicted departmental informal/formal shares; national closure is integral to the original estimator, not a post-hoc model-failure signal.
- Added bounded national-calibration adapter preserving frozen employed levels while matching complete ICML and (since 2001) factor-represented DANE margins.
- Included a read-only diagnostic reproducing the legacy independent scaling to expose when it violates `informal + formal = employed` locally.
- Added CLI `icml informality calibrate-national`, tests, full data audits and explicit blocked 2020 MLP output.
- No promotion to canonical informal-employment estimates: national rate candidates share inferred rates and cannot independently validate the departmental MLP.

## [2.2.6.dev0] — Experimental residual MLP for informal-employment rates

- Recovered original MLP effective architecture and saved config for audit.
- Fixed beta negative log-likelihood normalization and numerical boundaries.
- Implemented train-only scaling and genuinely operational inner-fold stopping.
- Evaluated historical T5 and recent GEIH separately; geographic/temporal fold separation.
- Retained author-style P90 MAPE across cities; compared Ridge/mean; residual ablation.
- Added noncanonical departmental candidate and explicit national-gap, covariate-shift and 2020 bridge gates.
- Added safe state_dict weights/scaler/config export and load, optional PyTorch dependency.
- Kept existing labor bases, prior informality candidates, checkpoint and source archives untouched.

## 2.2.5.dev0 — Informality feature consolidation (checkpoint; experimental)

- Restores labor, demographic, national, monthly-share, time, and cluster-relative feature families from the original informality notebook.
- Reuses `icml.modeling.clustering.TerritorialClustering` and `modeling.toml`: Ward fitted by geographic-temporal fold, plus separate descriptive and full-fit assignments.
- Applies DANE urban/rural population shares from original project projections without changing labor series.
- Creates 33-city and 33-department shared-schema matrices, 23-city weak-label training, 15 fold-safe splits and full-fit prediction-ready files.
- No MLP trained, no new departmental informal labels, no replacement of 2.2.4 or canonical labor CSVs.

## [2.2.4.dev0] — 2026-11-01 (secuencia de informalidad experimental)

- Nueva CLI `icml informality sequential` y configuración versionada: 13 áreas → dos nacionales → 23 ciudades → 33 señales → panel de entrenamiento urbano/inferencia departamental.
- Se materializa la segunda retropolación de diez ciudades individuales desde el nacional previamente reconstruido; las primeras 13 se conservan.
- Evaluación de anclas T5, ventanas, saltos, quiebres, identidades y transferencia urbana; contraste contra el candidato 2.2.2.
- Cierre dual **solo contrafactual**: grandes intervenciones de hasta 15 pp bloquean promoción. Ningún MLP entrenado ni etiquetas departamentales inventadas.
- Bases laborales canónicas 2.1.2 y fuentes DANE originales de entrada preservadas por SHA-256.

## [2.2.3.dev0] — 2026-11-01 (puerta metodológica, sin reestimación)

- Se añadió `icml informality audit-historical`: puerta de calidad 13 ciudades → nacional → 23 ciudades → predicción y cierre.
- Audita las anclas T5/T10, ventanas móviles, identidad contable, cobertura, sensibilidad de mensualidades, cambios extremos y quiebres candidatos.
- Documenta el doble empalme urbano del notebook original, las clases de ingeniería de variables y el MLP, diferenciando etapas implementadas de las pendientes.
- Conserva sin cambios todos los datos y productos laborales e informales de 2.2.2; los CSV 13/23 de salida son vistas diagnósticas, NO reconstrucciones nuevas.
- Publicación/certificación permanece bloqueada hasta completar la secuencia estadística y validar la predicción posterior al cierre.

## [2.2.2.dev0] — 2026-11-01

- Reconstrucción urbana histórica DANE-only como módulo experimental opcional.
- Señal propia DANE para las 13 áreas y puente hacia atrás del nacional desde 2021.
- 33 ciudades/señales y ambos nacionales con cantidades informales completas,
  sin modificar datos laborales congelados.
- Auditorías de anclas por definición, año oculto, ventanas y suavidad/identificación.
- `icml informality urban-history` y pruebas nuevas; publicación bloqueada hasta validar saltos.

## [2.2.1.dev0] — 2026-11-01

- Hito 5: experimento de extensión nacional 1993–2026 (dos universos),
  sin modificar el mercado laboral congelado ni las series recientes.
- Nueva fuente tabular ILOSTAT Colombia 2007–2019/2021–2024 con trazabilidad
  y rupturas de definición publicadas; archivo XLSX original preservado.
- Ajuste mensual antiguo de proxy de no pensión con cotas y regularización;
  ventanas 2020 con ceros espurios excluidas.
- Auditorías fuera de muestra por año, sensibilidad, identidades, puentes y
  discrepancias con ILOSTAT 2021–2024.
- Subcomando `icml informality historical`, independiente de `icml run`.
- Candidato marcado `EXPERIMENTAL_NOT_CANONICAL`; no se libera como
  estadística oficial ni homogénea.

## 2.2.0.dev0 — informalidad nacional, hito 5 (2026-11-01)

- Added optional `informality` stage (not part of the labor `icml run` chain).
- Frozen, hash-checked raw extraction from two original DANE annexes; 6,580 rolling windows with definitions and sentinels preserved.
- National domain and employment alignment audits, explicit 2021 methodology break, non-pension proxy kept separate.
- Recent (2021-01 through 2026-08) *latent monthly candidate* under the **new** definition, exactly reproducing official three-month rolling informal windows while holding `DANE_REFERENCIA` employed fixed.
- No alteration to labor or pre-2021 national informal estimates. No historically continuous national informal product yet; old-definition bridge still pending.

# Changelog

## 2.1.2.dev0 — three public labor databases (2026-11-01)

- The `quality` stage delivers exactly three public tables:
  `ciudades.csv`, `departamentos.csv`, and `nacionales.csv`.
- All 33 urban signals and 33 departments retain all six labor levels
  from 1993-01 through 2026-08, without missing values.
- Two national series (ICML sum of departments and DANE reference) are
  kept separately in `nacionales.csv`, both using text code `00`.
- Before 2001, the six coverage factors are the identity (1) so that
  the reconstructed historical territories are not excluded. Values
  of the original six labor quantities are unchanged.
- Post-2001 factors and reference alignment remain unchanged.
- The quality decision remains `REQUIERE_REVISION_METODOLOGICA`;
  demographic-linearity and break alerts require follow-up.
- The portable backup adds integrity verification and clarifies the
  public output contract without rearranging the source modules.

## 2.1.1.dev0 — quality-gate candidate (2026-11-01)

- Added a seventh, non-destructive `quality` stage and the unified `00`
  national + 33 territories panel, with DANE reference and factors.
- Added full identity, official deviation, shock, structural-break,
  demographic and annual-linearity diagnostics, with an explicit
  publication-approval state and SHA-256 manifests.
- No alteration to the six frozen 2.1.0 reconciliation products.
- Gate result: **methodological review required** on annual population
  plateaus and reconstructed PET curvature; no automatic certification.


## 2.1.0 — 2026-11-01

Departmental labor market closed: whole-territory departments, a national
total that covers the country, and monthly updates that do not rewrite
history. RC1 products are unchanged and still reproduced.

### Added
* **Representativeness factors** (`product.departmental_factors`,
  `product.national_icml`). Every territory publishes its whole universe;
  a factor per month and quantity makes the factor-weighted sum equal
  DANE's national total. Verified: GEIH's national = 23 departments +
  Bogotá + the nine capitals, within 0.014 %
  (`docs/evaluation/03_REPRESENTATIVENESS_FACTORS.md`).
* **Deviation from official figures** (`product.official_deviation`):
  median 0.04–0.43 %, maximum 1.89 %, with the part coming from the
  sources' non-additivity separable
  (`docs/evaluation/06_OFFICIAL_DEVIATION.md`).
* **Monthly update engine** (`icml.pipeline.vintage`): revision states
  and a graft. Recomputing everything would rewrite 16,932 final cells;
  the graft rewrites none
  (`docs/evaluation/04_UPDATE_POLICY.md`).
* **Post-closure transfer evaluation** (`icml evaluation run`) and
  closure variants (`docs/evaluation/01`, `02`, `05`).

### Changed
* 1993–2000: every territory now sits on its own demographic projection,
  with its rates untouched. The reconstructed national of that period was
  up to 1.6 % below the projections of the territories it covered.
* The sources' non-additivity is shared in proportion to size, as in the
  project's earlier consolidation. Annual anchors are no longer exact
  (up to 1.9 % in unemployed in 2021) instead of deforming Bogotá by
  9 % and a capital by 12 %. Each territory publishes the persons it
  absorbed.
* Artifacts are written with the shortest round-trip decimal.

## 2.0.0 — 2026-11-01

First release of `icml-colombia`: a production package that reproduces the
ICML 2.0 RC1 figures from the DANE sources.

### Added
* Six stages (`national`, `urban`, `departmental`, `integration`,
  `modeling`, `reconciliation`) with pure computations, TOML
  configuration validated strictly, an immutable artifact store with
  SHA-256 lineage and a manifest per run.
* `icml run` for the end-to-end chain and `icml <stage> run` for single
  stages; `icml golden capture|verify` for the RC1 reference set.
* Regression suite against 102 RC1 artifacts (see
  `docs/migration/01_MIGRATION_PLAN.md`, "Final status").

### Fixed relative to RC1 (no change in numbers)
* Unidentified annex blocks and rolling-window layouts now stop the run
  instead of being skipped or read at fixed offsets.
* Inter-stage files are no longer copied between phase folders; every
  input is resolved and hashed by the artifact store.
* Two hito 4 inputs without a traced producer are derived in the stage.

### Environment
* `requirements/lock-py312.txt` is part of the method: scipy 1.17.1,
  numpy 2.4.4 and xgboost 3.1.3 reproduce RC1; newer releases change the
  Chow-Lin rho and the XGBoost trees.

### Not included
* Charts, HTML galleries and the monthly publication workflow (planned
  for 2.1).
* Methodological changes, listed in `docs/METHODOLOGY_BACKLOG.md`.

## 2.2.8.dev0 — Auditoría posterior al cierre nacional (experimental)

- Añade `informality/postclosure_evaluation.py` y la CLI `icml informality audit-postclosure`.
- Comprueba integridad de empleo fijo, factores, identidades y cierres para los tres candidatos previos sin sobrescribirlos.
- Separa la intervención del margen ICML del efecto incremental de la referencia DANE representada.
- Audita divergencia entre predicciones *calibradas*, cambios de rankings y alertas mensuales, con sensibilidad a ±1 pp de objetivos nacionales.
- Mantiene bloqueada la selección y publicación: 2020 incompleto en MLP, etiquetas urbanas latentes y diferencias de definición no resueltas.

## 2.2.10.dev0 — Sensibilidad de los nacionales y puente de informalidad (experimental)

- Agrega `informality/national_bridge_stress.py` y la CLI `audit-national-bridge`.
- Reestima 3 variantes DANE-only del peso auxiliar nacional, y evalúa cuatro escenarios de estrés de 2020 y de diferencia entre universos.
- Compara las tasas **después** del cierre KL, los residuales nacionales y la sensibilidad territorial por escenario.
- Presenta tres opciones de 2020 para las MLP sin atribuirlas al DANE y realiza pseudohuecos retrospectivos para evaluar estabilidad frente a predicciones ajustadas previas (no validación externa).
- La puerta G4 bloquea publicación: diferencias hipotéticas de solo ±0,25 pp entre nacionales pueden producir grandes cambios locales.
- Preserva los tres CSV laborales, el diseño de la MLP y los checkpoints previos.


## 2.2.21.dev0 — Hito 20, organización operativa de producción (candidata)

- Distribución activa separada de experimentos históricos (retener H19 íntegro como archivo externo).
- `icml operations verify-products`: verifica ocho productos con SHA-256, sin reinterpretar estatus científico.
- `icml operations freeze-products`: copia atómica e inmutable de los ocho productos con manifiesto; nunca publica automáticamente.
- Catálogo, responsabilidades, manual de operación, política de revisión y puertas de liberación en `docs/production/`.
- No se reestimaron ni modificaron series laborales, informalidad o el ensamble H16.
- No se certificaron 102 golden ni una actualización con un nuevo mes real.

## 2.2.32.dev0 — H32 (2026-11-02)

- Recuperado y verificado el generador de `senales_historicas_23_y_donantes.csv` a partir de las medianas de ventanas GEIH trimestrales de 2007–2026; distingue el mapa de transferencia histórico del selector Pareto H30.
- Preservados los 24 valores sintéticos de calibración Cundinamarca 2021–2024, sin presentarlos como observaciones del anexo.
- `prepare-all-excel` produce nueve tablas internas verificadas. No se reentrena el modelo ni se modifica la vintage congelada.
- El modelo anterior se documenta como referencia comparativa solamente; `*_spliced` no es regresor del ICML vigente.
