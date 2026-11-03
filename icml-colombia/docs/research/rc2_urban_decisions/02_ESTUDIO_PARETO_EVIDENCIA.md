# 02 · Estudio de Pareto: evidencia y criterio de elección

## Conjunto factible y datos

**Nueve receptoras × 23 posibles donantes = 207 alternativas.** Para cada receptor, las cinco pérdidas de similitud se minimizan simultáneamente: (1) cambios logarítmicos de ocupados, (2) cambios logarítmicos de población, (3) tasas de desempleo/participación/ocupación, (4) brecha logarítmica de tamaños poblacionales y (5) dispersión del factor de escala. El tamaño es una propiedad auxiliar de semejanza, no una cantidad que se traslada.

## Regla reproducible

1. Formar la frontera no dominada: una alternativa se excluye solamente si otra no empeora las cinco pérdidas y mejora al menos una.
2. Entre alternativas eficientes, minimizar distancia euclidiana ponderada al ideal con pesos **0,30; 0,20; 0,20; 0,10; 0,20**, para los criterios en el orden anterior. Las normalizaciones se estiman usando las 506 parejas de ciudades con historia.
3. Añadir una tolerancia de **0,03 unidades logarítmicas** respecto al donante vigente en los diagnósticos 2025 y 2021. Esa tolerancia es una política de riesgo; no deriva de una ley estadística.
4. Guardar el catálogo bajo hash y no reevaluar en actualizaciones mensuales.

![Contraste de reglas](../exports/visualizacion/01_evidencia_global/01_reglas_validacion.png)

## Resultado retrospectivo (23 ciudades conocidas)

| Regla | WAPE medio | Peor ciudad | Control 2025 (log × 100) | Continuidad 2021 (log × 100) |
|---|---:|---:|---:|---:|
| frontera_distancia | 10.63 % | 17.44 % | 5.96 % | 4.78 % |
| equilibrado | 10.82 % | 18.86 % | 6.18 % | 5.02 % |
| factor_estable | 10.82 % | 18.86 % | 6.18 % | 5.02 % |
| pareto_con_guardia | 10.96 % | 17.44 % | 5.72 % | 4.40 % |
| frontera_minimax | 11.67 % | 24.08 % | 6.26 % | 4.77 % |
| frontera_media | 12.10 % | 28.67 % | 5.72 % | 4.23 % |

**Lectura:** la regla de menor WAPE promedio es la distancia al ideal sin guardas. La política con guardas cede precisión media, pero disminuye los desajustes de control frente a las referencias actuales. Ninguna domina a todas las demás en todos los indicadores.

## Sensibilidad a la tolerancia

![Sensibilidad](../exports/visualizacion/01_evidencia_global/03_sensibilidad_tolerancia.png)

En la tolerancia **0,00** solo 3 de 9 asignaciones coinciden con la política base 0,03; a 0,02 coinciden 7; a 0,04 coinciden 8; a 0,06 coinciden 5. Esta sensibilidad obliga a congelar la política junto con los donantes, no solo sus códigos.

## ¿La combinación de varios donantes es mejor?

En el experimento exploratorio, 1/2/3 donantes obtuvieron respectivamente WAPE medio 10,63 / 9,94 / 9,76 %, pero su peor ciudad empeoró de 17,44 a 20,59 y 22,30 %. No es una mejora de bienestar uniformemente favorable. No se optimizaron exhaustivamente las mezclas.

## Qué significa Pareto para las nueve ciudades

Si no existen restricciones de capacidad entre donantes, las nueve decisiones son separables. Elegir un donante no dominado por receptor vuelve la cartera eficiente respecto de las pérdidas definidas, pero no la hace única, causal ni históricamente verdadera. Dos de los nueve donantes sugeridos dominan estrictamente a sus vigentes en los cinco criterios.

## Evidencia reutilizable

- [207 alternativas y cinco pérdidas](../results/evaluacion_207_alternativas.csv)
- [23 × 6 pruebas retrospectivas](../results/validacion_23_ciudades_6_reglas.csv)
- [Resumen de estrategias](../results/comparacion_estrategias_23.csv)
- [Sensibilidad de tolerancias](../results/sensibilidad_tolerancia.csv)
- [Comparación de mezclas](../results/validacion_mezclas_pareto_23.csv)
