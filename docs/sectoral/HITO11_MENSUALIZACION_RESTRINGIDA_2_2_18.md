# ICML 2.2.18.dev0 — Hito 11, fase de inversión mensual de anexos móviles

**Estado: candidato de reconstrucción; NO cifras mensuales oficiales ni series canónicas.**

## Fuentes y alcance

- DANE, anexo marzo 2015: **163 trimestres móviles** consecutivos (julio–septiembre de 2001 a enero–marzo de 2015), agrupaciones históricas CIIU Rev. 3. La transformación Rev.3→Rev.4 del Hito 10 es **aproximada**, con tres escenarios (RAW/HALF/FULL).
- DANE, anexo agosto 2026: **140 meses directamente publicados** (enero 2015–agosto 2026) con **13 grupos** y `No informa`. Se conservaron sin alteraciones. La rama combinada `B+D_E` no se puede llamar dos ramas mensuales observadas.
- Denominador ICML: **ocupados mensuales del universo completo**; el representado GEIH se obtiene transferiendo las mismas participaciones sobre sus ocupados propios, no aplicando factores de población.
- Se reconstruyen **162 mensualidades históricas entre julio 2001 y diciembre 2014**, más 3 meses de frontera 2015 cuyos 13 grupos son datos mensuales oficiales pero la división B/D_E es un supuesto apoyado en la última ventana histórica. **Enero 1993–junio 2001 permanece sin anclas sectoriales suficientes**.

## Método y límites

Cada ventana histórica es una **restricción sobre el promedio de tres niveles sectoriales**. Invertirla no identifica las mensualidades de forma única y puede dar tasas negativas y saltos enormes. El estimador elegido busca minimizar la discrepancia con esas restricciones, impone participaciones sectoriales no negativas cuya suma es exactamente 100 % por mes, fija los 13 grupos mensuales publicados de 2015 en la frontera y usa penalización débil de primera diferencia **solo para seleccionar entre soluciones latentes**, nunca para modificar mensualidades observadas.

La penalización se escogió sobre seis conjuntos de **seis ventanas móviles consecutivas ocultadas**; estas pruebas utilizan información posterior al bloque ocultado, por lo que evalúan capacidad de interpolación y no predicción de años futuros.

| Intensidad de penalización | Error medio de ventanas ocultadas (pp) |
|---|---:|
| 0.03 | 0.1814 |
| 0.1 | 0.1745 |
| 0.3 | 0.1734 |
| 1.0 | 0.1794 |
| Interpolación simple de referencia | 0.1755 |

**Seleccionada λ=0.3**, con mejora leve respecto al benchmark, insuficiente para reclamar superioridad predictiva.

| Escenario | MAE ante trimestres de referencia (pp) | Máximo residuo (pp) | Mayor salto mensual (pp) |
|---|---:|---:|---:|
| RAW_HIST_VINTAGE | 0.0717 | 2.776 | 3.721 |
| HALF_2015_BRIDGE | 0.0689 | 2.208 | 2.962 |
| FULL_2015_BRIDGE | 0.0672 | 1.749 | 2.347 |

El ajuste **no reproduce exactamente todas las ventanas**: la clasificación y las diferentes vintages pueden ser incompatibles con la frontera mensual de 2015 o con tasas no negativas. Se informan todos los residuales y las alertas. El escenario FULL tiene máximos sobre todo en **`NO_INFO` de 2006**, incluidas ventanas terminadas en junio y octubre. No se alteró ningún dato original para forzar esos cierres.

La suma de las 15 categorías con los ocupados mensuales se cumple para cada universo, período y escenario: residuo máximo **7.5e-09 personas**. En cambio, el cumplimiento contable **no constituye prueba de exactitud** de las tasas sectoriales antiguas.

## Puerta de publicación

**BLOQUEADA:** no hay identificación única del mes, hay discrepancias de ventanas sectoriales y faltan fuentes anteriores a julio 2001. Los sectores sin anclas municipales no pueden considerarse observados. No integrar como series oficiales ni empalmar silenciosamente con 2015.

## Archivos nuevos

- `11_candidatos_historicos_mensuales_2001_2014_EXP.csv`: candidatos estimados 162 meses × 15 categorías × 2 universos × 3 escenarios.
- `11_estimaciones_mensuales_2001_2015_EXP_NO_OFICIALES.csv`: añade 2015-01 a 2015-03 como frontera identificada.
- `11_validacion_ventanas_ocultas.csv`: cuatro intensidades, seis validaciones por intensidad, benchmark.
- `11_comparacion_regularizaciones_y_escenarios.csv`: ajuste y volatilidad por escenario.
- `11_residuales_por_sector_y_ventana.csv`: desglose de cada restricción móvil por rama.
- `11_fidelidad_ventanas_3m_por_universo.csv`: errores medios/máximos por ventana y universo.
- `11_puerta_calidad.json`: metodología, cobertura, errores y SHA-256 de insumos.

## Siguiente trabajo, Hito 11 / Hito 12

1. Investigar anomalías de `NO_INFO` en 2006 y otras ventanas con residuales grandes; considerar versiones alternativas oficiales del anexo.
2. Buscar evidencia sectorial anterior a julio 2001; si falta, extender la historia como **estimación sin ancla**, con modelos y bandas de incertidumbre, pero no calificarla como referencia publicada.
3. Construir predictor sectorial departamental con una sola composición sobre ocupados del universo completo, controlar bloque geográfico y transferir al GEIH representado. No reutilizar trimestres móviles como mensualidades observadas, ni introducir datos externos no identificados.

**Ejecución**: `icml sectoral reconstruct-monthly --rolling-csv ... --recent-csv ... --totals-csv ... --nationals-csv ... --output ...`
