# ICML 2.2.10.dev0 — Puerta de sensibilidad nacional, definición y 2020

**Estatus:** `EXPERIMENTAL_NOT_CANONICAL`; no se modifican las tres bases laborales ni los modelos ya entrenados. Se conserva el candidato principal MLP residual de 92 variables con calibración Bernoulli-KL, y se evalúan como referencias la MLP de 19 variables y la transferencia urbana directa.

## Propósito y límites de la inferencia

La exactitud del cierre contable **no valida la distribución territorial**. Los dos nacionales actuales comparten la **misma tasa de informalidad inferida** y ocupados de universos diferentes; no son dos mediciones independientes de la informalidad. Antes de 2001 solo se aplica un cierre sobre `ICML_COMPLETO`; los factores de representatividad históricos son 1. Desde 2001 pueden imponerse dos márgenes, pero no debe confundirse esa solución algebraica con la verdad estadística.

Este experimento usa **exclusivamente las fuentes DANE ya conservadas**, sin tomar ILOSTAT como ancla. La información histórica de no afiliación a pensión y la informalidad antigua de tamaño de establecimiento siguen siendo **indicadores de conceptos distintos**, no observaciones equivalentes a la definición GEIH reciente.

## Escenarios nacionales reproducidos

1. `proxy_strength_0`, `proxy_strength_0.5` (referencia actual) y `proxy_strength_1`: se vuelve a ejecutar la función original `_national_historical` para variar el peso de la información nacional histórica de seguridad social. Se preservan las 13 áreas reconstruidas y la informalidad nacional reciente.
2. `stress_2020_minus_2pp` y `stress_2020_plus_2pp`: prueba triangular de ±2 pp en la tasa nacional durante 2020, con desviación nula al comienzo y al final del año. **No es información DANE nueva.**
3. `stress_dane_domain_minus_025pp` y `stress_dane_domain_plus_025pp`: prueba de ±0,25 pp en la **tasa representada DANE** durante 2001–2020 sin cambiar la tasa del universo ICML completo. Sirve para medir la identificabilidad de dos márgenes casi redundantes; **no implica que el DANE publicara esa diferencia**.

Cada escenario vuelve a calibrar las mismas predicciones mediante `national_closure.calibrate_month` (KL), y conserva empleados y factores congelados. Los escenarios no se utilizan para entrenar ni reentrenar la red.

## Resultados de auditoría

- **7 escenarios × 3 candidatos:** 274.428 registros calibrados en 8.316 meses-candidato-escenario, incluidos 404 meses de la transferencia urbana y 392 de cada MLP. El mayor residuo del margen nacional completo fue inferior a 0,000001 personas (dentro del error numérico), sin modificar ocupados.
- **Cambio del peso de seguridad social de 0,5 a 0 o 1:** variaciones departamentales absolutas medias de 1,019 y 0,992 pp; extremos 2,609 y 2,586 pp (todas las variantes y meses comparables).
- **Estrés de dominios ±0,25 pp:** variaciones medias 1,715 y 1,701 pp, con extremos 17,542 y 17,370 pp. **Puerta bloqueante.** El factor representado concentra aproximadamente el 97–98 % del empleo: los dos objetivos casi iguales pueden generar una respuesta local muy grande en territorios de menor representatividad.
- **2020:** se probaron para las dos MLP las opciones `seasonal_2019`, `interpolated` y `urban_shock` (2.376 filas calibradas). Las tres satisfacen los márgenes, pero las tasas finales difieren hasta **18,824 pp** entre métodos para el mismo departamento-mes. **Ninguna se incorpora a un producto oficial ni canónico.**
- **Pseudohuecos:** se ocultaron 2017, 2018, 2023 y 2024, dentro de definiciones compatibles. Los valores reconstruidos se contrastan con *predicciones MLP previamente ajustadas*, **no** con observaciones departamentales del DANE. Para la MLP 92, luego de aplicar el mismo cierre KL, el promedio absoluto de la diferencia interna fue 0,812 pp para `interpolated`, 1,023 para `seasonal_2019` y 2,067 para `urban_shock`. Para la MLP 19: 1,658, 1,913 y 2,486 pp. **No es validación externa ni una prueba fuera de muestra del MLP.**

## Puertas de calidad

| Puerta | Estado | Decisión |
|---|---|---|
| G1 Cobertura/empleo congelado | PASS | Sin regresión de la base laboral |
| G2 Cierre KL y formal + informal | PASS | Cierre numérico, no precisión territorial |
| G3 Sensibilidad al peso del proxy | WARNING | Registrar rangos y fuentes |
| G4 Diferencia entre universos | BLOCKED | No forzar dos tasas inferidas independientes sin evidencia |
| G5 Meses MLP 2020 | BLOCKED | Completar solo como escenario, con incertidumbre explícita |
| G6 Validación verdaderamente independiente | BLOCKED | Pseudohuecos no sustituyen observaciones |
| G7 Definiciones históricas | BLOCKED | El puente T5/no pensión/GEIH aún no está identificado oficialmente |
| G8 Integridad de checkpoints previos | PASS | Solo lectura y nuevos vintages |

**Decisión recomendada:** conservar MLP92 + KL como candidato de investigación y el producto experimental de informalidad nacional como **único margen obligatorio primario**, manteniendo la representatividad DANE en la auditoría, hasta demostrar una tasa representada de informalidad compatible e independientemente identificada. La dualidad permanece implementada, no suprimida. El ensayo no es permiso para convertir un nacional inferido en observación oficial.

## Reproducción

```bash
icml informality audit-national-bridge \
  --departments insumos/laboral/departamentos.csv \
  --nationals insumos/laboral/nacionales.csv \
  --sources insumos/informalidad/informality_source_observations.csv \
  --recent insumos/informalidad/national_informality_monthly_2021_2026.csv \
  --anchors13 insumos/anclas_dane/anclas_dane_agregado_13_areas_2001_2009.csv \
  --cities13 informalidad/secuencia_v003/01_ciudades_13.csv \
  --closures informalidad/national_calibration_v008 \
  --output informalidad/national_bridge_stress_NEW_VINTAGE
```

Salida inmutable, `manifest.json` y hashes por entrada. El comando **no toca** `icml run`, `ciudades.csv`, `departamentos.csv`, `nacionales.csv`, predicciones previas ni pesos MLP. Usa fuentes preservadas de 2.2.9 y el calibrador existente. Se mantienen los experimentos previos para comparación.
