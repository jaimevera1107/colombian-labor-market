# ICML 2.2.7.dev0 — Calibración nacional de informalidad: adaptación del código original

Fecha: 2026-11-01. **Experimental, no canónico.** La base laboral 2.1.2 permanece congelada.

## Qué hace realmente el notebook original

El método no terminaba en la MLP. La clase `InformalityProcessor` del notebook original, celda 166, primero calculaba para cada departamento `informals_yhat = employed * y_hat` y `formals_yhat = employed * (1-y_hat)`; después normalizaba por separado las participaciones predichas de informales y formales **entre departamentos**. Finalmente asignaba los totales nacionales `informals_nat = employed_nat * informality_rate_nat` y `formals_nat = employed_nat * (1-informality_rate_nat)` a esas participaciones; reconstruía la tasa departamental de los dos niveles asignados y agregaba de nuevo el nacional.

La calibración nacional **es parte del estimador final**, no una corrección incidental. Por tanto el cierre del candidato 2.2.6 no permite rechazar la red únicamente porque la suma previa difiera del nacional. La comparación del MLP original con líneas base debe realizarse con una misma regla final de calibración y métricas **posteriores** al cierre.

## Por qué se adaptó la fórmula a ICML 2.1.2

La versión original imponía simultáneamente dos totales (informales y formales) mediante factores distintos. Eso no garantiza que la suma `informals_d + formals_d` siga siendo igual al `employed_d` preexistente. Lo comprobamos en los candidatos actuales: hasta 310.406 personas de residuo por departamento-mes con esta distribución original, usando los totales del ICML completo.

ICML 2.1.2 tiene un contrato distinto: **ningún módulo posterior puede alterar ocupados territoriales ni sus seis magnitudes laborales**. Por eso la adaptación parametriza una tasa final por departamento como:

`p_d^final = logistic(logit(clip(p_d^MLP))+a_t + b_t*factor_employed_d,t)`.

Elegimos `a_t` y, cuando corresponde, `b_t` de forma que se cumpla:

- ICML completo: `sum_d employed_d,t * p_d^final = informal_ICML,t`.
- DANE representado desde 2001: `sum_d factor_employed_d,t * employed_d,t * p_d^final = informal_DANE,t`.
- Cada departamento: `formal_d,t = employed_d,t - informal_d,t`, `informal_d,t` en `[0, employed_d,t]`.

Este ajuste es el óptimo de entropía relativa de Bernoulli ponderada por ocupados, sujeto a los márgenes. Es una versión conservadora de la lógica del notebook: mantiene la estructura relativa de la red en escala logit mientras la calibra con el agregado nacional. **No implica que reproduzca exactamente las mismas cifras antiguas ni sustituye la validación de la MLP.**

Desde 1993 hasta diciembre de 2000 los factores son todos 1 por convención de reconstrucción y el nacional `DANE_REFERENCIA` del período es una *reconstrucción histórica*, cuyo ocupado no coincide necesariamente con la suma completa. No es legítimo imponerlo como un segundo objetivo independiente. Solo se impone ICML; la discrepancia histórica de DANE queda documentada.

## Evidencia ejecutada sobre el candidato 2.2.6

| Candidato anterior al cierre | Meses calibrados | Meses bloqueados | Brecha media previa ICML, valor absoluto | Cambio medio ponderado después de calibrar | Mayor cambio local |
|---|---:|---:|---:|---:|---:|
| Señal urbana directa | 404 | 0 | 12,02 pp | 12,07 pp | 15,03 pp |
| MLP residual 92 características | 392 | 12 (todo 2020) | 16,08 pp | 16,08 pp | 22,44 pp |
| MLP residual 19 características comparables | 392 | 12 (todo 2020) | 8,04 pp | 8,08 pp | 13,61 pp |

Todos los meses ejecutados reproducen el nacional ICML y, desde 2001, el representado DANE, con residuos inferiores a `3e-8` personas; el máximo residuo de identidad por departamento es inferior a `5e-10` personas. Esto comprueba **aritmética**, no precisión territorial.

El nacional histórico DANE y el ICML del candidato usan la **misma tasa mensual inferida**. El doble cierre aporta dos márgenes de contabilidad, pero no dos observaciones independientes. Calibrar todas las opciones a esos mismos márgenes no permite afirmar que una opción predice mejor informalidad departamental porque su brecha nacional final sea cero.

La señal urbana directa y las dos MLP son **candidatos separados**; no se mezclan silenciosamente. Los 12 meses de 2020 faltantes en el producto de MLP se bloquean, no se imputan dentro de la etapa de cierre.

## Puertas pendientes de selección

1. Validación urbana por ciudad y período excluido, usando definiciones homogéneas. Evaluar candidatos tras un cierre equivalente, evitando utilizar el objetivo del fold de evaluación para ajustar su predicción.
2. Sensibilidad de distribución territorial frente a la MLP: tamaño de los cambios, saltos de tasa, dominancia de clúster/territorio, estructura de rankings y anclas disponibles.
3. Independencia del objetivo nacional: revisar el puente de informalidad por definición/ámbito y su incertidumbre, sin confundir DANE histórico reconstruido con observación.
4. Validación de estabilidad de factores de representatividad, particularmente 2001–2014 y el cambio de cobertura desde 2014.
5. Resolver el año 2020 antes de presentar 33×404 mensualidades como producto final.
6. Solo después de estas puertas, integrar informalidad a las tres bases analíticas; por ahora los CSV se almacenan en un subdirectorio experimental.

## Uso

```bash
icml informality calibrate-national \
  --departments insumos/laboral/departamentos.csv \
  --predictions informalidad/mlp_v005/05_department_predictions_EXPERIMENTAL.csv \
  --national informalidad/secuencia_v003/02_nacionales.csv \
  --rate-column candidate_rate_provisional \
  --label mlp_residual_92 \
  --allow-missing-months \
  --output informalidad/national_calibration_NUEVA_CORRIDA
```

El comando no escribe en los archivos de entrada y rechaza sobrescribir una salida existente.

## Fuentes de código utilizadas

Notebook original `2 - Estimación Departamental.ipynb`: `InformalityProcessor`, métodos `_compute_predicted_counts`, `_compute_national_counts`, `_scale_to_national`, `_aggregate_national`. Contrato laboral vigente: `insumos/laboral/departamentos.csv`, `insumos/laboral/nacionales.csv`. Nacional informal experimental: `informalidad/secuencia_v003/02_nacionales.csv`.
