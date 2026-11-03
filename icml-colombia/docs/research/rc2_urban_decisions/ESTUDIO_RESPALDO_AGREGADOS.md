# ICML 2.0 — Etapa A · Donantes agregados como mecanismo de respaldo

**Estado:** estudio experimental. No altera el catálogo de donantes individuales ni la reconstrucción integrada existente.

## 1. Fuentes y definición

Datos utilizados exclusivamente del anexo `Anexo GEIH Agosto 2026.xlsx` incluido en el proyecto y paneles originales existentes de 23 ciudades y 32 proxies urbanas. Hash SHA-256 del anexo: `ade9b213c799e967c121091438a53617f3a3ab8d85d311f5cada08e2461473d9`.

Se extrajeron cuatro series oficiales de **ventanas móviles trimestrales** (12 ventanas por año, 2007–2024): 13 ciudades y áreas metropolitanas, 23 ciudades y áreas metropolitanas, cabeceras y centros poblados y rural disperso. Para el estudio las 12 ventanas móviles se promedian por año: **esto no equivale estrictamente al promedio de doce observaciones mensuales puntuales**, ni equivale necesariamente a la proxy 12 meses de las ciudades receptoras. Es una comparación exploratoria sobre tendencias anuales.

El agregado ofrece **variación temporal**. Su nivel se ajusta a cada receptor con razón de sumas en 2021–2024; **no** se copia el tamaño del agregado al receptor. El año 2025 se excluye por cobertura trimestral incompleta en el anexo para algunos agregados; no debe interpretarse como año completo. En este ensayo no existe validación temporal independiente de 2025.

### Auditoría de cobertura de agregados

Se contrastaron los agregados oficiales de 13 y 23 ciudades contra la suma de las series individuales disponibles en el proyecto. Mayor diferencia relativa (2007–2024, variables ocupados, desocupados, PET y población):

- **13 ciudades:** 8.880 %
- **23 ciudades:** 8.516 %

La diferencia puede reflejar distinta ventana, redondeo o tratamiento de áreas metropolitanas; debe inspeccionarse antes de utilizar equivalencias algebraicas entre fuentes.

## 2. Pseudovalidación 2007–2020 en 23 ciudades conocidas

Para cada ciudad histórica, se oculta 2007–2020, se ajusta el factor solo con proxies 2021–2024 y se compara con la historia conocida. **Antifuga:** se resta la ciudad receptora del agregado cuando está incluida (13 ciudades, 23 ciudades y cabeceras). En rural disperso no se hace esa resta.

| Donante | WAPE medio 23 ciudades | Mayor WAPE ciudad | Ciudades donde vence al individual |
|---|---:|---:|---:|
| Cabeceras | 9.45 % | 20.57 % | 16 |
| 23 ciudades | 9.46 % | 24.63 % | 19 |
| 13 ciudades | 9.48 % | 24.65 % | 19 |
| Centros poblados y rural disperso | 10.66 % | 27.84 % | 12 |
| Individual Pareto propuesto | 10.96 % | 17.44 % | — |

![WAPE de donantes agregados](exports/visualizacion/01_comparacion_23_ciudades.png)

![Peor caso](exports/visualizacion/02_peor_caso_23_ciudades.png)

**La comparación individual vs. agregado no es completamente homogénea en soporte temporal**; el valor numérico sirve como cribado exploratorio, no como ranking concluyente. Además, los agregados oficiales difieren en algunas variables de la suma de sus ciudades: en 2021 el desfase de desocupados alcanza cerca de 9 %. Esto es una alerta de comparabilidad, no un error que se deba imputar.

El respaldo agregado **no necesita superar el donante individual en promedio** para ser útil: puede ser una alternativa robusta para receptores cuyo donante particular sea inestable o incompatibles con la estructura laboral. No debe activarse por una sola métrica.

## 3. Nueve receptoras: compatibilidad observada 2021–2024

Criterios: distancia de crecimientos de ocupados y población, estabilidad del factor de escala y error retrospectivo del tipo de donante en las 23 ciudades. La puntuación sintética (50 % tendencia, 30 % estabilidad, 20 % backtest) es una **regla exploratoria declarada**, no una clasificación Pareto consolidada de las 27 alternativas.

| Receptora | Agregado mejor puntuado | Error log crecimiento (×100) | Inestabilidad factor log (×100) |
|---|---|---:|---:|
| Arauca | Cabeceras | 8.31 | 9.19 |
| Yopal | 23 ciudades | 3.14 | 3.08 |
| Mocoa | Cabeceras | 5.92 | 5.32 |
| San Andrés | 23 ciudades | 9.07 | 10.40 |
| Leticia | Cabeceras | 9.82 | 9.60 |
| Inírida | Cabeceras | 4.63 | 3.84 |
| San José del Guaviare | Cabeceras | 2.99 | 2.76 |
| Mitú | Cabeceras | 6.94 | 5.09 |
| Puerto Carreño | Cabeceras | 2.47 | 2.22 |

![Ranking](exports/visualizacion/03_ranking_agregados_nueve.png)

![Diferencias de tendencias agregadas](exports/visualizacion/04_perfiles_agregados.png)

## 4. Política de respaldo recomendada

1. Mantener inmóvil el catálogo individual actual hasta que una revisión metodológica explícita apruebe un cambio.
2. Incorporar los cuatro agregados como **candidatos de segundo nivel** si el individuo muestra baja adecuación o requiere correcciones sustantivas.
3. Auditar por receptor y por variable: quiebre en 2020–2021, tasa de crecimiento, no negatividad, identidades contables, variación del factor de empalme y sensibilidad a excluir un donante.
4. Comparar cada agregado contra las alternativas individuales con Pareto en dimensiones comparables; no sumar ingenuamente correlaciones de tamaño y tendencias.
5. No recalcular la selección cada mes; congelar donante + tipo + ventana de calibración + hash de datos en archivo de configuración. Ante nueva información, regenerar únicamente las alertas, no el donante.
6. La prevalencia de poblaciones rurales en ciudades pequeñas no prueba que la trayectoria rural agregada deba transferirse: exige comprobación empírica, especialmente porque la receptora es población urbana y no todo el departamento.

**Limitaciones:** (a) los donantes de 13, 23 y cabeceras contienen a las pseudo-receptoras, por lo que se resta su contribución anual para evitar optimismo, aunque puedan subsistir diferencias entre ventanas y universos; (b) ningún ejercicio observa el pasado real de las nueve receptoras; (c) hay cambios GEIH entre 2020 y 2021 que requieren auditoría de comparabilidad; (d) el agregado de centros poblados y rural disperso no mide por sí mismo ciudades.
