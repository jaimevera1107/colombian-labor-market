# Bloque II · Hito 5 — Informalidad nacional (v2.2.0.dev0)

## Alcance y principio de no intervención

**Los seis niveles laborales de `ciudades.csv`, `departamentos.csv` y
`nacionales.csv` permanecen inalterados**. El módulo es una etapa opcional,
separada de `icml run`, que consume `quality.nacionales` y las observaciones
extraídas de los anexos de informalidad. No crea todavía una serie
homogénea de informalidad **1993–2026**; esto sigue siendo el objetivo
científico, no algo que deba fingirse logrado.

## Fuentes originales y trazabilidad

| Fuente | SHA-256 del fichero original | Papel |
| --- | --- | --- |
| Anexo GEIH Informalidad Marzo 2021.xls | `451907808e5636044f69c401aea9a3924a2949cdd18cc30141685afc6b7bcfdb` | 2007–2021, antigua definición urbana y proxy nacional de no afiliación a pensiones |
| Anexo GEIH Informalidad Agosto 2026.xlsx | `3da594e046a2c67deeeaaaed1bd0d0f81f243ea48429be6481ca426044d28ffc` | 2021–2026, definición GEIH reciente |

Estos hashes se verificaron contra los originales del ZIP de recursos.
`data/sources/informality/informality_source_observations.csv` es el
snapshot tabular ya extraído por el proyecto original (`hito19`),
conservado **byte a byte** e identificado por SHA-256 en
`configs/rc1/informality.toml`. No se sustituyeron filas ni definiciones.
Para auditoría exhaustiva, los XLS/XLSX originales permanecen en el ZIP
de recursos separado. La extracción original se documenta en
`ICML_Produccion_Integral/src/icml_v2/informality_source_bridge.py`.

Se incluyen los 6.580 registros (4.732 antiguos y 1.848 recientes).
Los **110 ceros simultáneos** de ocupados/formales/informales de 2020
permanecen como `ZERO_SENTINEL_POSSIBLE_MISSING`, excluidos de ajustes;
no se convierten en observaciones válidas por interpolación.

## Definiciones y dominios

- GEIH antigua urbana: informalidad según tamaño de empresa/establecimiento;
  disponible para 23 ciudades y agregados urbanos históricos.
- Fuente histórica nacional/urbana/rural: **proxy de no afiliación a pensiones**,
  conceptualmente distinta de informalidad actual.
- GEIH nueva: empleo informal según la definición reciente, con series
  nacionales, cabeceras, rural y ciudades. Todas las observaciones son
  **promedios de trimestres móviles** de tres meses, no datos puntuales.
- Dos ventanas de fuentes distintas que terminan en marzo de 2021
  son un solapamiento de definiciones, **no** la misma magnitud en dos
  archivos: nueva menos proxy nacional = **−3,155 puntos porcentuales**.

## Correspondencia con el nacional laboral

Para cada ventana se promedian los ocupados **mensuales** ya publicados
en `nacionales.csv`, tanto `DANE_REFERENCIA` como `ICML_COMPLETO`.
Se compara con los ocupados del anexo de informalidad en **personas**
(conversión desde miles). No se modifica ningún valor en la base laboral.
En las 66 ventanas recientes la mayor discrepancia frente a
`DANE_REFERENCIA` es de 0,371 personas; la mediana de la brecha frente
a `ICML_COMPLETO` es alrededor del −2,02 %.

## Candidato mensual reciente (no oficial)

Las 66 medias móviles recientes establecen 66 ecuaciones para 68
incógnitas mensuales. **No identifican por sí solas los meses**.
Para crear un candidato interpretable se reconstruye la cantidad informal
por mínima curvatura (suma de cuadrados de segundas diferencias), bajo
las restricciones de reproducción exacta de las ventanas. Se mantienen
**fijos** los ocupados mensuales de `DANE_REFERENCIA`; los formales
son el residuo `ocupados − informales`. Se rechazan niveles negativos,
violaciones de límites y diferencias de ventana fuera de tolerancia.

Resultado: 68 tasas mensuales latentes, 2021-01 a 2026-08; **cada celda
se marca no oficial** y no se promueve automáticamente al universo
completo del ICML. La elección de curvatura es una **hipótesis del modelo**.
El ajuste no identifica la informalidad 1993–2020 ni garantiza precisión
sobre cambios intra-trimestrales no observados.

## Artefactos del hito

- `sources/national_windows.csv`: 705 observaciones nacionales/urbanas/rurales de ambas definiciones.
- `audit/source_inventory.csv`: fuente, universo, definición, cobertura y ceros.
- `audit/labor_alignment.csv`: referencia DANE y nacional ICML, variaciones de ocupados por ventana.
- `audit/definition_overlap.csv`: discontinuidad metodológica 2021.
- `audit/source_domain_closure.csv`: diferencias nacionales vs cabeceras+rural.
- `candidates/national_informality_monthly_2021_2026.csv`: mensualidades latentes nuevas; no equivalen a observación DANE.
- `audit/window_reproduction.csv`: reproducción de medias oficiales de informalidad y formalidad.
- `audit/summary.json` y `manifest.json`: decisión y procedencia.

## Puerta de salida / lo que sigue

**G0 y G1 superadas** para el catálogo nacional nuevo y para la
consistencia de ocupados 2021–2026. **Puerta metodológica de empalme
histórico aún abierta**: antes de construir una serie comparable bajo
la definición nueva en 1993–2020 se necesita evaluar el empalme con
la antigua proxy y las señales disponibles. Debe verificarse estabilidad
por falsos cortes en años recientes, sensibilidad del método y ruptura
2020–2021; las diferencias de estimandos se publicarán y no se ocultarán.

El siguiente hito operativo es la reconstrucción de señales urbanas,
pero puede desarrollarse en paralelo el **puente nacional histórico**.

No se exige obtener observaciones inexistentes de los diez territorios
sin ancla; sus tasas deberán validarse mediante ocultamiento territorial
cuando corresponda.


## Actualización posterior — 2.2.1.dev0

La extensión histórica nacional se implementó en un módulo **opcional y
experimental**, separado de esta etapa reciente. Se conservan intactas
las 68 mensualidades GEIH latentes y los seis niveles laborales. Véase
[`HITO5_HISTORICO.md`](HITO5_HISTORICO.md). La puerta de comparabilidad
histórica **sigue abierta**, aunque se produjo un candidato completo 1993–2026.
