# Hito 8 — Experimento de calibración restringida (2.2.9.dev0)

## Propósito y límites

Comparar **cinco calibradores distintos** sobre tres *predictores previamente congelados*, sin tocar los seis componentes laborales, factores de expansión, series nacionales de referencia ni pesos de la MLP. La calibración nacional es parte constitutiva del método ICML original; su intervención **no equivale a error predictivo**. Las dos series nacionales actuales comparten una tasa de informalidad inferida: su cierre es una prueba contable, no una validación externa independiente.

**No hay selección de modelo departamental ganador** en esta etapa, ni retroproyección de los meses de 2020 faltantes en las dos MLP. La calidad de la reconstrucción histórica y el puente entre definiciones siguen sin certificar.

## Candidatos y objetivos

Candidatos: `urban_direct`, `mlp_residual_92` y `mlp_shared19`. Cada mes se preserva el nivel de ocupados por departamento `e_d`. Se estima una tasa `q_d` acotada entre cero y uno, partiendo de la tasa predicha `p_d`.

Restricciones en personas:

- `sum(e_d * q_d) = informales_nacional_ICML`.
- Desde 2001, `sum(e_d * factor_employed_d * q_d) = informales_DANE_representado`.
- Antes de 2001, el factor 1 es supuesto de continuidad y no ofrece segundo margen independiente; se impone solo el nacional ICML.
- `formales_d = e_d * (1-q_d)` por construcción.

## Cinco métodos

1. **`kl_original`** — mínimo Bernoulli-KL. Implementación de `national_closure.py` reutilizada sin cambios.
2. **`l2_employment`** — mínima suma ponderada por ocupados de `(q-p)^2`.
3. **`l2_variance`** — mínima alteración cuadrática con penalización inversa de la varianza `max(p*(1-p),0.04)`; mantiene más rígidas las tasas extremas.
4. **`l2_temporal_1`** — método L2 con penalización adicional sobre el *cambio mensual del ajuste* `[(q_t-p_t)-(q_{t-1}-p_{t-1})]^2`, peso 1.
5. **`l2_temporal_4`** — misma formulación, peso 4.

La memoria temporal es **hacia delante solamente**, evita información del futuro y se reinicia en huecos de predicción y en la transición `2021-01`. No suaviza directamente la informalidad ni pretende eliminar rupturas reales. Su comportamiento dependerá de parámetros y del orden de los meses; por eso no se adopta sin pruebas incrementales por vintage.

Las alternativas cuadráticas se resuelven como problemas convexos con cotas `[0,1]`, igualdad en uno o dos márgenes y un sistema dual de dimensión 1–2. Si falla el sistema dual, se intenta optimización cuadrática restringida explícita. Nunca se sustituyen silenciosamente restricciones inalcanzables por aproximaciones.

## Resultados sobre los tres candidatos

**Señal urbana directa (404 meses):**

| Método | Intervención ponderada media (pp) | Máximo local (pp) | Saltos nuevos >5 pp | Salto medio absoluto del ajuste (pp) |
|---|---:|---:|---:|---:|
| KL original | 12,0651 | 15,0252 | **90** | 0,3274 |
| L2 | 12,0653 | **13,8605** | 95 | 0,3117 |
| L2-varianza | 12,0650 | 14,5333 | 100 | 0,3289 |
| L2 temporal 1 | 12,0652 | **13,8605** | 93 | 0,3103 |
| L2 temporal 4 | 12,0651 | **13,8605** | 93 | **0,3095** |

**MLP residual de 92 variables (392 meses, sin 2020):**

| Método | Intervención ponderada media (pp) | Máximo local (pp) | Saltos nuevos >5 pp | Salto medio absoluto del ajuste (pp) |
|---|---:|---:|---:|---:|
| KL original | 16,0813 | 22,4369 | **12** | **0,5294** |
| L2 | 16,0813 | **21,6348** | 16 | 0,5332 |
| L2-varianza | 16,0814 | 21,8703 | 17 | 0,5476 |
| L2 temporal 1 | 16,0812 | **21,6348** | 13 | 0,5319 |
| L2 temporal 4 | 16,0812 | **21,6348** | 13 | 0,5317 |

**MLP de 19 variables (392 meses, sin 2020):**

| Método | Intervención ponderada media (pp) | Máximo local (pp) | Saltos nuevos >5 pp | Salto medio absoluto del ajuste (pp) |
|---|---:|---:|---:|---:|
| KL original | 8,0819 | 13,6146 | **41** | **0,6536** |
| L2 | 8,0816 | **12,8963** | 43 | 0,6568 |
| L2-varianza | 8,0820 | 13,2319 | 43 | 0,6639 |
| L2 temporal 1 | 8,0816 | **12,8963** | 45 | 0,6566 |
| L2 temporal 4 | 8,0816 | 12,8965 | 45 | 0,6568 |

Las cifras pueden variar únicamente por precisión de exportación, no por cambios de fuentes. El archivo CSV contiene métricas sin redondeo de presentación.

## Lectura metodológica

- La selección **no** se resuelve eligiendo el modelo más cercano al nacional antes de calibrar: todas las variantes reproducen los mismos márgenes, por diseño.
- La calibración cuadrática reduce **máximos locales** entre 0,7 y 1,2 pp frente a KL, pero en estos candidatos genera un número igual o mayor de saltos nuevos de más de 5 pp.
- Penalizar cambios de la **corrección** no mejora de manera estable los saltos de la serie final; las propias predicciones y restricciones son una fuente importante de inestabilidad.
- En esta batería, **no hay ganadora dominante**: KL puede ser preferible para evitar saltos y L2-temporal para limitar la magnitud máxima o suavizar ajustes de la señal urbana. No hay evidencia nueva de precisión departamental.
- Debe validarse especialmente el efecto de las anclas nacionales sobre 2020 y el puente metodológico de 2021 antes de promoción a producción.

## Puertas de calidad y decisión

| Puerta | Estado |
|---|---|
| Identidades formales/informales y ocupados departamentales | APROBADA |
| Márgenes ICML y DANE representado | APROBADA |
| Cotas de las tasas 0–100 % y completitud de meses disponibles | APROBADA |
| Comparación con el método KL anterior | APROBADA |
| Estabilidad temporal, saltos nuevos y rankings | REVISIÓN |
| Validación espacial independiente de la informalidad departamental | NO VERIFICABLE CON LAS FUENTES ACTUALES |
| Puente de 2020 y cambios de definición | PENDIENTE |

**Decisión:** conservar el KL original como referencia operativa *experimental* de cierre mientras se realiza una evaluación de sensibilidad de los márgenes por vintage, sin promover ninguna variante ni candidato departamental a canónico. La evidencia útil es la frontera de compromiso entre extremos de intervención, estabilidad temporal y distorsión territorial.

## Reproducción

```bash
icml informality compare-calibrators \
  --closures <carpeta_national_calibration_v008> \
  --departments <departamentos.csv> \
  --national <02_nacionales.csv> \
  --output <directorio_nuevo_inmutable>
```

Archivos generados: CSV con todos los experimentos, métricas mensuales, comparaciones temporales, tabla resumen, puerta y manifiesto SHA-256. Se conservan los archivos de entrada con sus hashes; no hay escritura en las carpetas originales.
