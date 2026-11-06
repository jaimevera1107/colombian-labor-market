# ICML 2.2.5.dev0 — Hito 7: consolidación previa al MLP (checkpoint)

**Estado:** implementación experimental reproducible; no se ha entrenado ni elegido el modelo de informalidad, no se ha reajustado el nacional ni se ha modificado ninguna magnitud laboral. Sigue bloqueada la publicación de informalidad departamental.

## Correspondencia con el notebook original

En `2 - Estimación Departamental.ipynb`, la preparación anterior a `MLPInformality` combinaba: `LaborMarketRateCalculator`, la base conjunta `type=city / type=dep`, tasas, participaciones poblacionales y mensuales, distribución cabecera/rural, comparación con tasas nacionales, columnas `*_cluster`, medianas, residuos y razones por clúster. Posteriormente se preparaban `train_df` y `predict_df` usando un mismo inventario de columnas.

| Función anterior | Implementación 2.2.5 |
|---|---|
| Magnitudes, tasas y porcentajes poblacionales | `feature_consolidation.py`, mismas definiciones contables sobre los respectivos ocupados congelados |
| Participación mensual | Suma de 33 señales urbanas **o** de 33 departamentos, separadas por tipo; no confundir con una cifra publicada DANE |
| Estructura cabecera / rural | Proyecciones DANE del proyecto original (`population_projections_legacy.csv`) por código y año, sin recalibrar niveles laborales |
| Tasa nacional de desempleo | Derivada de `ICML_COMPLETO`, no de la tasa reconstruida de informalidad |
| Clústeres | Se reutiliza directamente `icml.modeling.clustering.TerritorialClustering` y **la misma configuración `configs/rc1/modeling.toml` del bloque laboral**. K-Means descriptivo separado de Ward por fold y Ward para ajuste pleno |
| `*_cluster`, `*_cluster_mean`, residuos, cocientes | Calculados por tipo de población con medianas de territorios que pertenecen al conjunto de entrenamiento; no usan informalidad de ciudades excluidas |
| `train_df` | Sólo tasas **mensuales latentes** de las 23 ciudades con ventanas DANE, 2007–2025 excluyendo 2020 (4.968 filas) |
| `predict_df` | 33 departamentos × 404 meses, sin etiquetas departamentales fabricadas; igual esquema de X |

**No se ha intentado replicar exactamente los ID del mapa manual de clústeres del notebook antiguo.** El notebook tiene claves duplicadas (20 y 50) y el bloque laboral 2.1 utiliza otra clasificación basada en perfiles y validación. Usar los **mismos clústeres del laboral actual** significa reutilizar su algoritmo y la configuración congelada; para comprobar la identidad de asignaciones de un vintage laboral específico haría falta confrontar su artefacto de asignaciones, que no se entregó como resultado congelado en 2.2.4. Aquí se incluyen todos los mapas generados.

## Contratos de datos

Se escribe un panel urbano de 13.332 registros y otro departamental de 13.332. Los 33 territorios incluyen el dominio urbano sintético de Cundinamarca; **no es un departamento observado de informalidad**. Las matrices mantienen una fila por clave de territorio y mes entre 1993-01 y 2026-08. Todas las seis cantidades laborales están completas.

- `04_training_cities_all_history.csv`: información de las 33 ciudades durante 404 meses; sólo 23 tienen objetivo latente y se identifican las fechas aptas.
- `04_training_cities_eligible_weak.csv`: 4.968 filas de objetivos mensuales **latentes**, excluido 2020 por la anomalía histórica.
- `04_prediction_departments_all_history.csv`: todos los departamentos sin objetivo, con clúster sólo descriptivo; **no usar ese clúster para validación fuera de muestra**.
- `04_training_full_fit_weak.csv`, `04_training_full_fit_old_t5.csv`, `04_training_full_fit_new_geih.csv` y `04_prediction_full_fit_33_departments.csv`: submuestras por definición y contrato común de predictores con clúster Ward calculado para ajuste final con datos hasta 2025.
- `04_fold_safe_training_validation.csv`: entrenamiento/validación geográfico-temporal con clúster Ward reajustado dentro de cada una de 15 particiones; `04_folds.csv` define los cortes y la cuarentena temporal.
- `04_cluster_reference_assignments.csv`, `04_cluster_k_candidates.csv`, `04_cluster_fold_assignments.csv`, `04_cluster_full_fit_assignments.csv`: procedencia del agrupamiento.
- `04_feature_contract.json` contiene la lista blanca exacta de predictores (`model_feature_columns`), no construir X con «todas las numéricas».

## Restricciones que siguen vigentes

1. Los predictores **no** incluyen informalidad nacional, tasa proxy urbana ni el objetivo. La tasa urbana se retira físicamente de los archivos de entrenamiento. El objetivo mensual de ciudad es inferido a partir de ventanas móviles; no es observación mensual oficial ni 4.968 observaciones estadísticamente independientes.
2. El objetivo histórico 2007–2019 utiliza una definición antigua y el posterior a 2021 usa una nueva. No se permite entrenamiento conjunto como si midieran lo mismo: `eligible_pooled_definition_training=False`. Se debe validar el puente de definición antes de usar un único MLP.
3. La tasa urbana transferida al departamento sirve de baseline **separado**, no de etiqueta del departamento. El predictor no puede alterar `employed`, `population` o los otros cuatro niveles congelados.
4. Las medianas de clúster se calculan con las covariables laborales de los territorios de entrenamiento dentro de cada fold. Los clústeres descriptivos utilizan todo el histórico hasta 2020 y no son válidos como particiones de validación.
5. `tempdisagg 0.6.3` y el entorno numérico del ICML deben instalarse para ejecutar las pruebas de regresión golden; cargar el código local en `PYTHONPATH` permite algunas pruebas unitarias, pero no sustituye la instalación con metadatos de versión.
6. Es una validación retrospectiva: algunas señales laborales originales fueron reconstruidas usando vintages posteriores. No se debe presentar la CV como evaluación **as-of** de un pronóstico en tiempo real.
7. Los 10 territorios sin ancla departamental **no necesitan** observaciones inexistentes: el banco de validación debe juzgar la transferencia donde exista información comparable y cuantificar su sensibilidad.

## Ejecución

```bash
icml informality consolidate-features \
  --cities insumos/laboral/ciudades.csv \
  --departments insumos/laboral/departamentos.csv \
  --nationals insumos/laboral/nacionales.csv \
  --urban-informality informalidad/secuencia_v003/03_ciudades_33.csv \
  --population insumos/demografia/population_projections_legacy.csv \
  --modeling-config configs/rc1/modeling.toml \
  --output informalidad/NUEVO_VINTAGE_VACIO
```

Se prohíbe sobreescribir un vintage existente. La entrada `--population` proviene del ZIP original de producción y su huella consta en el manifiesto. Este checkpoint no sustituye al experimento 2.2.4, que permanece adjunto íntegramente.

## Próxima puerta

1. Resolver el puente de definición antes del ajuste conjunto del modelo; si no, entrenar y validar por estrato de definición.
2. Implementar el MLP residual original y al menos una línea base simple, aplicando exactamente la misma transformación por fold y comprobando si mejora la señal urbana **después del cierre**.
3. Estudiar el desplazamiento ciudad → departamento y la intervención de la conciliación antes de publicar las estimaciones departamentales.
